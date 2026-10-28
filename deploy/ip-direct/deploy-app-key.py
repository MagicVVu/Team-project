"""Run as root with a reviewed JSON source bundle; updates only backend.

Backups stay private on server. No migrations, firewall changes or AI restarts.
"""
import base64
import copy
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import sys
import time
from datetime import datetime, timezone

import yaml

CONFIG = Path('/srv/magicvvu/magicvvu-starter/deploy/compose.yaml')
EDGE = Path('/srv/magicvvu/ip-direct/serve.py')
BACKEND = 'magicvvu-starter-backend-1'
OTHERS = ['magicvvu-starter-agent-1', 'magicvvu-starter-db-1']


def run(*args):
    result = subprocess.run(args, capture_output=True, timeout=180)
    if result.returncode:
        diagnostic = Path('/srv/magicvvu/releases/app-key-last-error.log')
        diagnostic.write_bytes(result.stdout + result.stderr)
        diagnostic.chmod(0o600)
        raise RuntimeError('Command failed (output withheld): ' + args[0])
    return result.stdout.decode().strip()


def inspect():
    return {c['Name'].lstrip('/'): c for c in json.loads(run('docker', 'inspect', BACKEND, *OTHERS))}


def main():
    assert os.geteuid() == 0
    bundle = json.loads(Path(sys.argv[1]).read_text())
    key = bundle['key']
    assert re.fullmatch('[a-f0-9]{64}', key)
    before = inspect()
    backend = before[BACKEND]
    assert backend['State']['Health']['Status'] == 'healthy'
    # Docker regenerates NAT rules and iptables-save includes wall-clock comments.
    # Compare the actual source filter and host input policy instead.
    def source_firewall():
        return (run('iptables', '-t', 'raw', '-S'), run('iptables', '-S', 'INPUT'))
    firewall = source_firewall()
    env_hash = hashlib.sha256((CONFIG.parent / '.env').read_bytes()).hexdigest()
    release = Path('/srv/magicvvu/releases') / ('app-key-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    release.mkdir(mode=0o700)
    shutil.copy2(CONFIG, release / 'compose-before.yaml')
    shutil.copy2(EDGE, release / 'serve-before.py')
    original = CONFIG.read_text()
    run('docker', 'cp', BACKEND + ':/app/app/main.py', str(release / 'main-before.py'))
    source = (release / 'main-before.py').read_text()
    assert source.count('from app.login_guard import LoginGuard') == 1
    assert 'AppKeyMiddleware' not in source
    source = source.replace('from app.login_guard import LoginGuard',
                            'from app.login_guard import LoginGuard\nfrom app.app_access import AppKeyMiddleware')
    source = source.replace('app.state.login_guard = LoginGuard()',
                            'app.state.login_guard = LoginGuard()\napp.add_middleware(AppKeyMiddleware)')
    assert source.count('app.add_middleware(AppKeyMiddleware)') == 1
    (release / 'main.py').write_text(source)
    for name in ('app_access.py', 'serve.py', 'ca.pem'):
        (release / name).write_bytes(base64.b64decode(bundle[name]))
    image = 'magicvvu/backend:app-key-' + release.name.removeprefix('app-key-').lower()
    base_image = backend['Config']['Image']
    assert run('docker', 'image', 'inspect', base_image, '--format', '{{.Id}}') == backend['Image']
    (release / '.dockerignore').write_text('*\n!Dockerfile\n!main.py\n!app_access.py\n')
    (release / 'Dockerfile').write_text(f'FROM {base_image}\nCOPY --chown=10001:10001 main.py app_access.py /app/app/\n')
    run('docker', 'build', '--pull=false', '-t', image, str(release))
    env = dict(x.split('=', 1) for x in backend['Config']['Env'])
    env['MAGICVVU_APP_API_KEY'] = key
    envfile = release / 'private-candidate.env'
    envfile.write_text('\n'.join(k + '=' + v for k, v in env.items()) + '\n')
    envfile.chmod(0o600)
    network = next(iter(backend['NetworkSettings']['Networks']))
    candidate = 'magicvvu-app-key-candidate'
    probe = '''import json,urllib.request,urllib.error,time,os
def check(path,expected,key=None):
 h={} if key is None else {"X-MagicVVu-App-Key":key}
 try:
  r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8000"+path,headers=h),timeout=3)
  code=r.status
 except urllib.error.HTTPError as e: code=e.code
 assert code==expected,(path,code,expected)
for i in range(30):
 try: check("/api/v1/health",200); break
 except OSError: time.sleep(1)
else: raise RuntimeError("candidate not ready")
check("/api/v1/users/me",403)
check("/api/v1/users/me",403,"wrong")
check("/api/v1/users/me",401,os.environ["MAGICVVU_APP_API_KEY"])
check("/api/v1/ready",200)
'''
    try:
        run('docker', 'run', '-d', '--name', candidate, '--network', network, '--env-file', str(envfile),
            image, 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000', '--no-proxy-headers')
        for extra_network in backend['NetworkSettings']['Networks']:
            if extra_network != network:
                run('docker', 'network', 'connect', extra_network, candidate)
        run('docker', 'exec', candidate, 'python', '-c', probe)
    except Exception:
        (release / 'candidate.log').write_text(run('docker', 'logs', candidate))
        raise
    finally:
        run('docker', 'rm', '-f', candidate)
        envfile.unlink(missing_ok=True)
    old = yaml.safe_load(original)
    expected = copy.deepcopy(old)
    expected['services']['backend']['image'] = image
    expected['services']['backend']['environment']['MAGICVVU_APP_API_KEY'] = key
    # Restrict replacements to the backend section, preserving private values/comments.
    section = re.search(r'(?ms)^  backend:\n.*?(?=^  [a-zA-Z_][\w-]*:|\Z)', original)
    assert section
    block, count = re.subn(r'(?m)^(    image:).*$', lambda m: m[1] + ' ' + image, section[0])
    assert count == 1 and 'MAGICVVU_APP_API_KEY' not in block
    block, count = re.subn(r'(?m)^    environment:\s*$',
        '    environment:\n      MAGICVVU_APP_API_KEY: "' + key + '"', block)
    assert count == 1
    changed = original[:section.start()] + block + original[section.end():]
    assert yaml.safe_load(changed) == expected
    staged = CONFIG.with_suffix('.app-key.tmp')
    staged.write_text(changed)
    shutil.copystat(CONFIG, staged)
    os.chown(staged, CONFIG.stat().st_uid, CONFIG.stat().st_gid)
    run('docker', 'compose', '-f', str(staged), 'config', '--quiet')
    ctx = ssl.create_default_context(cafile=str(release / 'ca.pem'))
    ctx.check_hostname = False  # Loopback transport; still verifies the existing team CA.

    def tls(path, expected_status, access=None, method='GET'):
        conn = http.client.HTTPSConnection('127.0.0.1', 8000, context=ctx, timeout=5)
        try:
            conn.connect()
            fingerprint = hashlib.sha256(conn.sock.getpeercert(binary_form=True)).hexdigest()
            conn.request(method, path, headers={} if access is None else {'X-MagicVVu-App-Key': access})
            response = conn.getresponse()
            response.read()
            assert response.status == expected_status, (path, response.status, expected_status)
            return fingerprint
        finally:
            conn.close()

    cert_before = tls('/api/v1/health', 200)
    try:
        staged.replace(CONFIG)
        shutil.copy2(release / 'serve.py', EDGE)
        run('docker', 'compose', '-f', str(CONFIG), 'up', '-d', '--no-deps', '--pull', 'never', 'backend')
        for _ in range(45):
            after = inspect()
            if after[BACKEND]['State'].get('Health', {}).get('Status') == 'healthy':
                break
            time.sleep(1)
        else:
            raise RuntimeError('Backend health failed')
        for path in ('/health', '/api/v1/health', '/api/v1/users/me'):
            tls(path, 403)
            tls(path, 403, 'wrong')
        assert tls('/api/v1/health', 200, key) == cert_before
        tls('/api/v1/users/me', 401, key)
        for path in ('/api/v1/auth/login', '/api/v1/auth/register'):
            tls(path, 403, method='POST')
            tls(path, 422, key, method='POST')
        tls('/internal/v1/inventory/search', 404, key)
        tls('/api/v1/ready', 404, key)
        new_env = dict(x.split('=', 1) for x in after[BACKEND]['Config']['Env'])
        assert new_env == env
        assert all(after[n]['Id'] == before[n]['Id'] for n in OTHERS)
        assert source_firewall() == firewall
        assert hashlib.sha256((CONFIG.parent / '.env').read_bytes()).hexdigest() == env_hash
    except Exception:
        shutil.copy2(release / 'compose-before.yaml', CONFIG)
        shutil.copy2(release / 'serve-before.py', EDGE)
        run('docker', 'compose', '-f', str(CONFIG), 'up', '-d', '--no-deps', '--pull', 'never', 'backend')
        raise
    finally:
        staged.unlink(missing_ok=True)
    report = dict(passed=True, image=image, backup=str(release), tls_fingerprint=cert_before,
                  candidate_passed=True, missing_wrong_key=403, key_without_login=401,
                  login_register_validation=422, private_routes=404,
                  agent_database_unchanged=True, firewall_unchanged=True, existing_env_unchanged=True)
    (release / 'verification.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


if __name__ == '__main__':
    main()
