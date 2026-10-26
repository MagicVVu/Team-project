"""Authenticated fact capture -> real AI reader/forecast, with invalidation and retries."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from test_v09_execution import execution_state, seed_draft, headers, body, post, PG
from test_backend_p1_integration import real_p7
from test_backend_p4_planning import planning, get, parse, tool_headers
from app.models import InventoryItem, HouseholdMember
from app.execution_models import BusinessEvent, DraftOperation
from app.planning_fact_models import InventoryPlanningFacts, PlanningFactWrite
from app.services import planning_facts as service


def url(ids):
    return f'/api/v1/households/{ids["home"]}/inventory-items/{ids["batch"]}/planning-facts'


def patch(client, ids, *, version=0, inventory_version=1, who="user", **sections):
    payload = {"operation_id": str(uuid4()), "expected_inventory_version": inventory_version,
        "expected_facts_version": version, "source": "家庭成员核对记录", **sections}
    return client.patch(url(ids), headers=headers(who), json=payload), payload


def day(offset=1, **changes):
    return {"day": (service.now().astimezone(service.business_zone()).date()-timedelta(days=offset)).isoformat(),
        "records_complete": True, "stockout": False, "unexplained_adjustment": False, **changes}


def test_empty_facts_are_unknown_and_scoped(planning):
    client, Session, ids = planning
    r = client.get(url(ids), headers=headers())
    assert r.status_code == 200 and r.headers['cache-control'] == 'no-store'
    assert r.json()['facts_version'] == 0 and r.json()['coverage'] == []
    assert r.json()['stock_verification'] is r.json()['preferences'] is r.json()['risk_facts'] is None
    assert client.get(url(ids)).status_code == 401
    assert client.get(url(ids), headers=headers('outsider')).status_code == 404
    denied, _ = patch(client, ids, who='outsider', preferences={'minimum_stock':'8'})
    assert denied.status_code == 404
    with Session() as db:
        assert db.query(InventoryPlanningFacts).count() == db.query(PlanningFactWrite).count() == 0


def test_capture_projects_to_contract_and_does_not_mutate_stock(planning):
    client, Session, ids = planning
    before = get(planning).json()['data']
    r, payload = patch(client, ids, preferences={'minimum_stock':'8', 'lead_days':2, 'coverage_days':14,
        'order_unit':'盒','pack_size':'1'}, coverage=[day()],
        stock_verification={'quantity':'5','unit':'盒'},
        risk_facts={'category':'household','storage_condition':'ambient','label_storage_condition':'ambient','is_opened':False})
    assert r.status_code == 200, r.text
    value = r.json()
    assert value['facts_version'] == 1 and value['inventory_written'] is False
    assert value['invalidated_sections'] == []
    assert value['provenance']['stock_verification']['actor_user_id'] == str(ids['user'])
    assert value['stock_verification']['checked_at']
    assert client.patch(url(ids), headers=headers(), json=payload).json() == value
    assert client.get(url(ids), headers=headers()).json() == value
    response = get(planning)
    assert response.status_code == 200, response.text
    snap = parse(response.json()['data'])
    item = snap.items[0]
    assert item.preferences.minimum_stock == 8 and item.preferences.lead_days == 2
    assert item.stock_verification.source == '家庭成员核对记录' and item.usable_quantity_verified
    assert item.coverage[0].records_complete and item.recording_completeness_source
    assert item.category == item.batches[0].category == 'household'
    assert before['snapshot_id'] != snap.snapshot_id
    assert get(planning, params={'item_key':str(ids['batch'])}).json()['data']['snapshot_id'] == snap.snapshot_id
    batch = client.get('/internal/v1/inventory/batches/'+str(ids['batch']), headers=tool_headers(ids)).json()['data']['batch']
    assert batch['category'] == 'household' and batch['storage_condition'] == 'ambient'
    with Session() as db:
        row = db.get(InventoryItem, ids['batch'])
        assert row.quantity == 5 and row.version == 1 and row.minimum_quantity == 0
        assert db.query(PlanningFactWrite).count() == 1
        assert db.query(BusinessEvent).filter_by(event_type='Counted').count() == 1
        assert db.query(DraftOperation).count() == 0


@pytest.mark.parametrize('sections,code', [
    ({'stock_verification':{'quantity':'4','unit':'盒'}}, 'STOCK_COUNT_MISMATCH'),
    ({'stock_verification':{'quantity':'5','unit':'瓶'}}, 'STOCK_COUNT_MISMATCH'),
    ({'coverage':[day(0)]}, 'COVERAGE_DAY_OUT_OF_RANGE'),
    ({'coverage':[day(3661)]}, 'COVERAGE_DAY_OUT_OF_RANGE'),
    ({'risk_facts':{'label_context_valid':True}}, 'LABEL_DATE_REQUIRED'),
])
def test_invalid_observations_roll_back_all_sections(planning, sections, code):
    client, Session, ids = planning
    response, _ = patch(client, ids, preferences={'minimum_stock':'7'}, **sections)
    assert response.status_code in {409,422} and response.json()['detail']['code'] == code
    with Session() as db:
        assert db.query(InventoryPlanningFacts).count() == db.query(PlanningFactWrite).count() == 0


@pytest.mark.parametrize('sections', [
    {'coverage':None}, {'coverage':[]}, {'coverage':[day(),day()]},
    {'coverage':[day(records_complete='true')]}, {'coverage':[day(day=123)]},
    {'preferences':{'pack_size':'2'}}, {'preferences':{'coverage_days':True}},
    {'preferences':{'minimum_stock':'0.0000001'}}, {'risk_facts':{'source':'injected'}},
    {'stock_verification':{'quantity':'5','unit':'盒','checked_at':'2026-10-01T00:00:00Z'}},
])
def test_strict_public_input(planning, sections):
    client, _, ids = planning
    response, _ = patch(client, ids, **sections)
    assert response.status_code == 422, response.text


def test_versions_and_durable_idempotency(planning):
    client, Session, ids = planning
    r, payload = patch(client, ids, preferences={'minimum_stock':'8'})
    assert r.status_code == 200
    assert patch(client, ids, preferences={'minimum_stock':'9'})[0].json()['detail']['code'] == 'PLANNING_FACTS_VERSION_CONFLICT'
    assert patch(client, ids, version=1, inventory_version=2, preferences=None)[0].json()['detail']['code'] == 'INVENTORY_VERSION_CONFLICT'
    assert client.patch(url(ids), headers=headers(), json={**payload,'source':'different'}).json()['detail']['code'] == 'OPERATION_ID_CONFLICT'
    assert patch(client, ids, version=1, preferences=None)[0].status_code == 200
    assert client.patch(url(ids), headers=headers(), json=payload).json() == r.json()
    with Session.begin() as db:
        db.delete(db.get(HouseholdMember, (ids['home'],ids['user'])))
    assert client.patch(url(ids), headers=headers(), json=payload).status_code == 404


def test_inventory_changes_invalidate_only_bound_facts(planning):
    client, _, ids = planning
    r, _ = patch(client, ids, preferences={'minimum_stock':'8'}, coverage=[day()],
        stock_verification={'quantity':'5','unit':'盒'}, risk_facts={'category':'household','storage_condition':'ambient'})
    assert r.status_code == 200
    changed = client.patch(url(ids).removesuffix('/planning-facts'), headers=headers(), json={
        'expected_version':1, 'operation_id':str(uuid4()),'storage_location':'储物柜'})
    assert changed.status_code == 200
    facts = client.get(url(ids), headers=headers()).json()
    assert set(facts['invalidated_sections']) == {'stock_verification','risk_facts'}
    snap = parse(get(planning).json()['data'])
    assert snap.items[0].stock_verification is None
    assert snap.items[0].preferences.minimum_stock == 8
    assert snap.items[0].coverage[0].records_complete
    assert snap.items[0].batches[0].storage_condition is None


def test_late_history_change_invalidates_attestation(planning):
    client, Session, ids = planning
    r, _ = patch(client, ids, coverage=[day()])
    assert r.status_code == 200
    yesterday = service.now() - timedelta(days=1)
    # A historical adjustment arriving after attestation must not be counted as zero consumption.
    with Session.begin() as db:
        item = db.get(InventoryItem, ids['batch'])
        item.history_json = [{'kind':'adjust','created_at':yesterday.isoformat(),'id':'late-import'}]
    result = client.get(url(ids), headers=headers()).json()
    assert result['invalidated_sections'] == ['coverage:'+day()['day']]
    assert not result['coverage'][0]['records_complete'] and result['coverage'][0]['unexplained_adjustment']
    assert not parse(get(planning).json()['data']).items[0].coverage[0].records_complete


def test_clear_and_revoke_are_explicit(planning):
    client, _, ids = planning
    assert patch(client, ids, preferences={'minimum_stock':'0'}, coverage=[day()],
        stock_verification={'quantity':'5','unit':'盒'}, risk_facts={'category':'household'})[0].status_code == 200
    r, _ = patch(client, ids, version=1, preferences=None, stock_verification=None,
        risk_facts=None, coverage=[day(records_complete=False)])
    assert r.status_code == 200 and r.json()['facts_version'] == 2
    assert r.json()['stock_verification'] is r.json()['preferences'] is r.json()['risk_facts'] is None
    assert not r.json()['coverage'][0]['records_complete']


def test_calendar_zone_is_server_owned_and_changes_invalidate_coverage(planning, monkeypatch):
    client, _, ids = planning
    assert patch(client, ids, coverage=[day()])[0].status_code == 200
    monkeypatch.setenv('MAGICVVU_HOUSEHOLD_TIMEZONE', 'UTC')
    facts = client.get(url(ids), headers=headers()).json()
    assert facts['household_timezone'] == 'UTC' and facts['invalidated_sections'][0].startswith('coverage:')
    r = client.post('/api/v1/agent/messages', headers=headers(), json={
        'household_id':str(ids['home']), 'text':'牛奶消耗统计','request_id':uuid4().hex,
        'household_timezone':'Asia/Shanghai'})
    assert r.status_code == 422 and r.json()['detail']['code'] == 'HOUSEHOLD_TIMEZONE_MISMATCH'


def test_migration_preserves_stock_and_refuses_evidence_loss(planning):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect
    client, Session, ids = planning
    engine = Session.kw['bind']
    module_path = Path(__file__).resolve().parents[1] / 'alembic/versions/20261023_0010_planning_facts.py'
    spec = importlib.util.spec_from_file_location('planning_migration', module_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            migration.upgrade()
    with Session() as db:
        assert db.get(InventoryItem,ids['batch']).quantity == 5
    assert patch(client, ids, preferences={'minimum_stock':'8'})[0].status_code == 200
    with pytest.raises(RuntimeError, match='Planning evidence exists'):
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                migration.downgrade()
    assert 'planning_fact_writes' in inspect(engine).get_table_names()
    with Session() as db:
        assert db.query(PlanningFactWrite).count() == 1
        assert db.get(InventoryItem,ids['batch']).quantity == 5


def test_real_ai_uses_attested_history_and_verified_inventory(planning, real_p7):
    client, Session, ids = planning
    for n in range(5):
        draft_id, _ = seed_draft(Session, ids, quantity='0.1', expected_version=n+1)
        r = post(client, draft_id, body())
        assert r.status_code == 200, r.text
    with Session.begin() as db:
        for n, event in enumerate(db.scalars(select(BusinessEvent).order_by(BusinessEvent.id))):
            # Only the synthetic fixture is backdated; every event was committed by the real service.
            event.occurred_at = service.now()-timedelta(days=n+1)
    r, _ = patch(client, ids, inventory_version=6, preferences={'minimum_stock':'8'},
        coverage=[day(n) for n in range(1,15)], stock_verification={'quantity':'4.5','unit':'盒'},
        risk_facts={'category':'household'})
    assert r.status_code == 200, r.text
    from v1.tools import RemoteReader, Reader
    from p0.schemas import Scope
    from p3.forecast import evaluate
    from p3.procurement import suggest
    import os
    reader = Reader(RemoteReader('http://backend:8000',os.environ['BACKEND_TOOL_TOKEN']), service.now)
    scope = Scope(user_id=str(ids['user']),household_id=str(ids['home']))
    snap = asyncio.run(reader.planning_context(scope))
    forecast = evaluate(snap.items[0],snap,'Asia/Shanghai')
    assert forecast.status == 'estimated' and forecast.summary.observed_days == 14
    assert forecast.summary.effective_events == 5 and forecast.summary.effective_quantity == Decimal('0.5')
    assert suggest(snap.items[0],snap,forecast,[]).suggested_quantity == Decimal('3.5')
    r = client.post('/api/v1/agent/messages', headers=headers(), json={
        'household_id':str(ids['home']),'text':'牛奶消耗统计','request_id':uuid4().hex})
    assert r.status_code == 200, r.text
    summary = r.json()['result']['consumption_summary'][0]
    assert summary['status'] == 'complete' and Decimal(summary['effective_quantity']) == Decimal('0.5')
    assert r.json()['inventory_written'] is False


@pytest.mark.skipif(not PG, reason='PostgreSQL row locks required')
@pytest.mark.parametrize('same_operation', [False, True])
def test_concurrent_fact_writes_and_replays(planning, same_operation):
    client, Session, ids = planning
    first = {'operation_id':str(uuid4()),'expected_inventory_version':1,'expected_facts_version':0,
        'source':'concurrent fixture','preferences':{'minimum_stock':'8'}}
    second = first if same_operation else {**first,'operation_id':str(uuid4())}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda payload: client.patch(url(ids),headers=headers(),json=payload), [first, second]))
    assert sorted(r.status_code for r in responses) == ([200,200] if same_operation else [200,409])
    if same_operation: assert responses[0].json() == responses[1].json()
    with Session() as db:
        assert db.query(PlanningFactWrite).count() == 1
        assert db.get(InventoryPlanningFacts,ids['batch']).version == 1
