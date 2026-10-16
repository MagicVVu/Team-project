"""One shopping list per household; audit who added/purchased; stock once.

Revision ID: 20261014_0002
Revises: 20261014_0001
Create Date: 2026-10-14

Keep the original 0001 revision unchanged so deployments that already ran
0001 can migrate safely. If duplicate lists already exist, stop and reconcile
manually instead of silently deleting a family's shopping entries.
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20261014_0002"
down_revision: str | None = "20261014_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    duplicates = bind.execute(
        sa.text(
            "SELECT household_id, count(*) AS n FROM shopping_lists "
            "GROUP BY household_id HAVING count(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicates:
        raise RuntimeError(
            "Cannot enforce one shared shopping list per household: "
            "some households already have multiple lists. "
            "Back up and merge their shopping_list_items before retrying."
        )

    # Batch operations work on PostgreSQL and also support SQLite test migrations.
    with op.batch_alter_table("shopping_lists") as batch_op:
        batch_op.create_unique_constraint(
            "uq_shopping_lists_household_id", ["household_id"]
        )

    with op.batch_alter_table("shopping_list_items") as batch_op:
        batch_op.add_column(sa.Column("added_by_user_id", sa.Uuid(as_uuid=True), nullable=True))
        batch_op.add_column(sa.Column("purchased_by_user_id", sa.Uuid(as_uuid=True), nullable=True))
        batch_op.create_foreign_key(
            "fk_shopping_item_added_by", "users", ["added_by_user_id"], ["id"], ondelete="SET NULL"
        )
        batch_op.create_foreign_key(
            "fk_shopping_item_purchased_by", "users", ["purchased_by_user_id"], ["id"], ondelete="SET NULL"
        )

    with op.batch_alter_table("inventory_items") as batch_op:
        batch_op.add_column(sa.Column("source_shopping_list_item_id", sa.Uuid(as_uuid=True), nullable=True))
        batch_op.create_foreign_key(
            "fk_inventory_source_shopping_item", "shopping_list_items",
            ["source_shopping_list_item_id"], ["id"], ondelete="SET NULL",
        )
        batch_op.create_unique_constraint(
            "uq_inventory_source_shopping_item", ["source_shopping_list_item_id"]
        )


def downgrade() -> None:
    """Only for empty/test environments; drops purchase-attribution metadata."""
    with op.batch_alter_table("inventory_items") as batch_op:
        batch_op.drop_constraint("uq_inventory_source_shopping_item", type_="unique")
        batch_op.drop_constraint("fk_inventory_source_shopping_item", type_="foreignkey")
        batch_op.drop_column("source_shopping_list_item_id")
    with op.batch_alter_table("shopping_list_items") as batch_op:
        batch_op.drop_constraint("fk_shopping_item_purchased_by", type_="foreignkey")
        batch_op.drop_constraint("fk_shopping_item_added_by", type_="foreignkey")
        batch_op.drop_column("purchased_by_user_id")
        batch_op.drop_column("added_by_user_id")
    with op.batch_alter_table("shopping_lists") as batch_op:
        batch_op.drop_constraint("uq_shopping_lists_household_id", type_="unique")
