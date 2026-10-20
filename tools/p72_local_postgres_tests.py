"""Disposable real PostgreSQL acceptance, using an EDB portable runtime.

Fresh cache directory, random loopback port, private random password; no system
service. Fixtures verify the data_directory before writes. Stops and destroys
only this run's cluster in finally, never uses production/test server resources.
"""
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / '.cache/p72-postgresql/pgsql/bin'
assert (BIN / 'postgres.exe').is_file()
work = Path(tempfile.mkdtemp(prefix='p72-local-postgres-', dir=ROOT / '.cache')).resolve()
data, pwfile = work / 'data', work / 'password'
password = secrets.token_hex(24)
pwfile.write_text(password, encoding='ascii')
with socket.socket() as probe:
    probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
assert port >= 20000
env = dict(os.environ, DB_HOST='127.0.0.1', DB_PORT=str(port), DB_NAME='magicvvu_p7_execution_test',
    DB_USER='p72_test', DB_PASSWORD=password, PGPASSWORD=password, ISOLATED_APP_TEST='yes',
    DRAFT_EXECUTION_PG_TEST='yes', P72_LOCAL_EPHEMERAL='yes', P72_PG_DATA_DIR=str(data),
    PYTHONPATH=str(ROOT / 'backend/server') + os.pathsep + str(ROOT / 'agent'))
result = {'production_database_accessed': False, 'data_directory': str(data), 'host': '127.0.0.1',
    'port': port, 'database': env['DB_NAME'], 'system_service_installed': False}


def run(args, cwd=ROOT, check=True, timeout=120):
    # Windows pg_ctl children may inherit PIPE handles; files avoid that hang.
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        p = subprocess.run([str(a) for a in args], cwd=cwd, env=env, stdout=out, stderr=err,
            timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        out.seek(0); err.seek(0)
        p.stdout, p.stderr = out.read().decode('utf-8', 'replace'), err.read().decode('utf-8', 'replace')
    if check and p.returncode: raise RuntimeError(Path(str(args[0])).name + ' failed: ' + p.stderr[-2000:])
    return p


try:
    result['version'] = run([BIN / 'postgres.exe', '--version']).stdout.strip()
    run([BIN / 'initdb.exe', '-D', data, '-U', 'p72_test', '--pwfile', pwfile,
         '--auth=scram-sha-256', '--encoding=UTF8', '--locale=C'])
    pwfile.unlink()
    run([BIN / 'pg_ctl.exe', '-D', data, '-l', work / 'server.log', '-o', f'-h 127.0.0.1 -p {port}', '-w', 'start'])
    run([BIN / 'createdb.exe', '-h', '127.0.0.1', '-p', str(port), '-U', 'p72_test', env['DB_NAME']])
    result['migration'] = []
    for target in ('head', '20261017_0007', 'head'):
        p = run([sys.executable, '-m', 'alembic', 'upgrade' if target == 'head' else 'downgrade', target], cwd=ROOT / 'backend/server')
        result['migration'].append({'target': target, 'exit_code': p.returncode, 'log': p.stderr})
    p = run([sys.executable, '-m', 'pytest', 'backend/server/tests', '-q', '--tb=short', '--basetemp=' + str(work / 'pytest')], check=False, timeout=300)
    result.update(exit_code=p.returncode, stdout=p.stdout, stderr=p.stderr)
finally:
    result['postgres_stopped'] = (not (data / 'postmaster.pid').exists() or
        run([BIN / 'pg_ctl.exe', '-D', data, '-w', '-m', 'fast', 'stop'], check=False).returncode == 0)
    if pwfile.exists(): pwfile.unlink()
    assert data.resolve().parent == work and work.parent == (ROOT / '.cache').resolve()
    assert work.name.startswith('p72-local-postgres-')
    if result['postgres_stopped'] and data.exists(): shutil.rmtree(data)
    result['cluster_removed'] = not data.exists()
    (ROOT / 'reports/p72/evidence/P6-postgres-local.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in {'stdout', 'stderr', 'migration'}}, ensure_ascii=False))
