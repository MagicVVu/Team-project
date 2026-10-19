"""Single-transaction business execution. Caller commits once, or rolls back all.

Lock order: task -> draft -> household membership -> inventory/shared list.
Legacy AI state stays prospective; only this durable ledger proves execution.
"""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid5

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.execution_models import BusinessEvent, DraftDecision, DraftOperation
from app.execution_schemas import AddFields, ConsumeFields, MoveFields, PlanFields, Target
from app.models import AIDraft, AITask, HouseholdMember, InventoryItem, ShoppingList, ShoppingListItem
from app.services.ai_inventory import UNIT_CANONICAL
from app.shopping_schemas import ShoppingItemResponse, StockResponse

EDITABLE = {"ADD": set(AddFields.model_fields), "MOVE": {"to_location"},
            "PLAN_ADD": {"quantity", "unit"}, "CONSUME": {"quantity", "unit"}}
EXECUTION_TTL = timedelta(minutes=15)


def fail(code, status=409):
    raise HTTPException(status, detail={"code": code})


def now():
    return datetime.now(timezone.utc)


def aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def request_hash(draft_id, body):
    value = {"draft_id": str(draft_id), **body.model_dump(mode="json", exclude={"operation_id"})}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def membership(db, user_id, household_id, lock=False):
    query = select(HouseholdMember).where(HouseholdMember.user_id == user_id,
                                          HouseholdMember.household_id == household_id)
    if lock:
        query = query.with_for_update(read=True)
    if db.scalar(query) is None:
        fail("DRAFT_NOT_FOUND", 404)


def owned(db, identity, draft_id, lock=False):
    initial = db.scalar(select(AIDraft).where(AIDraft.id == draft_id, AIDraft.user_id == identity.user.id))
    if initial is None:
        fail("DRAFT_NOT_FOUND", 404)
    task_query = select(AITask).where(AITask.id == initial.task_id, AITask.user_id == identity.user.id)
    draft_query = select(AIDraft).where(AIDraft.id == draft_id, AIDraft.user_id == identity.user.id)
    if lock:
        task_query = task_query.with_for_update().execution_options(populate_existing=True)
        draft_query = draft_query.with_for_update().execution_options(populate_existing=True)
    task, draft = db.scalar(task_query), db.scalar(draft_query)
    if task is None or draft is None or task.household_id != draft.household_id:
        fail("DRAFT_NOT_FOUND", 404)
    membership(db, identity.user.id, draft.household_id, lock)
    return task, draft


def expiry(task, draft):
    limits = [aware(task.updated_at) + EXECUTION_TTL, aware(draft.updated_at) + EXECUTION_TTL]
    if task.expires_at:
        limits.append(aware(task.expires_at))
    return min(limits)


def revision(task, draft, body):
    if body.draft_revision != draft.revision or body.task_revision != task.revision:
        fail("DRAFT_REVISION_CONFLICT")


def pending(task, draft):
    if task.status != "needs_confirmation" or draft.status != "pending":
        fail("DRAFT_NOT_PENDING")
    if not isinstance(task.result_json, dict) or task.result_json.get("status") != "needs_confirmation":
        fail("TASK_RESULT_INCONSISTENT")
    if task.result_json.get("draft") != draft.command_json:
        fail("DRAFT_SOURCE_CHANGED")


def execution_status(db, identity, draft_id):
    task, draft = owned(db, identity, draft_id)
    decision = db.get(DraftDecision, draft_id)
    action = draft.command_json.get("action") if isinstance(draft.command_json, dict) else None
    reason = None
    if decision:
        status = decision.status
    elif task.status != "needs_confirmation" or draft.status != "pending":
        status, reason = "superseded", "DRAFT_NOT_PENDING"
    elif expiry(task, draft) <= now():
        status, reason = "expired", "DRAFT_EXPIRED"
    elif action not in EDITABLE:
        status, reason = "unavailable", "ACTION_NOT_EXECUTABLE"
    elif action == "PLAN_ADD" and automated_plan(task):
        status, reason = "unavailable", "PLANNING_REVALIDATION_UNAVAILABLE"
    else:
        status = "pending"
    receipt = db.get(DraftOperation, decision.operation_id).receipt_json if decision and decision.operation_id else None
    return {"draft_id": str(draft.id), "task_id": str(task.id), "status": status,
            "draft_revision": draft.revision, "task_revision": task.revision, "action": action,
            "editable_fields": sorted(EDITABLE.get(action, set())), "reason_code": reason,
            "expires_at": expiry(task, draft).isoformat(),
            "operation_id": str(decision.operation_id) if decision and decision.operation_id else None,
            "receipt": receipt}


def operation_for(db, identity, operation_id):
    operation = db.scalar(select(DraftOperation).where(DraftOperation.id == operation_id,
                                                      DraftOperation.user_id == identity.user.id))
    if operation is None:
        fail("OPERATION_NOT_FOUND", 404)
    membership(db, identity.user.id, operation.household_id)
    return operation


def recover(db, identity, draft_id, body):
    existing = db.get(DraftOperation, body.operation_id)
    if existing is None:
        return None
    if (existing.user_id != identity.user.id or existing.draft_id != draft_id
            or existing.request_hash != request_hash(draft_id, body)):
        fail("OPERATION_ID_CONFLICT")
    membership(db, identity.user.id, existing.household_id, lock=True)
    return existing.receipt_json


def automated_plan(task):
    result = task.result_json or {}
    return bool(result.get("planning_basis") or result.get("quantity_source") == "planning_calculation"
                or result.get("intent") == "SUGGEST_PURCHASE")


def unit(value):
    canonical = UNIT_CANONICAL.get(value)
    if canonical is None:
        fail("UNIT_UNSUPPORTED", 422)
    return canonical


def converted(quantity, source_unit, target_unit):
    source, target = unit(source_unit), unit(target_unit)
    factors = {"ml": ("volume", Decimal(1)), "L": ("volume", Decimal(1000)),
               "g": ("mass", Decimal(1)), "kg": ("mass", Decimal(1000)),
               "吨": ("mass", Decimal(1000000))}
    if source == target:
        return quantity
    if source not in factors or target not in factors or factors[source][0] != factors[target][0]:
        fail("UNIT_MISMATCH", 422)
    result = quantity * factors[source][1] / factors[target][1]
    # Never silently round a conversion below the inventory's six-place precision.
    if result <= 0 or result > Decimal("1000000000") or result.normalize().as_tuple().exponent < -6:
        fail("CONVERTED_QUANTITY_INVALID", 422)
    return result


def command(task, draft, edits):
    if not isinstance(draft.command_json, dict):
        fail("INVALID_DRAFT_FIELDS", 422)
    raw = dict(draft.command_json)
    action = raw.pop("action", None)
    if action not in EDITABLE:
        fail("ACTION_NOT_EXECUTABLE")
    if not set(edits).issubset(EDITABLE[action]):
        fail("PROTECTED_OR_UNKNOWN_FIELD", 422)
    if action == "PLAN_ADD" and automated_plan(task):
        fail("PLANNING_REVALIDATION_UNAVAILABLE")
    target = None
    try:
        if action in {"MOVE", "CONSUME"}:
            target = Target.model_validate({k: raw.pop(k) for k in ("name", "batch_id", "expected_version")})
        if action == "PLAN_ADD":
            # Name and any identity/provenance always come from the stored draft.
            from app.execution_schemas import Name
            from pydantic import TypeAdapter
            name = TypeAdapter(Name).validate_python(raw.pop("name"))
        values = {**raw, **edits}
        schema = {"ADD": AddFields, "MOVE": MoveFields, "CONSUME": ConsumeFields, "PLAN_ADD": PlanFields}[action]
        fields = schema.model_validate(values)
        if action == "PLAN_ADD":
            # Quantity is user-editable, but changing a package into a mass is not.
            converted(Decimal(1), fields.unit, raw["unit"])
            normalized = {"action": action, "name": name, **fields.model_dump(mode="json")}
        else:
            normalized = {"action": action, **(target.model_dump(mode="json") if target else {}),
                          **fields.model_dump(mode="json")}
        if hasattr(fields, "unit"):
            normalized["unit"] = unit(fields.unit)
        return action, target, fields, normalized
    except (ValidationError, KeyError, TypeError, ValueError):
        fail("INVALID_DRAFT_FIELDS", 422)


def persist_event(db, **values):
    db.add(BusinessEvent(**values))
    db.flush()


def execute(db, identity, draft_id, body):
    task, draft = owned(db, identity, draft_id, lock=True)
    prior = recover(db, identity, draft_id, body)
    if prior is not None:
        return prior
    revision(task, draft, body)
    if db.get(DraftDecision, draft_id) is not None:
        fail("DRAFT_ALREADY_DECIDED")
    pending(task, draft)
    if expiry(task, draft) <= now():
        fail("DRAFT_EXPIRED")
    action, target, fields, normalized = command(task, draft, body.edits)
    at = now()
    event_id = uuid5(body.operation_id, "event")
    before, batch_versions, item, shopping = {}, {}, None, None
    quantity, event_type = None, {"ADD": "StockAdded", "MOVE": "StockMoved", "PLAN_ADD": "PlanAdded", "CONSUME": "Consumed"}[action]
    if action == "ADD":
        item = InventoryItem(id=uuid5(body.operation_id, "inventory"), household_id=draft.household_id,
            created_by_user_id=identity.user.id, name=fields.name, quantity=fields.quantity,
            unit=unit(fields.unit), storage_location=fields.location, purchased_on=fields.purchased_at,
            expires_on=fields.label_expiry, category="其他", minimum_quantity=0,
            status="ACTIVE", version=1, history_json=[])
        db.add(item)
        quantity = fields.quantity
    elif action in {"MOVE", "CONSUME"}:
        item = db.scalar(select(InventoryItem).where(InventoryItem.id == target.batch_id,
            InventoryItem.household_id == draft.household_id).with_for_update().execution_options(populate_existing=True))
        if item is None:
            fail("INVENTORY_NOT_FOUND", 404)
        if item.status != "ACTIVE" or item.quantity <= 0:
            fail("INVENTORY_NOT_ACTIVE")
        if item.version != target.expected_version:
            fail("INVENTORY_VERSION_CONFLICT")
        if item.name != target.name:
            fail("INVENTORY_IDENTITY_CHANGED")
        before = StockResponse.model_validate(item).model_dump(mode="json")
        if action == "MOVE":
            item.storage_location = fields.to_location
        else:
            quantity = converted(fields.quantity, fields.unit, item.unit)
            if quantity > item.quantity:
                fail("INSUFFICIENT_STOCK", 422)
            item.quantity -= quantity
            item.status = "ACTIVE" if item.quantity > 0 else "FINISHED"
        item.version += 1
    else:
        shared = db.scalar(select(ShoppingList).where(ShoppingList.household_id == draft.household_id).with_for_update())
        if shared is None:
            fail("SHOPPING_LIST_MISSING")
        # Lock/re-read current pending items. Automatic recommendations remain disabled.
        db.scalars(select(ShoppingListItem).where(ShoppingListItem.shopping_list_id == shared.id,
            ShoppingListItem.is_checked.is_(False)).with_for_update()).all()
        shopping = ShoppingListItem(id=uuid5(body.operation_id, "shopping"), shopping_list_id=shared.id,
            added_by_user_id=identity.user.id, name=normalized["name"], quantity=fields.quantity,
            unit=unit(fields.unit), is_checked=False)
        quantity = fields.quantity
        db.add(shopping)
    if item is not None:
        item.history_json = ([{"id": str(body.operation_id), "event_id": str(event_id),
                              "kind": event_type, "created_at": at.isoformat()}] + (item.history_json or []))[:30]
    db.flush()
    after = (StockResponse.model_validate(item) if item is not None else ShoppingItemResponse.model_validate(shopping)).model_dump(mode="json")
    if item is not None:
        batch_versions[str(item.id)] = item.version
    receipt = {"protocol_version": "draft-operation-receipt-1", "operation_id": str(body.operation_id),
        "draft_id": str(draft.id), "task_id": str(task.id), "draft_revision": draft.revision,
        "task_revision": task.revision, "scope": {"user_id": str(identity.user.id), "household_id": str(draft.household_id)},
        "status": "committed", "action": action, "committed_at": at.isoformat(),
        "trace_id": "op_" + body.operation_id.hex, "batch_versions": batch_versions,
        "event_ids": [str(event_id)], "inventory_written": item is not None,
        "shopping_written": shopping is not None,
        "result": {"inventory_item" if item is not None else "shopping_item": after}}
    db.add(DraftOperation(id=body.operation_id, draft_id=draft.id, user_id=identity.user.id,
        household_id=draft.household_id, draft_revision=draft.revision, task_revision=task.revision,
        action=action, request_hash=request_hash(draft_id, body), command_json=normalized,
        receipt_json=receipt, committed_at=at))
    db.flush()
    persist_event(db, id=event_id, operation_id=body.operation_id, household_id=draft.household_id,
        actor_user_id=identity.user.id, inventory_item_id=item.id if item is not None else None,
        shopping_item_id=shopping.id if shopping is not None else None, event_type=event_type,
        quantity=quantity, unit=item.unit if item is not None else shopping.unit,
        before_json=before, after_json=after, occurred_at=at)
    db.add(DraftDecision(draft_id=draft.id, draft_revision=draft.revision, task_revision=task.revision,
                         status="committed", operation_id=body.operation_id, decided_at=at))
    db.flush()
    return receipt


def cancel(db, identity, draft_id, body):
    task, draft = owned(db, identity, draft_id, lock=True)
    revision(task, draft, body)
    prior = db.get(DraftDecision, draft_id)
    if prior:
        if prior.status != "cancelled":
            fail("DRAFT_ALREADY_COMMITTED")
        return {"draft_id": str(draft.id), "status": "cancelled"}
    pending(task, draft)
    db.add(DraftDecision(draft_id=draft.id, draft_revision=draft.revision, task_revision=task.revision,
                         status="cancelled", operation_id=None, decided_at=now()))
    db.flush()
    return {"draft_id": str(draft.id), "status": "cancelled"}
