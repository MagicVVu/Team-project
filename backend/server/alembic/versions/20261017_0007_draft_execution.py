"""Add durable draft decisions, operation receipts and semantic business events."""
import sqlalchemy as sa
from alembic import op

revision = "20261017_0007"
down_revision = "20261016_0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("draft_operations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("draft_id", sa.Uuid(), sa.ForeignKey("ai_drafts.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("household_id", sa.Uuid(), sa.ForeignKey("households.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("draft_revision", sa.Integer(), nullable=False),
        sa.Column("task_revision", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("command_json", sa.JSON(), nullable=False),
        sa.Column("receipt_json", sa.JSON(), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("draft_revision >= 1 AND task_revision >= 1", name="ck_operation_revisions"),
        sa.CheckConstraint("action IN ('ADD','MOVE','PLAN_ADD','CONSUME')", name="ck_operation_action"))
    op.create_index("ix_draft_operations_household_id", "draft_operations", ["household_id"])
    op.create_table("draft_decisions",
        sa.Column("draft_id", sa.Uuid(), sa.ForeignKey("ai_drafts.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("draft_revision", sa.Integer(), nullable=False),
        sa.Column("task_revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("operation_id", sa.Uuid(), sa.ForeignKey("draft_operations.id", ondelete="RESTRICT"), unique=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("draft_revision >= 1 AND task_revision >= 1", name="ck_decision_revisions"),
        sa.CheckConstraint("(status = 'committed' AND operation_id IS NOT NULL) OR (status = 'cancelled' AND operation_id IS NULL)", name="ck_decision_status"))
    op.create_table("business_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("operation_id", sa.Uuid(), sa.ForeignKey("draft_operations.id", ondelete="RESTRICT"), unique=True, nullable=False),
        sa.Column("household_id", sa.Uuid(), sa.ForeignKey("households.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("inventory_item_id", sa.Uuid(), sa.ForeignKey("inventory_items.id", ondelete="RESTRICT")),
        sa.Column("shopping_item_id", sa.Uuid(), sa.ForeignKey("shopping_list_items.id", ondelete="SET NULL")),
        sa.Column("event_type", sa.String(24), nullable=False),
        sa.Column("quantity", sa.Numeric(16, 6)),
        sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("before_json", sa.JSON(), nullable=False),
        sa.Column("after_json", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("event_type IN ('StockAdded','StockMoved','PlanAdded','Consumed')", name="ck_business_event_type"),
        sa.CheckConstraint("(event_type = 'StockMoved' AND quantity IS NULL) OR (event_type != 'StockMoved' AND quantity IS NOT NULL AND quantity > 0 AND quantity <= 1000000000)", name="ck_business_event_quantity"))
    op.create_index("ix_business_events_household_id", "business_events", ["household_id"])


def downgrade():
    # An application rollback keeps this additive schema. Never discard receipts.
    connection = op.get_bind()
    for name in ("business_events", "draft_decisions", "draft_operations"):
        if connection.execute(sa.text("SELECT COUNT(*) FROM " + name)).scalar():
            raise RuntimeError("Execution audit data exists; retain 0007 or restore an isolated backup")
    op.drop_index("ix_business_events_household_id", table_name="business_events")
    op.drop_table("business_events")
    op.drop_table("draft_decisions")
    op.drop_index("ix_draft_operations_household_id", table_name="draft_operations")
    op.drop_table("draft_operations")
