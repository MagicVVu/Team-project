"""Read actual ledger facts without inferring missing consumption or product links.

Current inventory has batch identities, not a product catalogue. Each item_key is
therefore the real batch ID. Unmapped pending rows are explicitly incomplete.
"""
import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

<<<<<<< Updated upstream
from app.execution_models import BusinessEvent, DraftOperation
=======
from app.execution_models import BusinessEvent
>>>>>>> Stashed changes
from app.models import InventoryItem, ShoppingListItem, ShoppingList, HouseholdMember
from app.services.ai_inventory import to_p1_batch, IncompatibleInventory


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def read_snapshot(db, user_id, household_id, name=None, item_key=None):
    if db.get(HouseholdMember, (household_id, user_id)) is None:
        raise HTTPException(404, 'Planning scope not found')
    rows = db.scalars(select(InventoryItem).where(InventoryItem.household_id == household_id)
        .order_by(InventoryItem.id).limit(1001)).all()
    events = db.scalars(select(BusinessEvent).where(BusinessEvent.household_id == household_id)
        .order_by(BusinessEvent.occurred_at, BusinessEvent.id).limit(20001)).all()
    shopping = db.scalars(select(ShoppingListItem).join(ShoppingList).where(ShoppingList.household_id == household_id)
        .order_by(ShoppingListItem.id).limit(10001)).all()
    if len(rows) > 1000 or len(events) > 20000 or len(shopping) > 10000:
        raise HTTPException(409, 'Planning snapshot exceeds complete read limits')
    # Hash all current pending/purchased rows; successful query does not establish recording completeness.
    shopping_hash = digest([(r.id, r.name, r.quantity, r.unit, r.is_checked) for r in shopping])
    watermark = digest([(r.id, r.event_type, r.quantity, r.unit, r.before_json, r.after_json, r.occurred_at) for r in events])
    kinds = {'StockAdded': 'Added', 'StockMoved': 'Moved', 'Consumed': 'Consumed', 'Opened': 'Opened', 'Discarded': 'Discarded'}
    selected = [r for r in rows if (not name or name.casefold() in r.name.casefold()) and (not item_key or str(r.id) == item_key)]
    items = []
    try:
        for row in selected:
            batch = {**to_p1_batch(row), 'category': 'unknown'}
            item_events = []
            for event in events:
                if event.inventory_item_id != row.id or event.event_type not in kinds:
                    continue
                at = event.occurred_at
                if at.tzinfo is None: at = at.replace(tzinfo=timezone.utc)
<<<<<<< Updated upstream
                recorded = db.get(DraftOperation, event.operation_id).committed_at
                if recorded.tzinfo is None: recorded = recorded.replace(tzinfo=timezone.utc)
                item_events.append({'id': str(event.id), 'item_key': str(row.id), 'kind': kinds[event.event_type],
                    'quantity': str(event.quantity or 0), 'unit': event.unit, 'occurred_at': at.isoformat(),
                    'recorded_at': recorded.isoformat(), 'committed': True, 'related_event_id': None})
            items.append({'item_key': str(row.id), 'name': row.name, 'unit': batch['unit'], 'version': row.version,
                'category': 'unknown', 'batches': [batch], 'events': item_events,
                'coverage': [], 'recording_completeness_source': None,
                'preferences': {'version': row.version, 'minimum_stock': str(row.minimum_quantity) if row.minimum_quantity > 0 else None,
=======
                item_events.append({'id': str(event.id), 'item_key': str(row.id), 'kind': kinds[event.event_type],
                    'quantity': str(event.quantity or 0), 'unit': event.unit, 'occurred_at': at.isoformat(),
                    'recorded_at': at.isoformat(), 'committed': True, 'related_event_id': None})
            items.append({'item_key': str(row.id), 'name': row.name, 'unit': batch['unit'], 'version': row.version,
                'category': 'unknown', 'batches': [batch], 'events': item_events,
                'coverage': [], 'recording_completeness_source': None,
                'preferences': {'version': row.version, 'minimum_stock': str(row.minimum_quantity),
>>>>>>> Stashed changes
                    'coverage_days': None, 'lead_days': None, 'order_unit': None, 'pack_size': None},
                'usable_quantity_verified': False, 'stock_verification': None})
    except IncompatibleInventory as error:
        raise HTTPException(409, str(error)) from None
    keys = {i['item_key'] for i in items}
    pending, pending_complete = [], True
    links = {r.source_shopping_list_item_id: str(r.id) for r in rows if r.source_shopping_list_item_id}
    for row in shopping:
        if row.is_checked: continue
        key = links.get(row.id)
        if key is None:
            pending_complete = False  # Never bind pending purchases to stock by matching text names.
        elif key in keys:
            pending.append({'id': str(row.id), 'item_key': key, 'quantity': str(row.quantity),
                'unit': row.unit, 'status': 'pending', 'confirmed': True, 'visibility': 'shared'})
    snapshot = {'protocol_version': 'v1-planning-context-1',
        'scope': {'user_id': str(user_id), 'household_id': str(household_id)},
        'event_watermark': watermark, 'shopping_version': int(shopping_hash[:15], 16) + 1,
        'items_complete': True, 'history_complete': True, 'pending_complete': pending_complete,
        'next_cursor': None, 'items': items, 'pending': pending}
    snapshot['snapshot_id'] = digest(snapshot)
    snapshot['as_of'] = datetime.now(timezone.utc).isoformat()
    return snapshot


def snapshot(db, user_id, household_id, name=None, item_key=None):
    if db.bind.dialect.name != 'postgresql':
        return read_snapshot(db, user_id, household_id, name, item_key)
    # Authentication has already queried the request session. Use a separate
    # read-only repeatable-read transaction and recheck membership inside it.
    engine = db.get_bind().execution_options(isolation_level='REPEATABLE READ', postgresql_readonly=True)
    with Session(engine) as reader:
        return read_snapshot(reader, user_id, household_id, name, item_key)
