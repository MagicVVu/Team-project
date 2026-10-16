"""v0.3 shared-shopping smoke test; leaves NO test rows on success/failure.

Checks six tables, one-list-per-household uniqueness, attribution, transaction
purchase-to-stock and idempotence. Outer transaction always rolls back.
"""

from decimal import Decimal
from uuid import uuid4

from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import engine
from app.models import Household, HouseholdMember, InventoryItem, ShoppingList, ShoppingListItem, User
from app.services.shopping import ShoppingAccessError, purchase_and_stock

REQUIRED_TABLES = {
    "users", "households", "household_members", "inventory_items",
    "shopping_lists", "shopping_list_items",
}


def main() -> None:
    with engine.connect() as connection:
        inspector = inspect(connection)
        missing = REQUIRED_TABLES - set(inspector.get_table_names())
        if missing:
            raise RuntimeError("Missing tables: " + ", ".join(sorted(missing)))

        unique_constraints = inspector.get_unique_constraints("shopping_lists")
        if not any(
            c["name"] == "uq_shopping_lists_household_id" and c["column_names"] == ["household_id"]
            for c in unique_constraints
        ):
            raise RuntimeError("Missing one-list-per-household UNIQUE constraint")

    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                owner = User(
                    email=f"schema-smoke-{uuid4().hex}@example.invalid",
                    password_hash="NOT_A_REAL_PASSWORD_HASH_DO_NOT_USE",
                    display_name="Smoke Test Owner",
                )
                outsider = User(
                    email=f"schema-outsider-{uuid4().hex}@example.invalid",
                    password_hash="NOT_A_REAL_PASSWORD_HASH_DO_NOT_USE",
                    display_name="Smoke Test Outsider",
                )
                session.add_all([owner, outsider])
                session.flush()
                family = Household(name="temporary-shared-household", created_by_user_id=owner.id)
                session.add(family)
                session.flush()
                session.add(HouseholdMember(household_id=family.id, user_id=owner.id, role="owner"))
                shopping_list = ShoppingList(
                    household_id=family.id, name="Shared Shopping List", created_by_user_id=owner.id
                )
                session.add(shopping_list)
                session.flush()
                item = ShoppingListItem(
                    shopping_list_id=shopping_list.id,
                    name="Test Milk",
                    quantity=Decimal("2.000"), unit="瓶",
                    added_by_user_id=owner.id,
                )
                session.add(item)
                session.flush()

                # The same household cannot have two lists.
                try:
                    with session.begin_nested():
                        session.add(ShoppingList(
                            household_id=family.id, name="Forbidden Second List",
                            created_by_user_id=owner.id,
                        ))
                        session.flush()
                except IntegrityError:
                    pass
                else:
                    raise AssertionError("Second list was unexpectedly permitted")

                # A non-member must not be able to mark something purchased.
                try:
                    purchase_and_stock(
                        session, household_id=family.id,
                        shopping_item_id=item.id, actor_user_id=outsider.id
                    )
                except ShoppingAccessError:
                    pass
                else:
                    raise AssertionError("Non-member could purchase a household item")

                first = purchase_and_stock(
                    session, household_id=family.id,
                    shopping_item_id=item.id, actor_user_id=owner.id,
                    storage_location="冰箱",
                )
                second = purchase_and_stock(
                    session, household_id=family.id,
                    shopping_item_id=item.id, actor_user_id=owner.id,
                )
                assert first.newly_stocked and not second.newly_stocked
                assert first.inventory_item_id == second.inventory_item_id

                items = session.scalars(select(InventoryItem).where(
                    InventoryItem.source_shopping_list_item_id == item.id
                )).all()
                assert len(items) == 1, "Repeat purchase created duplicate stock"
                assert items[0].household_id == family.id
                assert items[0].quantity == Decimal("2.000")
                assert items[0].unit == "瓶"
                assert item.is_checked and item.checked_at and item.purchased_by_user_id == owner.id
                assert item.added_by_user_id == owner.id
                print("SCHEMA SMOKE PASSED: 6 tables, 1 shared list, attribution, atomic stock, idempotence, permission")
        finally:
            transaction.rollback()
            print("TEST DATA ROLLED BACK")


if __name__ == "__main__":
    main()
