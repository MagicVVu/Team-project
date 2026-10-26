"""SSH read-only baseline. Emits allowlisted metadata; never environment/log bodies."""
import json
import pathlib
import subprocess
import argparse

REMOTE = r"""
import json,subprocess
def run(args,stdin=None):
 p=subprocess.run(args,input=stdin,text=True,capture_output=True,timeout=40)
 if p.returncode: raise RuntimeError('read-only command failed: '+args[0])
 return p.stdout
out={'ssh_user':run(['id','-un']).strip(),'host':run(['hostname']).strip(),
 'deployment_path':'/srv/magicvvu/magicvvu-starter','deployment_git_present':False}
out['compose']=[]
for line in run(['sudo','-n','docker','compose','-f','/srv/magicvvu/magicvvu-starter/deploy/compose.yaml','ps','--format','json']).splitlines():
 row=json.loads(line);out['compose'].append({k:row[k] for k in ['Name','Image','Health','State','Ports']})
out['preflight']=json.loads(run(['sudo','-n','docker','exec','magicvvu-starter-backend-1','python','-m','app.p8_preflight']))
script='''
import json,asyncio,httpx
from sqlalchemy import text
from app.main import app,health_check
from app.database import engine
from app.routers.draft_execution import capabilities
with engine.connect() as c: versions=list(c.execute(text('SELECT version_num FROM alembic_version')).scalars())
async def ai():
 async with httpx.AsyncClient(trust_env=False) as c:
  h=(await c.get('http://agent:8767/health')).json()
  spec=(await c.get('http://agent:8767/openapi.json')).json()
  return {'health':{k:v for k,v in h.items() if k in ['status','maintenance_release','active_human_rule_count','engine','conversation_memory_protocol']},'paths':list(spec['paths'])}
s=app.openapi()
print(json.dumps({'migration':versions,'backend_health':health_check(),'capabilities':capabilities(None),'shopping_update':s['components']['schemas']['ShoppingItemUpdate'],'backend_paths':list(s['paths']),'ai':asyncio.run(ai())}))
'''
out['runtime']=json.loads(run(['sudo','-n','docker','exec','-i','magicvvu-starter-backend-1','python','-'],script))
out['logs']={}
for name in ['magicvvu-starter-backend-1','magicvvu-starter-agent-1','magicvvu-starter-db-1']:
 p=subprocess.run(['sudo','-n','docker','logs','--since','30m','--tail','300',name],capture_output=True,text=True,timeout=10)
 lines=(p.stdout+p.stderr).splitlines()
 out['logs'][name]={'sampled_lines':len(lines),'traceback_lines':sum('Traceback (most recent call last)' in x for x in lines),'fatal_lines':sum('FATAL' in x for x in lines),'raw_logs_exported':False}
print(json.dumps(out))
"""

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='reports/backend-ai-p9/production-baseline.json')
    args = parser.parse_args()
    p = subprocess.run(['ssh', 'magicvvu', 'python3 -'], input=REMOTE,
                       capture_output=True, text=True, encoding='utf-8', timeout=120)
    if p.returncode:
        raise SystemExit('SSH baseline failed; no raw output exported')
    result = json.loads(p.stdout)
    path = pathlib.Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'saved': str(path), 'preflight': result['preflight']}))
