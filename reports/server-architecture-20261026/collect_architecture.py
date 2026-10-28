"""Read-only production architecture inventory; export metadata, never credentials or rows."""
import datetime
import hashlib
import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(__file__).resolve().parent

BACKEND = r'''
import datetime, hashlib, inspect as pyinspect, json, pathlib, platform, subprocess
import httpx
from sqlalchemy import inspect, text
from app.main import app
from app.database import engine
from app.routers.agent_gateway import check_config
from app.routers.draft_execution import capabilities

result = {'python':platform.python_version(), 'capabilities':capabilities(None)}
result['routes'] = [{'path':r.path,'methods':sorted(r.methods),
 'file':pyinspect.getsourcefile(r.endpoint),'line':pyinspect.getsourcelines(r.endpoint)[1],
 'function':r.endpoint.__name__} for r in app.routes if hasattr(r,'methods')]
result['openapi'] = app.openapi()
with engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 result['migration'] = list(c.execute(text('SELECT version_num FROM alembic_version')).scalars())
 result['postgres_version'] = c.execute(text('SHOW server_version')).scalar()
 result['database_size_bytes'] = c.execute(text('SELECT pg_database_size(current_database())')).scalar()
 metadata = inspect(c)
 result['tables'] = {t:{'columns':[{'name':x['name'],'type':str(x['type']),'nullable':x['nullable']} for x in metadata.get_columns(t)],
 'primary_key':metadata.get_pk_constraint(t)['constrained_columns'],
 'foreign_keys':[{'columns':x['constrained_columns'],'target_table':x['referred_table'],'target_columns':x['referred_columns']} for x in metadata.get_foreign_keys(t)],
 'unique_constraints':[x['column_names'] for x in metadata.get_unique_constraints(t)]} for t in metadata.get_table_names()}
result['source_hashes'] = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ['app','alembic'] for p in pathlib.Path(folder).rglob('*.py')}
with httpx.Client(timeout=12,trust_env=False) as client:
 result['backend_health'] = client.get('http://127.0.0.1:8000/api/v1/health').json()
 result['backend_ready'] = client.get('http://127.0.0.1:8000/api/v1/ready').json()
 result['unauthenticated_capabilities_status'] = client.get('http://127.0.0.1:8000/api/v1/agent/execution-capabilities').status_code
 url = check_config()[0].rstrip('/')
 result['agent_health'] = client.get(url+'/health').json()
 result['agent_openapi'] = client.get(url+'/openapi.json').json()
preflight = subprocess.run(['python','-m','app.p9_preflight'],capture_output=True,text=True,timeout=60,check=True)
result['preflight'] = json.loads(preflight.stdout)
print(json.dumps(result,ensure_ascii=False))
'''

AGENT = r'''
import hashlib,json,pathlib,platform
import importlib.metadata
print(json.dumps({'python':platform.python_version(),
 'packages':{n:importlib.metadata.version(n) for n in ['fastapi','pydantic','httpx','uvicorn']},
 'normalized_source_hashes':{str(p):hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest() for folder in ['conversation','interaction','v1','p3','p2','p1','p0','integration','review'] for p in pathlib.Path('/app/agent',folder).rglob('*.py')},
 'source_hashes':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ['conversation','interaction','v1','p3','p2','p1','p0','integration','review'] for p in pathlib.Path('/app/agent',folder).rglob('*.py')}}))
'''

HOST = r'''
import datetime,hashlib,json,pathlib,subprocess
def run(args,stdin=None,timeout=30):
 p=subprocess.run(args,input=stdin,text=True,capture_output=True,timeout=timeout)
 if p.returncode: raise RuntimeError('Read-only inventory failed: '+args[0])
 return p.stdout
names=['magicvvu-starter-backend-1','magicvvu-starter-agent-1','magicvvu-starter-db-1']
raw=json.loads(run(['docker','inspect',*names]))
out={'checked_at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
 'scope':'Read-only metadata; no model calls; no business row export; no service mutation',
 'host':{},'containers':[]}
for key,cmd in {'os':['cat','/etc/os-release'],'kernel':['uname','-srmo'],'uptime':['uptime'],
 'cpu_count':['nproc'],'memory':['free','-h'],'disk':['df','-h','/'],
 'listeners':['ss','-lntup'],'stats':['docker','stats','--no-stream','--format','{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.PIDs}}'],
 'docker_version':['docker','version','--format','{{.Server.Version}}'],
 'compose_version':['docker','compose','version','--short'],
 'services':['systemctl','--no-pager','--plain','list-units','--type=service','--state=running'],
 'timers':['systemctl','--no-pager','--plain','list-timers','--all']}.items(): out['host'][key]=run(cmd)
allowed=['AUTH_ALLOW_UNVERIFIED_SIGNUP','MAGICVVU_ENABLE_DOCS','P0_MODE','P0_ENGINE','P3_ENGINE','BACKEND_BASE_URL','DB_HOST','DB_PORT','MAGICVVU_OPEN_ENABLED','MAGICVVU_DISCARD_ENABLED','MAGICVVU_REFERENCE_MESSAGES_ENABLED','HOUSEHOLD_TIMEZONE']
for row in raw:
 c,h=row['Config'],row['HostConfig']
 env=dict(x.split('=',1) for x in c.get('Env',[]) if '=' in x)
 # Never export environment wholesale or command arguments containing credentials.
 out['containers'].append({'name':row['Name'].lstrip('/'),'image':c['Image'],'image_id':row['Image'],
 'status':row['State']['Status'],'health':row['State'].get('Health',{}).get('Status'),
 'started_at':row['State']['StartedAt'],'restart_count':row['RestartCount'],
 'entrypoint':c.get('Entrypoint'),'command':c.get('Cmd') if row['Name'].endswith(('backend-1','agent-1')) else ['postgres'],
 'user':c.get('User'),'working_dir':c.get('WorkingDir'),'ports':row['NetworkSettings']['Ports'],
 'networks':list(row['NetworkSettings']['Networks']),
 'mounts':[{k:m.get(k) for k in ['Type','Name','Source','Destination','RW']} for m in row['Mounts']],
 'restart_policy':h['RestartPolicy'],'memory_bytes':h['Memory'],'nano_cpus':h['NanoCpus'],
 'pids_limit':h.get('PidsLimit'),'read_only_rootfs':h['ReadonlyRootfs'],
 'cap_drop':h.get('CapDrop'),'security_opt':h.get('SecurityOpt'),
 'logging':h['LogConfig'],'environment_allowlist':{k:env[k] for k in allowed if k in env},
 'compose_files':c.get('Labels',{}).get('com.docker.compose.project.config_files'),
 'compose_workdir':c.get('Labels',{}).get('com.docker.compose.project.working_dir')})
network_names=sorted({n for r in raw for n in r['NetworkSettings']['Networks']})
out['networks']=[{k:n.get(k) for k in ['Name','Driver','Internal','EnableIPv6','IPAM']} for n in json.loads(run(['docker','network','inspect',*network_names]))]
out['backend']=json.loads(run(['docker','exec','-i',names[0],'python','-'],BACKEND,timeout=90))
out['agent']=json.loads(run(['docker','exec','-i',names[1],'python','-'],AGENT))
out['edge_source_hashes']={}
for c in out['containers']:
 for m in c['mounts']:
  if (m['Source'] or '').endswith('.py'):
   p=pathlib.Path(m['Source'])
   if p.is_file(): out['edge_source_hashes'][str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
out['logs']={}
for name in names:
 p=subprocess.run(['docker','logs','--since','60m','--tail','300',name],text=True,capture_output=True,timeout=15)
 lines=(p.stdout+p.stderr).splitlines()
 out['logs'][name]={'sampled_lines':len(lines),'traceback_lines':sum('Traceback (most recent call last)' in l for l in lines),'fatal_lines':sum('FATAL' in l for l in lines),'raw_logs_exported':False}
print(json.dumps(out,ensure_ascii=False))
'''

if __name__ == '__main__':
    source = 'BACKEND = '+repr(BACKEND)+'\nAGENT = '+repr(AGENT)+'\n'+HOST
    p = subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','magicvvu','python3 -'],
                       input=source,capture_output=True,text=True,encoding='utf-8',timeout=180)
    if p.returncode:
        raise SystemExit('Inventory failed: '+p.stderr[-1500:])
    result = json.loads(p.stdout)
    comparisons = {}
    for kind,prefix,hashes in [('backend','backend/server',result['backend']['source_hashes']),
                                ('agent','agent',result['agent']['source_hashes'])]:
        rows=[]
        for name,digest in hashes.items():
            relative=name.removeprefix('/app/agent/')
            local=ROOT/prefix/relative
            rows.append({'file':f'{prefix}/{relative}','local_exists':local.exists(),
                         'sha256_matches':local.exists() and hashlib.sha256(local.read_bytes()).hexdigest()==digest})
            if kind == 'agent' and local.exists():
                rows[-1]['normalized_sha256_matches'] = hashlib.sha256(local.read_bytes().replace(b'\r\n',b'\n')).hexdigest() == result['agent']['normalized_source_hashes'][name]
        comparisons[kind]=rows
    result['local_source_comparison']=comparisons
    result['local_git_head']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    path=OUT/'runtime-inventory.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'saved':str(path),'checked_at':result['checked_at'],
      'backend_paths':len(result['backend']['openapi']['paths']),
      'tables':len(result['backend']['tables']),
      'source_comparison':{k:{'total':len(v),'matching':sum(r['sha256_matches'] for r in v)} for k,v in comparisons.items()},
      'preflight':result['backend']['preflight']},ensure_ascii=False))
