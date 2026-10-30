"""Physically remove ended objects, while retaining durable operation receipts."""
from sqlalchemy import delete, select, update
from app.models import InventoryItem, ShoppingListItem
from app.product_models import Product, ProductBatch
from app.planning_fact_models import InventoryPlanningFacts, PlanningFactWrite
from app.execution_models import BusinessEvent


def remove_empty_products(db, household_id):
    linked = select(ProductBatch.product_id)
    ids = list(db.scalars(select(Product.id).where(
        Product.household_id == household_id, ~Product.id.in_(linked))))
    if ids:
        db.execute(update(BusinessEvent).where(BusinessEvent.product_id.in_(ids))
                   .values(product_id=None).execution_options(synchronize_session=False))
        db.execute(delete(Product).where(Product.id.in_(ids)).execution_options(synchronize_session=False))
    return len(ids)


def remove_ended(db, item):
    if item.status == 'ACTIVE':
        return False
    db.flush()
    db.execute(update(BusinessEvent).where(BusinessEvent.inventory_item_id == item.id)
               .values(inventory_item_id=None).execution_options(synchronize_session=False))
    db.execute(update(ShoppingListItem).where(ShoppingListItem.source_inventory_item_id == item.id)
               .values(source_inventory_item_id=None).execution_options(synchronize_session=False))
    for model in (ProductBatch, InventoryPlanningFacts, PlanningFactWrite):
        db.execute(delete(model).where(model.inventory_item_id == item.id)
                   .execution_options(synchronize_session=False))
    db.delete(item)
    db.flush()
    remove_empty_products(db, item.household_id)
    return True


def sweep(db, household_id):
    """Caller holds the household lock and owns the commit/backup boundary."""
    rows = db.scalars(select(InventoryItem).where(InventoryItem.household_id == household_id,
        InventoryItem.status != 'ACTIVE').with_for_update()).all()
    for row in rows:
        remove_ended(db, row)
    empty = remove_empty_products(db, household_id)
    return {'deleted_inventory_items': len(rows), 'remaining_empty_products_deleted': empty}
