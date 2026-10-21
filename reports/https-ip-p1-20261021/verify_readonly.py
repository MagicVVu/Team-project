"""Follow-up P1 GET health checks and bounded read-only network probes."""
import concurrent.futures
import datetime
import glob
import json
import pathlib
import subprocess
import urllib.request


def run(args, timeout=18):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return {"rc": p.returncode, "stdout": p.stdout.strip(), "stderr": p.stderr.strip()[:1000]}
    except subprocess.TimeoutExpired:
        return {"timeout": True}


out = {"phase": "P1", "read_only": True, "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "health": {}}
for path in ['/api/v1/health', '/api/v1/ready']:
    try:
        with urllib.request.urlopen('http://127.0.0.1:8000' + path, timeout=8) as r:
            data = json.load(r)
            out['health'][path] = {"http": r.status, "body": {k: data[k] for k in ['status', 'service', 'version', 'isolated_test', 'database'] if k in data}}
    except Exception as e:
        out['health'][path] = {"error": type(e).__name__}

out['db_readiness'] = run(['docker', 'exec', 'magicvvu-starter-db-1', 'pg_isready', '-h', '127.0.0.1', '-p', '5432'])
scan = '''import ast,json,pathlib
rows=[]
for p in pathlib.Path('app').rglob('*.py'):
 if 'routers' not in p.parts and p.name != 'main.py': continue
 text=p.read_text(); tree=ast.parse(text)
 for node in ast.walk(tree):
  if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
   for d in node.decorator_list:
    if isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and d.func.attr in ['get','post','put','patch','delete','websocket'] and d.args and isinstance(d.args[0],ast.Constant):
     rows.append({'file':str(p),'method':d.func.attr,'path':d.args[0].value})
markers=[]
for p in pathlib.Path('app').rglob('*.py'):
 text=p.read_text()
 found=[s for s in ['StreamingResponse','text/event-stream','WebSocket','httpx.Timeout(13.0, connect=3.0)'] if s in text]
 if found: markers.append({'file':str(p),'markers':found})
print(json.dumps({'routes':rows,'streaming_timeout_markers':markers}))'''
out['deployed_route_metadata'] = run(['docker', 'exec', 'magicvvu-starter-backend-1', 'python', '-c', scan])
out['snap_certbot_info'] = run(['snap', 'info', 'certbot'], 18)
out['snap_changes'] = run(['snap', 'changes'], 8)

def probe(item):
    label, url = item
    return {"label": label, "result": run(['curl', '--noproxy', '*', '--proto', '=http,https', '--connect-timeout', '5', '--max-time', '12', '-sS', '-o', '/dev/null', '-w', 'http=%{http_code} peer=%{remote_ip} tls_verify=%{ssl_verify_result} total=%{time_total}', url], 14)}

checks = [('production_repeat_1', 'https://acme-v02.api.letsencrypt.org/directory'),
          ('staging_repeat', 'https://acme-staging-v02.api.letsencrypt.org/directory'),
          ('configured_aliyun_apt_mirror', 'http://mirrors.cloud.aliyuncs.com/ubuntu/dists/noble/Release')]
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    out['network_recheck'] = list(pool.map(probe, checks))
out['network_recheck'].append(probe(('production_repeat_2', 'https://acme-v02.api.letsencrypt.org/directory')))
out['extra_certificate_locations'] = []
for name in ['/etc/ssl/private/ssl-cert-snakeoil.key', '/etc/ssl/certs/ssl-cert-snakeoil.pem', *glob.glob('/home/*/.acme.sh'), *glob.glob('/home/*/.local/share/letsencrypt'), *glob.glob('/etc/caddy'), *glob.glob('/var/lib/caddy')]:
    p = pathlib.Path(name)
    if p.exists():
        s = p.stat()
        out['extra_certificate_locations'].append({'path': name, 'mode': oct(s.st_mode & 0o7777), 'size': s.st_size})
out['final_health'] = run(['docker', 'ps', '--format', '{{.Names}}|{{.Status}}|{{.Ports}}'])
out['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
print(json.dumps(out, ensure_ascii=False, indent=2))
