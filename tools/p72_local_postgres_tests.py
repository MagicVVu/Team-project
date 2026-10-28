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
import time
import urllib.request
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--stage', choices=('p1', 'p2', 'p3', 'p4', 'p8', 'p9'), default='p1')
stage = parser.parse_args().stage
evidence = ROOT / 'reports' / 'backend-ai-alignment' if stage == 'p8' else ROOT / 'reports'
if stage == 'p9':
    evidence = ROOT/'reports/backend-ai-p9'
evidence.mkdir(parents=True, exist_ok=True)
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
if stage in {'p4', 'p9'}:
    with socket.socket() as probe:
        # The production allowlist fixes port 8767; require that loopback port
        # to be free instead of changing the gateway or any existing service.
        probe.bind(('127.0.0.1', 8767))
        agent_port = probe.getsockname()[1]
    env.update(AI_SERVICE_URL='http://agent:8767', P4_AGENT_LOOPBACK_PORT=str(agent_port),
               AI_SERVICE_TOKEN=secrets.token_hex(24), BACKEND_TOOL_TOKEN=secrets.token_hex(24), P3_ENGINE='rules')
    if stage == 'p9':
        env.update(MAGICVVU_OPEN_EXECUTION='true', MAGICVVU_DISCARD_EXECUTION='true',
                   MAGICVVU_TRUSTED_REFERENCE_MESSAGES='true')


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
    options = f'-h 127.0.0.1 -p {port}'
    if stage == 'p9':
        # This verified disposable cluster tests transactions/locking, not power
        # loss durability. Avoid tens of thousands of Windows fsyncs for schemas.
        options += ' -c fsync=off -c synchronous_commit=off -c full_page_writes=off'
    run([BIN / 'pg_ctl.exe', '-D', data, '-l', work / 'server.log', '-o', options, '-w', 'start'])
    run([BIN / 'createdb.exe', '-h', '127.0.0.1', '-p', str(port), '-U', 'p72_test', env['DB_NAME']])
    result['migration'] = []
    if stage == 'p9':
        targets = ('head', '20261023_0010', 'head', '20261023_0009', 'head')
    elif stage == 'p8':
        targets = ('head', '20261023_0009', 'head', '20261023_0008', 'head', '20261017_0007', 'head', '20261016_0006', 'head')
    elif stage in ('p3', 'p4'):
        targets = ('head', '20261023_0008', 'head', '20261017_0007', 'head', '20261016_0006', 'head')
    else:
        targets = ('head', '20261017_0007', 'head', '20261016_0006', 'head') if stage == 'p2' else ('head', '20261016_0006', 'head')
    for target in targets:
        p = run([sys.executable, '-m', 'alembic', 'upgrade' if target == 'head' else 'downgrade', target], cwd=ROOT / 'backend/server')
        result['migration'].append({'target': target, 'exit_code': p.returncode, 'log': p.stderr})
    if stage in {'p8', 'p9'}:
        result['schema_check'] = run([sys.executable, '-m', 'alembic', 'check'], cwd=ROOT / 'backend/server').stdout.strip()
    # Boot the actual ASGI server against the migrated disposable database.
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        http_port = probe.getsockname()[1]
    with (work / 'uvicorn.log').open('wb') as log:
        boot = ([sys.executable, ROOT / 'tools/backend_p4_isolated_server.py', str(http_port)] if stage in {'p4', 'p9'}
                else [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(http_port)])
        server = subprocess.Popen([str(a) for a in boot], cwd=ROOT / 'backend/server',
            env=env, stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            base = f'http://127.0.0.1:{http_port}'
            client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for attempt in range(100):
                if server.poll() is not None:
                    raise RuntimeError('Isolated uvicorn exited before readiness')
                try:
                    with client.open(base + '/api/v1/health', timeout=1) as response:
                        health = json.load(response)
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError('Isolated uvicorn startup timed out')
            with client.open(base + '/api/v1/ready', timeout=5) as response:
                ready = json.load(response)
            assert health['version'] == '0.9.0' and health['isolated_test'] is True
            assert ready['database'] == 'ok'
            result['startup'] = {'health': health, 'ready': ready}
            if stage in {'p4', 'p9'}:
                probe_script = 'p9_http_probe.py' if stage == 'p9' else 'backend_p4_http_probe.py'
                probe_result = run([sys.executable, ROOT / 'tools'/probe_script, base], timeout=120)
                result['http_contract'] = {'exit_code': probe_result.returncode, 'stdout': probe_result.stdout}
        finally:
            server.terminate()
            server.wait(timeout=10)
    if stage == 'p9':
        # The real-HTTP smoke server enabled already released actions locally.
        # Legacy unit tests explicitly exercise the default-closed configuration
        # and opt in through their own fixtures; do not leak smoke-server flags.
        for key in ('MAGICVVU_OPEN_EXECUTION', 'MAGICVVU_DISCARD_EXECUTION', 'MAGICVVU_TRUSTED_REFERENCE_MESSAGES'):
            env.pop(key, None)
    p = run([sys.executable, '-m', 'pytest', 'backend/server/tests', '-q', '--tb=short',
             '--junitxml=' + str(evidence / f'backend-{stage}-postgres-tests.xml'),
             '--basetemp=' + str(work / 'pytest')], check=False, timeout=900 if stage == 'p9' else 300)
    result.update(exit_code=p.returncode, stdout=p.stdout, stderr=p.stderr)
finally:
    result['postgres_stopped'] = (not (data / 'postmaster.pid').exists() or
        run([BIN / 'pg_ctl.exe', '-D', data, '-w', '-t', '110', '-m', 'fast', 'stop'], check=False).returncode == 0)
    if pwfile.exists(): pwfile.unlink()
    assert data.resolve().parent == work and work.parent == (ROOT / '.cache').resolve()
    assert work.name.startswith('p72-local-postgres-')
    if result['postgres_stopped'] and data.exists(): shutil.rmtree(data)
    result['cluster_removed'] = not data.exists()
    (evidence / f'backend-{stage}-postgres-evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in {'stdout', 'stderr', 'migration'}}, ensure_ascii=False))

sys.exit(result.get('exit_code', 1) if result['postgres_stopped'] and result['cluster_removed'] else 1)
