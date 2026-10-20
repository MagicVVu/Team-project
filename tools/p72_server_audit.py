"""Read-only host audit; run through SSH stdin. Never emit environment secrets."""
import json
import subprocess
import urllib.request
from urllib.parse import urlsplit


def run(args):
    p = subprocess.run(args, capture_output=True, text=True, timeout=25)
    return p.stdout if p.returncode == 0 else None


def docker(*args):
    return run(['sudo', '-n', 'docker', *args])


ids = (docker('ps', '-aq') or '').split()
containers = json.loads(docker('inspect', *ids) or '[]') if ids else []
rows = []
for c in containers:
    env = dict(x.split('=', 1) for x in c['Config'].get('Env', []) if '=' in x)
    labels = c['Config'].get('Labels') or {}
    rows.append({
        'id': c['Id'], 'name': c['Name'].lstrip('/'), 'image': c['Config']['Image'],
        'image_id': c['Image'], 'status': c['State']['Status'],
        'health': c['State'].get('Health', {}).get('Status'),
        'project': labels.get('com.docker.compose.project'),
        'service': labels.get('com.docker.compose.service'),
        'config_files': labels.get('com.docker.compose.project.config_files'),
        'networks': list(c['NetworkSettings']['Networks']),
        'mounts': [{'type': m['Type'], 'name': m.get('Name'), 'source': m['Source'],
                    'destination': m['Destination'], 'rw': m['RW']} for m in c.get('Mounts', [])],
        'ports': c['HostConfig']['PortBindings'],
        'database': {k: env[k] for k in ('DB_HOST', 'DB_PORT', 'DB_NAME', 'POSTGRES_DB') if k in env},
        'isolated_test': env.get('ISOLATED_APP_TEST'),
        'dependencies': {k: urlsplit(env[k]).hostname for k in ('AI_SERVICE_URL', 'BACKEND_BASE_URL') if k in env},
    })
result = {'read_only': True, 'containers': rows,
          'compose': json.loads(docker('compose', 'ls', '--format', 'json') or '[]'),
          'volumes': (docker('volume', 'ls', '--format', '{{.Name}}') or '').splitlines(),
          'networks': (docker('network', 'ls', '--format', '{{.ID}}|{{.Name}}') or '').splitlines(),
          'disk': run(['df', '-h', '/srv']), 'docker_disk': docker('system', 'df'),
          'funnel': json.loads(run(['tailscale', 'funnel', 'status', '--json']) or '{}')}
for path in ['/api/v1/health', '/api/v1/ready']:
    try:
        with urllib.request.urlopen('http://127.0.0.1:8000' + path, timeout=10) as r:
            result[path] = {'status': r.status, 'body': json.load(r)}
    except (OSError, ValueError):
        result[path] = {'unavailable': True}
# Migration metadata only; no application records or credentials leave the host.
result['migration'] = docker('exec', 'magicvvu-starter-backend-1', 'alembic', 'current')
result['backup_file_metadata'] = run(['sudo', '-n', 'find', '/srv/magicvvu', '/home/admin',
    '-maxdepth', '4', '-type', 'f', '(', '-name', '*.dump', '-o', '-name', '*.sql.gz',
    '-o', '-name', '*handoff*', ')', '-printf', '%p|%s bytes|%TY-%Tm-%Td\n'])
print(json.dumps(result, ensure_ascii=False, indent=2))
