"""Server-side AI-only overlay; invoked by p85_release.py over stdin.

Backups and candidate code stay under ~/workspace/agent. The only edit outside
that workspace is the existing Compose agent image/command/healthcheck fields.
Backend, DB, ports, environment files and their containers are protected.
"""
import ast
import base64
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import textwrap
import time
import traceback
import urllib.request
import yaml

ROOT = Path('/home/magicvvu_ai/workspace/agent')
CONFIG = Path('/srv/magicvvu/magicvvu-starter/deploy/compose.yaml')
BASE = CONFIG.parent
AGENT = 'magicvvu-starter-agent-1'
BACKEND = 'magicvvu-starter-backend-1'
DB = 'magicvvu-starter-db-1'
FILES = {p:base64.b64decode(v, validate=True) for p,v in PAYLOAD['files'].items()}
HASHES = {p:hashlib.sha256(v).hexdigest() for p,v in FILES.items()}
assert HASHES == PAYLOAD['hashes']
SIGNATURE = hashlib.sha256(json.dumps(HASHES, sort_keys=True).encode()).hexdigest()
SAVE = ROOT/'.releases'/('p85-20261028-'+SIGNATURE[:12])
TAG = 'magicvvu/agent:p85-'+SIGNATURE[:12]
CMD = ['python','-m','uvicorn','conversation.p85.app:create_app','--factory','--host','0.0.0.0','--port','8767']
HEALTH = ['CMD','python','-m','conversation.p85.health']


def sha(raw): return hashlib.sha256(raw).hexdigest()
def safe(path):
    assert not ROOT.is_symlink() and path.resolve().is_relative_to(ROOT), 'Unsafe workspace path'
    assert not path.is_symlink(), 'Symlinked target'
    assert all(not p.is_symlink() for p in path.parents if p.is_relative_to(ROOT)), 'Symlinked parent'
    return path


def directory(path, mode=0o755):
    safe(path)
    missing=[]; part=path
    while not part.exists(): missing.append(part); part=part.parent
    for part in reversed(missing):
        part.mkdir(mode=mode); os.chown(part, ROOT.stat().st_uid, ROOT.stat().st_gid)


def private(name, value):
    path=safe(SAVE/name); directory(path.parent, 0o700)
    path.write_bytes(value if isinstance(value, bytes) else json.dumps(value, indent=2).encode()+b'\n')
    path.chmod(0o600)


def run(args, data=None, timeout=45):
    result=subprocess.run(args, input=data, capture_output=True, timeout=timeout)
    if result.returncode:
        if SAVE.exists(): private('last-command.private.log', result.stdout+result.stderr)
        raise RuntimeError('Command failed: '+args[0]+'; private diagnostic retained on server')
    return result.stdout


def inspect(name): return json.loads(run(['docker','inspect',name]))[0]
def env(obj): return dict(v.split('=',1) for v in obj['Config']['Env'])
def project(obj):
    return {'id':obj['Id'],'image_id':obj['Image'],'image':obj['Config']['Image'],
        'started_at':obj['State']['StartedAt'],'health':obj['State'].get('Health',{}).get('Status'),
        'identity_sha256':sha(json.dumps({k:obj[k] for k in ['Config','HostConfig','Mounts']}, sort_keys=True).encode())}


def identity(obj):
    value={k:obj['Config'].get(k) for k in ['Cmd','Entrypoint','WorkingDir','User','Healthcheck']}
    value.update(environment=env(obj), mounts=sorted(obj['Mounts'],key=lambda m:m['Destination']),
        networks=sorted(obj['NetworkSettings']['Networks']),
        host={k:obj['HostConfig'].get(k) for k in ['PortBindings','NetworkMode','ReadonlyRootfs','CapAdd','CapDrop',
            'SecurityOpt','Tmpfs','Memory','NanoCpus','RestartPolicy','PidsLimit','Dns','DnsSearch','DnsOptions']})
    for key in ['Dns','DnsSearch','DnsOptions']: value['host'][key]=value['host'][key] or []
    return value


def protected():
    names=run(['docker','ps','--format','{{.Names}}']).decode().splitlines()
    return {n:project(inspect(n)) for n in sorted(names) if n!=AGENT}


def workspace_hashes(): return {p:sha(safe(ROOT/p).read_bytes()) if (ROOT/p).is_file() else None for p in FILES}
def container_sources():
    obj=inspect(AGENT)
    mounts=[m['Destination'] for m in obj['Mounts']]
    code=r'''import hashlib,json,pathlib
r=pathlib.Path('/app/agent'); ignored=[pathlib.Path(x) for x in MOUNTS]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
selected={p:digest(r/p) if (r/p).is_file() else None for p in PATHS}
normalized={p:hashlib.sha256((r/p).read_bytes().replace(b'\r\n',b'\n')).hexdigest() if (r/p).is_file() else None for p in PATHS}
all_python={p.relative_to(r).as_posix():digest(p) for p in r.rglob('*.py') if '.cache' not in p.relative_to(r).parts and not any(x==p or x in p.parents for x in ignored)}
print(json.dumps({'hashes':selected,'lf_hashes':normalized,'all_python':all_python}))
'''
    return json.loads(run(['docker','exec',AGENT,'python','-B','-c','PATHS='+repr(list(FILES))+'\nMOUNTS='+repr(mounts)+'\n'+code]))


def sql(query):
    # psql obtains credentials only inside the existing DB container. No secrets
    # enter shell arguments, stdout, local reports, or copied source bundles.
    command='exec psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At'
    return run(['docker','exec','-i',DB,'sh','-c',command], ('BEGIN READ ONLY;\n'+query+'\nROLLBACK;\n').encode()).decode().strip()


def database_state():
    tables=json.loads(sql("SELECT json_agg(tablename) FROM pg_tables WHERE schemaname='public';")) or []
    versions=json.loads(sql('SELECT json_agg(version_num) FROM alembic_version;')) if 'alembic_version' in tables else None
    active={}
    for table, condition in [('ai_tasks',"status='processing' AND lease_until>CURRENT_TIMESTAMP"),
                              ('ai_conversation_bindings',"processing_nonce IS NOT NULL AND lease_until>CURRENT_TIMESTAMP")]:
        if table in tables: active[table]=int(sql('SELECT count(*) FROM '+table+' WHERE '+condition+';'))
    return {'schema_revision':versions,'active_leases':active}


def audit():
    assert ROOT.is_dir() and not ROOT.is_symlink()
    obj=inspect(AGENT); config=yaml.safe_load(CONFIG.read_bytes()); runtime=container_sources()
    drift=[]
    for p, raw in FILES.items():
        expected=sha(raw.replace(b'\r\n',b'\n'))
        actual=runtime['lf_hashes'][p]
        if actual is not None and actual!=expected: drift.append(p)
        path=safe(ROOT/p)
        if path.is_file() and sha(path.read_bytes().replace(b'\r\n',b'\n'))!=expected: drift.append('workspace:'+p)
        if path.exists() and not path.is_file(): drift.append('nonfile:'+p)
    assert not drift, 'Unreconciled AI source changes: '+', '.join(drift)
    # Public summary includes hashes and probe metadata, never Config.Env values.
    return {'stage':'audited','release':'V1-P8.5','source_sha256':SIGNATURE,'tag':TAG,
        'agent_before':project(obj),'protected':protected(),'database':database_state(),
        'compose_sha256':sha(CONFIG.read_bytes()),'workspace_hashes':workspace_hashes(),
        'runtime_hashes':runtime['hashes'],'all_python':runtime['all_python'],
        'agent_command':obj['Config']['Cmd'],'agent_healthcheck':obj['Config']['Healthcheck'],
        'compose_agent_command':config['services']['agent'].get('command'),
        'compose_agent_healthcheck':config['services']['agent'].get('healthcheck'),
        'deepseek_configured':env(obj).get('P3_ENGINE')=='deepseek' and bool(env(obj).get('DEEPSEEK_API_KEY')),
        'source_file_count':len(FILES),'formal_runtime_switched':False,'backend_modified':False}


def baseline():
    old=PAYLOAD['audit']
    assert sha(CONFIG.read_bytes())==old['compose_sha256'], 'Concurrent Compose edit'
    assert project(inspect(AGENT))==old['agent_before'], 'Concurrent AI runtime replacement'
    assert protected()==old['protected'], 'Another service changed; re-audit before release'
    assert workspace_hashes()==old['workspace_hashes'], 'Concurrent AI workspace edit'
    actual=container_sources()
    assert actual['hashes']==old['runtime_hashes'] and actual['all_python']==old['all_python'], 'Concurrent AI source edit'
    assert database_state()['schema_revision']==old['database']['schema_revision'], 'Concurrent schema migration'


def atomic(path, raw):
    if path!=CONFIG: safe(path)
    stat=path.stat() if path.exists() else None
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno()); tmp=Path(stream.name)
    tmp.chmod(stat.st_mode&0o777 if stat else 0o644)
    os.chown(tmp,stat.st_uid if stat else ROOT.stat().st_uid,stat.st_gid if stat else ROOT.stat().st_gid)
    tmp.replace(path)


def compose(args, config=CONFIG):
    return ['docker','compose','--project-directory',str(BASE),'--env-file',str(BASE/'.env'),
        '-p','magicvvu-starter','-f',str(config),*args]


def changed_compose(raw):
    before=yaml.safe_load(raw); after=copy.deepcopy(before)
    agent=after['services']['agent']; agent['image']=TAG
    if 'command' in agent: agent['command']=CMD
    if 'healthcheck' in agent: agent['healthcheck']['test']=HEALTH
    # Change only the three AI-specific fields; preserve other owners' YAML text.
    lines=raw.decode().splitlines(keepends=True); start=None; end=len(lines)
    for i,line in enumerate(lines):
        if re.match(r'^  agent:\s*$',line.rstrip()): start=i+1; continue
        if start is not None and i>=start and re.match(r'^  [^\s#]',line): end=i; break
    assert start is not None, 'Missing agent service'
    def field(i, indent, key, value):
        j=i+1
        while j<end:
            content=lines[j]
            width=len(content)-len(content.lstrip())
            indentless_item=width==indent and content.lstrip().startswith('- ')
            if content.strip() and not content.lstrip().startswith('#') and width<=indent and not indentless_item:
                break
            j+=1
        parsed=yaml.safe_load(textwrap.dedent(''.join(lines[i:j])))
        assert set(parsed)=={key}, 'Unexpected nested Compose field'
        lines[i]=' '*indent+key+': '+value+'\n'
        for n in range(i+1,j):
            if lines[n].strip() and not lines[n].lstrip().startswith('#'): lines[n]=''
    replace={'image':TAG}
    if 'command' in before['services']['agent']: replace['command']=json.dumps(CMD)
    inside_health=False; found=set()
    for i in range(start,end):
        line=lines[i]
        if re.match(r'^    healthcheck:\s*$',line.rstrip()): inside_health=True; continue
        if re.match(r'^    [^\s#]',line): inside_health=False
        if inside_health and re.match(r'^      test:',line):
            field(i,6,'test',json.dumps(HEALTH)); found.add('healthcheck'); continue
        match=re.match(r'^    (image|command):',line)
        if match and match[1] in replace:
            assert before['services']['agent'].get(match[1]) is not None
            field(i,4,match[1],replace[match[1]]); found.add(match[1])
    assert set(replace)<=found
    if 'healthcheck' in before['services']['agent']: assert 'healthcheck' in found
    result=''.join(lines).encode()
    assert yaml.safe_load(result)==after, 'Unexpected Compose changes'
    return result


def smoke(tag):
    code=r'''
import asyncio,json,datetime
from fastapi.testclient import TestClient
from conversation.engines import RuleEngine
from conversation.p85.app import create_app
class NoReads:
 def __getattr__(self,key):raise AssertionError('Unexpected tool access: '+key)
now=datetime.datetime.now(datetime.timezone.utc)
client=TestClient(create_app(engine=RuleEngine(),reader=NoReads(),now=lambda:now))
health=client.get('/health').json()
assert health['maintenance_release']=='V1-P8.5'
from conversation.p85.health import check
assert check(health)
paths=client.get('/openapi.json').json()['paths']
for route in ['/agent/message','/agent/clarification','/agent/conversation-turn','/planning/revalidate',
 '/agent/dialogue/understand','/agent/dialogue/resolve','/agent/dialogue/respond',
 '/agent/dialogue/p85/understand','/agent/dialogue/p85/resolve','/agent/dialogue/p85/respond']: assert route in paths
scope={'user_id':'33333333-3333-4333-8333-333333333333','household_id':'22222222-2222-4222-8222-222222222222'}
headers={'Authorization':'Bearer p85-candidate-synthetic-token','X-User-Id':scope['user_id'],'X-Household-Id':scope['household_id']}
body={'text':'它在哪','request_id':'p85-isolated-check','context':{'scope':scope,'conversation_id':'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','revision':0,'trusted_now':now.isoformat()}}
assert client.post('/agent/dialogue/p85/understand',json=body).status_code==401
understood=client.post('/agent/dialogue/p85/understand',json=body,headers=headers).json()
assert understood['understanding_calls']==0
resolved=client.post('/agent/dialogue/p85/resolve',json={**body,'plan':understood['plan'],'plan_context_revision':understood['context_revision']},headers=headers).json()
assert resolved['model_calls']==0 and resolved['result'] is None
print(json.dumps({'isolated_no_network':True,'old_routes_retained':True,'new_routes_verified':True,'internal_auth_verified':True,'model_calls':0,'inventory_reads':0,'inventory_writes':False}))
'''
    args=['docker','run','--rm','--pull','never','--network','none','--read-only','--cap-drop','ALL',
        '--security-opt','no-new-privileges','--tmpfs','/tmp:rw,noexec,nosuid,size=32m','--memory','320m','--pids-limit','96',
        '-e','PYTHONDONTWRITEBYTECODE=1','-e','AI_SERVICE_TOKEN=p85-candidate-synthetic-token',
        '-e','P3_ENGINE=rules','--entrypoint','python','-i',tag,'-B','-']
    return json.loads(run(args,code.encode(),timeout=60))


def prepare():
    baseline()
    assert not (SAVE/'prepare.json').exists() and not (SAVE/'deployed.json').exists(), 'Release already prepared or deployed'
    if (SAVE/'agent.before.private.json').exists():
        assert project(json.loads((SAVE/'agent.before.private.json').read_text()))==project(inspect(AGENT)), 'Original backup no longer matches'
        assert (SAVE/'compose.before.private.yaml').read_bytes()==CONFIG.read_bytes(), 'Compose backup no longer matches'
    directory(SAVE,0o700); SAVE.chmod(0o700)
    original=inspect(AGENT)
    private('agent.before.private.json',original); private('compose.before.private.yaml',CONFIG.read_bytes())
    private('audit.private.json',PAYLOAD['audit'])
    private('configuration-digests.private.json',{str(p):sha(p.read_bytes()) for p in [BASE/'.env',ROOT/'.env.runtime'] if p.is_file()})
    existing={p:sha(safe(ROOT/p).read_bytes()) for p in FILES if (ROOT/p).is_file()}
    private('workspace-before-manifest.json',existing)
    for rel in FILES:
        path=safe(ROOT/rel)
        if path.is_file() and sha(path.read_bytes())!=HASHES[rel]: private('workspace-before/'+rel,path.read_bytes())
    candidate=safe(ROOT/'candidates'/('p85-'+SIGNATURE[:12]))
    if candidate.exists():
        assert all((candidate/p).is_file() and sha((candidate/p).read_bytes())==HASHES[p] for p in FILES), 'Candidate source changed'
    directory(candidate)
    for rel,raw in FILES.items():
        if rel.endswith('.py'): ast.parse(raw.decode('utf-8-sig'),filename=rel)
        path=safe(candidate/rel); directory(path.parent); atomic(path,raw)
    # Existing runtime code was checked for unknown drift. Overlay only changed
    # owned files, deriving from its immutable image to retain unrelated code.
    overlay={p:raw for p,raw in FILES.items() if PAYLOAD['audit']['runtime_hashes'][p]!=HASHES[p]}
    recipe='FROM '+original['Image']+'\nLABEL magicvvu.ai_adapter_release="V1-P8.5" magicvvu.p85_source_sha256="'+SIGNATURE+'"\n'
    timing=original['Config']['Healthcheck']
    flags=' '.join('--'+flag+'='+str(timing[key])+suffix for flag,key,suffix in [
        ('interval','Interval','ns'),('timeout','Timeout','ns'),('start-period','StartPeriod','ns'),('retries','Retries','')])
    recipe+='COPY source/ /app/agent/\nCMD '+json.dumps(CMD)+'\nHEALTHCHECK '+flags+' CMD ["python","-m","conversation.p85.health"]\n'
    archive=io.BytesIO()
    with tarfile.open(fileobj=archive,mode='w') as tar:
        for rel,raw in [('Dockerfile',recipe.encode()),*[('source/'+p,b) for p,b in overlay.items()]]:
            info=tarfile.TarInfo(rel); info.size=len(raw); info.mode=0o644; info.mtime=0; tar.addfile(info,io.BytesIO(raw))
    result=subprocess.run(['docker','build','--pull=false','--network=none','-t',TAG,'-'],input=archive.getvalue(),
        capture_output=True,timeout=180,env={**os.environ,'DOCKER_BUILDKIT':'0'})
    private('agent-build.private.log',result.stdout+result.stderr)
    assert result.returncode==0, 'Candidate build failed'
    check=smoke(TAG)
    candidate_config=changed_compose(CONFIG.read_bytes()); private('compose.candidate.private.yaml',candidate_config)
    run(compose(['config','--quiet'],SAVE/'compose.candidate.private.yaml'))
    baseline()
    result={'stage':'prepared','release':'V1-P8.5','tag':TAG,'source_sha256':SIGNATURE,'overlay_files':sorted(overlay),
        'candidate_directory':str(candidate),'backup_directory':str(SAVE),'candidate_checks':check,
        'backend_modified':False,'database_migrations_executed':False,'formal_runtime_switched':False}
    private('prepare.json',result); return result


def fetch(origin,path,headers=None,body=None):
    request=urllib.request.Request(origin+path,headers=headers or {},data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=22) as response: return json.load(response)


def agent_origin():
    obj=inspect(AGENT)
    return 'http://'+next(iter(obj['NetworkSettings']['Networks'].values()))['IPAddress']+':8767'


def wait_healthy():
    for _ in range(40):
        obj=inspect(AGENT)
        if obj['State'].get('Health',{}).get('Status')=='healthy': return
        if obj['State']['Status'] in {'exited','dead'}: raise RuntimeError('AI service exited')
        time.sleep(2)
    raise RuntimeError('AI health deadline exceeded')


def verify():
    old=PAYLOAD['audit']; original=json.loads((SAVE/'agent.before.private.json').read_text())
    obj=inspect(AGENT); assert obj['Config']['Image']==TAG
    assert protected()==old['protected'], 'Protected service changed'
    expected=identity(original); expected['Cmd']=CMD
    expected['Healthcheck']={**expected['Healthcheck'],'Test':HEALTH}
    assert identity(obj)==expected, 'Unrelated AI settings changed'
    assert obj['State'].get('Health',{}).get('Status')=='healthy'
    current=container_sources()
    assert current['hashes']==HASHES
    expected_python={**old['all_python'],**{p:HASHES[p] for p in FILES if p.endswith('.py')}}
    assert current['all_python']==expected_python, 'Unrelated AI source changed'
    assert workspace_hashes()==HASHES
    assert CONFIG.read_bytes()==(SAVE/'compose.candidate.private.yaml').read_bytes(), 'Concurrent Compose edit'
    for path,digest in json.loads((SAVE/'configuration-digests.private.json').read_text()).items():
        assert sha(Path(path).read_bytes())==digest, 'Environment file changed'
    assert database_state()['schema_revision']==old['database']['schema_revision']
    origin=agent_origin(); health=fetch(origin,'/health')
    assert health['maintenance_release']=='V1-P8.5' and health['conversation_dialogue_protocol']=='p85-dialogue-1'
    assert health['engine']=='deepseek' and not health['inventory_writes'] and not health['shopping_writes']
    api=fetch(origin,'/openapi.json')
    assert all('/agent/dialogue/p85/'+s in api['paths'] for s in ['understand','resolve','respond'])
    assert all('/agent/dialogue/'+s in api['paths'] for s in ['understand','resolve','respond'])
    return {'stage':'verified','release':'V1-P8.5','source_sha256':SIGNATURE,'tag':TAG,'agent':project(obj),'agent_health':health,
        'protected_services_unchanged':True,'backend_container_unchanged':True,'database_container_unchanged':True,
        'environment_files_unchanged':True,'unrelated_ai_source_preserved':True,'source_files_verified':len(FILES),
        'old_ai_routes_retained':True,'database_schema_revision':old['database']['schema_revision'],
        'database_migrations_executed':False,'business_writes_performed':False,
        'backend_p85_integration_verified':False,'app_joint_acceptance':False,'backup_directory':str(SAVE)}


def switch():
    assert (SAVE/'prepare.json').exists() and not (SAVE/'deployed.json').exists()
    baseline(); inflight=database_state()['active_leases']
    assert not any(inflight.values()), 'Wait for in-flight AI tasks before switching'
    raw=CONFIG.read_bytes(); candidate=(SAVE/'compose.candidate.private.yaml').read_bytes()
    changed=False; synced=[]
    try:
        baseline()
        for rel,content in FILES.items():
            path=safe(ROOT/rel)
            if not path.is_file() or sha(path.read_bytes())!=HASHES[rel]:
                directory(path.parent); atomic(path,content); synced.append(rel)
        atomic(CONFIG,candidate); changed=True
        run(compose(['up','-d','--no-deps','--no-build','--pull','never','agent']),timeout=120)
        wait_healthy(); value=verify()
        value.update(stage='deployed',synchronized_files=synced,inflight_before_switch=inflight,
            compose_changes=['services.agent.image','services.agent.command','services.agent.healthcheck.test'])
        private('deployed.json',value); return value
    except Exception:
        if changed:
            assert CONFIG.read_bytes()==candidate, 'Concurrent deployment; do not overwrite it during rollback'
            atomic(CONFIG,raw)
            run(compose(['up','-d','--no-deps','--no-build','--pull','never','agent']),timeout=120)
            wait_healthy()
        for rel in synced:
            path=safe(ROOT/rel); backup=SAVE/'workspace-before'/rel
            assert path.is_file() and sha(path.read_bytes())==HASHES[rel], 'Concurrent workspace edit during rollback'
            if backup.is_file(): atomic(path,backup.read_bytes())
            elif PAYLOAD['audit']['workspace_hashes'][rel] is None: path.unlink()
        private('rollback.json',{'rolled_back':True,'backend_changed':False,'database_or_budget_restored':False})
        raise


def model_check():
    import datetime
    obj=inspect(AGENT); settings=env(obj)
    assert settings.get('P3_ENGINE')=='deepseek' and settings.get('DEEPSEEK_API_KEY')
    scope={'user_id':'33333333-3333-4333-8333-333333333333','household_id':'22222222-2222-4222-8222-222222222222'}
    headers={'Authorization':'Bearer '+settings['AI_SERVICE_TOKEN'],'Content-Type':'application/json',
        'X-User-Id':scope['user_id'],'X-Household-Id':scope['household_id']}
    body={'text':'你好，先聊聊整理房间的心情，不查库存，也不登记任何操作。','request_id':'p85-release-'+str(time.time_ns()),
        'context':{'scope':scope,'conversation_id':'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','revision':0,
            'trusted_now':datetime.datetime.now(datetime.timezone.utc).isoformat()},'remaining_seconds':12}
    origin=agent_origin(); start=time.monotonic()
    understood=fetch(origin,'/agent/dialogue/p85/understand',headers,body)
    assert understood['understanding_calls']==1
    assert not understood['plan']['action'] and not understood['plan']['reads'], 'Probe must not query real inventory'
    frame=fetch(origin,'/agent/dialogue/p85/resolve',headers,{**body,'plan':understood['plan'],
        'plan_context_revision':understood['context_revision'],'remaining_seconds':min(12,18-(time.monotonic()-start))})
    assert frame['result'] is None and frame['model_calls']==0 and not frame['evidence'] and not frame['expression_required']
    response=fetch(origin,'/agent/dialogue/p85/respond',headers,{'text':body['text'],'resolved':frame,'remaining_seconds':min(8,18-(time.monotonic()-start))})
    assert response['response_calls']==0 and response['reply']
    return {'release':'V1-P8.5','protocol':'p85-dialogue-1','synthetic_provider_verified':True,'model':settings.get('LLM_MODEL'),
        'understanding_calls':1,'response_calls':0,'total_calls':1,'latency_ms':(time.monotonic()-start)*1000,
        'production_inventory_read':False,'business_writes_performed':False,'tasks_or_sessions_created':False,
        'secrets_printed_or_uploaded':False,'app_joint_acceptance':False}


try:
    if STAGE=='audit': result=audit()
    elif STAGE=='baseline-check': baseline(); result={'baseline_unchanged':True}
    elif STAGE=='prepare': result=prepare()
    elif STAGE=='candidate-check': result=smoke(TAG)
    elif STAGE=='switch': result=switch()
    elif STAGE=='verify': result=verify(); private('verified.json',result)
    elif STAGE=='model-check': result=model_check(); private('model-check.json',result)
    elif STAGE=='capture':
        result={'release':'V1-P8.5','openapi':fetch(agent_origin(),'/openapi.json'),'source':'running_ai_service','backend_modified':False}
    else: raise RuntimeError('Invalid release stage')
    print(json.dumps(result))
except Exception as error:
    if SAVE.exists(): private('failure.private.txt',str(error).encode())
    print(json.dumps({'stage':STAGE,'failed':True,'error_type':type(error).__name__,'reason':str(error),
        'frames':[{'function':f.name,'line':f.lineno} for f in traceback.extract_tb(error.__traceback__)],
        'private_diagnostics_on_server':SAVE.exists()}))
    raise SystemExit(1)
