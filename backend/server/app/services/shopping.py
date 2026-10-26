"""Atomic, idempotent internal purchase-to-inventory operation.

Only trusted backend code should invoke this service, after authenticating the
user. It DOES NOT expose an HTTP route or accept untrusted user IDs on the web.

Caller MUST wrap it in ``with session.begin():``; successful status and stock
row are committed together. On failure, the caller's transaction rolls back.
"""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import HouseholdMember, InventoryItem, ShoppingList, ShoppingListItem


class ShoppingAccessError(PermissionError):
    """Actor is not an active member of the requested household."""


class ShoppingItemNotFound(LookupError):
    """The shopping item does not belong to this household."""


class PurchaseReconciliationRequired(RuntimeError):
    """Legacy checked row has no linked inventory; do not stock it twice."""


@dataclass(frozen=True)
class PurchaseResult:
    inventory_item_id: UUID
    newly_stocked: bool


def purchase_and_stock(
    session: Session,
    *,
    household_id: UUID,
    shopping_item_id: UUID,
    actor_user_id: UUID,
    storage_location: str | None = None,
    expires_on: date | None = None,
    actual_quantity: Decimal | None = None,
) -> PurchaseResult:
    """Mark purchased + insert a new inventory batch in the SAME transaction.

    Concurrency: ``FOR UPDATE`` locks the shopping item row on PostgreSQL so
    concurrent purchasers serialize. The inventory source UNIQUE constraint
    is the second line of defense. Repeated calls return the same inventory ID.

    New stock is a *separate batch*, never blindly merged with existing stock:
    expiry date, purchase date and provenance may differ.

    ``session`` must be in a transaction (use ``with session.begin():``).
    Only commit at the caller's transaction boundary.
    """
    if not session.in_transaction():
        raise RuntimeError("purchase_and_stock requires an active transaction")

    authorized = session.scalar(
        select(HouseholdMember.user_id).where(
            HouseholdMember.household_id == household_id,
            HouseholdMember.user_id == actor_user_id,
        )
    )
    if authorized is None:
        raise ShoppingAccessError("Actor is not a member of this household")

    item = session.scalar(
        select(ShoppingListItem)
        .join(ShoppingList, ShoppingList.id == ShoppingListItem.shopping_list_id)
        .where(
            ShoppingList.household_id == household_id,
            ShoppingListItem.id == shopping_item_id,
        )
        .with_for_update(of=ShoppingListItem)
    )
    if item is None:
        raise ShoppingItemNotFound("Shopping item not found in household")

    existing_stock = session.scalar(
        select(InventoryItem).where(
            InventoryItem.source_shopping_list_item_id == item.id
        )
    )
    if existing_stock is not None:
        if not item.is_checked:
            raise PurchaseReconciliationRequired(
                "Shopping item is unchecked but a linked stock row already exists"
            )
        return PurchaseResult(existing_stock.id, newly_stocked=False)

    if item.is_checked:
        raise PurchaseReconciliationRequired(
            "This item was purchased before stock-link tracking was enabled; "
            "reconcile manually instead of creating duplicate inventory"
        )

    now = datetime.now(timezone.utc)
    if actual_quantity is not None:
        item.quantity = actual_quantity
    source = session.scalar(select(InventoryItem).where(InventoryItem.id == item.source_inventory_item_id)
        .with_for_update().execution_options(populate_existing=True)) if item.source_inventory_item_id else None
    if source is not None and source.household_id != household_id:
        raise ShoppingItemNotFound("Source inventory is not in this household")
    stock = InventoryItem(
        household_id=household_id,
        name=item.name,
        quantity=item.quantity,
        unit=item.unit,
        category=source.category if source else None,
        minimum_quantity=source.minimum_quantity if source else Decimal(0),
        purchased_on=now.date(),
        expires_on=expires_on,
        storage_location=storage_location or (source.storage_location if source else None),
        history_json=[{"message": f"采购入库 {item.quantity} {item.unit}", "created_at": now.isoformat()}],
        created_by_user_id=actor_user_id,
        source_shopping_list_item_id=item.id,
    )
    session.add(stock)
    item.is_checked = True
    item.checked_at = now
    item.purchased_by_user_id = actor_user_id
    session.flush()  # Ensure DB constraints are checked before returning.
    from app.product_models import ProductBatch
    from app.services import ledger
    if source is not None:
        link = session.get(ProductBatch, source.id)
        if link is not None:
            session.add(ProductBatch(inventory_item_id=stock.id, product_id=link.product_id,
                actor_user_id=actor_user_id, source='purchase_from_explicit_source_batch'))
            session.flush()
    request_id = uuid5(item.id, 'purchase-and-stock')
    ledger.save(session, request_id, household_id, actor_user_id,
        ledger.digest(['purchase', str(item.id)]), {'inventory_item_id': str(stock.id)})
    ledger.append(session, stock, actor_user_id, 'Purchased', {}, request_id=request_id, quantity=stock.quantity)
    return PurchaseResult(stock.id, newly_stocked=True)
