"""Run on the Docker host from an uploaded, credential-free source directory.

Creates a unique internal network and RAM-backed PostgreSQL, destroys exactly
those resources in finally. Never attaches an existing DB, network or volume.
"""
import json
import secrets
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

root = Path(sys.argv[1]).resolve()
assert root.is_dir() and str(root).startswith('/home/admin/magicvvu-p72-')
prefix = 'magicvvu-p72-ephemeral-' + uuid4().hex[:12]
network, database, runner = prefix + '-net', prefix + '-db', prefix + '-runner'
password = secrets.token_hex(24)


def docker(*args, check=True, timeout=300):
    return subprocess.run(['sudo', '-n', 'docker', *args], capture_output=True,
                          text=True, timeout=timeout, check=check)


result = {'production_database_accessed': False, 'network': network, 'database': database,
          'runner': runner, 'persistent_volume_created': False}
try:
    docker('network', 'create', '--internal', network)
    docker('run', '-d', '--name', database, '--network', network, '--network-alias', 'db',
           '--tmpfs', '/var/lib/postgresql/data:rw,nosuid,size=512m',
           '-e', 'POSTGRES_DB=magicvvu_p7_execution_test', '-e', 'POSTGRES_USER=p72_test',
           '-e', 'POSTGRES_PASSWORD=' + password,
           'sha256:2d2b8998d31037bf721cfdf764d76ba74171b4fab3431b7f72c27c56ddbdf9e3')
    for _ in range(40):
        if docker('exec', database, 'pg_isready', '-U', 'p72_test', '-d', 'magicvvu_p7_execution_test', check=False).returncode == 0:
            break
        time.sleep(0.5)
    else:
        raise RuntimeError('Temporary PostgreSQL did not become ready')
    command = ['run', '--rm', '--name', runner, '--network', network,
        '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
        '--tmpfs', '/tmp:rw,nosuid,size=256m', '-v', str(root) + ':/repo:ro',
        '-e', 'DB_HOST=db', '-e', 'DB_NAME=magicvvu_p7_execution_test', '-e', 'DB_USER=p72_test',
        '-e', 'DB_PASSWORD=' + password, '-e', 'DRAFT_EXECUTION_PG_TEST=yes',
        '-e', 'ISOLATED_APP_TEST=yes', '-e', 'PYTHONDONTWRITEBYTECODE=1',
        '-e', 'PYTHONPATH=/repo/backend/server:/repo/agent',
        '--entrypoint', 'python', 'magicvvu/backend:p7-rc-tests-04f930a',
        '-m', 'pytest', '/repo/backend/server/tests', '-q', '--tb=short', '-p', 'no:cacheprovider',
        '--basetemp=/tmp/p72-pytest']
    p = docker(*command, check=False, timeout=420)
    result.update(exit_code=p.returncode, stdout=p.stdout, stderr=p.stderr)
finally:
    result['runner_removed'] = docker('rm', '-f', runner, check=False).returncode in (0, 1)
    result['database_removed'] = docker('rm', '-f', database, check=False).returncode == 0
    result['network_removed'] = docker('network', 'rm', network, check=False).returncode == 0
    print(json.dumps(result, ensure_ascii=False, indent=2))
