"""Add conversation cursor and idempotent input receipts; retain existing tasks."""
import sqlalchemy as sa
from alembic import op

revision = "20261023_0008"
down_revision = "20261017_0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("ai_conversation_bindings",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("household_id", sa.Uuid(), sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("ai_tasks.id", ondelete="SET NULL")),
        sa.Column("reference_json", sa.JSON()),
        sa.Column("processing_nonce", sa.String(36)),
        sa.Column("lease_until", sa.DateTime(timezone=True)))
    op.create_table("ai_conversation_turns",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("household_id", sa.Uuid(), sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_id", sa.String(100), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("task_id", sa.Uuid(), sa.ForeignKey("ai_tasks.id", ondelete="SET NULL")),
        sa.Column("source_revision", sa.Integer()),
        sa.Column("binding_json", sa.JSON()),
        sa.Column("resolution_json", sa.JSON()),
        sa.Column("response_json", sa.JSON()),
        sa.Column("phase", sa.String(24), nullable=False),
        sa.Column("processing_nonce", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "household_id", "request_id", name="uq_conversation_request"))


def downgrade():
    for table in ("ai_conversation_turns", "ai_conversation_bindings"):
        if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM " + table)).scalar():
            raise RuntimeError("Conversation evidence exists; retain 0008 and roll back application only")
    op.drop_table("ai_conversation_turns")
    op.drop_table("ai_conversation_bindings")
