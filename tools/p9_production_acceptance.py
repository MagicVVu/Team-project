"""Explicitly authorized P9 production acceptance in one dedicated household.

No existing user data is targeted. One paid conversation request, no paid retry.
Keep the ledger; disable the test user and revoke test sessions in finally.
"""
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
from sqlalchemy import inspect, select, text
from app.database import SessionLocal, engine
from app.models import User, Household, HouseholdMember, ShoppingList, AuthSession, AITask, AIDraft
from app.execution_models import BusinessEvent
from app.security import hash_password, digest_token
from app.services.planning_context import snapshot
from app.main import health_check


def existing_rows():
    """Private in-memory row fingerprints; raw business data never leaves this process."""
    with engine.connect() as db:
        db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        schema = inspect(db)
        out = {}
        for table in schema.get_table_names():
            keys = schema.get_pk_constraint(table)['constrained_columns']
            assert keys
            quoted = '"'+table.replace('"','""')+'"'
            rows = db.execute(text('SELECT row_to_json(t)::text FROM '+quoted+' t')).scalars()
            out[table] = {}
            for raw in rows:
                row = json.loads(raw)
                identity = tuple(str(row[k]) for k in keys)
                out[table][identity] = hashlib.sha256(raw.encode()).hexdigest()
        return out


def main():
    assert health_check()['maintenance_release'] == 'V1-P9'
    before = existing_rows()
    user, home, shared = [uuid4() for _ in range(3)]
    token = secrets.token_urlsafe(32)
    marker = 'P9_RELEASE_ACCEPTANCE_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    result = {'passed': False, 'test_family_marker': marker, 'household_id': str(home), 'user_id': str(user),
              'paid_requests_attempted': 0, 'checks': {}, 'raw_credentials_exported': False}
    try:
        with SessionLocal.begin() as db:
            db.add(User(id=user, email=marker.lower()+'@example.invalid', display_name='P9 专用发布验收',
                        password_hash=hash_password(secrets.token_urlsafe(40))))
            db.flush()
            db.add(Household(id=home, name=marker, created_by_user_id=user))
            db.flush()
            db.add(HouseholdMember(household_id=home, user_id=user, role='owner'))
            db.add(ShoppingList(id=shared, household_id=home, name='P9专用验收采购'))
            db.add(AuthSession(user_id=user, token_hash=digest_token(token),
                               expires_at=datetime.now(timezone.utc)+timedelta(minutes=30)))
        with httpx.Client(base_url='http://127.0.0.1:8000', timeout=25, trust_env=False,
                          headers={'Authorization': 'Bearer '+token}) as client:
            def call(method, path, body=None, status=200):
                response = client.request(method, path, json=body)
                assert response.status_code == status, (path, response.status_code)
                return response.json() if response.content else None

            root = f'/api/v1/households/{home}'
            batch = call('POST', root+'/inventory-items', {'id': str(uuid4()), 'name': '牛奶', 'quantity': '5',
                'unit': '盒', 'category': 'household', 'storage_location': '专用验收冷藏室'}, 201)
            product = call('POST', root+'/products', {'id': str(uuid4()), 'name': '牛奶', 'base_unit': '盒',
                'source': '专用验收人工核对', 'specification': '仅用于发布验收'}, 201)
            call('PUT', root+'/inventory-items/'+batch['id']+'/product', {'operation_id': str(uuid4()),
                'expected_inventory_version': batch['version'], 'product_id': product['product_id'], 'source': '验收显式关联'})

            def seeded(action, fields, extra=None):
                task, draft = uuid4(), uuid4()
                command = {'action': action, **fields}
                with SessionLocal.begin() as db:
                    db.add(AITask(id=task, user_id=user, household_id=home, request_id=uuid4().hex,
                        request_hash='release-fixture', original_text='P9专用验收固定草稿（不是AI生成）',
                        household_timezone='Asia/Shanghai', status='needs_confirmation', revision=1,
                        result_json={'status': 'needs_confirmation', 'draft': command, **(extra or {})}))
                    db.flush()
                    db.add(AIDraft(id=draft, task_id=task, user_id=user, household_id=home,
                                  status='pending', revision=1, command_json=command))
                return str(draft)

            def execute(action, fields, extra=None):
                draft = seeded(action, fields, extra)
                request = {'operation_id': str(uuid4()), 'draft_revision': 1, 'task_revision': 1, 'edits': {}}
                route = f'/api/v1/drafts/{draft}/commit'
                receipt = call('POST', route, request)
                assert receipt['action'] == action
                assert call('POST', route, request) == receipt
                assert call('GET', '/api/v1/operations/'+request['operation_id']) == receipt
                feedback = call('POST', '/api/v1/operations/'+request['operation_id']+'/feedback')
                expected = {'not_applicable'} if action == 'PLAN_ADD' else {'available', 'partial'}
                assert feedback['feedback_status'] in expected
                result['checks'][action] = {'passed': True, 'operation_id': request['operation_id'],
                    'draft_generated_by': 'explicit_release_fixture', 'feedback_status': feedback['feedback_status']}
                return receipt

            execute('ADD', {'name': '专用验收纸巾', 'quantity': '2', 'unit': '包', 'location': '专用验收储物柜',
                            'purchased_at': None, 'label_expiry': None})

            def target():
                current = call('GET', root+'/inventory-items/'+batch['id'])
                return {'name': current['name'], 'batch_id': current['id'], 'expected_version': current['version']}

            execute('MOVE', {**target(), 'to_location': '专用验收冷藏上层'})
            execute('CONSUME', {**target(), 'quantity': '1', 'unit': '盒'})
            source = target()
            plan = execute('PLAN_ADD', {'name': '牛奶', 'quantity': '2', 'unit': '盒'},
                {'procurement_source': {'batch_id': source['batch_id'], 'expected_version': source['expected_version']}})
            execute('OPEN', {**target(), 'opened_at': datetime.now(timezone.utc).date().isoformat()})
            execute('DISCARD', {**target(), 'discard_mode': 'partial', 'quantity': '1', 'unit': '盒'})
            item = plan['result']['shopping_item']
            url = root+'/shopping-list/items/'+item['id']
            clear = {'operation_id': str(uuid4()), 'expected_version': item['version'], 'source_inventory_item_id': None}
            cleared = call('PATCH', url, clear)
            relink = {'operation_id': str(uuid4()), 'expected_version': cleared['version'], 'source_inventory_item_id': batch['id']}
            call('PATCH', url, relink)
            assert call('PATCH', url, clear) == cleared
            assert call('GET', root+'/shopping-list/items?status=pending')['items'][0]['source_inventory_item_id'] == batch['id']
            bought = call('POST', url+'/purchase', {})
            assert not call('POST', url+'/purchase', {})['newly_stocked']
            result['checks']['source_patch_purchase_retries'] = {'passed': True, 'new_batch_id': bought['inventory_item']['id']}
            current = call('GET', root+'/inventory-items/'+batch['id'])
            operation = uuid4()
            adjusted = call('POST', root+'/inventory-items/'+batch['id']+'/adjustments', {
                'operation_id': str(operation), 'expected_version': current['version'], 'delta': '1'})
            events = call('GET', root+'/inventory-events')['events']
            adjustment = next(e for e in events if e['request_id'] == str(operation))
            corrected = call('POST', root+'/inventory-items/'+batch['id']+'/corrections', {
                'operation_id': str(uuid4()), 'expected_version': adjusted['version'], 'quantity': current['quantity'],
                'related_event_id': adjustment['event_id'], 'reason': '专用验收：修正数量调整'})
            with SessionLocal() as db:
                facts = snapshot(db, user, home, with_provenance=True)
                assert len(facts['provenance']['product_aggregates_v1']) == 1
                group = facts['provenance']['product_aggregates_v1'][0]
                assert len(group['batches']) == 2 and Decimal(group['total_quantity']) == 5
                consumed = db.scalars(select(BusinessEvent).where(BusinessEvent.household_id == home,
                    BusinessEvent.event_type == 'Consumed')).all()
                assert len(consumed) == 1 and consumed[0].quantity == 1
                basis = facts['provenance']['revalidation_basis']
            result['checks']['ledger_product_aggregation'] = {'passed': True, 'consumption_events': 1, 'aggregate_quantity': '5'}
            automatic = seeded('PLAN_ADD', {'name': '牛奶', 'quantity': '1', 'unit': '盒'},
                {'planning_basis': basis, 'quantity_source': 'planning_calculation',
                 'procurement_source': {'batch_id': batch['id'], 'expected_version': corrected['version']}})
            report = call('POST', f'/api/v1/drafts/{automatic}/planning-revalidation', {
                'draft_revision': 1, 'task_revision': 1, 'edits': {}})
            assert report['status'] == 'blocked' and 'RISK_RULE_REVIEW_REQUIRED' in report['blockers']
            refused = call('POST', f'/api/v1/drafts/{automatic}/commit', {'operation_id': str(uuid4()),
                'draft_revision': 1, 'task_revision': 1, 'edits': {}}, 409)
            assert refused['detail']['code'] == 'PLANNING_REVALIDATION_UNAVAILABLE'
            result['checks']['automatic_commit_closed'] = {'passed': True, 'code': refused['detail']['code']}

            # The original DeepSeek adapter makes one HTTP POST and has no SDK retries.
            session = call('POST', '/api/v1/agent/conversation/reset', {'household_id': str(home), 'request_id': uuid4().hex})
            message = {'household_id': str(home), 'request_id': uuid4().hex, 'text': '查询牛奶库存数量',
                'conversation_id': session['conversation_id'], 'conversation_revision': session['conversation_revision']}
            result['paid_requests_attempted'] = 1
            turn = call('POST', '/api/v1/agent/conversation-turns', message)
            result['model_response'] = {'kind': turn['kind'], 'model_calls': turn['model_calls'],
                'error_code': turn.get('error_code'), 'task_status': (turn.get('task') or {}).get('status')}
            assert turn['task'] and turn['task']['status'] == 'answered'
            assert turn['model_calls'] == 1
            # GET recovery only: never resubmit the paid request after an uncertain result.
            recovered = call('GET', '/api/v1/agent/conversation-turns/'+message['request_id']+'?household_id='+str(home))
            assert recovered['response'] == turn
            history = call('GET', '/api/v1/agent/conversation?household_id='+str(home))
            assert history['conversation_id'] == session['conversation_id']
            result['checks']['deepseek_memory_recovery'] = {'passed': True, 'model_calls': turn['model_calls'],
                'request_id': message['request_id'], 'task_status': turn['task']['status']}
            caps = call('GET', '/api/v1/agent/execution-capabilities')
            assert caps['automatic_planning_commit'] is False and caps['manual_plan_only'] is True
            result['passed'] = True
    except Exception as error:
        result.update(passed=False, error_type=type(error).__name__, error=str(error)[:300])
    finally:
        with SessionLocal.begin() as db:
            account = db.get(User, user)
            if account is not None:
                assert account.display_name == 'P9 专用发布验收'
                account.is_active = False
                for session in db.scalars(select(AuthSession).where(AuthSession.user_id == user)):
                    session.revoked_at = datetime.now(timezone.utc)
        result['synthetic_account_disabled'] = True
        result['test_ledger_retained'] = True
        after = existing_rows()
        changed = {table: sum(after.get(table, {}).get(key) != value for key, value in rows.items())
                   for table, rows in before.items()}
        result['existing_rows_audit'] = {'unchanged': not any(changed.values()),
            'rows_compared': sum(len(rows) for rows in before.values()), 'changed_rows_per_table': changed}
        result['passed'] &= result['existing_rows_audit']['unchanged']
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
