"""Expand existing execution ledger without rewriting inventory or history."""
from alembic import op
import sqlalchemy as sa

revision = '20261020_0008'
down_revision = '20261017_0007'
branch_labels = None
depends_on = None


def constraints(expanded):
    actions = "'ADD','MOVE','PLAN_ADD','CONSUME'" + (",'OPEN','DISCARD'" if expanded else '')
    events = "'StockAdded','StockMoved','PlanAdded','Consumed'" + (",'Opened','Discarded'" if expanded else '')
    no_quantity = "'StockMoved','Opened'" if expanded else "'StockMoved'"
    with op.batch_alter_table('draft_operations') as batch:
        batch.drop_constraint('ck_operation_action', type_='check')
        batch.create_check_constraint('ck_operation_action', f'action IN ({actions})')
    with op.batch_alter_table('business_events') as batch:
        batch.drop_constraint('ck_business_event_type', type_='check')
        batch.drop_constraint('ck_business_event_quantity', type_='check')
        batch.create_check_constraint('ck_business_event_type', f'event_type IN ({events})')
        batch.create_check_constraint('ck_business_event_quantity',
            f'(event_type IN ({no_quantity}) AND quantity IS NULL) OR '
            f'(event_type NOT IN ({no_quantity}) AND quantity IS NOT NULL AND quantity > 0 AND quantity <= 1000000000)')


def upgrade():
    constraints(True)


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT COUNT(*) FROM draft_operations WHERE action IN ('OPEN','DISCARD')")).scalar():
        raise RuntimeError('OPEN/DISCARD audit exists; retain 0008 when rolling back the application')
    constraints(False)
