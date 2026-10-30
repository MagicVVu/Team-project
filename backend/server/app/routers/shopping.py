"""Authenticated shared shopping list and atomic purchase-to-stock routes."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.dependencies import Identity, get_db, get_identity
from app.models import InventoryItem, ShoppingList, ShoppingListItem
from app.services import ledger
from app.routers.households import membership_or_404
from app.services.shopping import (
    PurchaseReconciliationRequired,
    ShoppingAccessError,
    ShoppingItemNotFound,
    purchase_and_stock,
)
from app.shopping_schemas import (
    PurchaseRequest, PurchaseResponse, ShoppingItemCreate, ShoppingItemResponse,
    ShoppingItemUpdate, ShoppingListResponse, ShoppingPage, StockResponse,
)

router = APIRouter(prefix="/api/v1/households", tags=["Shared shopping"])


def shared_list(db: Session, household_id: UUID, user_id: UUID) -> ShoppingList:
    membership_or_404(db, household_id, user_id)
    shopping_list = db.scalar(select(ShoppingList).where(ShoppingList.household_id == household_id))
    if shopping_list is None:
        raise HTTPException(status_code=409, detail="Household shopping list is missing; reconciliation required")
    return shopping_list


def locked_pending_item(db: Session, shopping_list_id: UUID, item_id: UUID) -> ShoppingListItem:
    item = db.scalar(select(ShoppingListItem).where(
        ShoppingListItem.shopping_list_id == shopping_list_id,
        ShoppingListItem.id == item_id,
    ).with_for_update().execution_options(populate_existing=True))
    if item is None:
        raise HTTPException(status_code=404, detail="Shopping item not found")
    linked_stock = db.scalar(select(InventoryItem.id).where(
        InventoryItem.source_shopping_list_item_id == item.id,
    ))
    if item.is_checked or linked_stock is not None:
        raise HTTPException(status_code=409, detail="Purchased items are retained as history; create a new item to buy again")
    return item


@router.get("/{household_id}/shopping-list", response_model=ShoppingListResponse)
def get_shopping_list(
    household_id: UUID, identity: Identity = Depends(get_identity), db: Session = Depends(get_db),
) -> ShoppingListResponse:
    return ShoppingListResponse.model_validate(shared_list(db, household_id, identity.user.id))


@router.get("/{household_id}/shopping-list/items", response_model=ShoppingPage)
def list_items(
    household_id: UUID,
    status: Literal["pending", "purchased", "all"] = "pending",
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    identity: Identity = Depends(get_identity), db: Session = Depends(get_db),
) -> ShoppingPage:
    shopping_list = shared_list(db, household_id, identity.user.id)
    filters = [ShoppingListItem.shopping_list_id == shopping_list.id]
    if status != "all":
        filters.append(ShoppingListItem.is_checked.is_(status == "purchased"))
    total = db.scalar(select(func.count()).select_from(ShoppingListItem).where(*filters))
    items = db.scalars(select(ShoppingListItem).where(*filters)
                       .order_by(ShoppingListItem.created_at.desc(), ShoppingListItem.id.asc())
                       .limit(limit).offset(offset)).all()
    return ShoppingPage(items=[ShoppingItemResponse.model_validate(item) for item in items],
                        total=total, limit=limit, offset=offset)


@router.post("/{household_id}/shopping-list/items", response_model=ShoppingItemResponse, status_code=201)
def create_item(
    household_id: UUID, payload: ShoppingItemCreate,
    identity: Identity = Depends(get_identity), db: Session = Depends(get_db),
) -> ShoppingItemResponse:
    shopping_list = shared_list(db, household_id, identity.user.id)
    values = payload.model_dump(exclude_none=True)
    if payload.source_inventory_item_id is not None:
        source = db.get(InventoryItem, payload.source_inventory_item_id)
        if source is None or source.household_id != household_id or source.status not in ("ACTIVE", "FINISHED"):
            raise HTTPException(404, "Source inventory item not found")
        if source.name != payload.name or source.unit != payload.unit:
            raise HTTPException(409, "Source inventory changed; refresh before planning")
    if payload.id is not None:
        existing = db.get(ShoppingListItem, payload.id)
        if existing is not None:
            if (existing.shopping_list_id == shopping_list.id and existing.added_by_user_id == identity.user.id
                    and existing.name == payload.name and existing.quantity == payload.quantity
                    and existing.unit == payload.unit and existing.source_inventory_item_id == payload.source_inventory_item_id):
                return ShoppingItemResponse.model_validate(existing)
            raise HTTPException(409, "Shopping item ID is already used")
    item = ShoppingListItem(shopping_list_id=shopping_list.id, added_by_user_id=identity.user.id,
                            **values)
    db.add(item)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Concurrent shopping item creation; refresh list") from None
    result = ShoppingItemResponse.model_validate(item)
    db.commit()
    return result


@router.patch("/{household_id}/shopping-list/items/{item_id}", response_model=ShoppingItemResponse)
@ledger.retry_conflicts
def update_item(
    household_id: UUID, item_id: UUID, payload: ShoppingItemUpdate,
    identity: Identity = Depends(get_identity), db: Session = Depends(get_db),
) -> ShoppingItemResponse:
    shopping_list = shared_list(db, household_id, identity.user.id)
    fingerprint = ledger.digest(['shopping_patch', str(item_id), payload.model_dump(mode='json', exclude_unset=True)])
    if payload.operation_id:
        previous = ledger.replay(db, payload.operation_id, household_id, identity.user.id, fingerprint)
        if previous is not None:
            return ShoppingItemResponse.model_validate(previous)
    item = locked_pending_item(db, shopping_list.id, item_id)
    if payload.operation_id:
        previous = ledger.replay(db, payload.operation_id, household_id, identity.user.id, fingerprint)
        if previous is not None:
            return ShoppingItemResponse.model_validate(previous)
    if payload.expected_version is not None and payload.expected_version != ShoppingItemResponse.model_validate(item).version:
        raise HTTPException(409, {'code': 'SHOPPING_VERSION_CONFLICT'})
    changes = payload.model_dump(exclude_unset=True, exclude={'expected_version', 'operation_id'})
    source_id = changes.get('source_inventory_item_id', item.source_inventory_item_id)
    if source_id is not None:
        source = db.scalar(select(InventoryItem).where(InventoryItem.id == source_id,
            InventoryItem.household_id == household_id).with_for_update().execution_options(populate_existing=True))
        if source is None:
            raise HTTPException(404, {'code': 'SOURCE_INVENTORY_NOT_FOUND'})
        from app.services.ai_inventory import UNIT_CANONICAL
        if (source.status not in ('ACTIVE', 'FINISHED') or source.name != changes.get('name', item.name)
                or UNIT_CANONICAL.get(source.unit, source.unit) != UNIT_CANONICAL.get(changes.get('unit', item.unit), changes.get('unit', item.unit))):
            raise HTTPException(409, {'code': 'SHOPPING_SOURCE_MISMATCH'})
    for key, value in changes.items():
        setattr(item, key, value)
    db.flush()
    result = ShoppingItemResponse.model_validate(item)
    if payload.operation_id:
        ledger.save(db, payload.operation_id, household_id, identity.user.id, fingerprint, result.model_dump(mode='json'))
    db.commit()
    return result


@router.delete("/{household_id}/shopping-list/items/{item_id}", status_code=204)
def delete_item(
    household_id: UUID, item_id: UUID,
    identity: Identity = Depends(get_identity), db: Session = Depends(get_db),
) -> Response:
    shopping_list = shared_list(db, household_id, identity.user.id)
    item = locked_pending_item(db, shopping_list.id, item_id)
    db.delete(item)
    db.commit()
    return Response(status_code=204)


@router.post("/{household_id}/shopping-list/items/{item_id}/purchase", response_model=PurchaseResponse)
def purchase_item(
    household_id: UUID, item_id: UUID, payload: PurchaseRequest,
    identity: Identity = Depends(get_identity), db: Session = Depends(get_db),
) -> PurchaseResponse:
    shared_list(db, household_id, identity.user.id)
    # get_identity has already opened this session's transaction. Commit once,
    # after both the item and its new stock have passed database constraints.
    try:
        purchase = purchase_and_stock(db, household_id=household_id, shopping_item_id=item_id,
                                      actor_user_id=identity.user.id, **payload.model_dump())
    except (ShoppingAccessError, ShoppingItemNotFound):
        db.rollback()
        raise HTTPException(status_code=404, detail="Shopping item not found") from None
    except PurchaseReconciliationRequired:
        db.rollback()
        raise HTTPException(status_code=409, detail="Purchase history requires reconciliation; no stock created") from None
    item = db.get(ShoppingListItem, item_id)
    stock = purchase.inventory_snapshot or db.get(InventoryItem, purchase.inventory_item_id)
    result = PurchaseResponse(item=ShoppingItemResponse.model_validate(item),
                              inventory_item=StockResponse.model_validate(stock),
                              newly_stocked=purchase.newly_stocked,
                              created_count=len(purchase.inventory_item_ids) if purchase.newly_stocked else 0,
                              inventory_item_ids=list(purchase.inventory_item_ids))
    db.commit()
    return result
