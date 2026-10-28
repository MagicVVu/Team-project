"""Persist planning observations and retry receipts; no historical facts inferred."""
from alembic import op
import sqlalchemy as sa

revision = "20261023_0010"
down_revision = "20261023_0009"
branch_labels = depends_on = None


def upgrade():
    op.create_table("inventory_planning_facts",
        sa.Column("inventory_item_id", sa.Uuid(), sa.ForeignKey("inventory_items.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("facts_json", sa.JSON(), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_planning_facts_version"))
    op.create_table("planning_fact_writes",
        sa.Column("operation_id", sa.Uuid(), primary_key=True),
        sa.Column("inventory_item_id", sa.Uuid(), sa.ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("household_id", sa.Uuid(), sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_planning_fact_writes_inventory_item_id", "planning_fact_writes", ["inventory_item_id"])


def downgrade():
    for table in ("planning_fact_writes", "inventory_planning_facts"):
        if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM " + table)).scalar():
            raise RuntimeError("Planning evidence exists; retain 0010 and roll back the application only")
    op.drop_table("planning_fact_writes")
    op.drop_table("inventory_planning_facts")
