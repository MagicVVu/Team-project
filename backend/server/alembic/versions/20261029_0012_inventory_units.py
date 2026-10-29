"""One inventory row per physical item, with reversible legacy expansion.

Run with application writers stopped. The private backup table keeps the exact
pre-migration records; downgrade refuses to overwrite any later business write.
Historical event payloads and operation receipts are never rewritten.
"""
import copy
import hashlib
import json
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid5

from alembic import op
import sqlalchemy as sa

revision = '20261029_0012'
down_revision = '20261026_0011'
branch_labels = depends_on = None

BACKUP = 'inventory_unit_migration_backup'
MAX_BATCH_ITEMS = 10000
MAX_TOTAL_ITEMS = 1000000
MEASURE_UNITS = {'g', 'kg', 'mg', 'ml', 'l', 't', '克', '千克', '公斤', '毫克',
                 '毫升', '升', '吨', '斤', '两', '公升', '公克'}
RESTORED_TABLES = ('inventory_items', 'products', 'product_batches', 'inventory_planning_facts')
GUARDED_TABLES = (*RESTORED_TABLES, 'business_events', 'planning_fact_writes',
                  'mutation_receipts', 'draft_operations', 'draft_decisions',
                  'shopping_list_items', 'ai_drafts', 'ai_tasks')


def normalized(value):
    return unicodedata.normalize('NFKC', value).strip().casefold()


def matches(left, right):
    left, right = normalized(left), normalized(right)
    return bool(left and right and (left == right or
        {left[i:i+2] for i in range(len(left)-1)} &
        {right[i:i+2] for i in range(len(right)-1)}))


def amount(value):
    return format(Decimal(value), 'f').rstrip('0').rstrip('.') if '.' in format(Decimal(value), 'f') else str(value)


def expansion(row):
    """Terminal records remain historical; mass/volume represents one portion."""
    quantity = Decimal(row['quantity'])
    if not quantity.is_finite() or quantity < 0 or quantity > 1000000000:
        raise RuntimeError('Invalid legacy quantity for inventory item '+str(row['id']))
    measured = normalized(row['unit']) in MEASURE_UNITS
    fractional = quantity != quantity.to_integral_value()
    terminal = row['status'] != 'ACTIVE' or quantity == 0
    count = 1 if terminal or measured or fractional else int(quantity)
    if count > MAX_BATCH_ITEMS:
        raise RuntimeError('Legacy batch exceeds 10000 items: '+str(row['id']))
    specification = (amount(quantity) + row['unit']) if measured or fractional or (terminal and quantity > 0) else None
    return {'count': count, 'specification': specification,
            'unit': '份' if measured or fractional else row['unit'],
            'status': 'FINISHED' if row['status'] == 'ACTIVE' and quantity == 0 else row['status']}


def audit_rows(rows):
    total, portions, expanded = 0, 0, 0
    for row in rows:
        value = expansion(row)
        total += value['count']
        portions += value['unit'] == '份' and value['specification'] is not None
        expanded += value['count'] - 1
    if total > MAX_TOTAL_ITEMS:
        raise RuntimeError('Legacy expansion exceeds 1000000 total inventory items')
    return {'source_rows': len(rows), 'target_rows': total, 'additional_rows': expanded,
            'portion_rows': portions, 'max_batch_items': MAX_BATCH_ITEMS,
            'max_total_items': MAX_TOTAL_ITEMS}


def serial(value):
    if isinstance(value, (UUID, Decimal, date, datetime)):
        return str(value)
    raise TypeError(type(value).__name__)


def encoded(value):
    return json.loads(json.dumps(value, default=serial, ensure_ascii=False))


def table(bind, name):
    return sa.Table(name, sa.MetaData(), autoload_with=bind)


def snapshot(bind, name):
    rows = encoded([dict(row) for row in bind.execute(sa.select(table(bind, name))).mappings()])
    return sorted(rows, key=lambda row: json.dumps(row, sort_keys=True, ensure_ascii=False))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def restore_values(target, values):
    result = dict(values)
    for column in target.columns:
        value = result.get(column.name)
        if value is None:
            continue
        if isinstance(column.type, sa.Uuid):
            result[column.name] = UUID(value)
        elif isinstance(column.type, sa.Numeric):
            result[column.name] = Decimal(value)
        elif isinstance(column.type, sa.DateTime):
            result[column.name] = datetime.fromisoformat(value)
        elif isinstance(column.type, sa.Date):
            result[column.name] = date.fromisoformat(value)
    return result


def invalidated_facts(value):
    facts = copy.deepcopy(value)
    for entry in facts.get('coverage', {}).values():
        if isinstance(entry, dict):
            entry['day_hash'] = 'inventory-unit-migration:'+str(entry.get('day_hash', ''))
    return facts


def grouped_products(bind):
    """Deterministic shortest-name representatives, scoped to one household."""
    products, links, inventory = (table(bind, name) for name in ('products', 'product_batches', 'inventory_items'))
    events = table(bind, 'business_events')
    users = table(bind, 'users')
    homes = {row['id']: row for row in bind.execute(sa.select(table(bind, 'households'))).mappings()}
    user_ids = set(bind.scalars(sa.select(users.c.id)))
    all_products = [dict(row) for row in bind.execute(sa.select(products)).mappings()]
    all_products.sort(key=lambda p: (str(p['household_id']), len(p['name']), normalized(p['name']), str(p['id'])))
    canonical = {}
    remaps = {}
    for product in all_products:
        if normalized(product['base_unit']) in MEASURE_UNITS:
            product['base_unit'] = '份'
            bind.execute(products.update().where(products.c.id == product['id']).values(base_unit='份'))
        options = canonical.setdefault(product['household_id'], [])
        found = sorted([p for p in options if matches(p['name'], product['name'])],
            key=lambda p: (normalized(p['name']) != normalized(product['name']), len(p['name']),
                           normalized(p['name']), str(p['id'])))
        if found:
            remaps[product['id']] = found[0]['id']
        else:
            options.append(product)
    for old, new in remaps.items():
        bind.execute(links.update().where(links.c.product_id == old).values(product_id=new))
        bind.execute(events.update().where(events.c.product_id == old).values(product_id=new))
        bind.execute(products.delete().where(products.c.id == old))
    linked = set(bind.scalars(sa.select(links.c.inventory_item_id)))
    rows = [dict(row) for row in bind.execute(sa.select(inventory)).mappings()]
    rows.sort(key=lambda r: (str(r['household_id']), len(r['name']), normalized(r['name']), str(r['id'])))
    for row in rows:
        if row['id'] in linked:
            continue
        options = canonical.setdefault(row['household_id'], [])
        found = sorted([p for p in options if matches(p['name'], row['name'])],
            key=lambda p: (normalized(p['name']) != normalized(row['name']), len(p['name']),
                           normalized(p['name']), str(p['id'])))
        actor = row['created_by_user_id'] or homes[row['household_id']]['created_by_user_id']
        if actor not in user_ids:
            raise RuntimeError('Cannot attribute product migration: '+str(row['id']))
        if found:
            product = found[0]
        else:
            product = {'id': uuid5(row['id'], 'inventory-unit-product'), 'household_id': row['household_id'],
                'name': row['name'], 'specification': None, 'base_unit': row['unit'],
                'category': {'食品': 'food', 'food': 'food', '药品': 'medicine', 'medicine': 'medicine',
                    '日用品': 'household', 'household': 'household'}.get(row['category'], 'unknown'),
                'tags_json': [], 'source': 'inventory_unit_migration', 'actor_user_id': actor,
                'version': 1, 'created_at': row['created_at']}
            bind.execute(products.insert().values(**product))
            options.append(product)
        bind.execute(links.insert().values(inventory_item_id=row['id'], product_id=product['id'],
            source='inventory_unit_migration', actor_user_id=actor, created_at=row['created_at']))
    # A former fractional count (for example half a box) is now one portion
    # too. Only change a product's count unit when all its physical members
    # use portions; mixed whole packages retain their original package unit.
    units_by_product = {}
    for product_id, unit in bind.execute(sa.select(links.c.product_id, inventory.c.unit)
            .join(inventory, inventory.c.id == links.c.inventory_item_id)):
        units_by_product.setdefault(product_id, set()).add(unit)
    for product_id, units in units_by_product.items():
        if units == {'份'}:
            bind.execute(products.update().where(products.c.id == product_id).values(base_unit='份'))
    # Existing product quantities are now item counts as well. Invalidate product
    # revisions so pending identity choices cannot refer to the old batch model.
    bind.execute(products.update().values(version=products.c.version+1))
    return len(remaps)


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        # Prevent concurrent writes from creating an incomplete snapshot. The
        # release also stops application containers before invoking Alembic.
        bind.execute(sa.text('LOCK TABLE '+', '.join(GUARDED_TABLES)+' IN ACCESS EXCLUSIVE MODE'))
    before = {name: snapshot(bind, name) for name in RESTORED_TABLES}
    event_table = table(bind, 'business_events')
    before['event_products'] = encoded([{'id': row['id'], 'product_id': row['product_id']}
        for row in bind.execute(sa.select(event_table.c.id, event_table.c.product_id)
                                .order_by(event_table.c.id)).mappings()])
    audit = audit_rows(before['inventory_items'])
    op.create_table(BACKUP, sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('payload_json', sa.JSON(), nullable=False))
    # An intake operation creates one event for each physical item. Preserve
    # operation/request foreign keys while allowing their one-to-many events.
    event_uniques = sa.inspect(bind).get_unique_constraints('business_events')
    changed_uniques = [entry for entry in event_uniques
                       if entry['column_names'] in (['operation_id'], ['request_id'])]
    with op.batch_alter_table('business_events') as batch:
        for entry in changed_uniques:
            batch.drop_constraint(entry['name'], type_='unique')
        batch.create_index('ix_business_events_operation_id', ['operation_id'])
        batch.create_index('ix_business_events_request_id', ['request_id'])
    with op.batch_alter_table('inventory_items') as batch:
        batch.add_column(sa.Column('specification', sa.String(200), nullable=True))
        batch.drop_constraint('uq_inventory_source_shopping_item', type_='unique')
    if bind.dialect.name != 'sqlite':
        op.alter_column('products', 'name', type_=sa.String(200), existing_type=sa.String(80))
    inventory = table(bind, 'inventory_items')
    links, facts = table(bind, 'product_batches'), table(bind, 'inventory_planning_facts')
    links_by_id = {row['inventory_item_id']: dict(row) for row in bind.execute(sa.select(links)).mappings()}
    facts_by_id = {row['inventory_item_id']: dict(row) for row in bind.execute(sa.select(facts)).mappings()}
    for original in before['inventory_items']:
        row = restore_values(inventory, original)
        converted = expansion(row)
        changes = {key: converted[key] for key in ('specification', 'unit', 'status')}
        changes['version'] = row['version']+1
        # Quantity exists only until the final DDL step, which lets old NOT NULL
        # and range constraints continue to protect the transitional inserts.
        bind.execute(inventory.update().where(inventory.c.id == row['id']).values(**changes))
        if row['id'] in facts_by_id:
            bind.execute(facts.update().where(facts.c.inventory_item_id == row['id'])
                .values(facts_json=invalidated_facts(facts_by_id[row['id']]['facts_json'])))
        for ordinal in range(1, converted['count']):
            new_id = uuid5(row['id'], 'inventory-unit:'+str(ordinal))
            cloned = {**row, **changes, 'id': new_id, 'version': 1, 'quantity': Decimal(1)}
            bind.execute(inventory.insert().values(**cloned))
            if row['id'] in links_by_id:
                bind.execute(links.insert().values(**{**links_by_id[row['id']], 'inventory_item_id': new_id}))
            if row['id'] in facts_by_id:
                bind.execute(facts.insert().values(**{**facts_by_id[row['id']], 'inventory_item_id': new_id,
                    'facts_json': invalidated_facts(facts_by_id[row['id']]['facts_json'])}))
    merged = grouped_products(bind)
    with op.batch_alter_table('inventory_items') as batch:
        batch.drop_constraint('ck_inventory_items_quantity_nonnegative', type_='check')
        batch.drop_constraint('ck_inventory_items_quantity_ai_max', type_='check')
        batch.drop_column('quantity')
    after = {name: digest(snapshot(bind, name)) for name in GUARDED_TABLES}
    bind.execute(table(bind, BACKUP).insert().values(id=1,
        payload_json={'before': before, 'after': after, 'event_uniques': changed_uniques,
                      'audit': {**audit, 'merged_products': merged}}))


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        bind.execute(sa.text('LOCK TABLE '+', '.join(GUARDED_TABLES)+' IN ACCESS EXCLUSIVE MODE'))
    backup_table = table(bind, BACKUP)
    backup = bind.execute(sa.select(backup_table.c.payload_json).where(backup_table.c.id == 1)).scalar_one()
    for name, expected in backup['after'].items():
        if digest(snapshot(bind, name)) != expected:
            raise RuntimeError('Inventory unit migration has later business writes in '+name+
                '; retain 0012 and use the pre-release database backup for a coordinated rollback')
    before = backup['before']
    op.add_column('inventory_items', sa.Column('quantity', sa.Numeric(16, 6), nullable=True))
    inventory = table(bind, 'inventory_items')
    links, facts = table(bind, 'product_batches'), table(bind, 'inventory_planning_facts')
    events, products = table(bind, 'business_events'), table(bind, 'products')
    bind.execute(links.delete())
    bind.execute(facts.delete())
    bind.execute(events.update().values(product_id=None))
    original_ids = {UUID(row['id']) for row in before['inventory_items']}
    current_ids = set(bind.scalars(sa.select(inventory.c.id)))
    for item_id in current_ids-original_ids:
        bind.execute(inventory.delete().where(inventory.c.id == item_id))
    for row in before['inventory_items']:
        values = restore_values(inventory, row)
        bind.execute(inventory.update().where(inventory.c.id == values['id']).values(**values))
    bind.execute(products.delete())
    for row in before['products']:
        bind.execute(products.insert().values(**restore_values(products, row)))
    for target, rows in ((links, before['product_batches']), (facts, before['inventory_planning_facts'])):
        for row in rows:
            bind.execute(target.insert().values(**restore_values(target, row)))
    for row in before['event_products']:
        bind.execute(events.update().where(events.c.id == UUID(row['id']))
                     .values(product_id=UUID(row['product_id']) if row['product_id'] else None))
    with op.batch_alter_table('inventory_items') as batch:
        batch.drop_column('specification')
        batch.alter_column('quantity', nullable=False)
        batch.create_check_constraint('ck_inventory_items_quantity_nonnegative', 'quantity >= 0')
        batch.create_check_constraint('ck_inventory_items_quantity_ai_max', 'quantity <= 1000000000')
        batch.create_unique_constraint('uq_inventory_source_shopping_item', ['source_shopping_list_item_id'])
    if bind.dialect.name != 'sqlite':
        op.alter_column('products', 'name', type_=sa.String(80), existing_type=sa.String(200))
    with op.batch_alter_table('business_events') as batch:
        batch.drop_index('ix_business_events_operation_id')
        batch.drop_index('ix_business_events_request_id')
        for entry in backup['event_uniques']:
            batch.create_unique_constraint(entry['name'], entry['column_names'])
    op.drop_table(BACKUP)
