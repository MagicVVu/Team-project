"""Expand v0.4 inventory batches for P1 read-only AI tools.

Revision ID: 20261014_0004
Revises: 20261014_0003

Preserves original inventory IDs, household membership, shopping provenance,
original locations, dates, and units. Zero-quantity legacy records have no
lifecycle provenance, so FINISHED is only a provisional legacy classification.
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20261014_0004"
down_revision: str | None = "20261014_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NUMERIC(12,3) -> NUMERIC(16,6) keeps all existing values exact.
    # Batch alter makes the test migration work on both SQLite and PostgreSQL.
    with op.batch_alter_table("inventory_items") as batch:
        batch.alter_column(
            "quantity", existing_type=sa.Numeric(12, 3),
            type_=sa.Numeric(16, 6), existing_nullable=False,
        )
        batch.add_column(sa.Column("opened_at", sa.Date(), nullable=True))
        batch.add_column(sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'ACTIVE'")))
        batch.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")))
        batch.create_check_constraint("ck_inventory_items_quantity_ai_max", "quantity <= 1000000000")
        batch.create_check_constraint("ck_inventory_items_version_positive", "version >= 1")
        batch.create_check_constraint(
            "ck_inventory_items_status", "status IN ('ACTIVE', 'FINISHED', 'DISCARDED', 'REVERSED')"
        )
    # No historic events in v0.4: zero stock cannot be distinguished as consumed
    # vs discarded. Use FINISHED pending manual reconciliation; never invent events.
    op.execute("UPDATE inventory_items SET status = 'FINISHED' WHERE quantity = 0")


def downgrade() -> None:
    """Local-only. Downgrading discards version/opened_at/status and may lose precision.

    Never invoke on a deployed system with changed inventory; restore from the
    verified PostgreSQL backup only after an incident-response assessment.
    """
    with op.batch_alter_table("inventory_items") as batch:
        batch.drop_constraint("ck_inventory_items_status", type_="check")
        batch.drop_constraint("ck_inventory_items_version_positive", type_="check")
        batch.drop_constraint("ck_inventory_items_quantity_ai_max", type_="check")
        batch.drop_column("version")
        batch.drop_column("status")
        batch.drop_column("opened_at")
        batch.alter_column("quantity", existing_type=sa.Numeric(16, 6), type_=sa.Numeric(12, 3), existing_nullable=False)
