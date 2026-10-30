"""Transaction-local append-only events and permanent CRUD retry receipts."""
import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid5
from functools import wraps
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.product_models import MutationReceipt, ProductBatch
from app.execution_models import BusinessEvent


def retry_conflicts(function):
    """Roll back a losing transaction, then recover through the same scope/hash checks."""
    @wraps(function)
    def guarded(*args, **kwargs):
        db = kwargs['db']
        try:
            return function(*args, **kwargs)
        except IntegrityError:
            db.rollback()
            try:
                return function(*args, **kwargs)
            except IntegrityError:
                db.rollback()
                raise HTTPException(409, {'code': 'MUTATION_CONFLICT'}) from None
    return guarded


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def replay(db, operation_id, home, actor, fingerprint):
    receipt = db.get(MutationReceipt, operation_id)
    if receipt is None:
        return None
    if (receipt.household_id != home or receipt.actor_user_id != actor or receipt.request_hash != fingerprint):
        raise HTTPException(409, {'code': 'OPERATION_ID_CONFLICT'})
    return receipt.response_json


def save(db, operation_id, home, actor, fingerprint, response):
    db.add(MutationReceipt(operation_id=operation_id, household_id=home, actor_user_id=actor,
        request_hash=fingerprint, response_json=response))
    db.flush()


def append(db, item, actor, kind, before, *, request_id=None, operation_id=None,
           event_id=None, related_event_id=None, quantity=None):
    from app.shopping_schemas import StockResponse
    link = db.get(ProductBatch, item.id)
    event = BusinessEvent(id=event_id or uuid5(request_id, 'event'),
        operation_id=operation_id, request_id=request_id, household_id=item.household_id,
        actor_user_id=actor, inventory_item_id=item.id, product_id=link.product_id if link else None,
        event_type=kind, quantity=quantity, unit=item.unit, before_json=before,
        after_json=StockResponse.model_validate(item).model_dump(mode='json'),
        related_event_id=related_event_id, occurred_at=datetime.now(timezone.utc), created_at=datetime.now(timezone.utc))
    db.add(event)
    db.flush()
    return event


def recorded_at(event, operation):
    return operation.committed_at if operation else event.created_at


def valid_origin(db, event, operation, household_id):
    if operation is not None:
        return (operation.household_id == household_id and operation.user_id == event.actor_user_id
                and event.request_id is None)
    receipt = db.get(MutationReceipt, event.request_id) if event.request_id else None
    return (event.operation_id is None and receipt is not None and receipt.household_id == household_id
            and receipt.actor_user_id == event.actor_user_id)


def quantity_delta(event):
    from decimal import Decimal
    if event.shopping_item_id is not None or (event.inventory_item_id is None and not event.after_json.get('id')):
        return None
    before, after = event.before_json, event.after_json
    if before and before.get('unit') != after.get('unit'):
        return None  # Unit edits are not a quantity delta in either unit.
    def count(snapshot):
        if 'quantity' in snapshot:  # Preserve the meaning of historical batch events.
            return Decimal(snapshot['quantity'])
        return Decimal(1) if snapshot.get('status') == 'ACTIVE' else Decimal(0)
    return str(count(after) - count(before))
