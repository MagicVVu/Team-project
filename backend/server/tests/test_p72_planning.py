import sys
from pathlib import Path
from sqlalchemy import select
from test_v09_execution import execution_state, seed_draft, post, body
from app.models import InventoryItem, ShoppingListItem

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'agent'))
from v1.schemas import PlanningSnapshot
from p3.history import consumption
from p3.forecast import evaluate


def auth(ids):
    return {'Authorization': 'Bearer synthetic-tool-token', 'X-User-Id': str(ids['user']), 'X-Household-Id': str(ids['home'])}


def test_real_ledger_contract_separates_transport_from_recording(execution_state, monkeypatch):
    client, Session, ids = execution_state
    monkeypatch.setenv('BACKEND_TOOL_TOKEN', 'synthetic-tool-token')
    draft, _ = seed_draft(Session, ids)
    assert post(client, draft, body()).status_code == 200
    response = client.get('/internal/v1/planning/context', headers=auth(ids))
    assert response.status_code == 200, response.text
    snapshot = PlanningSnapshot.model_validate(response.json()['data'])
    assert snapshot.history_complete and snapshot.items_complete
    assert len(snapshot.items) == 1 and snapshot.items[0].batches[0].quantity == 4
    item = snapshot.items[0]
    assert item.item_key == str(ids['batch']) and item.events[0].kind == 'Consumed'
    assert item.recording_completeness_source is None and item.coverage == [] and item.stock_verification is None
    summary = consumption(item, snapshot, 'Asia/Shanghai')
    assert summary.status == 'insufficient_data' and 'RECORDING_COMPLETENESS_UNKNOWN' in summary.reason_codes
    forecast = evaluate(item, snapshot, 'Asia/Shanghai')
    assert forecast.reference_date is None and forecast.status == 'insufficient_data'
    second = client.get('/internal/v1/planning/context', headers=auth(ids)).json()['data']
    assert second['snapshot_id'] == snapshot.snapshot_id
    with Session.begin() as db: db.get(InventoryItem, ids['batch']).version += 1
    assert client.get('/internal/v1/planning/context', headers=auth(ids)).json()['data']['snapshot_id'] != snapshot.snapshot_id


def test_unknown_pending_mapping_is_not_guessed(execution_state, monkeypatch):
    client, Session, ids = execution_state
    monkeypatch.setenv('BACKEND_TOOL_TOKEN', 'synthetic-tool-token')
    draft, _ = seed_draft(Session, ids, 'PLAN_ADD', name='牛奶')
    assert post(client, draft, body()).status_code == 200
    result = client.get('/internal/v1/planning/context', headers=auth(ids)).json()['data']
    assert result['pending_complete'] is False and result['pending'] == []
    assert result['items'][0]['item_key'] == str(ids['batch'])
    assert client.get('/internal/v1/planning/context').status_code == 401
    headers = auth(ids); headers['X-User-Id'] = str(ids['outsider'])
    assert client.get('/internal/v1/planning/context', headers=headers).status_code == 404
