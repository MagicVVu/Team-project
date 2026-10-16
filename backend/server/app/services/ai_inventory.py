"""P1-compatible read-only batch serializer.

No DB mutation and no substitute units/statuses. Invalid legacy data is surfaced
as a conflict for human reconciliation, never silently omitted or altered.
"""
from decimal import Decimal

from app.models import InventoryItem

# Exactly the canonical unit values recognized by agent/p0/domain.py
# (aliases below are mapped to canonical spellings without changing semantics).
UNIT_CANONICAL = {
    "毫升": "ml", "ml": "ml", "mL": "ml", "升": "L", "l": "L", "L": "L",
    "克": "g", "g": "g", "千克": "kg", "公斤": "kg", "kg": "kg",
    "盒": "盒", "瓶": "瓶", "包": "包", "袋": "袋", "个": "个", "卷": "卷", "片": "片",
}
ALLOWED_STATUS = {"ACTIVE", "FINISHED", "DISCARDED", "REVERSED"}
MAX_QUANTITY = Decimal("1000000000")


class IncompatibleInventory(ValueError):
    pass


def to_p1_batch(item: InventoryItem) -> dict:
    name = item.name
    if not name or len(name) > 80 or not name.strip():
        raise IncompatibleInventory("Inventory name is incompatible with AI P1 (1-80 nonblank characters)")
    unit = UNIT_CANONICAL.get(item.unit)
    if not unit:
        raise IncompatibleInventory("Inventory has a unit unsupported by AI P1; reconcile before AI use")
    quantity = item.quantity
    if (not isinstance(quantity, Decimal) or not quantity.is_finite()
            or quantity < 0 or quantity > MAX_QUANTITY
            or quantity.as_tuple().exponent < -6):
        raise IncompatibleInventory("Inventory quantity is incompatible with AI P1")
    if item.status not in ALLOWED_STATUS or item.version is None or item.version < 1:
        raise IncompatibleInventory("Inventory lifecycle fields are invalid")
    if item.storage_location is not None and len(item.storage_location) > 120:
        raise IncompatibleInventory("Inventory location is too long for AI P1")
    return {
        "id": str(item.id),
        "household_id": str(item.household_id),
        "name": name,
        "quantity": format(quantity, "f"),  # JSON string, never binary float
        "unit": unit,
        "location": item.storage_location,
        "purchased_at": item.purchased_on.isoformat() if item.purchased_on is not None else None,
        "label_expiry": item.expires_on.isoformat() if item.expires_on is not None else None,
        "opened_at": item.opened_at.isoformat() if item.opened_at is not None else None,
        "status": item.status,
        "version": item.version,
    }
