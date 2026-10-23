"""One consistent, bounded, read-only view of committed household facts.

Transport completeness is separate from real-world recording completeness.
There is no durable coverage/stock-verification writer in this application.
"""
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.execution_models import BusinessEvent, DraftOperation
from app.models import InventoryItem, ShoppingListItem, ShoppingList, HouseholdMember, User
from app.services.ai_inventory import to_p1_batch, IncompatibleInventory, UNIT_CANONICAL

ITEM_LIMIT, EVENT_LIMIT, SHOPPING_LIMIT = 1000, 20000, 10000
KINDS = {'StockAdded': 'Added', 'StockMoved': 'Moved', 'Consumed': 'Consumed',
         'Opened': 'Opened', 'Discarded': 'Discarded'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def minimum_fact(row):
    # A legacy positive value cannot come from the zero database default.
    # Zero needs structured evidence from the authenticated CRUD writer.
    for entry in row.history_json or []:
        fact = entry.get('minimum_preference') if isinstance(entry, dict) else None
        if isinstance(fact, dict) and fact.get('source') == 'authenticated_inventory_input':
            try:
                matches = Decimal(fact.get('quantity', 'NaN')) == row.minimum_quantity and fact.get('unit') == row.unit
            except (InvalidOperation, ValueError, TypeError):
                matches = False
            if matches and fact.get('actor_user_id') and fact.get('recorded_at'):
                return str(row.minimum_quantity), {**fact, 'retention': 'last_30_inventory_history_entries'}
        if fact:
            break  # Never resurrect a superseded explicit preference.
    if row.minimum_quantity > 0:
        return str(row.minimum_quantity), {'source': 'inventory_items.minimum_quantity', 'explicit_actor_time': None}
    return None, None


def read_snapshot(db, user_id, household_id, name=None, item_key=None, *, with_provenance=False):
    # First SELECT in the dedicated transaction acquires the PostgreSQL MVCC
    # snapshot and reads database time; no client time is accepted.
    pg = db.bind.dialect.name == 'postgresql'
    clock = func.clock_timestamp() if pg else func.strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')
    scope = db.execute(select(HouseholdMember.user_id, clock).join(User).where(
        HouseholdMember.household_id == household_id, HouseholdMember.user_id == user_id,
        User.is_active.is_(True))).first()
    if scope is None:
        raise HTTPException(404, 'Planning scope not found')
    as_of = aware(scope[1] if isinstance(scope[1], datetime) else datetime.fromisoformat(scope[1])).isoformat()
    rows = db.scalars(select(InventoryItem).where(InventoryItem.household_id == household_id)
        .order_by(InventoryItem.id).limit(ITEM_LIMIT + 1)).all()
    # Outer join detects broken or cross-scope provenance instead of hiding it.
    event_rows = db.execute(select(BusinessEvent, DraftOperation).outerjoin(DraftOperation,
        BusinessEvent.operation_id == DraftOperation.id).where(BusinessEvent.household_id == household_id)
        .order_by(BusinessEvent.occurred_at, BusinessEvent.id).limit(EVENT_LIMIT + 1)).all()
    lists = db.scalars(select(ShoppingList).where(ShoppingList.household_id == household_id)).all()
    shopping = db.scalars(select(ShoppingListItem).join(ShoppingList).where(ShoppingList.household_id == household_id)
        .order_by(ShoppingListItem.id).limit(SHOPPING_LIMIT + 1)).all()
    if len(rows) > ITEM_LIMIT or len(event_rows) > EVENT_LIMIT or len(shopping) > SHOPPING_LIMIT:
        raise HTTPException(409, {'code': 'PLANNING_INCOMPLETE', 'message': 'Planning snapshot exceeds complete read limits'})
    ids = {r.id for r in rows}
    grouped = {r.id: [] for r in rows}
    event_sources = {}
    for event, operation in event_rows:
        if (operation is None or operation.household_id != household_id or
                (event.inventory_item_id is not None and event.inventory_item_id not in ids)):
            raise IncompatibleInventory('Planning event provenance requires reconciliation')
        event_sources[str(event.id)] = {'operation_id': str(event.operation_id),
            'household_id': str(event.household_id), 'batch_id': str(event.inventory_item_id) if event.inventory_item_id else None,
            'event_type': event.event_type, 'actor_user_id': str(event.actor_user_id),
            'occurred_at': aware(event.occurred_at).isoformat(), 'recorded_at': aware(operation.committed_at).isoformat(),
            'quantity': str(event.quantity) if event.quantity is not None else None, 'unit': event.unit,
            'related_event_id': None, 'relation_support': 'not_supported_by_current_business_ledger'}
        if event.event_type in KINDS and event.inventory_item_id is not None:
            unit = UNIT_CANONICAL.get(event.unit)
            if unit is None:
                raise IncompatibleInventory('Planning event unit requires reconciliation')
            grouped[event.inventory_item_id].append({'id': str(event.id), 'item_key': str(event.inventory_item_id),
                'kind': KINDS[event.event_type], 'quantity': str(event.quantity if event.quantity is not None else 0),
                'unit': unit, 'occurred_at': aware(event.occurred_at).isoformat(),
                'recorded_at': aware(operation.committed_at).isoformat(), 'committed': True, 'related_event_id': None})
    # Content tokens, NOT monotonically increasing commit sequences.
    watermark = digest([(e.id, e.event_type, e.quantity, e.unit, e.before_json, e.after_json,
                         e.occurred_at, o.committed_at) for e, o in event_rows])
    shopping_hash = digest([(r.id, r.shopping_list_id, r.name, r.source_inventory_item_id,
        r.quantity, r.unit, r.is_checked, r.checked_at, r.purchased_by_user_id) for r in shopping] +
        [('list', r.id) for r in lists])
    selected = [r for r in rows if (not name or name.casefold() in r.name.casefold()) and (not item_key or str(r.id) == item_key)]
    items, item_sources = [], {}
    for row in selected:
        category = row.category if row.category in {'food', 'medicine', 'household'} else 'unknown'
        batch = {**to_p1_batch(row), 'category': category, 'product_id': None, 'label_date_type': 'unknown',
            'label_context_valid': None, 'storage_condition': None, 'label_storage_condition': None,
            'is_opened': True if row.opened_at is not None else None}
        minimum, pref_source = minimum_fact(row)
        items.append({'item_key': str(row.id), 'name': row.name, 'unit': batch['unit'], 'version': row.version,
            'category': category, 'batches': [batch], 'events': grouped[row.id], 'coverage': [],
            'recording_completeness_source': None,
            'preferences': {'version': row.version, 'minimum_stock': minimum, 'coverage_days': None,
                'lead_days': None, 'order_unit': None, 'pack_size': None},
            'usable_quantity_verified': False, 'stock_verification': None})
        adjustments = [e for e in row.history_json or [] if isinstance(e, dict) and e.get('kind') in {'adjust', 'edit_quantity'}]
        item_sources[str(row.id)] = {'identity': 'inventory_batch_only', 'product_id': None,
            'raw_category': row.category, 'minimum_preference': pref_source,
            'preference_version_source': 'inventory_items.version_conservative',
            'recording_completeness': 'unknown', 'stock_verification': 'unknown',
            'known_quantity_adjustments': adjustments, 'adjustment_history_complete': False,
            'reason_codes': ['RECORDING_COMPLETENESS_UNKNOWN', 'NO_COMPLETE_COVERAGE_DAYS', 'STOCK_VERIFICATION_REQUIRED'],
            'missing_sources': ['product_catalogue', 'coverage_attestation', 'stockout_history', 'stock_verification',
                'lead_days', 'coverage_days', 'order_pack', 'label_date_type', 'storage_conditions']}
    keys = {i['item_key'] for i in items}
    pending, pending_complete, shopping_sources = [], len(lists) == 1, []
    # Acquisition link proves purchase provenance, not future pending demand.
    # Only explicit source_inventory_item_id associates a shopping request.
    for row in shopping:
        linked = row.source_inventory_item_id in ids
        key = str(row.source_inventory_item_id) if linked else None
        valid = linked and row.unit in UNIT_CANONICAL and 0 < row.quantity <= Decimal('1000000000')
        shopping_sources.append({'id': str(row.id), 'item_key': key, 'source_inventory_item_id':
            str(row.source_inventory_item_id) if linked else None, 'name': row.name,
            'quantity': str(row.quantity), 'unit': row.unit, 'confirmed': True,
            'status': 'purchased' if row.is_checked else 'pending',
            'association': 'explicit_batch_fk' if linked else 'unknown', 'version': digest(
                (row.id, row.name, row.source_inventory_item_id, row.quantity, row.unit, row.is_checked, row.checked_at))})
        if not row.is_checked and not valid:
            pending_complete = False
        if valid and key in keys:
            pending.append({'id': str(row.id), 'item_key': key, 'quantity': str(row.quantity),
                'unit': UNIT_CANONICAL[row.unit], 'status': 'purchased' if row.is_checked else 'pending',
                'confirmed': True, 'visibility': 'shared'})
    result = {'protocol_version': 'v1-planning-context-1',
        'scope': {'user_id': str(user_id), 'household_id': str(household_id)}, 'as_of': as_of,
        'event_watermark': watermark, 'shopping_version': int(shopping_hash[:15], 16) + 1,
        'items_complete': True, 'history_complete': True, 'pending_complete': pending_complete,
        'next_cursor': None, 'items': items, 'pending': pending}
    provenance = {'schema_version': 'backend-planning-provenance-1',
        'isolation': 'postgresql_repeatable_read_read_only' if pg else 'sqlite_explicit_read_transaction',
        'history_complete_means': 'all_existing_semantic_ledger_rows_read_not_real_world_coverage',
        'event_watermark_kind': 'sha256_visible_ledger_content_not_commit_sequence',
        'shopping_version_kind': 'content_digest_60_bits_not_monotonic',
        'database_rows_complete': True, 'shopping_list_present': len(lists) == 1,
        'recording_completeness': 'unknown', 'automatic_planning_commit': False,
        'items': item_sources, 'events': event_sources, 'shopping': shopping_sources}
    # V1 selection compares this token across name and item_key reads. It must
    # identify household facts, independent of selectors or the capture clock;
    # otherwise unchanged selections loop forever. Every request still executes
    # fresh DB reads and supplies its own DB as_of (never a cached relabel).
    result['snapshot_id'] = digest({'scope': result['scope'],
        'inventory': [[getattr(row, column.name) for column in InventoryItem.__table__.columns] for row in rows],
        'events': event_sources, 'event_watermark': watermark, 'shopping_content': shopping_hash})
    return {'data': result, 'provenance': provenance} if with_provenance else result


def snapshot(db, user_id, household_id, name=None, item_key=None, *, with_provenance=False):
    bind = db.get_bind()
    if bind.dialect.name == 'postgresql':
        bind = bind.execution_options(isolation_level='REPEATABLE READ', postgresql_readonly=True)
    elif bind.dialect.name != 'sqlite':
        raise HTTPException(503, {'code': 'PLANNING_CONTEXT_UNAVAILABLE', 'message': 'Unsupported snapshot isolation'})
    try:
        # Use neither the authentication transaction nor its identity map.
        # SQLite SELECT requires explicit BEGIN in Python legacy transaction mode.
        with bind.connect() as connection:
            if bind.dialect.name == 'sqlite':
                connection.exec_driver_sql('BEGIN')
            with Session(connection, autoflush=False) as reader:
                return read_snapshot(reader, user_id, household_id, name, item_key, with_provenance=with_provenance)
    except IncompatibleInventory as error:
        raise HTTPException(409, {'code': 'PLANNING_CONTRACT_INVALID', 'message': str(error)}) from None
    except SQLAlchemyError:
        raise HTTPException(503, {'code': 'PLANNING_CONTEXT_UNAVAILABLE', 'message': 'Planning read failed; no partial snapshot'}) from None
