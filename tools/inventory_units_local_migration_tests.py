"""Run unit-migration tests against a disposable loopback PostgreSQL cluster."""
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile

from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parents[1]
CACHE = (ROOT / '.cache').resolve()
BIN = CACHE / 'p72-postgresql/pgsql/bin'
REPORT = ROOT / 'reports/inventory-units-20261029'
REPORT.mkdir(exist_ok=True, parents=True)
assert (BIN / 'postgres.exe').is_file()
work = Path(tempfile.mkdtemp(prefix='inventory-unit-migration-', dir=CACHE)).resolve()
data = work / 'data'
pwfile = work / 'password'
password = secrets.token_hex(24)
pwfile.write_text(password, encoding='ascii')
with socket.socket() as probe:
    probe.bind(('127.0.0.1', 0))
    port = probe.getsockname()[1]
assert port >= 20000
database = 'inventory_units_migration_test'
url = URL.create('postgresql+psycopg', username='units_test', password=password,
    host='127.0.0.1', port=port, database=database)
env = dict(os.environ, PGPASSWORD=password,
    INVENTORY_UNITS_TEST_DATABASE_URL=url.render_as_string(hide_password=False))
evidence = {'production_database_accessed': False, 'host': '127.0.0.1', 'port': port,
    'database': database, 'data_directory': str(data), 'tests_exit_code': None}


def run(args, cwd=ROOT, timeout=120):
    with tempfile.TemporaryFile() as output:
        result = subprocess.run([str(a) for a in args], cwd=cwd, env=env,
            stdout=output, stderr=subprocess.STDOUT, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        output.seek(0)
        result.output = output.read().decode('utf-8', 'replace')
    return result


started = False
try:
    init = run([BIN / 'initdb.exe', '-D', data, '-U', 'units_test', '--pwfile', pwfile,
        '--auth=scram-sha-256', '--encoding=UTF8', '--locale=C'])
    assert init.returncode == 0, init.output
    pwfile.unlink()
    boot = run([BIN / 'pg_ctl.exe', '-D', data, '-l', work / 'postgres.log', '-o',
        f'-h 127.0.0.1 -p {port} -c fsync=off -c synchronous_commit=off -c full_page_writes=off',
        '-w', 'start'])
    assert boot.returncode == 0, boot.output
    started = True
    created = run([BIN / 'createdb.exe', '-h', '127.0.0.1', '-p', port, '-U', 'units_test', database])
    assert created.returncode == 0, created.output
    tests = run([sys.executable, '-m', 'pytest', 'tests/test_inventory_unit_migration.py', '-q',
        '--junitxml='+str(REPORT / 'migration-postgres-tests.xml')], cwd=ROOT / 'backend/server')
    (REPORT / 'migration-postgres-tests.log').write_text(tests.output, encoding='utf-8')
    evidence['tests_exit_code'] = tests.returncode
    print(tests.output)
finally:
    if started:
        stop = run([BIN / 'pg_ctl.exe', '-D', data, '-m', 'fast', '-w', 'stop'])
        evidence['postgres_stopped'] = stop.returncode == 0
    if not started or evidence.get('postgres_stopped'):
        assert work.parent == CACHE and work.name.startswith('inventory-unit-migration-')
        shutil.rmtree(work)
        evidence['cluster_removed'] = not work.exists()
    (REPORT / 'migration-postgres-evidence.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
sys.exit(evidence['tests_exit_code'] or 0)
