"""Run on magicvvu as root: stage/test/release the per-object inventory change.

Private configuration and database backups stay on the server. The release
reuses the running images and overlays only the reviewed source files.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tarfile
import time

ROOT = Path('/srv/magicvvu/releases/inventory-units-20261029')
CONFIG = Path('/srv/magicvvu/magicvvu-starter/deploy/compose.yaml')
IMAGES = {s: f'magicvvu/{s}:inventory-units-20261029' for s in ('backend', 'agent')}
TEST_IMAGE = 'magicvvu/backend:inventory-units-tests-20261029'
NET = 'magicvvu-inventory-units-test-20261029'
DB = NET + '-db'


def run(args, *, timeout=180, input=None):
    p = subprocess.run(args, input=input, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(f'{args[0]} failed: {p.stdout[-1200:]} {p.stderr[-1200:]}')
    return p.stdout.strip()


def containers():
    return {s: json.loads(run(['docker', 'inspect', f'magicvvu-starter-{s}-1']))[0]
            for s in ('backend', 'agent', 'db')}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))


def dump(path):
    with path.open('wb') as out:
        subprocess.run(['docker', 'exec', 'magicvvu-starter-db-1', 'pg_dump', '-U',
                        'magicvvu_admin', '-d', 'magicvvu', '-Fc'], stdout=out,
                       stderr=subprocess.PIPE, check=True, timeout=120)
    path.chmod(0o600)


def stage():
    ROOT.mkdir(mode=0o700)
    with tarfile.open('/tmp/magicvvu-inventory-units-20261029.tar.gz') as archive:
        archive.extractall(ROOT, filter='data')
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    for name, digest in manifest.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    before = containers()
    write_json(ROOT / 'containers.before.private.json', before)
    shutil.copy2(CONFIG, ROOT / 'compose.before.yaml')
    (ROOT / 'baseline/backend').mkdir(parents=True)
    run(['docker', 'cp', 'magicvvu-starter-backend-1:/app/.', str(ROOT / 'baseline/backend')])
    for package in ('conversation', 'p0', 'p1', 'p2', 'p3', 'v1', 'interaction', 'integration', 'eval'):
        target = ROOT / 'test-project/agent' / package
        target.parent.mkdir(parents=True, exist_ok=True)
        run(['docker', 'cp', 'magicvvu-starter-agent-1:/app/agent/' + package, str(target)])
    shutil.copytree(ROOT / 'baseline/backend', ROOT / 'test-project/backend/server', dirs_exist_ok=True)
    for service, target in (('backend', 'backend/server'), ('agent', 'agent')):
        shutil.copytree(ROOT / 'overlay' / service, ROOT / 'test-project' / target, dirs_exist_ok=True)
        folder = ROOT / ('build-' + service)
        folder.mkdir()
        shutil.copytree(ROOT / 'overlay' / service, folder / 'source')
        destination = '/app/' if service == 'backend' else '/app/agent/'
        (folder / 'Dockerfile').write_text(f'FROM {before[service]["Config"]["Image"]}\nCOPY source/ {destination}\n')
        run(['docker', 'build', '--network=none', '-t', IMAGES[service], str(folder)])
    shutil.copytree(ROOT / 'tests/backend', ROOT / 'test-project/backend/server/tests', dirs_exist_ok=True)
    shutil.copytree(ROOT / 'tests/agent', ROOT / 'test-project/agent/tests', dirs_exist_ok=True)
    folder = ROOT / 'build-tests'
    folder.mkdir()
    shutil.copytree(ROOT / 'overlay/backend', folder / 'source')
    (folder / 'Dockerfile').write_text('FROM magicvvu/backend:chat-reliability-tests-20261029\nCOPY source/ /app/\n')
    run(['docker', 'build', '--network=none', '-t', TEST_IMAGE, str(folder)])
    dump(ROOT / 'database-staging.dump')
    print('STAGED', flush=True)


def test():
    run(['docker', 'network', 'create', '--internal', NET])
    password = secrets.token_hex(24)
    try:
        run(['docker', 'run', '-d', '--name', DB, '--network', NET, '--network-alias', 'db',
             '-e', 'POSTGRES_USER=magicvvu_admin', '-e', 'POSTGRES_PASSWORD=' + password,
             '-e', 'POSTGRES_DB=magicvvu_clone_test', 'public.ecr.aws/docker/library/postgres:17'])
        for _ in range(40):
            if subprocess.run(['docker', 'exec', DB, 'pg_isready', '-h', '127.0.0.1', '-U', 'magicvvu_admin'], capture_output=True).returncode == 0:
                break
            time.sleep(1)
        with (ROOT / 'database-staging.dump').open('rb') as backup:
            restored = subprocess.run(['docker', 'exec', '-i', DB, 'pg_restore', '-U', 'magicvvu_admin',
                            '-d', 'magicvvu_clone_test', '--no-owner', '--no-privileges', '--exit-on-error'],
                           stdin=backup, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
            assert restored.returncode == 0, restored.stderr.decode(errors='replace')[-2000:]
        prefix = ['docker', 'run', '--rm', '--network', NET, '-v', str(ROOT / 'test-project') + ':/verify',
                  '-w', '/verify', '-e', 'PYTHONPATH=/verify/agent:/verify/backend/server:/verify/backend/server/tests',
                  '-e', 'DB_USER=magicvvu_admin', '-e', 'DB_PASSWORD=' + password, '-e', 'DB_HOST=db',
                  '-e', 'DB_PORT=5432', '-e', 'DB_NAME=magicvvu_clone_test', '--entrypoint', 'python', TEST_IMAGE]
        result = run(prefix + ['/verify/clone_verify.py'], timeout=240)
        print(result, flush=True)
        run(['docker', 'exec', DB, 'createdb', '-U', 'magicvvu_admin', 'magicvvu_p7_execution_test'])
        pfx = prefix.copy()
        pfx[pfx.index('DB_NAME=magicvvu_clone_test')] = 'DB_NAME=magicvvu_p7_execution_test'
        pfx[pfx.index('--entrypoint'):pfx.index('--entrypoint')] = ['-e', 'DRAFT_EXECUTION_PG_TEST=yes', '-e', 'PHYSICAL_INVENTORY_PG_TEST=yes']
        pfx[pfx.index('--entrypoint'):pfx.index('--entrypoint')] = ['-e',
            'INVENTORY_UNITS_TEST_DATABASE_URL=postgresql+psycopg://magicvvu_admin:' + password + '@db:5432/magicvvu_p7_execution_test']
        tests = json.loads((ROOT / 'test-selection.json').read_text())
        for name, files in tests.items():
            p = subprocess.run(pfx + ['-m', 'pytest', *files, '-q', '--tb=short',
                              '--junitxml=/verify/' + name + '.xml'], capture_output=True, text=True, timeout=300)
            (ROOT / (name + '.log')).write_text(p.stdout + '\n' + p.stderr)
            print(name, p.stdout[-3500:], flush=True)
            assert p.returncode == 0, name
        write_json(ROOT / 'tests-passed.json', {'passed': True, 'clone_upgrade_downgrade': True,
                                              'real_model_calls': 0, 'test_selection': tests})
    finally:
        subprocess.run(['docker', 'rm', '-f', '-v', DB], capture_output=True)
        subprocess.run(['docker', 'network', 'rm', NET], capture_output=True)


def refresh():
    """Apply a reviewed source revision while retaining the original baseline."""
    with tarfile.open('/tmp/magicvvu-inventory-units-20261029.tar.gz') as archive:
        archive.extractall(ROOT, filter='data')
    for name, digest in json.loads((ROOT / 'manifest.json').read_text()).items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
    for service, target in (('backend', 'backend/server'), ('agent', 'agent')):
        shutil.copytree(ROOT / 'overlay' / service, ROOT / 'test-project' / target, dirs_exist_ok=True)
        folder = ROOT / ('build-' + service)
        shutil.copytree(ROOT / 'overlay' / service, folder / 'source', dirs_exist_ok=True)
        run(['docker', 'build', '--network=none', '-t', IMAGES[service], str(folder)])
    for service, target in (('backend', 'backend/server'), ('agent', 'agent')):
        shutil.copytree(ROOT / 'tests' / service, ROOT / 'test-project' / target / 'tests', dirs_exist_ok=True)
    folder = ROOT / 'build-tests'
    shutil.copytree(ROOT / 'overlay/backend', folder / 'source', dirs_exist_ok=True)
    run(['docker', 'build', '--network=none', '-t', TEST_IMAGE, str(folder)])
    (ROOT / 'tests-passed.json').unlink(missing_ok=True)
    print('CANDIDATE_REFRESHED', flush=True)


def test_agent():
    """Finish AI fixture tests after a successful backend/clone test run."""
    import xml.etree.ElementTree as ET
    suites = list(ET.parse(ROOT / 'test-project/backend-postgres-tests.xml').getroot().iter('testsuite'))
    assert suites and all(int(s.get('failures', 0)) == 0 and int(s.get('errors', 0)) == 0 for s in suites)
    assert json.loads((ROOT / 'test-project/clone-verification.json').read_text())['passed']
    tests = json.loads((ROOT / 'test-selection.json').read_text())
    args = ['docker', 'run', '--rm', '--network=none', '-v', str(ROOT / 'test-project') + ':/verify',
            '-w', '/verify', '-e', 'PYTHONPATH=/verify/agent', '--entrypoint', 'python', TEST_IMAGE,
            '-m', 'pytest', *tests['agent-tests'], '-q', '--tb=short', '--junitxml=/verify/agent-tests.xml']
    p = subprocess.run(args, capture_output=True, text=True, timeout=180)
    (ROOT / 'agent-tests.log').write_text(p.stdout + '\n' + p.stderr)
    print(p.stdout[-3500:], flush=True)
    assert p.returncode == 0
    write_json(ROOT / 'tests-passed.json', {'passed': True, 'clone_upgrade_downgrade': True,
                                         'real_model_calls': 0, 'test_selection': tests})


def install(content):
    staged = CONFIG.with_name('compose.inventory-units.tmp.yaml')
    staged.write_text(content)
    shutil.copystat(CONFIG, staged)
    run(['docker', 'compose', '-f', str(staged), 'config', '--quiet'])
    staged.replace(CONFIG)


def healthy():
    for _ in range(40):
        after = containers()
        if all(c['State'].get('Health', {}).get('Status') == 'healthy' for c in after.values()):
            return after
        time.sleep(2)
    raise RuntimeError('Services did not become healthy')


def release():
    import yaml
    assert json.loads((ROOT / 'tests-passed.json').read_text())['passed']
    before = containers()
    original = (ROOT / 'compose.before.yaml').read_text()
    assert CONFIG.read_text() == original, 'Compose changed after staging'
    staged_before = json.loads((ROOT / 'containers.before.private.json').read_text())
    assert all(before[s]['Image'] == staged_before[s]['Image'] for s in before), 'Running images changed'
    environment = dict(v.split('=', 1) for v in before['backend']['Config']['Env'])
    # All maintenance commands share existing runtime credentials without printing them.
    env_args = [part for key, value in environment.items() for part in ('-e', key + '=' + value)]
    networks = list(before['backend']['NetworkSettings']['Networks'])
    db_network = next(n for n in networks if n in before['db']['NetworkSettings']['Networks'])
    def command(image, *args):
        return run(['docker', 'run', '--rm', '--network', db_network, *env_args,
                    '--entrypoint', 'python', image, *args])
    candidate = original
    expected = yaml.safe_load(original)
    for service in ('backend', 'agent'):
        old = before[service]['Config']['Image']
        candidate, n = re.subn(r'(?m)^(\s*image:\s*)' + re.escape(old) + r'(\s*(?:#.*)?)$',
                              lambda m: m[1] + IMAGES[service] + m[2], candidate)
        assert n == 1
        expected['services'][service]['image'] = IMAGES[service]
    assert yaml.safe_load(candidate) == expected
    idle_code = """import json
from app.database import engine
from sqlalchemy import text
with engine.connect() as db:
 print(json.dumps(db.execute(text("SELECT (SELECT count(*) FROM ai_conversation_bindings WHERE processing_nonce IS NOT NULL AND lease_until > now()) + (SELECT count(*) FROM ai_tasks WHERE processing_nonce IS NOT NULL AND lease_until > now())")).scalar()))
"""
    for _ in range(24):
        if json.loads(run(['docker', 'exec', 'magicvvu-starter-backend-1', 'python', '-c', idle_code])) == 0:
            break
        time.sleep(5)
    else:
        raise RuntimeError('Active chat requests have not drained; services remain unchanged')
    # A short maintenance window prevents old writers from touching the new schema.
    run(['docker', 'compose', '-f', str(CONFIG), 'stop', '-t', '90', 'agent', 'backend'], timeout=210)
    migrated = False
    installed = False
    try:
        dump(ROOT / 'database-before.dump')
        output = command(IMAGES['backend'], '-m', 'alembic', 'upgrade', 'head')
        migrated = True
        print('MIGRATED', output[-600:], flush=True)
        # Validate the committed schema before opening traffic.
        schema = json.loads(command(IMAGES['backend'], '-c',
            "import json;from sqlalchemy import inspect,text;from app.database import engine;"
            "print(json.dumps({'columns':[c['name'] for c in inspect(engine).get_columns('inventory_items')],"
            "'rows':engine.connect().execute(text('select count(*) from inventory_items')).scalar()}))"))
        assert 'quantity' not in schema['columns'] and 'specification' in schema['columns']
        install(candidate)
        installed = True
        run(['docker', 'compose', '-f', str(CONFIG), 'up', '-d', '--no-deps', '--no-build', '--pull', 'never', 'backend', 'agent'])
        after = healthy()
        checks = {'quantity_column_removed': True, 'database_container_unchanged': before['db']['Id'] == after['db']['Id']}
        for s in ('backend', 'agent'):
            checks[s + '_environment_unchanged'] = dict(v.split('=', 1) for v in before[s]['Config']['Env']) == dict(v.split('=', 1) for v in after[s]['Config']['Env'])
            checks[s + '_mounts_unchanged'] = before[s]['Mounts'] == after[s]['Mounts']
            checks[s + '_ports_unchanged'] = before[s]['HostConfig']['PortBindings'] == after[s]['HostConfig']['PortBindings']
            checks[s + '_image_applied'] = after[s]['Config']['Image'] == IMAGES[s]
        for name, digest in json.loads((ROOT / 'manifest.json').read_text()).items():
            if not name.startswith('overlay/'):
                continue
            _, service, *parts = name.split('/')
            path = ('/app/' if service == 'backend' else '/app/agent/') + '/'.join(parts)
            actual = run(['docker', 'exec', f'magicvvu-starter-{service}-1', 'python', '-c',
                          'from pathlib import Path;import hashlib;print(hashlib.sha256(Path(' + repr(path) + ').read_bytes()).hexdigest())'])
            checks[name] = actual == digest
        assert all(checks.values()), checks
        verification = {'deployed': True, 'images': IMAGES, 'checks': checks, 'inventory_rows': schema['rows'],
                        'backup_directory': str(ROOT), 'production_model_calls': 0}
        write_json(ROOT / 'verification.json', verification)
        print(json.dumps(verification), flush=True)
    except Exception:
        # Downgrade is guarded by migration snapshots and refuses to erase new writes.
        # Do not restart old code after traffic has opened: preserve data for inspection.
        if not installed:
            if migrated:
                command(IMAGES['backend'], '-m', 'alembic', 'downgrade', '20261026_0011')
            run(['docker', 'compose', '-f', str(CONFIG), 'start', 'backend', 'agent'])
        raise


if __name__ == '__main__':
    assert os.geteuid() == 0
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('stage', 'refresh', 'test', 'test_agent', 'release'))
    args = parser.parse_args()
    globals()[args.action]()
