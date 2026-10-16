"""Authenticated shared shopping list and atomic purchase-to-stock routes."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.dependencies import Identity, get_db, get_identity
from app.models import InventoryItem, ShoppingList, ShoppingListItem
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
    ).with_for_update())
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
    item = ShoppingListItem(shopping_list_id=shopping_list.id, added_by_user_id=identity.user.id,
                            **payload.model_dump())
    db.add(item)
    db.flush()
    result = ShoppingItemResponse.model_validate(item)
    db.commit()
    return result


@router.patch("/{household_id}/shopping-list/items/{item_id}", response_model=ShoppingItemResponse)
def update_item(
    household_id: UUID, item_id: UUID, payload: ShoppingItemUpdate,
    identity: Identity = Depends(get_identity), db: Session = Depends(get_db),
) -> ShoppingItemResponse:
    shopping_list = shared_list(db, household_id, identity.user.id)
    item = locked_pending_item(db, shopping_list.id, item_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    db.flush()
    result = ShoppingItemResponse.model_validate(item)
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
    stock = db.get(InventoryItem, purchase.inventory_item_id)
    result = PurchaseResponse(item=ShoppingItemResponse.model_validate(item),
                              inventory_item=StockResponse.model_validate(stock),
                              newly_stocked=purchase.newly_stocked)
    db.commit()
    return result
