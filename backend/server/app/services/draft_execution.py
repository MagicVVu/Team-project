"""Single-transaction business execution. Caller commits once, or rolls back all.

Lock order: task -> draft -> household membership -> inventory/shared list.
Legacy AI state stays prospective; only this durable ledger proves execution.
"""
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.execution_models import BusinessEvent, DraftDecision, DraftOperation
from app.execution_schemas import AddFields, ConsumeFields, MoveFields, PlanFields, Target, OpenFields, DiscardFields
from app.models import AIDraft, AITask, HouseholdMember, InventoryItem, ShoppingList, ShoppingListItem
from app.services.ai_inventory import UNIT_CANONICAL
from app.shopping_schemas import ShoppingItemResponse, StockResponse

EDITABLE = {"ADD": set(AddFields.model_fields), "MOVE": {"to_location"},
            "PLAN_ADD": {"quantity", "unit"}, "CONSUME": set(),
            "OPEN": {"opened_at"}, "DISCARD": set()}
EXECUTION_TTL = timedelta(minutes=15)


def action_enabled(action):
    if action in {"OPEN", "DISCARD"}:
        return os.getenv(f"MAGICVVU_{action}_EXECUTION", "false").lower() == "true"
    return action in EDITABLE


def editable(action, raw, task=None):
    if action == "CONSUME" and task is not None and (task.result_json or {}).get("consume_mode") == "all":
        return set()
    if action == "DISCARD" and isinstance(raw, dict) and raw.get("discard_mode") == "all":
        return set()
    return EDITABLE.get(action, set())


def business_day(task, at=None):
    try:
        return (at or now()).astimezone(ZoneInfo(task.household_timezone)).date()
    except (ZoneInfoNotFoundError, ValueError):
        fail("TASK_TIMEZONE_INVALID")


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
    if task.result_json.get("reference_used") and task.expires_at is None:
        fail("REFERENCE_EXPIRY_UNAVAILABLE")


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
    elif not action_enabled(action):
        status, reason = "unavailable", "ACTION_NOT_EXECUTABLE"
    elif action == "PLAN_ADD" and automated_plan(task):
        status, reason = "unavailable", "PLANNING_REVALIDATION_UNAVAILABLE"
    else:
        status = "pending"
    receipt = db.get(DraftOperation, decision.operation_id).receipt_json if decision and decision.operation_id else None
    return {"draft_id": str(draft.id), "task_id": str(task.id), "status": status,
            "draft_revision": draft.revision, "task_revision": task.revision, "action": action,
            "editable_fields": sorted(editable(action, draft.command_json, task)), "reason_code": reason,
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
    if not action_enabled(action):
        fail("ACTION_NOT_EXECUTABLE")
    if not set(edits).issubset(editable(action, draft.command_json, task)):
        fail("PROTECTED_OR_UNKNOWN_FIELD", 422)
    if action == "PLAN_ADD" and automated_plan(task):
        fail("PLANNING_REVALIDATION_UNAVAILABLE")
    target = None
    try:
        if action in {"MOVE", "CONSUME", "OPEN", "DISCARD"}:
            target = Target.model_validate({k: raw.pop(k) for k in ("name", "batch_id", "expected_version")})
        if action == "PLAN_ADD":
            # Name and any identity/provenance always come from the stored draft.
            from app.execution_schemas import Name
            from pydantic import TypeAdapter
            name = TypeAdapter(Name).validate_python(raw.pop("name"))
        values = {**raw, **edits}
        if action == "OPEN" and edits.get("opened_at") in {"今天", "昨天"}:
            values["opened_at"] = business_day(task, aware(task.created_at)) - timedelta(days=edits["opened_at"] == "昨天")
        schema = {"ADD": AddFields, "MOVE": MoveFields, "CONSUME": ConsumeFields,
                  "PLAN_ADD": PlanFields, "OPEN": OpenFields, "DISCARD": DiscardFields}[action]
        fields = schema.model_validate(values)
        if action == "OPEN" and fields.opened_at > business_day(task):
            fail("OPEN_DATE_IN_FUTURE", 422)
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
    from app.product_models import ProductBatch
    if values.get('inventory_item_id'):
        link = db.get(ProductBatch, values['inventory_item_id'])
        values['product_id'] = link.product_id if link else None
    values['created_at'] = now()
    db.add(BusinessEvent(**values))
    db.flush()


def target_item(db, household_id, target, lock=False):
    query = select(InventoryItem).where(InventoryItem.id == target.batch_id,
        InventoryItem.household_id == household_id).execution_options(populate_existing=True)
    if lock:
        query = query.with_for_update()
    item = db.scalar(query)
    if item is None:
        fail("INVENTORY_NOT_FOUND", 404)
    if item.status != "ACTIVE" or item.quantity <= 0:
        fail("INVENTORY_NOT_ACTIVE")
    if item.version != target.expected_version:
        fail("INVENTORY_VERSION_CONFLICT")
    if item.name != target.name:
        fail("INVENTORY_IDENTITY_CHANGED")
    return item


def stock_changes(action, fields, item, normalized):
    """The same exact business projection is used by read-only preview and commit."""
    quantity, changes = None, {"version": item.version + 1}
    if action == "MOVE":
        changes["storage_location"] = fields.to_location
    elif action == "OPEN":
        if item.opened_at is not None:
            fail("ALREADY_OPENED")
        changes["opened_at"] = fields.opened_at
    else:
        quantity = converted(fields.quantity, fields.unit, item.unit)
        if action == "DISCARD" and fields.discard_mode == "all":
            if quantity != item.quantity:
                fail("DISCARD_ALL_QUANTITY_CONFLICT")
            quantity = item.quantity
            normalized["quantity"], normalized["unit"] = str(quantity), item.unit
        if quantity > item.quantity:
            fail("INSUFFICIENT_STOCK", 422)
        if quantity != Decimal(1):
            fail("SINGLE_OBJECT_CONSUMPTION_REQUIRED", 422)
        changes["status"] = "DISCARDED" if action == "DISCARD" else "FINISHED"
    return quantity, changes


def preview(db, identity, draft_id, body):
    task, draft = owned(db, identity, draft_id)
    revision(task, draft, body)
    if db.get(DraftDecision, draft_id) is not None:
        fail("DRAFT_ALREADY_DECIDED")
    pending(task, draft)
    if expiry(task, draft) <= now():
        fail("DRAFT_EXPIRED")
    action, target, fields, normalized = command(task, draft, body.edits)
    if action not in {"OPEN", "DISCARD"}:
        fail("PREVIEW_ACTION_UNAVAILABLE")
    item = target_item(db, draft.household_id, target)
    quantity, changes = stock_changes(action, fields, item, normalized)
    before = StockResponse.model_validate(item).model_dump(mode="json")
    after = StockResponse.model_validate({**before, **changes}).model_dump(mode="json")
    return {"draft_id": str(draft.id), "task_id": str(task.id), "draft_revision": draft.revision,
        "task_revision": task.revision, "command": normalized, "before": before, "after": after,
        "event_type": "Opened" if action == "OPEN" else "Discarded",
        "event_quantity": quantity, "quantity_source": ("current_batch" if fields.discard_mode == "all"
            else "user_input") if action == "DISCARD" else None,
        "expires_at": expiry(task, draft).isoformat(), "prospective": True, "inventory_written": False}


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
    if draft.command_json.get('action') == 'PLAN_ADD' and automated_plan(task):
        basis = (task.result_json or {}).get('planning_basis')
        if isinstance(basis, dict) and basis.get('protocol_version') == 'planning-revalidation-1':
            from app.services.planning_revalidation import inspect
            report = inspect(db, identity, draft_id, body)
            if report['mismatches']:
                raise HTTPException(409, {'code': 'PLANNING_BASIS_STALE', 'mismatches': report['mismatches'],
                                          'regenerate_required': True})
            raise HTTPException(409, {'code': 'PLANNING_REVALIDATION_UNAVAILABLE', 'blockers': report['blockers']})
    action, target, fields, normalized = command(task, draft, body.edits)
    from app.services.product_grouping import lock_household
    lock_household(db, draft.household_id)
    at = now()
    event_id = uuid5(body.operation_id, "event")
    before, batch_versions, item, shopping = {}, {}, None, None
    created_objects = []
    quantity, event_type = None, {"ADD": "StockAdded", "MOVE": "StockMoved", "PLAN_ADD": "PlanAdded",
                                "CONSUME": "Consumed", "OPEN": "Opened", "DISCARD": "Discarded"}[action]
    if action == "ADD":
        from app.services.physical_inventory import add_objects
        created_objects = add_objects(db, first_id=uuid5(body.operation_id, "inventory"),
            household_id=draft.household_id, actor_user_id=identity.user.id,
            name=fields.name, quantity=fields.quantity, unit=unit(fields.unit),
            storage_location=fields.location, purchased_on=fields.purchased_at,
            expires_on=fields.label_expiry, category="其他", minimum_quantity=0, history_json=[])
        item = created_objects[0]
        quantity = Decimal(1)
    elif action in {"MOVE", "CONSUME", "OPEN", "DISCARD"}:
        item = target_item(db, draft.household_id, target, lock=True)
        if action == "CONSUME" and (task.result_json or {}).get("consume_mode") == "all":
            if converted(fields.quantity, fields.unit, item.unit) != item.quantity:
                fail("CONSUME_ALL_QUANTITY_CONFLICT")
        before = StockResponse.model_validate(item).model_dump(mode="json")
        quantity, changes = stock_changes(action, fields, item, normalized)
        for key, value in changes.items():
            setattr(item, key, value)
    else:
        source = procurement_source(db, task, normalized, lock=True)
        shared = db.scalar(select(ShoppingList).where(ShoppingList.household_id == draft.household_id).with_for_update())
        if shared is None:
            fail("SHOPPING_LIST_MISSING")
        # Lock/re-read current pending items. Automatic recommendations remain disabled.
        db.scalars(select(ShoppingListItem).where(ShoppingListItem.shopping_list_id == shared.id,
            ShoppingListItem.is_checked.is_(False)).with_for_update()).all()
        shopping = ShoppingListItem(id=uuid5(body.operation_id, "shopping"), shopping_list_id=shared.id,
            added_by_user_id=identity.user.id, name=normalized["name"], quantity=fields.quantity,
            unit=unit(fields.unit), is_checked=False, source_inventory_item_id=source.id if source else None)
        quantity = fields.quantity
        db.add(shopping)
    for changed in created_objects or ([item] if item is not None else []):
        changed.history_json = ([{"id": str(body.operation_id), "event_id": str(event_id if changed == item else uuid5(body.operation_id, "event:" + str(changed.id))),
                              "kind": event_type, "created_at": at.isoformat()}] + (changed.history_json or []))[:30]
        batch_versions[str(changed.id)] = changed.version
    db.flush()
    after = (StockResponse.model_validate(item) if item is not None else ShoppingItemResponse.model_validate(shopping)).model_dump(mode="json")
    event_ids = [event_id] + [uuid5(body.operation_id, "event:" + str(row.id)) for row in created_objects[1:]]
    result = {"inventory_item" if item is not None else "shopping_item": after}
    if created_objects:
        result.update(created_count=len(created_objects), inventory_item_ids=[str(row.id) for row in created_objects],
            inventory_items=[StockResponse.model_validate(row).model_dump(mode="json") for row in created_objects])
    receipt = {"protocol_version": "draft-operation-receipt-1", "operation_id": str(body.operation_id),
        "draft_id": str(draft.id), "task_id": str(task.id), "draft_revision": draft.revision,
        "task_revision": task.revision, "scope": {"user_id": str(identity.user.id), "household_id": str(draft.household_id)},
        "status": "committed", "action": action, "committed_at": at.isoformat(),
        "trace_id": "op_" + body.operation_id.hex, "batch_versions": batch_versions,
        "event_ids": [str(value) for value in event_ids], "inventory_written": item is not None,
        "shopping_written": shopping is not None,
        "result": result}
    if action in {"OPEN", "DISCARD"}:
        receipt["execution"] = {"before": before, "after": after, "event_type": event_type,
            "quantity": str(quantity) if quantity is not None else None, "unit": item.unit,
            "discard_mode": fields.discard_mode if action == "DISCARD" else None,
            "quantity_source": ("current_batch" if fields.discard_mode == "all" else "user_input") if action == "DISCARD" else None}
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
    for row, extra_event_id in zip(created_objects[1:], event_ids[1:]):
        persist_event(db, id=extra_event_id, operation_id=body.operation_id, household_id=draft.household_id,
            actor_user_id=identity.user.id, inventory_item_id=row.id, shopping_item_id=None,
            event_type=event_type, quantity=Decimal(1), unit=row.unit, before_json={},
            after_json=StockResponse.model_validate(row).model_dump(mode="json"), occurred_at=at)
    db.add(DraftDecision(draft_id=draft.id, draft_revision=draft.revision, task_revision=task.revision,
                         status="committed", operation_id=body.operation_id, decided_at=at))
    db.flush()
    if item is not None:
        from app.services.inventory_cleanup import remove_ended
        remove_ended(db, item)
    return receipt


def procurement_source(db, task, normalized, lock=False):
    """Only saved AI provenance can link a manual plan, never a commit edit/name match."""
    source = (task.result_json or {}).get("procurement_source")
    if source is None:
        return None
    try:
        if set(source) != {"batch_id", "expected_version"} or type(source["expected_version"]) is not int:
            fail("PROCUREMENT_SOURCE_INVALID", 422)
        target = Target(name=normalized["name"], batch_id=UUID(source["batch_id"]),
                        expected_version=source["expected_version"])
    except (TypeError, ValueError, ValidationError):
        fail("PROCUREMENT_SOURCE_INVALID", 422)
    item = target_item(db, task.household_id, target, lock=lock)
    converted(Decimal(1), normalized["unit"], item.unit)
    return item


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
