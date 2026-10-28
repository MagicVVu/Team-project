"""P2 READ-ONLY collector, sent via SSH stdin. Does not import the application.
Only source code and selected metadata leave the host; never env values/keys.
"""
import datetime
import hashlib
import json
import pathlib
import subprocess


def run(args, timeout=20):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return {'rc': p.returncode, 'stdout': p.stdout.strip(), 'stderr': p.stderr.strip()[:500]}
    except subprocess.TimeoutExpired:
        return {'timeout': True}


out = {'phase': 'P2', 'mode': 'read-only', 'utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
out['listeners'] = run(['ss', '-lntp'])
out['software'] = run(['dpkg-query', '-W', '-f=${Package}\t${Version}\t${Status}\n', 'nginx', 'certbot', 'snapd'])
out['services'] = {s: run(['systemctl', 'show', s, '-p', 'ActiveState', '-p', 'SubState', '-p', 'UnitFileState']) for s in ['docker', 'nginx']}
out['baseline'] = []
for name in ['/srv/magicvvu/magicvvu-starter/deploy/compose.yaml', '/srv/magicvvu/magicvvu-starter/deploy/.env']:
    p = pathlib.Path(name)
    s = p.stat()
    out['baseline'].append({'path': name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'mode': oct(s.st_mode & 0o7777), 'uid': s.st_uid, 'gid': s.st_gid})
out['containers'] = []
source_program = r'''
import ast,hashlib,json,pathlib,re
root=pathlib.Path.cwd()
selected=[]
if MODE == 'backend':
 for p in pathlib.Path('app').rglob('*.py'):
  if 'routers' in p.parts or 'services' in p.parts or p.name in ['main.py','dependencies.py','security.py','login_guard.py','schemas.py','execution_schemas.py','inventory_schemas.py','shopping_schemas.py']:
   selected.append(p)
else:
 base=pathlib.Path('agent') if pathlib.Path('agent').is_dir() else pathlib.Path('.')
 for p in base.rglob('*.py'):
  if not any(x in p.parts for x in ['tests','eval','.cache','__pycache__','scripts']): selected.append(p)
rows=[]
for p in sorted(selected):
 if p.stat().st_size>180000: continue
 text=p.read_text(); original=text
 # Redact literal credential assignments if any; no .env/config files are exported.
 tree=ast.parse(text); spans=[]
 for node in ast.walk(tree):
  if isinstance(node,(ast.Assign,ast.AnnAssign)):
   value=node.value
   names=[n.id for n in ast.walk(node) if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Store)]
   if isinstance(value,ast.Constant) and isinstance(value.value,str) and len(value.value)>12 and any(re.search('secret|password|api_key|access_token|private_key',n,re.I) for n in names):
    spans.append((value.lineno,value.col_offset,value.end_lineno,value.end_col_offset))
 lines=text.splitlines(keepends=True)
 for a,b,c,d in sorted(spans,reverse=True):
  if a==c: lines[a-1]=lines[a-1][:b]+'"[REDACTED_LITERAL]"'+lines[a-1][d:]
 text=''.join(lines)
 text=re.sub(r'(https?://)[^\s\'"/]+:[^\s\'"/]+@',r'\1[REDACTED_USERINFO]@',text)
 text=re.sub(r'sk-[A-Za-z0-9_-]{20,}','[REDACTED_KEY]',text)
 if '-----BEGIN PRIVATE KEY-----' in text or '-----BEGIN OPENSSH PRIVATE KEY-----' in text: continue
 rows.append({'path':str(p),'sha256_original':hashlib.sha256(original.encode()).hexdigest(),'redacted':original!=text,'source':text})
print(json.dumps(rows))
'''
out['source_snapshots'] = {}
for service in ['backend', 'agent', 'db']:
    name = 'magicvvu-starter-' + service + '-1'
    raw = run(['docker', 'inspect', name])
    if raw.get('rc') != 0:
        out['containers'].append({'name': name, 'error': 'inspect failed'})
        continue
    c = json.loads(raw['stdout'])[0]
    env = dict(x.split('=', 1) for x in c['Config'].get('Env', []) if '=' in x)
    out['containers'].append({'name': name, 'image': c['Config']['Image'], 'image_id': c['Image'], 'status': c['State']['Status'], 'health': c['State'].get('Health', {}).get('Status'), 'restart_policy': c['HostConfig']['RestartPolicy'], 'ports': c['HostConfig']['PortBindings'], 'restarts': c['RestartCount'], 'workdir': c['Config'].get('WorkingDir'), 'numeric_timeout_env': {k: v for k,v in env.items() if ('TIMEOUT' in k or 'RETRIES' in k) and v.replace('.','',1).isdigit()}, 'security_config_presence': {k: bool(env.get(k)) for k in ['AI_SERVICE_TOKEN','BACKEND_TOOL_TOKEN']}, 'unverified_signup_flag': env.get('AUTH_ALLOW_UNVERIFIED_SIGNUP','false').lower() in ['1','true','yes']})
    if service != 'db':
        program = 'MODE=' + repr(service) + '\n' + source_program
        result = run(['docker', 'exec', name, 'python', '-B', '-c', program])
        out['source_snapshots'][service] = json.loads(result['stdout']) if result.get('rc') == 0 else {'error': 'source collection failed', 'rc': result.get('rc')}
out['certbot_snap_info'] = run(['snap', 'info', 'certbot'])
out['timers'] = run(['systemctl', 'list-timers', '--all', '--no-pager'])
out['certificate_dir_exists'] = pathlib.Path('/etc/letsencrypt').exists()
print(json.dumps(out, ensure_ascii=False, indent=2))
