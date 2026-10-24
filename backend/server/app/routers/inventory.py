"""App inventory with household authorization, version checks and safe retries."""
import hashlib
import json
from typing import Literal
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.dependencies import Identity, get_db, get_identity
from app.inventory_schemas import Adjustment, InventoryCreate, InventoryUpdate, Versioned
from app.models import InventoryItem
from app.routers.households import membership_or_404
from app.shopping_schemas import StockResponse

router = APIRouter(prefix="/api/v1/households/{household_id}/inventory-items", tags=["Inventory"])


class InventoryPage(BaseModel):
    items: list[StockResponse]
    total: int
    limit: int
    offset: int


def fingerprint(kind, payload):
    return hashlib.sha256((kind + json.dumps(payload.model_dump(mode="json"), sort_keys=True)).encode()).hexdigest()


def record(item, operation_id, digest, message, **facts):
    item.history_json = ([{"id": str(operation_id), "hash": digest, "message": message,
                          "created_at": datetime.now(timezone.utc).isoformat(), **facts}] + (item.history_json or []))[:30]


def minimum_preference(item, payload, actor_user_id):
    # Request field presence is evidence; the schema/database default is not.
    if "minimum_quantity" not in payload.model_fields_set:
        return {}
    return {"minimum_preference": {"quantity": str(item.minimum_quantity), "unit": item.unit,
        "source": "authenticated_inventory_input", "actor_user_id": str(actor_user_id),
        "recorded_at": datetime.now(timezone.utc).isoformat(), "inventory_version": item.version or 1}}


def replay(item, operation_id, digest):
    for entry in item.history_json or []:
        if entry.get("id") == str(operation_id):
            if entry.get("hash") != digest:
                raise HTTPException(409, "Operation ID was already used with different content")
            return True
    return False


def locked(db, household_id, item_id):
    item = db.scalar(select(InventoryItem).where(InventoryItem.household_id == household_id,
                                                InventoryItem.id == item_id).with_for_update())
    if item is None:
        raise HTTPException(404, "Inventory item not found")
    return item


@router.get("", response_model=InventoryPage)
def list_inventory(household_id: UUID, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                   status: Literal["ACTIVE", "FINISHED", "DISCARDED", "REVERSED", "all"] | None = None,
                   identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    membership_or_404(db, household_id, identity.user.id)
    filters = [InventoryItem.household_id == household_id]
    if status is None:
        filters.append(InventoryItem.status.in_(["ACTIVE", "FINISHED"]))
    elif status != "all":
        filters.append(InventoryItem.status == status)
    total = db.scalar(select(func.count()).select_from(InventoryItem).where(*filters))
    rows = db.scalars(select(InventoryItem).where(*filters).order_by(InventoryItem.created_at.desc(), InventoryItem.id)
                      .limit(limit).offset(offset)).all()
    return InventoryPage(items=[StockResponse.model_validate(row) for row in rows], total=total, limit=limit, offset=offset)


@router.get("/{item_id}", response_model=StockResponse)
def get_inventory(household_id: UUID, item_id: UUID,
                  identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    membership_or_404(db, household_id, identity.user.id)
    item = db.scalar(select(InventoryItem).where(InventoryItem.household_id == household_id, InventoryItem.id == item_id))
    if item is None:
        raise HTTPException(404, "Inventory item not found")
    return StockResponse.model_validate(item)


@router.post("", response_model=StockResponse, status_code=201)
def create_inventory(household_id: UUID, payload: InventoryCreate,
                     identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    membership_or_404(db, household_id, identity.user.id)
    digest = fingerprint("create", payload)
    existing = db.get(InventoryItem, payload.id)
    if existing is not None:
        if (existing.household_id == household_id and existing.created_by_user_id == identity.user.id
                and replay(existing, payload.id, digest)):
            return StockResponse.model_validate(existing)
        raise HTTPException(409, "Item ID is already in use; refresh inventory")
    item = InventoryItem(household_id=household_id, created_by_user_id=identity.user.id,
                         status="ACTIVE" if payload.quantity > 0 else "FINISHED", **payload.model_dump())
    record(item, payload.id, digest, f"首次录入 {payload.quantity} {payload.unit}", kind="create",
           **minimum_preference(item, payload, identity.user.id))
    db.add(item)
    try:
        db.flush()
        result = StockResponse.model_validate(item)
        db.commit()
        return result
    except IntegrityError:
        db.rollback()
        existing = db.get(InventoryItem, payload.id)
        if (existing is not None and existing.household_id == household_id
                and existing.created_by_user_id == identity.user.id and replay(existing, payload.id, digest)):
            return StockResponse.model_validate(existing)
        raise HTTPException(409, "Concurrent item creation; refresh inventory") from None


def mutate(db, household_id, item_id, payload, kind, actor_user_id=None):
    item = locked(db, household_id, item_id)
    digest = fingerprint(kind, payload)
    if replay(item, payload.operation_id, digest):
        return item
    if item.status not in ("ACTIVE", "FINISHED"):
        raise HTTPException(409, "Inventory item was removed; refresh inventory")
    if item.version != payload.expected_version:
        raise HTTPException(409, "Inventory changed on another device; refresh and confirm again")
    before_quantity, before_unit = str(item.quantity), item.unit
    if kind == "adjust":
        quantity = item.quantity + payload.delta
        if quantity < 0 or quantity > 1_000_000_000:
            raise HTTPException(422, "Resulting quantity is outside the allowed range")
        item.quantity = quantity
        message = f"数量调整 {payload.delta} {item.unit} → {quantity} {item.unit}"
    elif kind == "edit":
        changes = payload.model_dump(exclude_unset=True, exclude={"expected_version", "operation_id"})
        for key, value in changes.items():
            setattr(item, key, value)
        message = f"更新记录 → {item.quantity} {item.unit}"
    else:
        item.status = "DISCARDED"
        message = "删除库存记录（保留购买来源与历史）"
    if kind != "delete":
        item.status = "ACTIVE" if item.quantity > 0 else "FINISHED"
    item.version += 1
    facts = {"kind": "edit_quantity" if kind == "edit" and
             {"quantity", "unit"} & payload.model_fields_set else kind}
    if facts["kind"] in {"adjust", "edit_quantity"}:
        facts.update(before_quantity=before_quantity, before_unit=before_unit,
                     after_quantity=str(item.quantity), after_unit=item.unit)
    if kind == "edit":
        facts.update(minimum_preference(item, payload, actor_user_id))
    record(item, payload.operation_id, digest, message, **facts)
    db.flush()
    return item


@router.patch("/{item_id}", response_model=StockResponse)
def edit_inventory(household_id: UUID, item_id: UUID, payload: InventoryUpdate,
                   identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    membership_or_404(db, household_id, identity.user.id)
    result = StockResponse.model_validate(mutate(db, household_id, item_id, payload, "edit", identity.user.id))
    db.commit()
    return result


@router.post("/{item_id}/adjustments", response_model=StockResponse)
def adjust_inventory(household_id: UUID, item_id: UUID, payload: Adjustment,
                     identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    membership_or_404(db, household_id, identity.user.id)
    result = StockResponse.model_validate(mutate(db, household_id, item_id, payload, "adjust"))
    db.commit()
    return result


@router.delete("/{item_id}", status_code=204)
def delete_inventory(household_id: UUID, item_id: UUID, payload: Versioned,
                     identity: Identity = Depends(get_identity), db: Session = Depends(get_db)):
    membership_or_404(db, household_id, identity.user.id)
    mutate(db, household_id, item_id, payload, "delete")
    db.commit()
    return Response(status_code=204)
