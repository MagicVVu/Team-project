"""Read-only deployment audit plus HTTP startup/rollback in NEW synthetic rehearsal DB."""
import hashlib, json, os, subprocess, time
from pathlib import Path
from uuid import uuid4
assert os.geteuid()==0
ROOT=Path('/home/admin/magicvvu-p7-rc-20261017')
PROJECT='magicvvu-p7-execution-20261017'
def run(*args,**kwargs): return subprocess.run(['docker',*args],capture_output=True,**kwargs)
def inspect(name):return json.loads(run('inspect',name).stdout)[0]
def env(c):return dict(x.split('=',1) for x in c['Config']['Env'])
containers=[]
for c in json.loads(run('inspect',*run('ps','--format','{{.Names}}').stdout.decode().splitlines()).stdout):
    if 'magicvvu' not in c['Name']: continue
    containers.append({'name':c['Name'].lstrip('/'),'id':c['Id'],'image':c['Image'],'tag':c['Config']['Image'],
      'started_at':c['State']['StartedAt'],'restart_count':c['RestartCount'],'status':c['State']['Status'],
      'health':c['State'].get('Health',{}).get('Status'),'user':c['Config']['User'],
      'readonly_rootfs':c['HostConfig']['ReadonlyRootfs'],'cap_drop':c['HostConfig'].get('CapDrop'),
      'security_opt':c['HostConfig'].get('SecurityOpt'),'ports':c['NetworkSettings']['Ports'],
      'networks':list(c['NetworkSettings']['Networks']),'environment_names':sorted(env(c)),
      'command':c['Config']['Cmd']})
b=inspect(PROJECT+'-backend-1');ag=inspect(PROJECT+'-agent-1');be,ae=env(b),env(ag)
assert be['DB_NAME']=='magicvvu_p7_execution_test' and be['ISOLATED_APP_TEST']=='yes'
config={'AI_SERVICE_TOKEN':{'backend_configured':len(be.get('AI_SERVICE_TOKEN',''))>=32,'agent_matches':be.get('AI_SERVICE_TOKEN')==ae.get('AI_SERVICE_TOKEN')},
 'BACKEND_TOOL_TOKEN':{'backend_configured':bool(be.get('BACKEND_TOOL_TOKEN')),'agent_matches':be.get('BACKEND_TOOL_TOKEN')==ae.get('BACKEND_TOOL_TOKEN')},
 'AI_SERVICE_URL':{'fixed_internal_destination':be.get('AI_SERVICE_URL')=='http://agent:8767'},
 'BACKEND_BASE_URL':{'fixed_internal_destination':ae.get('BACKEND_BASE_URL')=='http://backend:8000'},
 'model':{'engine_rules':ae.get('P3_ENGINE')=='rules','provider_key_present':bool(ae.get('DEEPSEEK_API_KEY'))}}
health={}
for name,port,path in [(PROJECT+'-backend-1',8000,'/api/v1/health'),(PROJECT+'-agent-1',8767,'/health'),('magicvvu-starter-backend-1',8000,'/api/v1/health')]:
    p=run('exec',name,'python','-c',f"import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:{port}{path}').read().decode())")
    health[name]=json.loads(p.stdout)
hashes={}
for name,files in [(PROJECT+'-backend-1',['app/routers/draft_execution.py','app/services/draft_execution.py','app/execution_models.py','app/execution_schemas.py','alembic/versions/20261017_0007_draft_execution.py']),
                   (PROJECT+'-agent-1',['agent/conversation/manager.py','agent/conversation/engines.py'])]:
    base='/app/'
    p=run('exec',name,'python','-c',"import hashlib,json;from pathlib import Path;print(json.dumps({p:hashlib.sha256(Path('/app/'+p).read_bytes()).hexdigest() for p in "+repr(files)+"}))")
    hashes[name]=json.loads(p.stdout)
summary=json.loads((ROOT/'rehearsal.json').read_text()); dbname=summary['database']
assert dbname.startswith('magicvvu_p7_rc_')
private_env=dict(os.environ,**{k:be[k] for k in ('DB_HOST','DB_PORT','DB_USER','DB_PASSWORD') if k in be},DB_NAME=dbname,ISOLATED_APP_TEST='yes',AUTH_ALLOW_UNVERIFIED_SIGNUP='false')
startup=[]
for image,version in [('magicvvu/backend:draft-v0.9-test','0.9.0'),('magicvvu/backend:app-v0.8','0.8.0')]:
    name='magicvvu-p7-rc-startup-'+uuid4().hex[:8]
    args=['run','-d','--name',name,'--network',PROJECT+'_test_net','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--tmpfs','/tmp:rw,nosuid,size=64m']
    for key in ('DB_HOST','DB_PORT','DB_USER','DB_PASSWORD','DB_NAME','ISOLATED_APP_TEST','AUTH_ALLOW_UNVERIFIED_SIGNUP'):
        if key in private_env:args+=['-e',key]
    p=run(*args,image,env=private_env);assert p.returncode==0
    try:
        for _ in range(15):
            p=run('exec',name,'python','-c',"import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health',timeout=2).read().decode())")
            if p.returncode==0:break
            time.sleep(1)
        h=json.loads(p.stdout);assert h['version']==version and h['isolated_test'] is True
        startup.append({'image':image,'health':h,'database':dbname,'published_ports':inspect(name)['HostConfig']['PortBindings']})
    finally:
        run('stop','--time','5',name);run('rm',name)
summary['isolated_app_upgrade_and_rollback_health']=startup
(ROOT/'rehearsal.json').write_text(json.dumps(summary,indent=2))
result={'containers':containers,'configuration_checks':config,'health':health,'runtime_sha256':hashes,'rehearsal':summary}
(ROOT/'server-audit.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
