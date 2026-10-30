"""Intake dates survive expansion, replay and metadata edits."""
from datetime import date, datetime, timezone
from uuid import uuid4

import pytest

from test_physical_inventory import state, inventory, products
from test_v07_shopping import headers
from app.services import physical_inventory


@pytest.mark.parametrize('supplied', ['2026-10-29', None, 'omitted'])
def test_create_dates_all_objects_and_keeps_replay_stable(state, monkeypatch, supplied):
    client, Session, ids = state
    monkeypatch.setattr(physical_inventory, 'intake_date', lambda: date(2026, 10, 30))
    body = dict(id=str(uuid4()), name='入库日期苹果', quantity=3, storage_location='冰箱')
    if supplied != 'omitted':
        body['purchased_on'] = supplied
    expected = supplied if supplied not in (None, 'omitted') else '2026-10-30'
    response = client.post(inventory(ids), headers=headers(), json=body)
    assert response.status_code == 201, response.text
    assert response.json()['purchased_on'] == expected
    group, = products(client, ids)
    assert group['count'] == 3
    assert all(row['purchased_on'] == expected for row in group['inventory_items'])
    from app.models import InventoryItem
    from sqlalchemy import select
    with Session() as db:
        assert [row.purchased_on.isoformat() for row in db.scalars(select(InventoryItem))] == [expected] * 3
    monkeypatch.setattr(physical_inventory, 'intake_date', lambda: date(2026, 10, 31))
    assert client.post(inventory(ids), headers=headers(), json=body).json() == response.json()
    edited = client.patch(inventory(ids) + '/' + body['id'], headers=headers(), json={
        'expected_version': 1, 'operation_id': str(uuid4()), 'specification': '编辑不改变入库日期'})
    assert edited.status_code == 200, edited.text
    assert edited.json()['purchased_on'] == expected
    assert client.get(inventory(ids) + '/' + body['id'], headers=headers()).json()['purchased_on'] == expected


def test_legacy_fallback_uses_shanghai_day_at_utc_boundary(monkeypatch):
    class Clock:
        @staticmethod
        def now(tz):
            return datetime(2026, 10, 29, 17, 5, tzinfo=timezone.utc)
    monkeypatch.setattr(physical_inventory, 'datetime', Clock)
    assert physical_inventory.intake_date() == date(2026, 10, 30)
