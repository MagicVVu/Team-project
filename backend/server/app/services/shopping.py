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
    inventory_item_ids: tuple[UUID, ...] = ()
    inventory_snapshot: dict | None = None


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

    from app.services.product_grouping import lock_household
    lock_household(session, household_id)

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

    from app.services.product_grouping import lock_household
    lock_household(session, household_id)
    existing_rows = session.scalars(select(InventoryItem).where(
        InventoryItem.source_shopping_list_item_id == item.id).order_by(InventoryItem.created_at, InventoryItem.id)).all()
    first_id = uuid5(item.id, 'purchase-inventory')
    existing_stock = next((row for row in existing_rows if row.id == first_id), existing_rows[0] if existing_rows else None)
    if existing_stock is not None:
        if not item.is_checked:
            raise PurchaseReconciliationRequired(
                "Shopping item is unchecked but a linked stock row already exists"
            )
        return PurchaseResult(existing_stock.id, newly_stocked=False, inventory_item_ids=tuple(r.id for r in existing_rows))

    if item.is_checked:
        # All stocked objects may have been consumed and physically deleted.
        # Retained events/receipts prove the purchase; never restock on a retry.
        from app.product_models import MutationReceipt
        from app.execution_models import BusinessEvent
        request_id = uuid5(item.id, 'purchase-and-stock')
        receipt = session.get(MutationReceipt, request_id)
        if receipt is not None and receipt.household_id == household_id:
            first_id = receipt.response_json.get('inventory_item_id')
            events = session.scalars(select(BusinessEvent).where(BusinessEvent.request_id == request_id)).all()
            snapshot = next((e.after_json for e in events if e.after_json.get('id') == first_id), None)
            if snapshot is not None:
                return PurchaseResult(UUID(first_id), False,
                    tuple(UUID(value) for value in receipt.response_json.get('inventory_item_ids', [first_id])), snapshot)
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
    from app.product_models import ProductBatch
    from app.services import ledger
    from app.services.physical_inventory import add_objects
    source_link = session.get(ProductBatch, source.id) if source else None
    rows = add_objects(session, first_id=uuid5(item.id, 'purchase-inventory'), quantity=item.quantity,
        unit=item.unit, actor_user_id=actor_user_id, household_id=household_id,
        product_id=source_link.product_id if source_link else None,
        name=item.name, category=source.category if source else None,
        minimum_quantity=source.minimum_quantity if source else Decimal(0),
        specification=source.specification if source else None,
        purchased_on=now.date(), expires_on=expires_on,
        storage_location=storage_location or (source.storage_location if source else None),
        history_json=[{"message": "采购入库一个独立物品", "created_at": now.isoformat()}],
        source_shopping_list_item_id=item.id)
    item.is_checked = True
    item.checked_at = now
    item.purchased_by_user_id = actor_user_id
    session.flush()
    request_id = uuid5(item.id, 'purchase-and-stock')
    ledger.save(session, request_id, household_id, actor_user_id,
        ledger.digest(['purchase', str(item.id)]), {'inventory_item_id': str(rows[0].id),
            'inventory_item_ids': [str(row.id) for row in rows], 'created_count': len(rows)})
    for stock in rows:
        ledger.append(session, stock, actor_user_id, 'Purchased', {}, request_id=request_id,
            event_id=uuid5(request_id, 'event:' + str(stock.id)), quantity=Decimal(1))
    return PurchaseResult(rows[0].id, newly_stocked=True, inventory_item_ids=tuple(row.id for row in rows))
