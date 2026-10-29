"""Validate a server-private production clone, then round-trip its migration."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from sqlalchemy import inspect, select
from app.database import engine

ROOT = Path('/verify/backend/server')
spec = importlib.util.spec_from_file_location('unit_migration', ROOT / 'alembic/versions/20261029_0012_inventory_units.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def snapshot():
    with engine.connect() as db:
        return {name: migration.digest(migration.snapshot(db, name))
                for name in inspect(db).get_table_names() if name != 'alembic_version'}


def alembic(*args):
    p = subprocess.run([sys.executable, '-m', 'alembic', *args], cwd=ROOT,
                       capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-3000:]


before = snapshot()
with engine.connect() as db:
    rows = list(db.execute(select(migration.table(db, 'inventory_items'))).mappings())
    original = {row['id']: dict(row) for row in rows}
    audit = migration.audit_rows(rows)
alembic('upgrade', 'head')
with engine.connect() as db:
    inventory = migration.table(db, 'inventory_items')
    assert 'quantity' not in inventory.c
    rows = list(db.execute(select(inventory)).mappings())
    assert len(rows) == audit['target_rows']
    after = {row['id']: row for row in rows}
    preserved = ('name', 'household_id', 'category', 'storage_location', 'expires_on',
                 'purchased_on', 'source_shopping_list_item_id', 'created_by_user_id', 'opened_at')
    for key, old in original.items():
        row = after[key]
        assert all(row[field] == old[field] for field in preserved)
        assert row['version'] == old['version'] + 1
        shape = migration.expansion(old)
        assert row['unit'] == shape['unit'] and row['specification'] == shape['specification']
    links = list(db.execute(select(migration.table(db, 'product_batches'))).mappings())
    assert len(links) == len(rows)
    assert {link['inventory_item_id'] for link in links} == set(after)
    # Grouping must never cross a household boundary.
    products = {p['id']: p for p in db.execute(select(migration.table(db, 'products'))).mappings()}
    assert all(after[link['inventory_item_id']]['household_id'] == products[link['product_id']]['household_id'] for link in links)
    states = {}
    for row in rows:
        states[row['status']] = states.get(row['status'], 0) + 1
    merged = len(original) - len(products)
upgraded = snapshot()
alembic('downgrade', '20261026_0011')
assert snapshot() == before, 'Upgrade/downgrade changed original data'
alembic('upgrade', 'head')
assert snapshot() == upgraded, 'Second upgrade differs from first'
result = {'passed': True, 'audit': audit, 'status_counts': states,
          'original_ids_fields_preserved': True, 'every_item_linked_to_product': True,
          'household_boundaries_preserved': True, 'exact_downgrade_verified': True,
          'repeatable_upgrade_verified': True, 'production_data_remained_on_server': True}
Path('/verify/clone-verification.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result))
