"""App inventory metadata and shopping source references (additive)."""
import sqlalchemy as sa
from alembic import op

revision = "20261016_0006"
down_revision = "20261014_0005"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("inventory_items") as batch:
        batch.add_column(sa.Column("minimum_quantity", sa.Numeric(16, 6), nullable=False, server_default="0"))
        batch.add_column(sa.Column("history_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
        batch.create_check_constraint("ck_inventory_minimum_range", "minimum_quantity >= 0 AND minimum_quantity <= 1000000000")
    with op.batch_alter_table("shopping_list_items") as batch:
        batch.add_column(sa.Column("source_inventory_item_id", sa.Uuid(as_uuid=True), nullable=True))
        batch.create_foreign_key("fk_shopping_source_inventory", "inventory_items", ["source_inventory_item_id"], ["id"], ondelete="SET NULL")


def downgrade():
    with op.batch_alter_table("shopping_list_items") as batch:
        batch.drop_constraint("fk_shopping_source_inventory", type_="foreignkey")
        batch.drop_column("source_inventory_item_id")
    with op.batch_alter_table("inventory_items") as batch:
        batch.drop_constraint("ck_inventory_minimum_range", type_="check")
        batch.drop_column("history_json")
        batch.drop_column("minimum_quantity")
