"""Frozen migration rules and real PostgreSQL round trips, without app models.

Set INVENTORY_UNITS_TEST_DATABASE_URL to an explicitly isolated *test* database.
Every case runs in a random schema and rolls the whole schema back on completion.
"""
import importlib.util
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

VERSIONS = Path(__file__).resolve().parents[1] / 'alembic/versions'


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = load(VERSIONS / '20261029_0012_inventory_units.py')


def legacy(quantity, unit='个', status='ACTIVE'):
    return {'id': uuid4(), 'quantity': Decimal(quantity), 'unit': unit, 'status': status}


def test_expansion_counts_portions_and_terminal_records():
    assert migration.expansion(legacy('10')) == {
        'count': 10, 'specification': None, 'unit': '个', 'status': 'ACTIVE'}
    assert migration.expansion(legacy('1.500000', 'L')) == {
        'count': 1, 'specification': '1.5L', 'unit': '份', 'status': 'ACTIVE'}
    assert migration.expansion(legacy('0.5'))['specification'] == '0.5个'
    assert migration.expansion(legacy('500000', 'g'))['count'] == 1
    assert migration.expansion(legacy('0'))['status'] == 'FINISHED'
    assert migration.expansion(legacy('4', status='DISCARDED')) == {
        'count': 1, 'specification': '4个', 'unit': '个', 'status': 'DISCARDED'}


def test_audit_refuses_unbounded_expansion_without_rounding():
    with pytest.raises(RuntimeError, match='exceeds 10000'):
        migration.audit_rows([legacy('10001')])
    with pytest.raises(RuntimeError, match='Invalid legacy quantity'):
        migration.audit_rows([legacy('-1')])
    with pytest.raises(RuntimeError, match='exceeds 1000000'):
        migration.audit_rows([legacy('10000') for _ in range(101)])
    assert migration.audit_rows([legacy('10'), legacy('12'), legacy('1.5', 'L')])['target_rows'] == 23


def test_name_rule_is_normalized_contiguous_and_scoped_by_caller():
    assert migration.matches('苹果', '红苹果')
    assert migration.matches('A', ' a ')
    assert migration.matches('ＡＢ', 'ab')
    assert not migration.matches('苹果', '苹大果')
    assert not migration.matches('苹果', '苹梨')
    assert not migration.matches('', '')


def test_planning_facts_preserve_provenance_but_invalidate_batch_coverage():
    facts = {'coverage': {'2026-10-01': {'day_hash': 'old', 'source': 'person',
        'value': {'records_complete': True}}}, 'risk_facts': {'source': 'person'}}
    updated = migration.invalidated_facts(facts)
    assert updated['coverage']['2026-10-01']['day_hash'] == 'inventory-unit-migration:old'
    assert updated['coverage']['2026-10-01']['value']['records_complete'] is True
    assert updated['risk_facts'] == facts['risk_facts']
    assert facts['coverage']['2026-10-01']['day_hash'] == 'old'


@pytest.fixture
def pg():
    url = os.getenv('INVENTORY_UNITS_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Dedicated PostgreSQL migration database not requested')
    parsed = sa.make_url(url)
    assert parsed.drivername.startswith('postgresql') and 'test' in parsed.database
    engine = sa.create_engine(url)
    connection = engine.connect()
    transaction = connection.begin()
    schema = 'unit_migration_'+uuid4().hex
    connection.execute(sa.text('CREATE SCHEMA "'+schema+'"'))
    connection.execute(sa.text('SET LOCAL search_path TO "'+schema+'"'))
    context = MigrationContext.configure(connection)
    prior = sorted(path for path in VERSIONS.glob('*.py') if path.name != '20261029_0012_inventory_units.py')
    try:
        with Operations.context(context):
            for path in prior:
                load(path).upgrade()
        yield connection, context
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()


def seed(connection):
    t = lambda name: migration.table(connection, name)
    ids = {name: uuid4() for name in ('user', 'home', 'foreign_home', 'shopping_list', 'shopping',
        'apple', 'red_apple', 'milk', 'fraction', 'discarded', 'zero', 'foreign_apple',
        'apple_product', 'red_product', 'milk_product', 'fraction_product', 'foreign_product', 'event')}
    at = datetime(2026, 10, 29, 1, 2, 3, tzinfo=timezone.utc)
    connection.execute(t('users').insert().values(id=ids['user'], email='units@example.invalid',
        password_hash='synthetic', display_name='Unit migration'))
    connection.execute(t('households').insert(), [dict(id=ids[name], name=name,
        created_by_user_id=ids['user']) for name in ('home', 'foreign_home')])
    connection.execute(t('shopping_lists').insert().values(id=ids['shopping_list'], household_id=ids['home'],
        name='Synthetic', created_by_user_id=ids['user']))
    connection.execute(t('shopping_list_items').insert().values(id=ids['shopping'],
        shopping_list_id=ids['shopping_list'], name='苹果', quantity=Decimal(10), unit='个',
        added_by_user_id=ids['user']))
    items = []
    for key, name, quantity, unit, status in (
        ('apple', '苹果', '10', '个', 'ACTIVE'), ('red_apple', '红苹果', '12', '个', 'ACTIVE'),
        ('milk', '牛奶', '1.5', 'L', 'ACTIVE'), ('fraction', '旧半个', '0.5', '个', 'ACTIVE'),
        ('discarded', '废弃物', '4', '个', 'DISCARDED'), ('zero', '空库存', '0', '盒', 'ACTIVE'),
        ('foreign_apple', '苹果', '2', '个', 'ACTIVE')):
        items.append(dict(id=ids[key], household_id=ids['foreign_home'] if key == 'foreign_apple' else ids['home'],
            name=name, quantity=Decimal(quantity), unit=unit, status=status, version=4,
            category='食品', minimum_quantity=Decimal(0), history_json=[{'message': 'old batch'}],
            opened_at=None, purchased_on=at.date(), expires_on=at.date(),
            created_by_user_id=ids['user'], created_at=at, updated_at=at,
            storage_location='冰箱', source_shopping_list_item_id=ids['shopping'] if key == 'apple' else None))
    connection.execute(t('inventory_items').insert(), items)
    for key, item, name, unit in (('apple_product', 'apple', '苹果', '个'),
        ('red_product', 'red_apple', '红苹果', '个'), ('milk_product', 'milk', '牛奶', 'L'),
        ('fraction_product', 'fraction', '旧半个', '个'),
        ('foreign_product', 'foreign_apple', '苹果', '个')):
        connection.execute(t('products').insert().values(id=ids[key],
            household_id=ids['foreign_home'] if key == 'foreign_product' else ids['home'], name=name,
            base_unit=unit, category='food', tags_json=['original'], source='old grouping',
            actor_user_id=ids['user'], version=2))
        connection.execute(t('product_batches').insert().values(inventory_item_id=ids[item],
            product_id=ids[key], source='old grouping', actor_user_id=ids['user']))
    connection.execute(t('inventory_planning_facts').insert().values(inventory_item_id=ids['apple'], version=3,
        facts_json={'coverage': {'2026-10-01': {'day_hash': 'old', 'source': 'person'}},
                    'stock_verification': {'inventory_identity': {'quantity': '10', 'version': 4}}}))
    connection.execute(t('business_events').insert().values(id=ids['event'],
        household_id=ids['home'], actor_user_id=ids['user'], inventory_item_id=ids['red_apple'],
        event_type='Created', quantity=Decimal(12), unit='个', before_json={},
        after_json={'quantity': '12', 'name': '红苹果'}, product_id=ids['red_product'],
        occurred_at=at, created_at=at))
    return ids


def migrate(connection, context, direction):
    with Operations.context(context):
        getattr(migration, direction)()


def test_postgres_expands_links_preserves_history_and_completely_round_trips(pg):
    connection, context = pg
    ids = seed(connection)
    originals = {name: migration.snapshot(connection, name) for name in (*migration.RESTORED_TABLES, 'business_events')}
    migrate(connection, context, 'upgrade')
    t = lambda name: migration.table(connection, name)
    inventory, links, products = (t(name) for name in ('inventory_items', 'product_batches', 'products'))
    assert 'quantity' not in inventory.c and 'specification' in inventory.c
    rows = list(connection.execute(sa.select(inventory)).mappings())
    assert len(rows) == 28
    assert sum(r['name'] == '苹果' and r['household_id'] == ids['home'] for r in rows) == 10
    assert sum(r['name'] == '红苹果' for r in rows) == 12
    assert sum(r['name'] == '苹果' and r['household_id'] == ids['foreign_home'] for r in rows) == 2
    assert next(r for r in rows if r['id'] == ids['apple'])['version'] == 5
    assert next(r for r in rows if r['id'] == ids['milk'])['specification'] == '1.5L'
    assert next(r for r in rows if r['id'] == ids['milk'])['unit'] == '份'
    assert next(r for r in rows if r['id'] == ids['zero'])['status'] == 'FINISHED'
    assert next(r for r in rows if r['id'] == ids['discarded'])['specification'] == '4个'
    assert len(list(connection.execute(sa.select(links)))) == len(rows)
    assert connection.scalar(sa.select(sa.func.count()).select_from(links).where(links.c.product_id == ids['apple_product'])) == 22
    assert connection.scalar(sa.select(products.c.base_unit).where(products.c.id == ids['milk_product'])) == '份'
    assert connection.scalar(sa.select(products.c.base_unit).where(products.c.id == ids['fraction_product'])) == '份'
    event = connection.execute(sa.select(t('business_events'))).mappings().one()
    assert event['product_id'] == ids['apple_product']
    assert event['after_json'] == {'quantity': '12', 'name': '红苹果'}
    unique_columns = [entry['column_names'] for entry in sa.inspect(connection).get_unique_constraints('business_events')]
    assert ['operation_id'] not in unique_columns and ['request_id'] not in unique_columns
    indexes = {entry['name']: entry for entry in sa.inspect(connection).get_indexes('business_events')}
    assert not indexes['ix_business_events_request_id']['unique']
    assert not indexes['ix_business_events_operation_id']['unique']
    # A single authenticated intake receipt can own distinct events for each
    # created item. Roll the probe back so the downgrade guard sees no writes.
    probe = connection.begin_nested()
    request_id = uuid4()
    connection.execute(t('mutation_receipts').insert().values(operation_id=request_id,
        household_id=ids['home'], actor_user_id=ids['user'], request_hash='0'*64, response_json={}))
    for physical_item in [r for r in rows if r['name'] == '红苹果'][:2]:
        connection.execute(t('business_events').insert().values(id=uuid4(), request_id=request_id,
            household_id=ids['home'], actor_user_id=ids['user'], inventory_item_id=physical_item['id'],
            product_id=ids['apple_product'], event_type='Created', quantity=Decimal(1), unit='个',
            before_json={}, after_json={'name': '红苹果'}, occurred_at=event['occurred_at']))
    event_table = t('business_events')
    assert connection.scalar(sa.select(sa.func.count()).select_from(event_table)
        .where(event_table.c.request_id == request_id)) == 2
    probe.rollback()
    facts = list(connection.execute(sa.select(t('inventory_planning_facts'))).mappings())
    assert len(facts) == 10
    assert all(f['facts_json']['coverage']['2026-10-01']['day_hash'].startswith('inventory-unit-migration:') for f in facts)
    assert sum(r['source_shopping_list_item_id'] == ids['shopping'] for r in rows) == 10
    migrate(connection, context, 'downgrade')
    assert all(migration.snapshot(connection, name) == original for name, original in originals.items())
    assert migration.BACKUP not in sa.inspect(connection).get_table_names()
    restored_uniques = [entry['column_names'] for entry in sa.inspect(connection).get_unique_constraints('business_events')]
    assert ['operation_id'] in restored_uniques and ['request_id'] in restored_uniques
    # Repeated upgrade produces the same deterministic physical item IDs.
    migrate(connection, context, 'upgrade')
    assert set(connection.scalars(sa.select(t('inventory_items').c.id))) == {r['id'] for r in rows}


def test_postgres_later_business_writes_block_downgrade_without_changing_data(pg):
    connection, context = pg
    ids = seed(connection)
    migrate(connection, context, 'upgrade')
    inventory = migration.table(connection, 'inventory_items')
    connection.execute(inventory.update().where(inventory.c.id == ids['apple']).values(name='后来编辑'))
    before = migration.snapshot(connection, 'inventory_items')
    with pytest.raises(RuntimeError, match='later business writes in inventory_items'):
        migrate(connection, context, 'downgrade')
    assert migration.snapshot(connection, 'inventory_items') == before
    assert 'quantity' not in migration.table(connection, 'inventory_items').c


def test_postgres_excessive_legacy_batch_refuses_before_schema_or_data_change(pg):
    connection, context = pg
    ids = seed(connection)
    inventory = migration.table(connection, 'inventory_items')
    connection.execute(inventory.update().where(inventory.c.id == ids['apple']).values(quantity=Decimal(10001)))
    before = migration.snapshot(connection, 'inventory_items')
    with pytest.raises(RuntimeError, match='exceeds 10000'):
        migrate(connection, context, 'upgrade')
    assert migration.snapshot(connection, 'inventory_items') == before
    assert migration.BACKUP not in sa.inspect(connection).get_table_names()
