"""Attestations never create stock or consumption. Changed evidence is invalidated."""
import copy
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import select

from app.execution_models import BusinessEvent, DraftOperation
from app.models import InventoryItem
from app.planning_fact_models import InventoryPlanningFacts, PlanningFactWrite
from app.planning_fact_schemas import PlanningFactsResponse
from app.routers.households import membership_or_404
from app.services.ai_inventory import UNIT_CANONICAL

KINDS = {"StockAdded": "Added", "StockMoved": "Moved", "Consumed": "Consumed",
         "Opened": "Opened", "Discarded": "Discarded"}


def fail(code, status=409):
    raise HTTPException(status, {"code": code})


def now():
    return datetime.now(timezone.utc)


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def business_zone():
    try:
        return ZoneInfo(os.getenv("MAGICVVU_HOUSEHOLD_TIMEZONE", "Asia/Shanghai"))
    except (ValueError, ZoneInfoNotFoundError):
        fail("HOUSEHOLD_TIMEZONE_INVALID", 503)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def identity(item, section):
    fields = {"name": item.name, "unit": UNIT_CANONICAL.get(item.unit)}
    if section == "preferences":
        fields["minimum_quantity"] = str(item.minimum_quantity)
    elif section == "risk_facts":
        fields.update(category=item.category, location=item.storage_location,
                      expiry=str(item.expires_on), opened_at=str(item.opened_at))
    elif section == "stock_verification":
        fields.update(version=item.version, quantity=str(item.quantity), status=item.status)
    return fields


def event_value(event, operation):
    return {"id": str(event.id), "item_key": str(event.inventory_item_id),
            "kind": KINDS[event.event_type], "quantity": str(event.quantity if event.quantity is not None else 0),
            "unit": UNIT_CANONICAL.get(event.unit), "occurred_at": aware(event.occurred_at).isoformat(),
            "recorded_at": aware(operation.committed_at).isoformat(), "committed": True, "related_event_id": None}


def events_for(db, item):
    rows = db.execute(select(BusinessEvent, DraftOperation).outerjoin(DraftOperation,
        BusinessEvent.operation_id == DraftOperation.id).where(
        BusinessEvent.household_id == item.household_id, BusinessEvent.inventory_item_id == item.id)
        .order_by(BusinessEvent.occurred_at, BusinessEvent.id).limit(20001)).all()
    if len(rows) > 20000:
        fail("PLANNING_INCOMPLETE")
    if any(op is None or op.household_id != item.household_id for _, op in rows):
        fail("PLANNING_CONTRACT_INVALID")
    return [event_value(event, op) for event, op in rows if event.event_type in KINDS]


def day_hashes(item, events, days, zone):
    def calendar_day(timestamp):
        try:
            return aware(datetime.fromisoformat(timestamp)).astimezone(zone).date().isoformat()
        except (TypeError, ValueError):
            # Unknown adjustment dates cannot safely be excluded from a day.
            return None
    by_day, adjustments, undated = {}, {}, []
    for event in events:
        by_day.setdefault(calendar_day(event["occurred_at"]), []).append(event)
    for entry in item.history_json or []:
        if isinstance(entry, dict) and entry.get("kind") in {"adjust", "edit_quantity"}:
            day = calendar_day(entry.get("created_at"))
            if day is None:
                undated.append(entry)
            else:
                adjustments.setdefault(day, []).append(entry)
    return {day: digest({"identity": identity(item, "coverage"),
        "events": sorted(by_day.get(day, []) + by_day.get(None, []), key=lambda e: e["id"]),
        "adjustments": adjustments.get(day, []) + undated, "timezone": zone.key}) for day in days}


def project(item, stored, events):
    """Project only currently supported facts; retain source details for review."""
    zone = business_zone()
    facts = stored.facts_json if stored else {}
    invalid = []
    values = {"preferences": None, "risk_facts": None, "stock_verification": None, "coverage": []}
    for section in ("preferences", "risk_facts", "stock_verification"):
        envelope = facts.get(section)
        if not envelope:
            continue
        if envelope["inventory_identity"] != identity(item, section):
            invalid.append(section)
            continue
        values[section] = envelope["value"]
        if section == "stock_verification":
            values[section] = {**envelope["value"], "checked_at": envelope["recorded_at"],
                "source": envelope["source"], "inventory_version": envelope["inventory_version"]}
    hashes = day_hashes(item, events, facts.get("coverage", {}), zone)
    for day, envelope in sorted(facts.get("coverage", {}).items()):
        value = dict(envelope["value"])
        if envelope["day_hash"] != hashes[day]:
            value.update(records_complete=False, unexplained_adjustment=True)
            invalid.append("coverage:" + day)
        values["coverage"].append(value)
    provenance = {section: {k: v for k, v in envelope.items() if k != "value"}
        for section, envelope in facts.items() if section != "coverage" and envelope}
    if facts.get("coverage"):
        provenance["coverage"] = {day: {k: v for k, v in envelope.items() if k != "value"}
            for day, envelope in facts["coverage"].items()}
    return PlanningFactsResponse(household_id=item.household_id, inventory_item_id=item.id,
        inventory_version=item.version, facts_version=stored.version if stored else 0,
        household_timezone=zone.key, invalidated_sections=invalid, provenance=provenance,
        **values).model_dump(mode="json")


def owned_item(db, identity_value, household_id, item_id, *, write=False):
    membership_or_404(db, household_id, identity_value.user.id)
    item = db.scalar(select(InventoryItem).where(InventoryItem.id == item_id,
        InventoryItem.household_id == household_id).with_for_update(read=not write)
        .execution_options(populate_existing=True))
    if item is None:
        fail("INVENTORY_NOT_FOUND", 404)
    return item


def read(db, identity_value, household_id, item_id):
    item = owned_item(db, identity_value, household_id, item_id)
    return project(item, db.get(InventoryPlanningFacts, item.id), events_for(db, item))


def patch(db, identity_value, household_id, item_id, body):
    item = owned_item(db, identity_value, household_id, item_id, write=True)
    request_hash = digest({"user_id": str(identity_value.user.id), "household_id": str(household_id),
        "item_id": str(item_id), "body": body.model_dump(mode="json", exclude_unset=True)})
    previous = db.get(PlanningFactWrite, body.operation_id)
    if previous:
        if previous.request_hash != request_hash:
            fail("OPERATION_ID_CONFLICT")
        return previous.response_json
    if item.status not in {"ACTIVE", "FINISHED"}:
        fail("INVENTORY_TERMINAL")
    if item.version != body.expected_inventory_version:
        fail("INVENTORY_VERSION_CONFLICT")
    stored = db.get(InventoryPlanningFacts, item.id)
    if (stored.version if stored else 0) != body.expected_facts_version:
        fail("PLANNING_FACTS_VERSION_CONFLICT")
    if item.unit not in UNIT_CANONICAL:
        fail("INVENTORY_UNIT_UNSUPPORTED", 422)
    timestamp, zone = now(), business_zone()
    facts = copy.deepcopy(stored.facts_json) if stored else {}
    events = events_for(db, item)
    metadata = {"source": body.source, "actor_user_id": str(identity_value.user.id),
                "recorded_at": timestamp.isoformat(), "inventory_version": item.version}
    for section in ("preferences", "risk_facts", "stock_verification"):
        if section not in body.model_fields_set:
            continue
        value = getattr(body, section)
        if section == "stock_verification" and value is not None:
            if value.quantity != item.quantity or value.unit != UNIT_CANONICAL[item.unit]:
                fail("STOCK_COUNT_MISMATCH")
        if section == "risk_facts" and value is not None:
            if item.opened_at is not None and value.is_opened is False:
                fail("OPENED_STATE_CONFLICT", 422)
            if value.label_context_valid is True and (item.expires_on is None or value.label_date_type == "unknown"):
                fail("LABEL_DATE_REQUIRED", 422)
        facts[section] = ({**metadata, "inventory_identity": identity(item, section),
                           "value": value.model_dump(mode="json")} if value is not None else None)
    if body.coverage is not None:
        coverage = facts.setdefault("coverage", {})
        today = timestamp.astimezone(zone).date()
        hashes = day_hashes(item, events, [entry.day.isoformat() for entry in body.coverage], zone)
        for entry in body.coverage:
            if not today - timedelta(days=3660) <= entry.day < today:
                fail("COVERAGE_DAY_OUT_OF_RANGE", 422)
            day = entry.day.isoformat()
            coverage[day] = {**metadata, "timezone": zone.key, "value": entry.model_dump(mode="json"),
                             "day_hash": hashes[day]}
        if len(coverage) > 3660:
            fail("COVERAGE_LIMIT_EXCEEDED", 422)
    if stored is None:
        stored = InventoryPlanningFacts(inventory_item_id=item.id, version=1, facts_json=facts)
        db.add(stored)
    else:
        stored.version += 1
        stored.facts_json = facts
    result = project(item, stored, events)
    db.add(PlanningFactWrite(operation_id=body.operation_id, inventory_item_id=item.id,
        user_id=identity_value.user.id, household_id=household_id, request_hash=request_hash, response_json=result))
    db.flush()
    return result


def risk_fields(item, projected):
    fields = {"category": item.category if item.category in {"food", "medicine", "household"} else "unknown",
        "product_id": None, "label_date_type": "unknown", "label_context_valid": None,
        "storage_condition": None, "label_storage_condition": None,
        "is_opened": True if item.opened_at is not None else None}
    if projected["risk_facts"] is not None:
        fields.update(projected["risk_facts"])
    if item.opened_at is not None:
        fields["is_opened"] = True
    return fields
