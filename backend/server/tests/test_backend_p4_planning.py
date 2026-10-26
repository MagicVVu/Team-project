"""P4 facts from real services and isolated databases; coverage synthesis is test-only."""
import asyncio
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import OperationalError

from test_v09_execution import app, execution_state, seed_draft, body, post, headers, PG
from test_backend_p1_integration import real_p7
from test_backend_p3_open_discard import enabled, draft
from app.models import InventoryItem, ShoppingList, ShoppingListItem, User, HouseholdMember
from app.execution_models import BusinessEvent, DraftOperation
from app.services import planning_context as service

PATH = '/internal/v1/planning/context'
TOKEN = 'synthetic-p4-tool-token-not-a-production-secret'
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'agent'))


@pytest.fixture
def planning(execution_state, monkeypatch):
    monkeypatch.setenv('BACKEND_TOOL_TOKEN', TOKEN)
    return execution_state


def tool_headers(ids, **changes):
    return {'Authorization': 'Bearer ' + TOKEN, 'X-User-Id': str(ids['user']),
            'X-Household-Id': str(ids['home']), **changes}


def get(state, **kwargs):
    client, _, ids = state
    return client.get(PATH, headers=tool_headers(ids), **kwargs)


def parse(value):
    from v1.schemas import PlanningSnapshot
    return PlanningSnapshot.model_validate(value)


def save(name, value):
    directory = ROOT / '.cache' / 'backend-test-evidence'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ('backend-p4-postgres-examples.json' if PG else 'backend-p4-sqlite-examples.json')
    previous = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    previous[name] = value
    path.write_text(json.dumps(previous, ensure_ascii=False, indent=2), encoding='utf-8')


def test_registered_contract_and_real_unknown_facts(planning):
    client, Session, ids = planning
    response = get(planning)
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    payload = response.json()
    snapshot = parse(payload['data'])
    item = snapshot.items[0]
    assert snapshot.scope.household_id == str(ids['home'])
    assert item.item_key == item.batches[0].id == str(ids['batch'])
    assert item.batches[0].quantity == 5 and item.version == 1
    assert item.coverage == [] and item.recording_completeness_source is None
    assert item.stock_verification is None and not item.usable_quantity_verified
    assert item.preferences.minimum_stock is item.preferences.lead_days is item.preferences.pack_size is None
    assert item.batches[0].product_id is item.batches[0].storage_condition is None
    assert item.batches[0].label_date_type == 'unknown'
    assert item.batches[0].is_opened is None
    assert snapshot.history_complete and snapshot.items_complete
    assert payload['provenance']['recording_completeness'] == 'unknown'
    before = datetime.now(timezone.utc) - snapshot.as_of
    assert -1 < before.total_seconds() < 10
    alias = client.get('/internal/v1/ai/planning-context', headers=tool_headers(ids))
    assert alias.status_code == 200
    assert alias.json()['data']['items'] == payload['data']['items']
    assert snapshot.event_watermark == alias.json()['data']['event_watermark']
    schema = app.openapi()
    assert PATH in schema['paths'] and '/internal/v1/ai/planning-context' not in schema['paths']
    save('unknown_snapshot', payload)


@pytest.mark.parametrize('change,status', [
    ({'Authorization': ''}, 401), ({'Authorization': 'Bearer synthetic-user'}, 401),
    ({'X-Household-Id': str(uuid4())}, 404), ({'X-User-Id': 'not-a-uuid'}, 404)])
def test_internal_authentication_and_scope(planning, change, status):
    client, _, ids = planning
    assert client.get(PATH, headers=tool_headers(ids, **change)).status_code == status


@pytest.mark.parametrize('mode', ['inactive', 'removed', 'cross_household', 'unconfigured'])
def test_no_stale_identity_or_cross_family_access(planning, monkeypatch, mode):
    client, Session, ids = planning
    if mode == 'unconfigured':
        monkeypatch.delenv('BACKEND_TOOL_TOKEN')
        assert get(planning).status_code == 401
        return
    with Session.begin() as db:
        if mode == 'inactive': db.get(User, ids['user']).is_active = False
        elif mode == 'removed': db.delete(db.get(HouseholdMember, (ids['home'], ids['user'])))
    claimed = tool_headers(ids, **({'X-Household-Id': str(ids['foreign_home'])} if mode == 'cross_household' else {}))
    assert client.get(PATH, headers=claimed).status_code == 404


@pytest.mark.parametrize('params', [{'name': ' '}, {'name': '牛奶', 'item_key': str(uuid4())}, {'item_key': 'invalid'}])
def test_selectors_are_validated(planning, params):
    assert get(planning, params=params).status_code == 422


@pytest.mark.parametrize('limit', ['ITEM_LIMIT', 'EVENT_LIMIT', 'SHOPPING_LIMIT'])
def test_no_successful_truncated_snapshot(planning, monkeypatch, limit):
    client, Session, ids = planning
    d, _ = seed_draft(Session, ids)
    assert post(client, d, body()).status_code == 200
    with Session.begin() as db:
        db.add(ShoppingListItem(shopping_list_id=ids['list'], name='待购', quantity=1, unit='盒'))
    monkeypatch.setattr(service, limit, 0)
    response = get(planning)
    assert response.status_code == 409 and response.json()['detail']['code'] == 'PLANNING_INCOMPLETE'
    assert 'data' not in response.json()


def test_partial_query_failure_returns_no_data(planning):
    _, Session, _ = planning
    engine = Session.kw['bind']
    def fail(conn, cursor, statement, parameters, context, many):
        if 'FROM business_events' in statement:
            raise OperationalError('synthetic read failure', {}, Exception('offline'))
    event.listen(engine, 'before_cursor_execute', fail)
    try:
        response = get(planning)
        assert response.status_code == 503 and 'data' not in response.json()
        assert response.json()['detail']['code'] == 'PLANNING_CONTEXT_UNAVAILABLE'
    finally:
        event.remove(engine, 'before_cursor_execute', fail)


@pytest.mark.parametrize('action', ['CONSUME', 'PLAN_ADD', 'OPEN'])
def test_consistent_read_during_real_commit(planning, enabled, action):
    client, Session, ids = planning
    engine = Session.kw['bind']
    if not PG:
        with engine.connect() as db:
            assert db.exec_driver_sql('PRAGMA journal_mode=WAL').scalar().lower() == 'wal'
    d, _ = draft(Session, ids) if action == 'OPEN' else seed_draft(Session, ids, action)
    request = body()
    fired = []
    with ThreadPoolExecutor(max_workers=1) as pool:
        def concurrent(conn, cursor, statement, parameters, context, many):
            if 'FROM inventory_items' not in statement or fired:
                return
            fired.append(True)
            if PG:
                assert conn.get_isolation_level() == 'REPEATABLE READ'
                assert conn.exec_driver_sql('SHOW transaction_read_only').scalar() == 'on'
            committed = pool.submit(post, client, d, request).result(timeout=15)
            assert committed.status_code == 200, committed.text
        event.listen(engine, 'after_cursor_execute', concurrent)
        try:
            first = get(planning)
            assert first.status_code == 200, first.text
        finally:
            event.remove(engine, 'after_cursor_execute', concurrent)
    assert fired
    old = first.json()['data']
    new = get(planning).json()['data']
    assert old['items'][0]['version'] == 1 and old['items'][0]['events'] == []
    assert old['pending'] == []
    assert old['event_watermark'] != new['event_watermark']
    assert old['snapshot_id'] != new['snapshot_id']
    if action == 'CONSUME':
        assert Decimal(new['items'][0]['batches'][0]['quantity']) == 4
        assert new['items'][0]['events'][0]['kind'] == 'Consumed'
    elif action == 'OPEN':
        assert new['items'][0]['batches'][0]['is_opened'] is True
    else:
        assert old['shopping_version'] != new['shopping_version']
        assert not new['pending_complete']
    save('concurrent_' + action, {'old': old, 'new': new})


def test_events_provenance_and_exclusions(planning, enabled):
    client, Session, ids = planning
    d, _ = seed_draft(Session, ids)
    request = body()
    assert post(client, d, request).status_code == 200
    assert post(client, d, request).status_code == 200
    for kind, version in [('partial', 2), ('OPEN', 3)]:
        d, _ = draft(Session, ids, kind, expected_version=version, **({'quantity':'1'} if kind == 'partial' else {}))
        assert post(client, d, body()).status_code == 200
    adjustment = client.post(f"/api/v1/households/{ids['home']}/inventory-items/{ids['batch']}/adjustments",
        headers=headers(), json={'operation_id': str(uuid4()), 'expected_version': 4, 'delta': '-1'})
    assert adjustment.status_code == 200
    payload = get(planning).json()
    item = parse(payload['data']).items[0]
    assert len(item.events) == 4 and sum(e.quantity for e in item.events if e.kind == 'Consumed') == 1
    assert {e.kind for e in item.events} == {'Consumed', 'Opened', 'Discarded', 'Adjusted'}
    assert next(e.quantity for e in item.events if e.kind == 'Opened') == 0
    provenance = payload['provenance']
    assert len(provenance['items'][item.item_key]['known_quantity_adjustments']) == 1
    assert not provenance['items'][item.item_key]['adjustment_history_complete']
    for e in item.events:
        source = provenance['events'][e.id]
        assert source['batch_id'] == item.item_key and source['household_id'] == str(ids['home'])
        assert (source['operation_id'] or source['request_id']) and source['relation_support'] == 'inventory-ledger-1'
        assert e.recorded_at <= parse(payload['data']).as_of
    # Historical opening date is separate from registration timestamp.
    opened = next(e for e in item.events if e.kind == 'Opened')
    assert opened.recorded_at.astimezone(ZoneInfo('Asia/Shanghai')).date() > item.batches[0].opened_at
    save('semantic_events', payload)


@pytest.mark.parametrize('category', ['food', 'medicine', 'household', '食品', None])
def test_category_only_maps_explicit_contract_values(planning, category):
    _, Session, ids = planning
    with Session.begin() as db: db.get(InventoryItem, ids['batch']).category = category
    item = get(planning).json()['data']['items'][0]
    assert item['category'] == (category if category in {'food','medicine','household'} else 'unknown')
    assert item['batches'][0]['category'] == item['category']


def test_similar_names_are_separate_batches(planning):
    _, Session, ids = planning
    with Session.begin() as db:
        db.add(InventoryItem(household_id=ids['home'], name='牛奶', quantity=2, unit='瓶', version=1, status='ACTIVE'))
    items = parse(get(planning).json()['data']).items
    assert len(items) == 2 and len({i.item_key for i in items}) == 2
    assert all(len(i.batches) == 1 and i.batches[0].product_id is None for i in items)


@pytest.mark.parametrize('explicit,value', [(False, '0'), (True, '0'), (True, '2.5')])
def test_minimum_preference_has_real_authenticated_source(planning, explicit, value):
    client, _, ids = planning
    ident = uuid4()
    payload = dict(id=str(ident), name='纸巾', quantity='2', unit='包', storage_location='柜子')
    if explicit: payload['minimum_quantity'] = value
    path = f"/api/v1/households/{ids['home']}/inventory-items"
    assert client.post(path, headers=headers(), json=payload).status_code == 201
    result = get(planning, params={'item_key':str(ident)}).json()
    item = result['data']['items'][0]
    pref = item['preferences']
    assert (Decimal(pref['minimum_stock']) == Decimal(value)) if explicit else pref['minimum_stock'] is None
    if explicit:
        source = result['provenance']['items'][str(ident)]['minimum_preference']
        assert source['actor_user_id'] == str(ids['user']) and source['inventory_version'] == 1
        assert source['source'] == 'authenticated_inventory_input'
    assert pref['lead_days'] is pref['coverage_days'] is pref['pack_size'] is None


def test_preference_zero_edit_retry_and_retention_downgrade(planning):
    client, Session, ids = planning
    path = f"/api/v1/households/{ids['home']}/inventory-items/{ids['batch']}"
    payload = {'operation_id':str(uuid4()), 'expected_version':1, 'minimum_quantity':'0'}
    first = client.patch(path, headers=headers(), json=payload)
    assert first.status_code == 200 and client.patch(path, headers=headers(), json=payload).status_code == 200
    assert Decimal(get(planning).json()['data']['items'][0]['preferences']['minimum_stock']) == 0
    with Session.begin() as db:
        row = db.get(InventoryItem, ids['batch'])
        assert row.version == 2 and len(row.history_json) == 1
        row.history_json = [{'kind':'Moved'} for _ in range(30)]
    assert get(planning).json()['data']['items'][0]['preferences']['minimum_stock'] is None


@pytest.mark.parametrize('link,status,unit', [('explicit','pending','盒'), ('explicit','purchased','盒'),
    ('none','pending','盒'), ('foreign','pending','盒'), ('explicit','pending','件'), ('explicit','pending','瓶')])
def test_pending_association_and_unknown_duplicate_risk(planning, link, status, unit):
    _, Session, ids = planning
    with Session.begin() as db:
        foreign = InventoryItem(household_id=ids['foreign_home'], name='牛奶', quantity=1, unit='盒')
        db.add(foreign); db.flush()
        foreign_id = foreign.id
        key = ids['batch'] if link == 'explicit' else foreign.id if link == 'foreign' else None
        db.add(ShoppingListItem(shopping_list_id=ids['list'], source_inventory_item_id=key,
            name='牛奶', quantity=2, unit=unit, is_checked=status=='purchased'))
    response = get(planning)
    assert response.status_code == 200, response.text
    result = response.json()
    valid = link == 'explicit' and unit == '盒'
    assert result['data']['pending_complete'] == (status == 'purchased' or valid)
    assert len(result['data']['pending']) == int(valid)
    if valid: assert result['data']['pending'][0]['status'] == status
    else: assert result['provenance']['shopping'][0]['item_key'] is None or unit in {'件', '瓶'}
    if link == 'foreign':
        assert str(foreign_id) not in json.dumps(result)


def test_missing_shopping_list_is_not_empty_complete(planning):
    _, Session, ids = planning
    with Session.begin() as db: db.delete(db.get(ShoppingList, ids['list']))
    payload = get(planning).json()
    assert not payload['data']['pending_complete'] and not payload['provenance']['shopping_list_present']


def test_agent_real_http_reader_and_safe_degradation(planning, real_p7):
    client, Session, ids = planning
    from v1.tools import RemoteReader, Reader
    from p0.schemas import Scope
    from p3.history import consumption
    from p3.forecast import evaluate
    from p3.procurement import suggest
    scope = Scope(user_id=str(ids['user']), household_id=str(ids['home']))
    # real_p7 installs a distinct synthetic token and routes actual app HTTP requests.
    import os
    reader = Reader(RemoteReader('http://backend:8000', os.environ['BACKEND_TOOL_TOKEN']), lambda:datetime.now(timezone.utc))
    snap = asyncio.run(reader.planning_context(scope))
    item = snap.items[0]
    summary = consumption(item, snap, 'Asia/Shanghai')
    assert summary.status == 'insufficient_data' and summary.observed_days == 0
    assert 'RECORDING_COMPLETENESS_UNKNOWN' in summary.reason_codes
    assert 'NO_COMPLETE_COVERAGE_DAYS' in summary.reason_codes
    forecast = evaluate(item, snap, 'Asia/Shanghai')
    assert forecast.reference_date is None and forecast.daily_recorded_consumption is None
    assert suggest(item, snap, forecast, []).suggested_quantity is None
    assert any('STOCK_VERIFICATION_REQUIRED' in gap for gap in reader.gaps)
    assert ('backend', PATH) in real_p7
    # Actual gateway->Agent->backend HTTP chain, deterministic rule extraction.
    response = client.post('/api/v1/agent/messages', headers=headers(), json={
        'household_id':str(ids['home']), 'text':'牛奶消耗统计', 'request_id':uuid4().hex})
    assert response.status_code == 200, response.text
    assert ('agent','/agent/message') in real_p7
    assert client.get('/api/v1/agent/execution-capabilities', headers=headers()).json()['automatic_planning_commit'] is False
    save('agent_degraded', response.json())


@pytest.mark.parametrize('fault,code', [('stale','STALE_PLANNING_SNAPSHOT'), ('future','STALE_PLANNING_SNAPSHOT'),
    ('items','PLANNING_INCOMPLETE'), ('cursor','PLANNING_INCOMPLETE')])
def test_agent_preserves_snapshot_validation(planning, fault, code):
    from v1.tools import Reader
    from p0.domain import DomainError
    snap = parse(get(planning).json()['data'])
    if fault == 'stale': snap.as_of -= timedelta(minutes=6)
    if fault == 'future': snap.as_of += timedelta(minutes=1)
    if fault == 'items': snap.items_complete = False
    if fault == 'cursor': snap.next_cursor = 'more'
    class Delegate:
        async def planning_context(self, *a, **kw): return snap
    with pytest.raises(DomainError) as error:
        asyncio.run(Reader(Delegate(), lambda:datetime.now(timezone.utc)).planning_context(snap.scope))
    assert error.value.code == code


@pytest.mark.parametrize('coverage_fault,reason', [('unknown','RECORDING_COMPLETENESS_UNKNOWN'),
    ('incomplete','NO_COMPLETE_COVERAGE_DAYS'), ('stockout','UNEXPLAINED_STOCKOUT_OR_ADJUSTMENT'),
    ('adjustment','UNEXPLAINED_STOCKOUT_OR_ADJUSTMENT'), ('transport','HISTORY_TRANSPORT_INCOMPLETE')])
def test_test_only_coverage_failures_do_not_become_zero(planning, coverage_fault, reason):
    from p3.schemas import CoverageDay
    from p3.history import consumption
    snap = parse(get(planning).json()['data'])
    item = snap.items[0]
    day = snap.as_of.date() - timedelta(days=1)
    item.coverage = [CoverageDay(day=day, records_complete=coverage_fault!='incomplete',
        stockout=coverage_fault=='stockout', unexplained_adjustment=coverage_fault=='adjustment')]
    if coverage_fault != 'unknown': item.recording_completeness_source = 'TEST ONLY'
    if coverage_fault == 'transport': snap.history_complete = False
    result = consumption(item, snap, 'UTC')
    assert reason in result.reason_codes and result.status != 'complete'


def test_synthetic_complete_input_independently_recomputes_real_events(planning):
    client, Session, ids = planning
    from p3.schemas import CoverageDay
    from p3.forecast import evaluate
    from p3.procurement import suggest
    for n in range(5):
        d, _ = seed_draft(Session, ids, expected_version=n+1, quantity='.2')
        assert post(client, d, body()).status_code == 200
    # Synthetic timestamps solely build a documented historical test scenario.
    with Session.begin() as db:
        for n,e in enumerate(db.scalars(select(BusinessEvent).order_by(BusinessEvent.id)).all()):
            e.occurred_at -= timedelta(days=n+1)
    snap = parse(get(planning).json()['data'])
    item = snap.items[0]
    item.coverage = [CoverageDay(day=snap.as_of.date()-timedelta(days=n), records_complete=True, stockout=False)
                     for n in range(1,29)]
    item.recording_completeness_source = 'TEST ONLY synthetic coverage, not production evidence'
    item.usable_quantity_verified = True
    item.preferences.coverage_days, item.preferences.lead_days = 140, 0
    result = evaluate(item, snap, 'UTC')
    assert result.status == 'estimated' and result.summary.effective_quantity == Decimal('1')
    assert result.daily_recorded_consumption == Decimal('1') / 28
    assert result.current_stock == 4 and result.remaining_days == 112
    rec = suggest(item, snap, result, [])
    assert rec.source == 'recorded_history' and rec.target_stock == 5 and rec.suggested_quantity == 1
    # Incompatible events are rejected from reliable totals by the existing algorithm.
    item.events[0].unit = '瓶'
    assert 'EVENT_UNIT_CONFLICT' in evaluate(item, snap, 'UTC').reason_codes
    save('TEST_ONLY_complete_input', {'synthetic_coverage':True, 'forecast':json.loads(result.model_dump_json()),
                                     'recommendation':json.loads(rec.model_dump_json())})


def test_malformed_legacy_preference_is_unknown_not_complete(planning):
    _, Session, ids = planning
    with Session.begin() as db:
        row = db.get(InventoryItem, ids['batch'])
        row.history_json = [{'minimum_preference': {'source':'authenticated_inventory_input', 'quantity':'invalid'}}]
    response = get(planning)
    assert response.status_code == 200
    assert response.json()['data']['items'][0]['preferences']['minimum_stock'] is None


def test_read_endpoint_rechecks_membership_and_cannot_write(planning, monkeypatch):
    from app.routers import planning as route
    client, Session, ids = planning
    original = route.snapshot
    def revoked(db, user, home, *args, **kwargs):
        with Session.begin() as writer:
            writer.delete(writer.get(HouseholdMember, (home, user)))
        return original(db, user, home, *args, **kwargs)
    monkeypatch.setattr(route, 'snapshot', revoked)
    assert get(planning).status_code == 404
    assert client.post(PATH, headers=tool_headers(ids), json={'quantity':'100'}).status_code == 405
    with Session() as db:
        assert db.get(InventoryItem, ids['batch']).quantity == 5
        assert db.query(BusinessEvent).count() == db.query(DraftOperation).count() == 0


def test_legacy_positive_minimum_and_opaque_shopping_versions(planning):
    _, Session, ids = planning
    with Session.begin() as db:
        db.get(InventoryItem, ids['batch']).minimum_quantity = Decimal('2')
        item = ShoppingListItem(shopping_list_id=ids['list'], name='牛奶', quantity=1, unit='盒',
                                source_inventory_item_id=ids['batch'])
        db.add(item); db.flush()
        item_id = item.id
    first = get(planning).json()
    assert Decimal(first['data']['items'][0]['preferences']['minimum_stock']) == 2
    with Session.begin() as db: db.get(ShoppingListItem, item_id).source_inventory_item_id = None
    second = get(planning).json()
    assert first['data']['shopping_version'] != second['data']['shopping_version']
    assert second['data']['pending_complete'] is False


def test_published_v1_schema_field_shape_matches_backend():
    from app.planning_schemas import PlanningSnapshot as Backend
    from v1.schemas import PlanningSnapshot as Agent
    published = json.loads((ROOT/'docs/versions/V1-P6/planning-context.schema.json').read_text(encoding='utf-8'))
    assert set(published['properties']) == set(Backend.model_fields) == set(Agent.model_fields)
    for name, model in [('Batch', Backend.model_fields['items'].annotation.__args__[0].model_fields['batches'].annotation.__args__[0]),
                        ('Event', Backend.model_fields['items'].annotation.__args__[0].model_fields['events'].annotation.__args__[0])]:
        assert set(published['$defs'][name]['properties']) == set(model.model_fields)


def test_snapshot_identity_stable_across_fresh_reads_and_selectors(planning):
    first = get(planning).json()['data']
    selected = get(planning, params={'item_key':first['items'][0]['item_key']}).json()['data']
    assert first['snapshot_id'] == selected['snapshot_id']
    assert first['as_of'] != selected['as_of']


def test_real_agent_planning_selection_completes_without_snapshot_loop(planning, real_p7):
    client, Session, ids = planning
    with Session.begin() as db:
        db.add(InventoryItem(household_id=ids['home'], name='牛奶', quantity=2, unit='瓶', version=1, status='ACTIVE'))
    initial = client.post('/api/v1/agent/messages', headers=headers(), json={
        'household_id':str(ids['home']), 'text':'牛奶消耗统计', 'request_id':uuid4().hex})
    assert initial.status_code == 200
    task = initial.json()
    assert task['status'] == 'needs_clarification', task
    selected = client.post('/api/v1/agent/clarifications/'+task['task_id'], headers=headers(), json={
        'revision':task['revision'], 'answers':{'batch_id':str(ids['batch'])}})
    assert selected.status_code == 200, selected.text
    value = selected.json()
    assert value['status'] == 'answered', value
    assert value['result']['consumption_summary'][0]['item_key'] == str(ids['batch'])
