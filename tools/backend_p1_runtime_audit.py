"""Read-only runtime baseline. Never prints environment, credentials or user rows."""
import json
import subprocess
import argparse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--stage', choices=('p1', 'p2', 'p3'), default='p1')
stage = parser.parse_args().stage
REMOTE = r'''
import json, subprocess

def inside(name, code):
    value = subprocess.run(['docker', 'exec', name, 'python', '-c', code],
                           capture_output=True, text=True, check=True)
    return json.loads(value.stdout)

backend = 'magicvvu-starter-backend-1'
agent = 'magicvvu-starter-agent-1'
rows = subprocess.run(['docker', 'ps', '--format', '{{.Names}}|{{.Image}}|{{.Status}}'],
                      capture_output=True, text=True, check=True).stdout.splitlines()
result = {'containers': [row for row in rows if row.startswith('magicvvu-starter-')]}
result['backend'] = inside(backend, """
import json, hashlib, urllib.request
from pathlib import Path
from sqlalchemy import text
from app.database import engine
from app.routers.draft_execution import capabilities
files = ['routers/auth.py', 'routers/households.py', 'security.py', 'schemas.py',
         'routers/inventory.py', 'services/draft_execution.py', 'execution_models.py']
with engine.connect() as connection:
    revision = connection.execute(text('SELECT version_num FROM alembic_version')).scalar()
with urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health') as response:
    health = json.load(response)
print(json.dumps({'health': health, 'db_revision': revision,
    'capabilities': capabilities(identity=None),
    'source_sha256': {name: hashlib.sha256((Path('app') / name).read_text(encoding='utf-8').replace('\\r\\n', '\\n').encode()).hexdigest() for name in files}}))
""")
result['agent'] = inside(agent, """
import json, urllib.request
with urllib.request.urlopen('http://127.0.0.1:8767/health') as response:
    health = json.load(response)
keys = ['status', 'engine', 'release_version', 'inventory_writes', 'input_policy_version']
value = {key: health[key] for key in keys if key in health}
with urllib.request.urlopen('http://127.0.0.1:8767/openapi.json') as response:
    value['reply_adapter_route_present'] = '/agent/reply-resolution' in json.load(response)['paths']
print(json.dumps(value))
""")
print(json.dumps(result))
'''

response = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
    '-o', 'UpdateHostKeys=no', '-o', 'ConnectTimeout=12', 'magicvvu', 'sudo -n python3 -'],
    input=REMOTE, capture_output=True, text=True, timeout=60)
if response.returncode:
    raise RuntimeError('Read-only runtime audit failed; no remote changes performed')
result = json.loads(response.stdout)
result['checked_at_utc'] = datetime.now(timezone.utc).isoformat()
result['mode'] = 'read_only'
for name, value in result['backend']['source_sha256'].items():
    import hashlib
    local = ROOT / 'backend/server/app' / name
    result.setdefault('local_matches_runtime', {})[name] = hashlib.sha256(
    local.read_text(encoding='utf-8').replace('\r\n', '\n').encode()).hexdigest() == value
target = ROOT / f'reports/backend-{stage}-runtime-evidence.json'
target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
