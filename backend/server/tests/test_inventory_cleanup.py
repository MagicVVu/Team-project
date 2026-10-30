"""Ended objects are physically removed, without replaying purchases or commands."""
from uuid import UUID, uuid4
from unittest.mock import patch
import pytest
from sqlalchemy import func, select
from test_physical_inventory import state, add, products, inventory, draft, commit
from test_v07_shopping import headers, create, base
from app.models import InventoryItem, ShoppingListItem
from app.product_models import Product, ProductBatch
from app.execution_models import BusinessEvent
from app.services.inventory_cleanup import sweep


def adjust(client, ids, row):
    body = dict(expected_version=row['version'], operation_id=str(uuid4()), delta='-1')
    url = inventory(ids)+'/'+row['id']+'/adjustments'
    result = client.post(url, headers=headers(), json=body)
    assert result.status_code == 200, result.text
    return url, body, result.json()


def test_last_object_removed_and_all_original_requests_remain_idempotent(state):
    client, Session, ids = state
    response, creation = add(client, ids)
    row = response.json()
    url, body, result = adjust(client, ids, row)
    assert client.post(url, headers=headers(), json=body).json() == result
    assert products(client, ids) == []
    assert client.get(inventory(ids), headers=headers()).json()['total'] == 0
    assert client.post(inventory(ids), headers=headers(), json=creation).json() == row
    with Session() as db:
        assert db.get(InventoryItem, UUID(row['id'])) is None
        assert db.scalar(select(func.count()).select_from(Product)) == 0
        assert db.scalar(select(func.count()).select_from(ProductBatch)) == 0
        assert all(e.inventory_item_id is None and e.product_id is None for e in db.scalars(select(BusinessEvent)))
        from app.services.ledger import quantity_delta
        event = next(e for e in db.scalars(select(BusinessEvent)) if e.event_type == 'Adjusted')
        assert quantity_delta(event) == '-1'


@pytest.mark.parametrize('action', ['CONSUME', 'DISCARD'])
def test_draft_completion_deletes_last_object_and_replays_receipt(state, monkeypatch, action):
    client, Session, ids = state
    monkeypatch.setenv('MAGICVVU_DISCARD_EXECUTION','true')
    response, _ = add(client, ids)
    row = response.json()
    command = dict(action=action, name='苹果', batch_id=row['id'], expected_version=1, quantity='1', unit='个')
    if action == 'DISCARD': command['discard_mode'] = 'all'
    draft_id = draft(Session, ids, command)
    result, body = commit(client, draft_id)
    assert result.status_code == 200, result.text
    assert commit(client, draft_id, body)[0].json() == result.json()
    assert products(client, ids) == []
    with Session() as db: assert db.get(InventoryItem, UUID(row['id'])) is None
    if action == 'CONSUME':
        history = client.get(inventory(ids).rsplit('/',1)[0]+'/consumption-events', headers=headers()).json()
        assert history['items'][0]['inventory_item_id'] == row['id']


def test_purchase_retry_after_every_object_is_deleted_cannot_restock(state):
    client, Session, ids = state
    shopping = create(client, ids, quantity='2', unit='个', name='苹果')
    url = base(ids)+'/items/'+shopping['id']+'/purchase'
    first = client.post(url, headers=headers(), json={'storage_location':'冰箱'}).json()
    group, = products(client, ids)
    for row in group['inventory_items']: adjust(client, ids, row)
    repeated = client.post(url, headers=headers(), json={'actual_quantity':'99'})
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()['newly_stocked'] is False
    assert repeated.json()['inventory_item']['id'] == first['inventory_item']['id']
    assert products(client, ids) == []
    with Session() as db: assert db.scalar(select(func.count()).select_from(InventoryItem)) == 0


def test_sweep_preserves_active_objects_other_households_and_pending_shopping(state):
    client, Session, ids = state
    ended, _ = add(client, ids)
    active, _ = add(client, ids, name='牛奶')
    foreign, _ = add(client, ids, actor='outsider', home='other_home')
    plan = create(client, ids, name='苹果', unit='个', quantity='2', source_inventory_item_id=ended.json()['id'])
    with Session.begin() as db:
        db.get(InventoryItem, UUID(ended.json()['id'])).status = 'FINISHED'
        db.flush()
        assert sweep(db, ids['home'])['deleted_inventory_items'] == 1
    with Session() as db:
        assert db.get(InventoryItem, UUID(ended.json()['id'])) is None
        assert db.get(InventoryItem, UUID(active.json()['id'])) is not None
        assert db.get(InventoryItem, UUID(foreign.json()['id'])) is not None
        assert db.get(ShoppingListItem, UUID(plan['id'])).source_inventory_item_id is None


def test_cleanup_failure_rolls_back_status_events_and_receipt(state):
    client, Session, ids = state
    response, _ = add(client, ids)
    row = response.json()
    with patch('app.services.inventory_cleanup.remove_ended', side_effect=RuntimeError('injected cleanup failure')):
        result = client.post(inventory(ids)+'/'+row['id']+'/adjustments', headers=headers(),
            json=dict(expected_version=1, operation_id=str(uuid4()), delta='-1'))
    assert result.status_code == 500
    with Session() as db:
        assert db.get(InventoryItem, UUID(row['id'])).status == 'ACTIVE'
        assert db.scalar(select(func.count()).select_from(BusinessEvent)) == 1
