from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from test_v09_execution import execution_state, seed_draft, body, post, PG
from app.models import InventoryItem
from app.execution_models import BusinessEvent, DraftOperation


def draft_for(Session, ids, action, **updates):
    fields = {'opened_at': date.today().isoformat()} if action == 'OPEN' else dict(discard_mode='partial', quantity='2', unit='盒')
    # Existing helper builds a CONSUME-shaped source; replace only via fixture updates.
    if action == 'OPEN':
        from app.models import AIDraft, AITask
        draft, task = seed_draft(Session, ids, action)
        with Session.begin() as db:
            row = db.get(AIDraft, draft)
            command = {k: v for k, v in row.command_json.items() if k not in {'quantity', 'unit'}}
            command.update(fields, **updates)
            row.command_json = command
            db.get(AITask, task).result_json = dict(status='needs_confirmation', draft=command)
        return draft
    return seed_draft(Session, ids, action, **{**fields, **updates})[0]


@pytest.mark.parametrize('action,mode,remaining', [('OPEN', None, '5'), ('DISCARD', 'partial', '3'), ('DISCARD', 'all', '0')])
def test_open_discard_exact_recovery_and_events(execution_state, action, mode, remaining):
    client, Session, ids = execution_state
    updates = dict(discard_mode=mode, quantity='5' if mode == 'all' else '2') if mode else {}
    draft = draft_for(Session, ids, action, **updates)
    request = body()
    result = post(client, draft, request)
    assert result.status_code == 200, result.text
    assert post(client, draft, request).json() == result.json()
    with Session() as db:
        item = db.get(InventoryItem, ids['batch'])
        assert item.quantity == Decimal(remaining) and item.version == 2 and item.storage_location == '冰箱'
        assert item.status == ('DISCARDED' if remaining == '0' else 'ACTIVE')
        event = db.scalar(select(BusinessEvent))
        assert event.event_type == ('Opened' if action == 'OPEN' else 'Discarded')
        assert event.quantity == (None if action == 'OPEN' else Decimal(5) - Decimal(remaining))
        assert db.scalar(select(func.count()).select_from(DraftOperation)) == 1
        if action == 'OPEN': assert item.opened_at is not None and result.json()['result']['inventory_item']['opened_at']


@pytest.mark.parametrize('action,updates,status', [
    ('OPEN', {'opened_at': (date.today()+timedelta(days=2)).isoformat()}, 422),
    ('OPEN', {'opened_at': '2026-02-30'}, 422),
    ('DISCARD', {'quantity': '6'}, 422),
    ('DISCARD', {'quantity': '0.0000001'}, 422),
    ('DISCARD', {'unit': 'kg'}, 422),
    ('DISCARD', {'discard_mode': 'all', 'quantity': '4'}, 409),
    ('DISCARD', {'expected_version': 2}, 409),
])
def test_invalid_open_discard_is_atomic(execution_state, action, updates, status):
    client, Session, ids = execution_state
    draft = draft_for(Session, ids, action, **updates)
    result = post(client, draft, body())
    assert result.status_code == status, result.text
    with Session() as db:
        assert db.get(InventoryItem, ids['batch']).quantity == 5
        assert db.scalar(select(func.count()).select_from(BusinessEvent)) == 0


def test_second_open_does_not_mutate(execution_state):
    client, Session, ids = execution_state
    assert post(client, draft_for(Session, ids, 'OPEN'), body()).status_code == 200
    second = draft_for(Session, ids, 'OPEN', expected_version=2)
    result = post(client, second, body())
    assert result.status_code == 409 and result.json()['detail']['code'] == 'ALREADY_OPENED'
    with Session() as db:
        assert db.get(InventoryItem, ids['batch']).version == 2
        assert db.scalar(select(func.count()).select_from(BusinessEvent)) == 1


@pytest.mark.skipif(not PG, reason='PostgreSQL row locks required')
<<<<<<< Updated upstream
@pytest.mark.parametrize('action', ['OPEN', 'DISCARD'])
def test_concurrent_action_drafts_do_not_double_mutate(execution_state, action):
    client, Session, ids = execution_state
    drafts = [draft_for(Session, ids, action) for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda d: post(client, d, body()), drafts))
    assert sorted(r.status_code for r in results) == [200, 409]
    with Session() as db:
        item = db.get(InventoryItem, ids['batch'])
        assert item.quantity == (5 if action == 'OPEN' else 3) and item.version == 2
=======
def test_concurrent_discard_drafts_do_not_double_deduct(execution_state):
    client, Session, ids = execution_state
    drafts = [draft_for(Session, ids, 'DISCARD') for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda d: post(client, d, body()), drafts))
    assert sorted(r.status_code for r in results) == [200, 409]
    with Session() as db: assert db.get(InventoryItem, ids['batch']).quantity == 3
>>>>>>> Stashed changes
