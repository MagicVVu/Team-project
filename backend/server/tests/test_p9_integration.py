"""P9 synthetic households, real auth + shipped Agent + durable database writes."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from unittest.mock import patch
import pytest
from sqlalchemy import select
from test_v09_execution import execution_state, seed_draft, body, post, headers, PG
from test_backend_p4_planning import planning, get, parse
from app.models import InventoryItem, ShoppingListItem, AITask
from app.product_models import ProductBatch, MutationReceipt
from app.execution_models import BusinessEvent
from app.services import ledger


def root(ids):
    return f'/api/v1/households/{ids["home"]}'


def shopping(client, ids, **changes):
    response = client.post(root(ids)+'/shopping-list/items', headers=headers(), json={
        'name': '牛奶', 'quantity': '2', 'unit': '盒', **changes})
    assert response.status_code == 201, response.text
    return response.json()


def source_patch(client, ids, item, source, **changes):
    payload = {'operation_id': str(uuid4()), 'expected_version': item['version'],
               'source_inventory_item_id': str(source) if source else None, **changes}
    return client.patch(root(ids)+'/shopping-list/items/'+item['id'], headers=headers(), json=payload), payload


def product(client, ids, **changes):
    payload = {'id': str(uuid4()), 'name': '牛奶', 'base_unit': '盒', 'source': '成员核对包装', **changes}
    result = client.post(root(ids)+'/products', headers=headers(), json=payload)
    assert result.status_code == 201, result.text
    assert client.post(root(ids)+'/products', headers=headers(), json=payload).json() == result.json()
    return result.json()


def link(client, ids, batch_id, product_id, version=1):
    payload = {'operation_id': str(uuid4()), 'expected_inventory_version': version,
               'product_id': product_id, 'source': '逐批核对条码及规格'}
    result = client.put(root(ids)+f'/inventory-items/{batch_id}/product', headers=headers(), json=payload)
    assert result.status_code == 200, result.text
    assert client.put(root(ids)+f'/inventory-items/{batch_id}/product', headers=headers(), json=payload).json() == result.json()
    return result.json()


def add_batch(Session, ids, **changes):
    batch_id = uuid4()
    with Session.begin() as db:
        db.add(InventoryItem(id=batch_id, created_by_user_id=ids['user'],
            **{'household_id':ids['home'], 'name':'牛奶', 'quantity':3, 'unit':'盒', 'status':'ACTIVE', 'version':1, **changes}))
    return batch_id


def test_source_set_replace_clear_omit_replay_and_old_client(planning):
    client, Session, ids = planning
    other = add_batch(Session, ids)
    item = shopping(client, ids)
    response, payload = source_patch(client, ids, item, ids['batch'])
    assert response.status_code == 200, response.text
    linked = response.json()
    assert linked['source_inventory_item_id'] == str(ids['batch'])
    changed, _ = source_patch(client, ids, linked, other)
    assert changed.status_code == 200 and changed.json()['source_inventory_item_id'] == str(other)
    # A delayed retry returns its original receipt without reverting the newer source.
    url = root(ids)+'/shopping-list/items/'+item['id']
    assert client.patch(url, headers=headers(), json=payload).json() == linked
    omitted = client.patch(url, headers=headers(), json={'quantity':'4'})
    assert omitted.status_code == 200 and omitted.json()['source_inventory_item_id'] == str(other)
    cleared, _ = source_patch(client, ids, omitted.json(), None)
    assert cleared.status_code == 200 and cleared.json()['source_inventory_item_id'] is None
    stale, _ = source_patch(client, ids, linked, ids['batch'])
    assert stale.status_code == 409 and stale.json()['detail']['code'] == 'SHOPPING_VERSION_CONFLICT'
    assert get(planning).json()['provenance']['pending_state'] == 'association_unknown'


@pytest.mark.parametrize('case', ['cross_family','missing','purchased','unit','quantity','version_required'])
def test_source_validation(execution_state, case):
    client, Session, ids = execution_state
    item = shopping(client, ids)
    if case == 'cross_family':
        foreign = add_batch(Session, ids, household_id=ids['foreign_home'])
    source = foreign if case == 'cross_family' else uuid4() if case == 'missing' else ids['batch']
    if case == 'purchased':
        assert client.post(root(ids)+'/shopping-list/items/'+item['id']+'/purchase', headers=headers(), json={}).status_code == 200
    changes = {'unit':'瓶'} if case == 'unit' else {'quantity':'-1'} if case == 'quantity' else {}
    response, payload = source_patch(client, ids, item, source, **changes)
    if case == 'version_required':
        payload.pop('expected_version')
        response = client.patch(root(ids)+'/shopping-list/items/'+item['id'], headers=headers(), json=payload)
    assert response.status_code == ({'cross_family':404,'missing':404,'purchased':409,'unit':409,
                                    'quantity':422,'version_required':422}[case]), response.text


def test_pending_three_states_and_product_identity(planning):
    client, Session, ids = planning
    empty = get(planning).json()
    assert empty['data']['pending_complete'] and empty['provenance']['pending_state'] == 'none'
    item = shopping(client, ids)
    unknown = get(planning).json()
    assert not unknown['data']['pending_complete'] and unknown['provenance']['pending_count'] == 1
    linked, _ = source_patch(client, ids, item, ids['batch'])
    assert linked.status_code == 200
    complete = get(planning).json()
    assert complete['data']['pending_complete'] and complete['provenance']['pending_state'] == 'linked_complete'
    p = product(client, ids, tags=['包装标签'])
    link(client, ids, ids['batch'], p['product_id'])
    current = get(planning).json()
    assert current['data']['items'][0]['batches'][0]['product_id'] == p['product_id']
    assert p['platform_rule_review_status'] == 'unknown'
    assert current['provenance']['risk_rules']['version'] is None
    parse(current['data'])  # Existing shipped Agent DTO still accepts the unchanged data envelope.


@pytest.mark.parametrize('scenario', ['same','homonym','convertible','incompatible','expired'])
def test_product_aggregation_scenarios(planning, scenario):
    client, Session, ids = planning
    if scenario in {'convertible', 'incompatible'}:
        with Session.begin() as db:
            batch = db.get(InventoryItem, ids['batch']);batch.unit='g';batch.quantity=500
        extra = add_batch(Session, ids, unit='kg' if scenario == 'convertible' else '盒', quantity=2)
        base_unit = 'g'
    else:
        extra = add_batch(Session, ids, expires_on=date.today()-timedelta(days=1) if scenario == 'expired' else None)
        base_unit = '盒'
    p = product(client, ids, base_unit=base_unit)
    q = product(client, ids, base_unit=base_unit) if scenario == 'homonym' else p
    link(client, ids, ids['batch'], p['product_id'])
    link(client, ids, extra, q['product_id'])
    groups = get(planning).json()['provenance']['product_aggregates_v1']
    group = next(g for g in groups if g['product_id'] == p['product_id'])
    if scenario == 'homonym':
        assert len(groups) == 2 and all(len(g['batches']) == 1 for g in groups)
    elif scenario == 'incompatible':
        assert group['total_quantity'] is None and not group['quantity_complete']
        assert len(group['batches']) == 2
    else:
        assert Decimal(group['total_quantity']) == (2500 if scenario == 'convertible' else 8)
        assert len(group['batches']) == 2
        if scenario == 'expired':
            assert Decimal(group['nonexpired_active_quantity']) == 5
    assert group['usable_quantity'] is None and group['consumption_coverage_days'] is None


def test_purchase_preserves_mapping_provenance_and_one_event(planning):
    client, Session, ids = planning
    p = product(client, ids)
    link(client, ids, ids['batch'], p['product_id'])
    item = shopping(client, ids, source_inventory_item_id=str(ids['batch']))
    url = root(ids)+'/shopping-list/items/'+item['id']+'/purchase'
    first = client.post(url, headers=headers(), json={})
    assert first.status_code == 200, first.text
    stock = first.json()['inventory_item']
    assert client.post(url, headers=headers(), json={}).json()['newly_stocked'] is False
    with Session() as db:
        assert str(db.get(ProductBatch, UUID(stock['id'])).product_id) == p['product_id']
        assert db.query(BusinessEvent).filter_by(event_type='Purchased').count() == 1
    assert stock['source_shopping_list_item_id'] == item['id']


def test_ledger_retention_replay_correction_and_family_scope(planning):
    client, Session, ids = planning
    url = root(ids)+f'/inventory-items/{ids["batch"]}'
    initial = {'operation_id':str(uuid4()),'expected_version':1,'delta':'1'}
    for i in range(33):
        response = client.post(url+'/adjustments', headers=headers(), json=initial if i == 0 else {
            'operation_id':str(uuid4()),'expected_version':i+1,'delta':'1'})
        assert response.status_code == 200, response.text
    replay = client.post(url+'/adjustments', headers=headers(), json=initial)
    assert replay.status_code == 200 and Decimal(replay.json()['quantity']) == 6
    events_url = root(ids)+'/inventory-events'
    events = client.get(events_url, headers=headers()).json()['events']
    assert len(events) == 33 and all(e['event_type']=='Adjusted' for e in events)
    corrected = client.post(url+'/corrections', headers=headers(), json={
        'operation_id':str(uuid4()),'expected_version':34,'related_event_id':events[0]['event_id'],
        'quantity':'37','reason':'核对盘点，修正误录'})
    assert corrected.status_code == 200, corrected.text
    snapshot = get(planning).json()
    assert all(e['kind'] != 'Consumed' for e in snapshot['data']['items'][0]['events'])
    assert any(e['related_event_id'] for e in snapshot['data']['items'][0]['events'])
    assert client.get(events_url, headers=headers('outsider')).status_code == 404
    assert len(client.get(events_url+'?limit=10', headers=headers()).json()['events']) == 10
    with Session() as db:
        assert len(db.get(InventoryItem, ids['batch']).history_json) == 30
        assert db.query(BusinessEvent).count() == 34


def test_event_failure_rolls_back_inventory_and_retry(execution_state):
    client, Session, ids = execution_state
    url = root(ids)+f'/inventory-items/{ids["batch"]}/adjustments'
    payload = {'operation_id':str(uuid4()), 'expected_version':1,'delta':'1'}
    with patch('app.services.ledger.append', side_effect=RuntimeError('injected ledger failure')):
        assert client.post(url, headers=headers(), json=payload).status_code == 500
    with Session() as db:
        assert db.get(InventoryItem, ids['batch']).quantity == 5
        assert db.query(MutationReceipt).count() == db.query(BusinessEvent).count() == 0
    assert client.post(url, headers=headers(), json=payload).status_code == 200


def test_revalidation_stale_edits_unknown_rules_and_commit_disabled(planning):
    client, Session, ids = planning
    basis = get(planning).json()['provenance']['revalidation_basis']
    draft, task_id = seed_draft(Session, ids, 'PLAN_ADD', name='牛奶', unit='盒')
    with Session.begin() as db:
        task = db.get(AITask, task_id)
        task.result_json = {**task.result_json, 'quantity_source':'planning_calculation', 'planning_basis':basis,
                            'procurement_source':{'batch_id':str(ids['batch']),'expected_version':1}}
    url = f'/api/v1/drafts/{draft}/planning-revalidation'
    payload = {'draft_revision':1,'task_revision':1,'edits':{'quantity':'3'}}
    fresh = client.post(url, headers=headers(), json=payload)
    assert fresh.status_code == 200, fresh.text
    assert fresh.json()['status'] == 'blocked' and fresh.json()['user_adjusted']
    assert 'RISK_RULE_REVIEW_REQUIRED' in fresh.json()['blockers']
    assert fresh.json()['effective_request']['quantity'] == '3'
    shopping(client, ids)
    stale = client.post(url, headers=headers(), json=payload).json()
    assert stale['status'] == 'stale' and 'shopping_version' in stale['mismatches']
    assert post(client, draft, body()).json()['detail']['code'] == 'PLANNING_BASIS_STALE'
    assert client.post(url, headers=headers('outsider'), json=payload).status_code == 404


@pytest.mark.skipif(not PG, reason='PostgreSQL row locks required')
@pytest.mark.parametrize('same_request', [False, True])
def test_parallel_source_updates_and_same_request(execution_state, same_request):
    client, Session, ids = execution_state
    item = shopping(client, ids)
    url = root(ids)+'/shopping-list/items/'+item['id']
    payload = {'operation_id':str(uuid4()),'expected_version':item['version'],
               'source_inventory_item_id':str(ids['batch'])}
    def call(value):
        return client.patch(url, headers=headers(), json=value)
    # Different requests based on the same version: exactly one succeeds.
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(call, [payload, payload if same_request else {**payload,'operation_id':str(uuid4())}]))
    assert sorted(r.status_code for r in results) == ([200,200] if same_request else [200,409])
    if same_request:
        assert results[0].json() == results[1].json()
    # The winner can always recover its immutable receipt.
    assert any(r.status_code == 200 for r in results)


def test_p9_downgrade_preserves_new_evidence(execution_state):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    client, Session, ids = execution_state
    product(client, ids)
    path = Path(__file__).resolve().parents[1]/'alembic/versions/20261026_0011_products_ledger.py'
    spec = importlib.util.spec_from_file_location('p9_migration', path)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    with pytest.raises(RuntimeError, match='P9 evidence exists'):
        with Session.kw['bind'].begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                module.downgrade()
    with Session() as db:
        assert db.query(MutationReceipt).count() == 1


def test_correction_invalidates_original_consumption_day(planning):
    from datetime import datetime, timezone
    from test_ai_alignment_facts import patch as facts_patch, day
    client, Session, ids = planning
    draft, _ = seed_draft(Session, ids)
    receipt = post(client, draft, body()).json()
    event_id = UUID(receipt['event_ids'][0])
    with Session.begin() as db:
        db.get(BusinessEvent, event_id).occurred_at = datetime.now(timezone.utc)-timedelta(days=1)
    r, _ = facts_patch(client, ids, inventory_version=2, coverage=[day()])
    assert r.status_code == 200, r.text
    assert get(planning).json()['data']['items'][0]['coverage'][0]['records_complete']
    r = client.post(root(ids)+f'/inventory-items/{ids["batch"]}/corrections', headers=headers(), json={
        'operation_id':str(uuid4()),'expected_version':2,'related_event_id':str(event_id),'quantity':'5',
        'reason':'昨天消费误录，先恢复实盘数量并等待消费记录复核'})
    assert r.status_code == 200, r.text
    cover = get(planning).json()['data']['items'][0]['coverage'][0]
    assert not cover['records_complete'] and cover['unexplained_adjustment']


@pytest.mark.parametrize('key', ['snapshot_id','event_watermark','shopping_version','inventory_versions',
                                'facts_versions','product_versions','risk_rules'])
def test_revalidation_compares_every_basis_dimension(planning, key):
    client, Session, ids = planning
    basis = get(planning).json()['provenance']['revalidation_basis']
    # Simulate each stale saved version without allowing a client to submit it.
    basis[key] = 'obsolete-or-untrusted'
    draft, task_id = seed_draft(Session, ids, 'PLAN_ADD', name='牛奶', unit='盒')
    with Session.begin() as db:
        task = db.get(AITask, task_id)
        task.result_json = {**task.result_json, 'planning_basis':basis,
            'procurement_source':{'batch_id':str(ids['batch']),'expected_version':1}}
    request = {'draft_revision':1,'task_revision':1,'edits':{}}
    response = client.post(f'/api/v1/drafts/{draft}/planning-revalidation', headers=headers(), json=request)
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'stale' and key in response.json()['mismatches']
    assert post(client, draft, body()).json()['detail']['code'] == 'PLANNING_BASIS_STALE'
    with Session() as db:
        assert db.query(ShoppingListItem).count() == 0
