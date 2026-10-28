"""One consistent, bounded, read-only view of committed household facts.

Transport completeness is separate from real-world recording completeness.
User attestations are read from the same snapshot as inventory and events.
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
from app.planning_fact_models import InventoryPlanningFacts
from app.services import planning_facts
from app.services import ledger, products
from app.product_models import Product, ProductBatch
from app.services.ai_inventory import to_p1_batch, IncompatibleInventory, UNIT_CANONICAL

ITEM_LIMIT, EVENT_LIMIT, SHOPPING_LIMIT = 1000, 20000, 10000
KINDS = {'StockAdded': 'Added', 'StockMoved': 'Moved', 'Consumed': 'Consumed',
         'Opened': 'Opened', 'Discarded': 'Discarded', 'Created': 'Added', 'Purchased': 'Purchased',
         'Adjusted': 'Adjusted', 'Edited': 'Adjusted', 'Corrected': 'Adjusted', 'ProductLinked': 'Adjusted', 'Archived': 'Adjusted'}


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
    profiles = {p.inventory_item_id: p for p in db.scalars(select(InventoryPlanningFacts)
        .join(InventoryItem).where(InventoryItem.household_id == household_id)).all()}
    ids = {r.id for r in rows}
    catalogue = db.scalars(select(Product).where(Product.household_id == household_id).order_by(Product.id).limit(ITEM_LIMIT+1)).all()
    if len(catalogue) > ITEM_LIMIT:
        raise HTTPException(409, {'code': 'PLANNING_INCOMPLETE', 'message': 'Product snapshot exceeds complete read limits'})
    links = db.scalars(select(ProductBatch).join(InventoryItem).where(InventoryItem.household_id == household_id)).all()
    if any(link.product_id not in {p.id for p in catalogue} for link in links):
        raise IncompatibleInventory('Product association requires reconciliation')
    product_ids = {link.inventory_item_id: str(link.product_id) for link in links}
    grouped = {r.id: [] for r in rows}
    event_sources = {}
    for event, operation in event_rows:
        if (not ledger.valid_origin(db, event, operation, household_id) or
                (event.inventory_item_id is not None and event.inventory_item_id not in ids)):
            raise IncompatibleInventory('Planning event provenance requires reconciliation')
        event_sources[str(event.id)] = {'operation_id': str(event.operation_id) if event.operation_id else None,
            'request_id': str(event.request_id) if event.request_id else None,
            'product_id': str(event.product_id) if event.product_id else None,
            'household_id': str(event.household_id), 'batch_id': str(event.inventory_item_id) if event.inventory_item_id else None,
            'event_type': event.event_type, 'actor_user_id': str(event.actor_user_id),
            'occurred_at': aware(event.occurred_at).isoformat(), 'recorded_at': aware(ledger.recorded_at(event, operation)).isoformat(),
            'quantity': str(event.quantity) if event.quantity is not None else None, 'unit': event.unit,
            'quantity_delta': ledger.quantity_delta(event),
            'related_event_id': str(event.related_event_id) if event.related_event_id else None,
            'relation_support': 'inventory-ledger-1'}
        if event.event_type in KINDS and event.inventory_item_id is not None:
            unit = UNIT_CANONICAL.get(event.unit)
            if unit is None:
                raise IncompatibleInventory('Planning event unit requires reconciliation')
            grouped[event.inventory_item_id].append({'id': str(event.id), 'item_key': str(event.inventory_item_id),
                'kind': KINDS[event.event_type], 'quantity': str(event.quantity if event.quantity is not None else 0),
                'unit': unit, 'occurred_at': aware(event.occurred_at).isoformat(),
                'recorded_at': aware(ledger.recorded_at(event, operation)).isoformat(), 'committed': True,
                'related_event_id': str(event.related_event_id) if event.related_event_id else None})
    # Content tokens, NOT monotonically increasing commit sequences.
    watermark = digest([(e.id, e.event_type, e.quantity, e.unit, e.before_json, e.after_json,
                         e.occurred_at, ledger.recorded_at(e, o), e.related_event_id, e.product_id) for e, o in event_rows])
    shopping_hash = digest([(r.id, r.shopping_list_id, r.name, r.source_inventory_item_id,
        r.quantity, r.unit, r.is_checked, r.checked_at, r.purchased_by_user_id) for r in shopping] +
        [('list', r.id) for r in lists])
    selected = [r for r in rows if (not name or name.casefold() in r.name.casefold()) and (not item_key or str(r.id) == item_key)]
    items, item_sources = [], {}
    for row in selected:
        category = row.category if row.category in {'food', 'medicine', 'household'} else 'unknown'
        batch = {**to_p1_batch(row), 'category': category, 'product_id': product_ids.get(row.id), 'label_date_type': 'unknown',
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
        item_sources[str(row.id)] = {'identity': 'explicit_product_batch' if row.id in product_ids else 'inventory_batch_only',
            'product_id': product_ids.get(row.id),
            'raw_category': row.category, 'minimum_preference': pref_source,
            'preference_version_source': 'inventory_items.version_conservative',
            'recording_completeness': 'unknown', 'stock_verification': 'unknown',
            'known_quantity_adjustments': adjustments, 'adjustment_history_complete': False,
            'reason_codes': ['RECORDING_COMPLETENESS_UNKNOWN', 'NO_COMPLETE_COVERAGE_DAYS', 'STOCK_VERIFICATION_REQUIRED'],
            'missing_sources': ['product_catalogue', 'coverage_attestation', 'stockout_history', 'stock_verification',
                'lead_days', 'coverage_days', 'order_pack', 'label_date_type', 'storage_conditions']}
        if row.id in profiles:
            facts = planning_facts.project(row, profiles[row.id], grouped[row.id])
            current, source = items[-1], item_sources[str(row.id)]
            batch.update(planning_facts.risk_fields(row, facts))
            batch['product_id'] = product_ids.get(row.id)
            current['category'] = batch['category']
            current['preferences']['version'] = row.version + profiles[row.id].version
            current['coverage'] = facts['coverage']
            if facts['coverage']:
                current['recording_completeness_source'] = 'authenticated_household_attestation'
                source['recording_completeness'] = 'user_attested_per_day'
                source['reason_codes'] = [r for r in source['reason_codes']
                    if r not in {'RECORDING_COMPLETENESS_UNKNOWN', 'NO_COMPLETE_COVERAGE_DAYS'}]
                source['missing_sources'] = [r for r in source['missing_sources']
                    if r not in {'coverage_attestation', 'stockout_history'}]
            if facts['preferences'] is not None:
                current['preferences'].update(facts['preferences'])
                source['preference_version_source'] = 'inventory_version_plus_planning_facts_version'
                for key in ('lead_days', 'coverage_days'):
                    if facts['preferences'][key] is not None:
                        source['missing_sources'].remove(key)
                if facts['preferences']['pack_size'] is not None:
                    source['missing_sources'].remove('order_pack')
            verification = facts['stock_verification']
            if verification is not None:
                current['stock_verification'] = {k: verification[k] for k in ('checked_at', 'source')}
                current['usable_quantity_verified'] = True
                source['stock_verification'] = 'explicit_count_matches_inventory_version'
                source['reason_codes'].remove('STOCK_VERIFICATION_REQUIRED')
                source['missing_sources'].remove('stock_verification')
            if facts['risk_facts'] is not None:
                if facts['risk_facts']['label_date_type'] != 'unknown':
                    source['missing_sources'].remove('label_date_type')
                if all(facts['risk_facts'][k] is not None for k in ('storage_condition', 'label_storage_condition')):
                    source['missing_sources'].remove('storage_conditions')
            source['attestations'] = facts['provenance']
            source['invalidated_sections'] = facts['invalidated_sections']
    keys = {i['item_key'] for i in items}
    pending, pending_complete, shopping_sources = [], len(lists) == 1, []
    # Acquisition link proves purchase provenance, not future pending demand.
    # Only explicit source_inventory_item_id associates a shopping request.
    for row in shopping:
        linked = row.source_inventory_item_id in ids
        key = str(row.source_inventory_item_id) if linked else None
        source = next((r for r in rows if r.id == row.source_inventory_item_id), None)
        valid = (linked and row.unit in UNIT_CANONICAL and 0 < row.quantity <= Decimal('1000000000')
                 and products.convert(row.quantity, row.unit, source.unit) is not None)
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
        'recording_completeness': ('user_attested_per_day' if items and all(i['coverage'] for i in items)
            else 'partial_or_unknown' if any(i['coverage'] for i in items) else 'unknown'),
        'automatic_planning_commit': False,
        'items': item_sources, 'events': event_sources, 'shopping': shopping_sources}
    pending_count = sum(not row.is_checked for row in shopping)
    provenance['pending_state'] = ('shopping_list_missing' if len(lists) != 1 else
        'none' if pending_count == 0 else 'linked_complete' if pending_complete else 'association_unknown')
    provenance['pending_count'] = pending_count
    all_projected = {str(r.id): planning_facts.project(r, profiles[r.id], grouped[r.id])
                     for r in rows if r.id in profiles}
    provenance['product_aggregates_v1'] = products.aggregate(catalogue, links, rows, profiles,
        all_projected, datetime.fromisoformat(as_of).astimezone(planning_facts.business_zone()).date())
    provenance['ledger_coverage'] = 'durable_since_p9_plus_existing_draft_events_no_legacy_crud_backfill'
    provenance['risk_rules'] = {'review_status': 'unknown', 'version': None, 'source': 'ai_rule_owner_required'}
    # V1 selection compares this token across name and item_key reads. It must
    # identify household facts, independent of selectors or the capture clock;
    # otherwise unchanged selections loop forever. Every request still executes
    # fresh DB reads and supplies its own DB as_of (never a cached relabel).
    result['snapshot_id'] = digest({'scope': result['scope'],
        'inventory': [[getattr(row, column.name) for column in InventoryItem.__table__.columns] for row in rows],
        'planning_facts': [(str(key), p.version, p.facts_json) for key, p in sorted(profiles.items())],
        'events': event_sources, 'event_watermark': watermark, 'shopping_content': shopping_hash,
        'products': provenance['product_aggregates_v1']})
    provenance['revalidation_basis'] = {'protocol_version': 'planning-revalidation-1',
        'snapshot_id': result['snapshot_id'], 'event_watermark': watermark,
        'shopping_version': result['shopping_version'],
        'inventory_versions': {str(r.id): r.version for r in rows},
        'facts_versions': {str(r.id): profiles[r.id].version if r.id in profiles else 0 for r in rows},
        'product_versions': {str(p.id): p.version for p in catalogue},
        'risk_rules': provenance['risk_rules']}
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
