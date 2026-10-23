"""Extend execution checks for the existing OPEN/DISCARD inventory semantics.

No stock/event backfill, new columns, or changes to P2 conversation tables.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261023_0009"
down_revision = "20261023_0008"
branch_labels = None
depends_on = None

OLD_ACTIONS = "action IN ('ADD','MOVE','PLAN_ADD','CONSUME')"
NEW_ACTIONS = "action IN ('ADD','MOVE','PLAN_ADD','CONSUME','OPEN','DISCARD')"
OLD_TYPES = "event_type IN ('StockAdded','StockMoved','PlanAdded','Consumed')"
NEW_TYPES = "event_type IN ('StockAdded','StockMoved','PlanAdded','Consumed','Opened','Discarded')"
OLD_QUANTITY = "(event_type = 'StockMoved' AND quantity IS NULL) OR (event_type != 'StockMoved' AND quantity IS NOT NULL AND quantity > 0 AND quantity <= 1000000000)"
NEW_QUANTITY = "(event_type IN ('StockMoved','Opened') AND quantity IS NULL) OR (event_type NOT IN ('StockMoved','Opened') AND quantity IS NOT NULL AND quantity > 0 AND quantity <= 1000000000)"


def change_checks(actions, event_types, quantity):
    connection = op.get_bind()
    if connection.dialect.name == "sqlite" and connection.execute(sa.text(
            "SELECT COUNT(*) FROM draft_operations")).scalar():
        # SQLite's table-rebuild ALTER would drop a RESTRICT-referenced parent.
        # Never disable FK enforcement or risk audit rows to migrate a test DB.
        raise RuntimeError("Populated SQLite execution ledger cannot be rebuilt safely; use PostgreSQL for this migration")
    with op.batch_alter_table("business_events") as batch:
        batch.drop_constraint("ck_business_event_type", type_="check")
        batch.drop_constraint("ck_business_event_quantity", type_="check")
        batch.create_check_constraint("ck_business_event_type", event_types)
        batch.create_check_constraint("ck_business_event_quantity", quantity)
    with op.batch_alter_table("draft_operations") as batch:
        batch.drop_constraint("ck_operation_action", type_="check")
        batch.create_check_constraint("ck_operation_action", actions)


def upgrade():
    change_checks(NEW_ACTIONS, NEW_TYPES, NEW_QUANTITY)


def downgrade():
    connection = op.get_bind()
    new_operations = connection.execute(sa.text(
        "SELECT COUNT(*) FROM draft_operations WHERE action IN ('OPEN','DISCARD')")).scalar()
    new_events = connection.execute(sa.text(
        "SELECT COUNT(*) FROM business_events WHERE event_type IN ('Opened','Discarded')")).scalar()
    if new_operations or new_events:
        raise RuntimeError("OPEN/DISCARD audit data exists; keep 0009 and roll back application only")
    change_checks(OLD_ACTIONS, OLD_TYPES, OLD_QUANTITY)
