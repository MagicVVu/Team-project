"""P9 additive product identity, permanent CRUD receipts and shared event ledger.

No name-based grouping and no history_json-to-consumption backfill.
Rollback refuses to delete P9 evidence; roll back application while retaining schema.
"""
from alembic import op
import sqlalchemy as sa

revision = '20261026_0011'
down_revision = '20261023_0010'
branch_labels = depends_on = None

OLD_TYPES = "event_type IN ('StockAdded','StockMoved','PlanAdded','Consumed','Opened','Discarded')"
OLD_QUANTITY = "(event_type IN ('StockMoved','Opened') AND quantity IS NULL) OR (event_type NOT IN ('StockMoved','Opened') AND quantity IS NOT NULL AND quantity > 0 AND quantity <= 1000000000)"
NEW_TYPES = "event_type IN ('StockAdded','StockMoved','PlanAdded','Consumed','Opened','Discarded','Created','Adjusted','Purchased','Edited','Corrected','ProductLinked','Counted','Archived')"
NEW_QUANTITY = "(event_type IN ('StockMoved','Opened') AND quantity IS NULL) OR (event_type IN ('StockAdded','PlanAdded','Consumed','Discarded') AND quantity IS NOT NULL AND quantity > 0 AND quantity <= 1000000000) OR (event_type IN ('Created','Adjusted','Purchased','Edited','Corrected','ProductLinked','Counted','Archived') AND (quantity IS NULL OR (quantity >= 0 AND quantity <= 1000000000)))"


def upgrade():
    op.create_table('products',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('household_id', sa.Uuid(), sa.ForeignKey('households.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('name', sa.String(80), nullable=False), sa.Column('specification', sa.String(200)),
        sa.Column('base_unit', sa.String(30), nullable=False), sa.Column('category', sa.String(20), nullable=False),
        sa.Column('tags_json', sa.JSON(), nullable=False), sa.Column('source', sa.String(200), nullable=False),
        sa.Column('actor_user_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index('ix_products_household_id', 'products', ['household_id'])
    op.create_table('product_batches',
        sa.Column('inventory_item_id', sa.Uuid(), sa.ForeignKey('inventory_items.id', ondelete='RESTRICT'), primary_key=True),
        sa.Column('product_id', sa.Uuid(), sa.ForeignKey('products.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('source', sa.String(200), nullable=False),
        sa.Column('actor_user_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index('ix_product_batches_product_id', 'product_batches', ['product_id'])
    op.create_table('mutation_receipts',
        sa.Column('operation_id', sa.Uuid(), primary_key=True),
        sa.Column('household_id', sa.Uuid(), sa.ForeignKey('households.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('actor_user_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('request_hash', sa.String(64), nullable=False), sa.Column('response_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index('ix_mutation_receipts_household_id', 'mutation_receipts', ['household_id'])
    op.add_column('business_events', sa.Column('created_at', sa.DateTime(timezone=True)))
    op.execute('UPDATE business_events SET created_at = draft_operations.committed_at FROM draft_operations WHERE business_events.operation_id = draft_operations.id')
    with op.batch_alter_table('business_events') as batch:
        batch.add_column(sa.Column('request_id', sa.Uuid()))
        batch.add_column(sa.Column('related_event_id', sa.Uuid()))
        batch.add_column(sa.Column('product_id', sa.Uuid()))
        batch.create_foreign_key('fk_business_events_request', 'mutation_receipts', ['request_id'], ['operation_id'], ondelete='RESTRICT')
        batch.create_foreign_key('fk_business_events_related', 'business_events', ['related_event_id'], ['id'], ondelete='RESTRICT')
        batch.create_foreign_key('fk_business_events_product', 'products', ['product_id'], ['id'], ondelete='RESTRICT')
        batch.create_unique_constraint('uq_business_events_request_id', ['request_id'])
        batch.alter_column('created_at', nullable=False, server_default=sa.func.now())
        batch.alter_column('operation_id', nullable=True)
        for name in ('ck_business_event_type', 'ck_business_event_quantity'):
            batch.drop_constraint(name, type_='check')
        batch.create_check_constraint('ck_business_event_type', NEW_TYPES)
        batch.create_check_constraint('ck_business_event_quantity', NEW_QUANTITY)


def downgrade():
    bind = op.get_bind()
    for table in ('products', 'product_batches', 'mutation_receipts'):
        if bind.execute(sa.text('SELECT COUNT(*) FROM '+table)).scalar():
            raise RuntimeError('P9 evidence exists; retain 0011 and roll back application only')
    if bind.execute(sa.text('SELECT COUNT(*) FROM business_events WHERE operation_id IS NULL OR related_event_id IS NOT NULL OR product_id IS NOT NULL')).scalar():
        raise RuntimeError('P9 ledger evidence exists; retain 0011')
    with op.batch_alter_table('business_events') as batch:
        for name in ('ck_business_event_type', 'ck_business_event_quantity'):
            batch.drop_constraint(name, type_='check')
        batch.create_check_constraint('ck_business_event_type', OLD_TYPES)
        batch.create_check_constraint('ck_business_event_quantity', OLD_QUANTITY)
        batch.alter_column('operation_id', nullable=False)
        for name in ('fk_business_events_request', 'fk_business_events_related', 'fk_business_events_product'):
            batch.drop_constraint(name, type_='foreignkey')
        batch.drop_constraint('uq_business_events_request_id', type_='unique')
        for name in ('created_at', 'product_id', 'related_event_id', 'request_id'):
            batch.drop_column(name)
    for table in ('mutation_receipts', 'product_batches', 'products'):
        op.drop_table(table)
