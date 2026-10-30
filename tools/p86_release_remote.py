"""P8.6 overlay deployment. Invoked over stdin by p86_release.py.

All source and private rollback state stay under ~/workspace/agent. Production
Compose changes are restricted to two images, AI command/probe and AI protocol.
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
import urllib.request
import yaml

ROOT=Path('/home/magicvvu_ai/workspace/agent')
CONFIG=Path('/srv/magicvvu/magicvvu-starter/deploy/compose.yaml')
BASE=CONFIG.parent
NAMES={s:'magicvvu-starter-'+s+'-1' for s in ('agent','backend','db')}
FILES={s:{p:base64.b64decode(v,validate=True) for p,v in entries.items()} for s,entries in PAYLOAD['files'].items()}
HASHES={s:{p:hashlib.sha256(v).hexdigest() for p,v in entries.items()} for s,entries in FILES.items()}
SIG=hashlib.sha256(json.dumps(HASHES,sort_keys=True).encode()).hexdigest()
SAVE=ROOT/'.releases'/('p86-20261030-'+SIG[:12])
CANDIDATE=ROOT/'candidates'/('p86-'+SIG[:12])
TAGS={s:'magicvvu/'+s+':p86-'+SIG[:12] for s in FILES}
COMMAND=['python','-m','uvicorn','conversation.autonomous.app:create_app','--factory','--host','0.0.0.0','--port','8767']
PROBE=['CMD','python','-m','conversation.autonomous.health']
PROTOCOL='inventory-autonomous-1'


def sha(raw):return hashlib.sha256(raw).hexdigest()
def safe(path):
    assert not ROOT.is_symlink() and path.resolve().is_relative_to(ROOT),'Unsafe workspace target'
    assert not path.is_symlink() and all(not p.is_symlink() for p in path.parents if p.is_relative_to(ROOT)),'Symlinked target'
    return path


def directory(path,mode=0o755):
    safe(path);parts=[];cursor=path
    while not cursor.exists():parts.append(cursor);cursor=cursor.parent
    for cursor in reversed(parts):
        cursor.mkdir(mode=mode);os.chown(cursor,ROOT.stat().st_uid,ROOT.stat().st_gid)


def atomic(path,raw,mode=None):
    if path!=CONFIG:safe(path)
    previous=path.stat() if path.exists() else None
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno());temp=Path(stream.name)
    temp.chmod(mode if mode is not None else previous.st_mode&0o777 if previous else 0o644)
    os.chown(temp,previous.st_uid if previous else ROOT.stat().st_uid,previous.st_gid if previous else ROOT.stat().st_gid)
    temp.replace(path)


def private(name,value):
    target=safe(SAVE/name);directory(target.parent,0o700)
    atomic(target,value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False,indent=2).encode()+b'\n',0o600)


def run(args,data=None,timeout=60):
    value=subprocess.run(args,input=data,capture_output=True,timeout=timeout)
    if value.returncode:
        if SAVE.exists():private('last-error.private.log',value.stdout+value.stderr)
        raise RuntimeError('Command failed: '+args[0]+'; diagnostics retained privately')
    return value.stdout


def inspect(name):return json.loads(run(['docker','inspect',name]))[0]
def environment(obj):return dict(v.split('=',1) for v in obj['Config']['Env'])


def projection(obj):
    return {'id':obj['Id'],'image':obj['Config']['Image'],'image_id':obj['Image'],'started_at':obj['State']['StartedAt'],
        'health':obj['State'].get('Health',{}).get('Status'),
        'identity_sha256':sha(json.dumps({k:obj[k] for k in ('Config','HostConfig','Mounts')},sort_keys=True).encode())}


def sources(service,name=None):
    paths=list(FILES[service]);root='/app/agent' if service=='agent' else '/app'
    code=r'''
import hashlib,json,pathlib,os
r=pathlib.Path(ROOT)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
selected={p:sha(r/p) if (r/p).is_file() else None for p in PATHS}
lf={p:hashlib.sha256((r/p).read_bytes().replace(b'\r\n',b'\n')).hexdigest() if (r/p).is_file() else None for p in PATHS}
all_python={}
for current,dirs,files in os.walk(r):
 dirs[:]=[d for d in dirs if d not in {'.cache','__pycache__','tests','.git'}]
 for name in files:
  if name.endswith('.py'):
   p=pathlib.Path(current)/name;all_python[p.relative_to(r).as_posix()]=sha(p)
print(json.dumps({'hashes':selected,'lf_hashes':lf,'all_python':all_python}))
'''
    return json.loads(run(['docker','exec',name or NAMES[service],'python','-B','-c',
        'ROOT='+repr(root)+'\nPATHS='+repr(paths)+'\n'+code]))


def workspace():
    return {p:sha(safe(ROOT/p).read_bytes()) if (ROOT/p).is_file() else None for p in FILES['agent']}


def environment_files():
    paths={BASE/'.env',ROOT/'.env.runtime'}
    config=yaml.safe_load(CONFIG.read_bytes())
    for obj in (inspect(NAMES['agent']),inspect(NAMES['backend'])):
        for mount in obj['Mounts']:
            path=Path(mount['Source'])
            if path.is_file():paths.add(path)
    for service in config['services'].values():
        entries=service.get('env_file',[])
        if isinstance(entries,str):entries=[entries]
        for value in entries:
            if isinstance(value,str):paths.add((BASE/value).resolve())
    return {str(p):sha(p.read_bytes()) for p in paths if p.is_file()}


def sql(query):
    command='exec psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At'
    return run(['docker','exec','-i',NAMES['db'],'sh','-c',command],
        ('BEGIN READ ONLY;\n'+query+'\nROLLBACK;\n').encode()).decode().strip()


def database():
    revision=json.loads(sql('SELECT json_agg(version_num) FROM alembic_version;'))
    active={table:int(sql('SELECT count(*) FROM '+table+' WHERE '+condition+';')) for table,condition in
        [('ai_tasks',"status='processing' AND lease_until>CURRENT_TIMESTAMP"),
         ('ai_conversation_bindings',"processing_nonce IS NOT NULL AND lease_until>CURRENT_TIMESTAMP")]}
    return {'schema_revision':revision,'active_leases':active}


def protected():
    names=run(['docker','ps','--format','{{.Names}}']).decode().splitlines()
    return {name:projection(inspect(name)) for name in names if name not in (NAMES['agent'],NAMES['backend'])}


def audit():
    objects={s:inspect(n) for s,n in NAMES.items()}
    source={s:sources(s) for s in FILES};unknown=[]
    for service,entries in FILES.items():
        for path,raw in entries.items():
            actual=source[service]['lf_hashes'][path]
            expected=sha(raw.replace(b'\r\n',b'\n'))
            if actual not in (None,PAYLOAD['base'][service][path],expected):unknown.append(service+':'+path)
    workspace_unknown=[]
    for path in FILES['agent']:
        target=safe(ROOT/path)
        if target.is_file() and sha(target.read_bytes().replace(b'\r\n',b'\n')) not in PAYLOAD['known']['agent'][path]:
            workspace_unknown.append(path)
        assert not target.exists() or target.is_file(),'Workspace target is not a file'
    return {'stage':'audited','release':'V1-P8.6','source_sha256':SIG,'local_head':PAYLOAD['local_head'],
        'containers':{s:projection(obj) for s,obj in objects.items()},'protected':protected(),
        'compose_sha256':sha(CONFIG.read_bytes()),'environment_files':environment_files(),
        'sources':source,'workspace':workspace(),'unknown_runtime_changes':unknown,'unknown_workspace_changes':workspace_unknown,
        'database':database(),'tags':TAGS,'backup_directory':str(SAVE),'candidate_directory':str(CANDIDATE),
        'deepseek_configured':environment(objects['agent']).get('P3_ENGINE')=='deepseek' and bool(environment(objects['agent']).get('DEEPSEEK_API_KEY')),
        'protocol_before':environment(objects['backend']).get('AI_CONVERSATION_DIALOGUE_PROTOCOL'),
        'formal_runtime_switched':False}


def baseline():
    old=PAYLOAD['audit'];assert old['source_sha256']==SIG,'Local sources changed after audit'
    assert not old['unknown_runtime_changes'] and not old['unknown_workspace_changes'],'Unknown upstream edits require reconciliation'
    assert sha(CONFIG.read_bytes())==old['compose_sha256'],'Concurrent Compose change'
    assert environment_files()==old['environment_files'],'Concurrent private configuration change'
    for service in ('agent','backend'):
        assert projection(inspect(NAMES[service]))==old['containers'][service],'Concurrent runtime change'
        assert sources(service)==old['sources'][service],'Concurrent runtime source change'
    assert protected()==old['protected'],'Another protected service changed'
    assert workspace()==old['workspace'],'Concurrent workspace change'
    assert database()['schema_revision']==old['database']['schema_revision'],'Concurrent schema migration'
    for path,raw in FILES['backend'].items():
        target=safe(ROOT/'backend_adapters'/('p86-'+SIG[:12])/path)
        assert not target.exists() or target.is_file() and target.read_bytes()==raw,'Unknown adapter workspace edit'


def compose(args,config=CONFIG):
    return ['docker','compose','--project-directory',str(BASE),'--env-file',str(BASE/'.env'),
        '-p','magicvvu-starter','-f',str(config),*args]


def candidate_compose(raw):
    before=yaml.safe_load(raw);after=copy.deepcopy(before)
    after['services']['agent']['image']=TAGS['agent'];after['services']['agent']['command']=COMMAND
    after['services']['agent']['healthcheck']['test']=PROBE
    after['services']['backend']['image']=TAGS['backend']
    after['services']['backend']['environment']['AI_CONVERSATION_DIALOGUE_PROTOCOL']=PROTOCOL
    # Preserve the original YAML formatting/comments and all other fields.
    lines=raw.decode().splitlines(keepends=True);service=None;in_health=False;in_environment=False;seen=set()
    for i,line in enumerate(lines):
        found=re.match(r'^  (agent|backend|db):\s*$',line.rstrip())
        if found:service=found[1];in_health=in_environment=False;continue
        if re.match(r'^  [^\s#]',line):service=None
        if service not in ('agent','backend'):continue
        if re.match(r'^    [^\s#]',line):
            in_health=bool(re.match(r'^    healthcheck:',line));in_environment=bool(re.match(r'^    environment:',line))
        replacement=None;key=None
        if re.match(r'^    image:',line):key='image';replacement=TAGS[service]
        elif service=='agent' and re.match(r'^    command:',line):key='command';replacement=json.dumps(COMMAND)
        elif service=='agent' and in_health and re.match(r'^      test:',line):key='probe';replacement=json.dumps(PROBE)
        elif service=='backend' and in_environment and re.match(r'^      AI_CONVERSATION_DIALOGUE_PROTOCOL:',line):key='protocol';replacement=PROTOCOL
        if replacement is None:continue
        indent=len(line)-len(line.lstrip());name=line.strip().split(':',1)[0]
        j=i+1
        while j<len(lines):
            content=lines[j];width=len(content)-len(content.lstrip())
            if content.strip() and not content.lstrip().startswith('#') and (width<indent or width==indent and not content.lstrip().startswith('- ')):break
            j+=1
        assert set(yaml.safe_load(textwrap.dedent(''.join(lines[i:j]))))=={name},'Unexpected YAML field'
        lines[i]=' '*indent+name+': '+replacement+'\n'
        for n in range(i+1,j):
            if lines[n].strip() and not lines[n].lstrip().startswith('#'):lines[n]=''
        seen.add((service,key))
    assert seen=={('agent','image'),('agent','command'),('agent','probe'),('backend','image'),('backend','protocol')},'Missing Compose field'
    result=''.join(lines).encode();assert yaml.safe_load(result)==after,'Unexpected Compose changes'
    return result


def build(service):
    before=json.loads((SAVE/(service+'.before.private.json')).read_text())
    overlay={p:raw for p,raw in FILES[service].items() if PAYLOAD['audit']['sources'][service]['hashes'][p]!=HASHES[service][p]}
    destination='/app/agent/' if service=='agent' else '/app/'
    recipe='FROM '+before['Image']+'\nLABEL magicvvu.ai_adapter_release="V1-P8.6" magicvvu.p86_source_sha256="'+SIG+'"\nCOPY source/ '+destination+'\n'
    if service=='agent':
        recipe+='CMD '+json.dumps(COMMAND)+'\nHEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD ["python","-m","conversation.autonomous.health"]\n'
    else:recipe+='ENV AI_CONVERSATION_DIALOGUE_PROTOCOL='+PROTOCOL+'\n'
    archive=io.BytesIO()
    with tarfile.open(fileobj=archive,mode='w') as tar:
        for relative,content in [('Dockerfile',recipe.encode()),*[('source/'+p,raw) for p,raw in overlay.items()]]:
            info=tarfile.TarInfo(relative);info.size=len(content);info.mode=0o644;info.mtime=0;tar.addfile(info,io.BytesIO(content))
    result=subprocess.run(['docker','build','--pull=false','--network=none','-t',TAGS[service],'-'],
        input=archive.getvalue(),capture_output=True,timeout=180,env={**os.environ,'DOCKER_BUILDKIT':'0'})
    private(service+'-build.private.log',result.stdout+result.stderr)
    assert result.returncode==0,'Candidate image build failed'
    return sorted(overlay)


def isolated(service):
    if service=='agent':
        code=r'''
import datetime,json
from fastapi.testclient import TestClient
from conversation.engines import RuleEngine
from conversation.autonomous.app import create_app
from conversation.p85.app import create_app as old
from conversation.autonomous.health import check
class NoReads:
 def __getattr__(self,name):raise AssertionError('Unexpected external read')
c=TestClient(create_app(engine=RuleEngine(),reader=NoReads()))
h=c.get('/health').json();assert check(h) and h['maintenance_release']=='V1-P8.6'
api=c.get('/openapi.json').json();assert api['info']['version']=='0.8.6' and '/agent/dialogue/run' in api['paths']
assert TestClient(old(engine=RuleEngine(),reader=NoReads())).get('/health').json()['maintenance_release']=='V1-P8.5'
scope={'user_id':'33333333-3333-4333-8333-333333333333','household_id':'22222222-2222-4222-8222-222222222222'}
body={'text':'开始新任务','request_id':'p86-isolated','context':{'scope':scope,'conversation_id':'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','revision':0,'trusted_now':datetime.datetime.now(datetime.timezone.utc).isoformat()}}
assert c.post('/agent/dialogue/run',json=body).status_code==401
headers={'Authorization':'Bearer isolated-p86','X-User-Id':scope['user_id'],'X-Household-Id':scope['household_id']}
out=c.post('/agent/dialogue/run',json=body,headers=headers);assert out.status_code==200
value=out.json();assert value['model_calls']==0 and not value['inventory_writes'] and not value['shopping_writes']
print(json.dumps({'imports':True,'new_route':True,'legacy_factory':True,'internal_auth':True,'deterministic_run':True,'model_calls':0,'external_network':False}))
'''
    else:
        code=r'''
import json
from pydantic import ValidationError
from fastapi.testclient import TestClient
from app.main import app
from app.routers.draft_execution import capabilities
from app.services import autonomous,dialogue
from app.memory_schemas import Response
assert autonomous.enabled()
c=TestClient(app);assert c.get('/api/v1/health').status_code==200
assert c.get('/api/v1/agent/conversation').status_code==403
cap=capabilities(identity=None);assert cap['conversation_dialogue_protocol']=='inventory-autonomous-1' and cap['autonomous_fixed_call_limit'] is False
api=app.openapi()
assert '/api/v1/agent/conversation-turns' in api['paths'] and '/api/v1/agent/messages' in api['paths']
assert set(dialogue.PROTOCOL_KEYS)=={'p84-dialogue-1','p85-dialogue-1'}
assert autonomous.saved_state({'autonomous_v1':{'protocol_version':'inventory-autonomous-1'}})
body={'conversation_id':'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','conversation_revision':1,'request_id':'isolated','original_text':'synthetic','reply':'synthetic','kind':'explain','model_calls':4,
 'dialogue':{'protocol_version':'inventory-autonomous-1','calls':{'decision':4,'response':0,'total':4},'fallback_used':False,'stop_reason':'completed','status':'completed','tool_reads':1,'elapsed_ms':1,'ai_elapsed_ms':1}}
assert Response.model_validate(body).model_calls==4
try:Response.model_validate({**body,'dialogue':None})
except ValidationError:pass
else:raise AssertionError('Legacy call limit widened')
print(json.dumps({'imports':True,'public_auth':True,'capabilities':True,'calls_above_two':True,'legacy_limits':True,'old_routes':True,'database_connected':False,'business_writes':False}))
'''
    args=['docker','run','--rm','--pull','never','--network','none','--read-only','--cap-drop','ALL',
        '--security-opt','no-new-privileges','--tmpfs','/tmp:rw,noexec,nosuid,size=32m','--memory','384m','--pids-limit','96',
        '-e','PYTHONDONTWRITEBYTECODE=1','-e','AI_SERVICE_TOKEN=isolated-p86','-e','P3_ENGINE=rules',
        '-e','DB_PASSWORD=isolated-not-real','-e','MAGICVVU_APP_API_KEY=isolated-not-real','--entrypoint','python','-i',TAGS[service],'-B','-']
    return json.loads(run(args,code.encode(),timeout=60))


def prepare():
    baseline();assert not (SAVE/'deployed.json').exists(),'Already deployed'
    directory(SAVE,0o700)
    if not (SAVE/'compose.before.private.yaml').exists():
        private('compose.before.private.yaml',CONFIG.read_bytes())
        private('audit.private.json',PAYLOAD['audit'])
        for service in ('agent','backend'):private(service+'.before.private.json',inspect(NAMES[service]))
        for relative in FILES['agent']:
            path=safe(ROOT/relative)
            if path.is_file():private('workspace-before/'+relative,path.read_bytes())
    for service,entries in FILES.items():
        for path,raw in entries.items():
            if path.endswith('.py'):ast.parse(raw.decode('utf-8-sig'),filename=path)
            target=safe(CANDIDATE/('ai' if service=='agent' else 'backend_adapter')/path)
            directory(target.parent);atomic(target,raw)
    overlays={s:build(s) for s in FILES}
    checks={s:isolated(s) for s in FILES}
    candidate=candidate_compose(CONFIG.read_bytes());private('compose.candidate.private.yaml',candidate)
    run(compose(['config','--quiet'],SAVE/'compose.candidate.private.yaml'))
    baseline()
    result={'stage':'prepared','release':'V1-P8.6','source_sha256':SIG,'tags':TAGS,'overlay_files':overlays,
        'candidate_checks':checks,'backup_directory':str(SAVE),'formal_runtime_switched':False,'database_migrations':False}
    private('prepare.json',result);return result


def origin(service):
    obj=inspect(NAMES[service]);ip=next(iter(obj['NetworkSettings']['Networks'].values()))['IPAddress']
    return 'http://'+ip+(':8767' if service=='agent' else ':8000')


def fetch(service,path,body=None,headers=None,timeout=12):
    request=urllib.request.Request(origin(service)+path,headers=headers or {},data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=timeout) as response:return json.load(response)


def healthy():
    for _ in range(45):
        if all(inspect(NAMES[s])['State'].get('Health',{}).get('Status')=='healthy' for s in ('agent','backend')):return
        time.sleep(1)
    raise RuntimeError('New services did not become healthy')


def verify():
    old=PAYLOAD['audit'];agent,backend=inspect(NAMES['agent']),inspect(NAMES['backend'])
    assert protected()==old['protected'],'Protected services changed'
    assert environment_files()==old['environment_files'],'Private configuration changed'
    assert CONFIG.read_bytes()==(SAVE/'compose.candidate.private.yaml').read_bytes(),'Concurrent Compose edit'
    for service,obj in [('agent',agent),('backend',backend)]:
        original=json.loads((SAVE/(service+'.before.private.json')).read_text())
        rollback_image=json.loads(run(['docker','image','inspect',original['Image']]))[0]
        assert rollback_image['Id']==original['Image'],'Rollback image unavailable'
        assert obj['Config']['Image']==TAGS[service] and obj['State']['Health']['Status']=='healthy','Unexpected running image'
        before_env=environment(original);after_env=environment(obj)
        if service=='backend':before_env['AI_CONVERSATION_DIALOGUE_PROTOCOL']=PROTOCOL
        assert before_env==after_env and original['Mounts']==obj['Mounts'],'Runtime environment or mounts changed'
        for key in ('PortBindings','ReadonlyRootfs','CapDrop','SecurityOpt','RestartPolicy','Memory','NanoCpus','PidsLimit'):
            assert original['HostConfig'].get(key)==obj['HostConfig'].get(key),'Runtime policy changed'
        actual=sources(service);assert actual['hashes']==HASHES[service],'Delivered code hash mismatch'
        allowed=set(FILES[service]);before=old['sources'][service]['all_python'];after=actual['all_python']
        assert {p:h for p,h in before.items() if p not in allowed}=={p:h for p,h in after.items() if p not in allowed},'Unrelated runtime source changed'
    assert workspace()==HASHES['agent'],'AI workspace sync mismatch'
    assert all(sha(safe(ROOT/'backend_adapters'/('p86-'+SIG[:12])/p).read_bytes())==h
        for p,h in HASHES['backend'].items()),'Backend adapter workspace sync mismatch'
    health=fetch('agent','/health');assert health['maintenance_release']=='V1-P8.6' and health['engine']=='deepseek'
    assert health['conversation_dialogue_protocol']==PROTOCOL and health['dialogue_max_model_calls'] is None
    assert not health['inventory_writes'] and not health['shopping_writes']
    assert fetch('backend','/api/v1/health')['status']=='ok' and fetch('backend','/api/v1/ready')['status']=='ready'
    code="import json;from app.routers.draft_execution import capabilities;print(json.dumps(capabilities(identity=None)))"
    cap=json.loads(run(['docker','exec',NAMES['backend'],'python','-B','-c',code]))
    assert cap['conversation_dialogue_protocol']==PROTOCOL and cap['autonomous_fixed_call_limit'] is False
    assert database()['schema_revision']==old['database']['schema_revision'],'Database schema changed'
    api=fetch('agent','/openapi.json');assert api['info']['version']=='0.8.6' and '/agent/dialogue/run' in api['paths']
    return {'stage':'verified','release':'V1-P8.6','source_sha256':SIG,'tags':TAGS,
        'containers':{s:projection(inspect(n)) for s,n in NAMES.items()},'agent_health':health,'backend_capabilities':cap,
        'source_files_verified':{s:len(v) for s,v in FILES.items()},'database_schema':old['database']['schema_revision'],
        'database_container_unchanged':True,'other_runtime_sources_preserved':True,'private_configuration_unchanged':True,
        'rollback_images_available':True,
        'database_migrations_executed':False,'business_writes_performed':False,'app_joint_acceptance':False,
        'backup_directory':str(SAVE)}


def restore():
    candidate=(SAVE/'compose.candidate.private.yaml').read_bytes()
    assert CONFIG.read_bytes() in (candidate,(SAVE/'compose.before.private.yaml').read_bytes()),'Concurrent Compose edit; refusing overwrite'
    original=(SAVE/'compose.before.private.yaml').read_bytes()
    # A late rollback must still deserialize autonomous records accepted since
    # the switch. Keep the backwards-compatible adapter, turn new runs off.
    new_turns=int(sql("SELECT count(*) FROM ai_conversation_turns WHERE binding_json::jsonb ? 'autonomous_v1';"))
    if new_turns:
        expected=yaml.safe_load(original);expected['services']['backend']['image']=TAGS['backend']
        lines=original.decode().splitlines(keepends=True);inside=False;replaced=False
        for i,line in enumerate(lines):
            if re.match(r'^  backend:\s*$',line.rstrip()):inside=True;continue
            if re.match(r'^  [^\s#]',line):inside=False
            if inside and re.match(r'^    image:',line):lines[i]='    image: '+TAGS['backend']+'\n';replaced=True
        assert replaced and yaml.safe_load(''.join(lines))==expected,'Unsafe compatibility rollback'
        original=''.join(lines).encode()
    atomic(CONFIG,original)
    run(compose(['up','-d','--no-deps','--no-build','--pull','never','agent','backend']),timeout=120);healthy()
    for path in FILES['agent']:
        current=safe(ROOT/path);backup=SAVE/'workspace-before'/path
        if current.is_file() and sha(current.read_bytes())==HASHES['agent'][path]:
            if backup.is_file():atomic(current,backup.read_bytes())
            elif PAYLOAD['audit']['workspace'][path] is None:current.unlink()
    result={'stage':'rolled_back','source_sha256':SIG,'database_restored':False,'database_migrations_executed':False,
        'backwards_compatible_adapter_retained':bool(new_turns)}
    private('rollback.json',result);return result


def switch():
    baseline();assert (SAVE/'prepare.json').exists() and not (SAVE/'deployed.json').exists(),'Candidate not prepared or already deployed'
    assert not any(database()['active_leases'].values()),'Active AI leases; wait before switching'
    candidate=(SAVE/'compose.candidate.private.yaml').read_bytes();changed=False;stopped=False
    try:
        # Block new messages while checking final leases and switching the pair.
        run(compose(['stop','--timeout','80','backend']),timeout=100);stopped=True
        assert not any(database()['active_leases'].values()),'An in-flight AI turn has not drained'
        assert sha(CONFIG.read_bytes())==PAYLOAD['audit']['compose_sha256'],'Concurrent Compose edit'
        dump=safe(SAVE/'database-before.private.dump')
        command='exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc'
        with dump.open('wb') as stream:
            os.chmod(dump,0o600)
            result=subprocess.run(['docker','exec',NAMES['db'],'sh','-c',command],stdout=stream,stderr=subprocess.PIPE,timeout=120)
        assert result.returncode==0,'Private database backup failed'
        for path,raw in FILES['agent'].items():
            target=safe(ROOT/path);directory(target.parent);atomic(target,raw)
        for path,raw in FILES['backend'].items():
            target=safe(ROOT/'backend_adapters'/('p86-'+SIG[:12])/path);directory(target.parent);atomic(target,raw)
        atomic(CONFIG,candidate);changed=True
        run(compose(['up','-d','--no-deps','--no-build','--pull','never','agent','backend']),timeout=120)
        healthy();value=verify()
        value.update(stage='deployed',synced_ai_files=len(FILES['agent']),synced_backend_adapter_files=len(FILES['backend']),
            private_database_backup=True,compose_changes=['agent.image','agent.command','agent.healthcheck.test','backend.image','backend.environment.AI_CONVERSATION_DIALOGUE_PROTOCOL'])
        private('deployed.json',value);return value
    except Exception:
        if changed:restore()
        elif stopped:run(compose(['start','backend']),timeout=100)
        raise


def model_check():
    import datetime
    env=environment(inspect(NAMES['agent']))
    scope={'user_id':'33333333-3333-4333-8333-333333333333','household_id':'22222222-2222-4222-8222-222222222222'}
    headers={'Authorization':'Bearer '+env['AI_SERVICE_TOKEN'],'Content-Type':'application/json',
        'X-User-Id':scope['user_id'],'X-Household-Id':scope['household_id']}
    ctx={'scope':scope,'conversation_id':'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','revision':0,
        'trusted_now':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    value=fetch('agent','/agent/dialogue/run',{'text':'你好，我想聊聊整理房间的心情，先不查物品、不登记操作。',
        'request_id':'p86-release-synthetic-'+str(time.time_ns()),'context':ctx,'remaining_seconds':25},headers,timeout=30)
    assert value['protocol_version']==PROTOCOL and value['status']=='completed','Real model greeting did not complete'
    assert value['model_calls']>=1 and value['tool_reads']==0 and not value['inventory_writes'] and not value['shopping_writes']
    deterministic=fetch('agent','/agent/dialogue/run',{'text':'开始新任务','request_id':'p86-release-zero-'+str(time.time_ns()),'context':ctx},headers)
    assert deterministic['model_calls']==0 and deterministic['tool_reads']==0
    return {'stage':'model_checked','source_sha256':SIG,'real_deepseek':True,'model_calls':value['model_calls'],
        'stop_reason':value['stop_reason'],'elapsed_ms':value['elapsed_ms'],'deterministic_calls':0,
        'inventory_reads':0,'business_writes':False,'production_account_created':False,'app_joint_acceptance':False}


def capture():
    result=verify()
    code='import json;from app.main import app;print(json.dumps(app.openapi()))'
    result.update(stage='captured',apis={'ai':fetch('agent','/openapi.json'),
        'backend':json.loads(run(['docker','exec',NAMES['backend'],'python','-B','-c',code]))})
    return result


def network_check():
    # Exercise the actual backend service credentials without creating a user,
    # conversation row, inventory record or confirmation in production.
    code=r'''
import asyncio,datetime,json
from uuid import UUID
from types import SimpleNamespace
from app.services.autonomous import call,Result
user='33333333-3333-4333-8333-333333333333';home='22222222-2222-4222-8222-222222222222'
identity=SimpleNamespace(user=SimpleNamespace(id=UUID(user)))
body={'text':'开始新任务','request_id':'p86-backend-link-check','context':{
 'scope':{'user_id':user,'household_id':home},'conversation_id':'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
 'revision':0,'trusted_now':datetime.datetime.now(datetime.timezone.utc).isoformat()}}
async def check():
 result=Result.model_validate(await call(identity,UUID(home),'/agent/dialogue/run',body,8))
 assert result.model_calls==0 and result.tool_reads==0 and not result.inventory_writes and not result.shopping_writes
 legacy=await call(identity,UUID(home),'/agent/dialogue/p85/understand',body,8)
 assert legacy['understanding_calls']==0
 print(json.dumps({'backend_to_ai_authenticated':True,'autonomous_calls':0,'legacy_p85_calls':0,
  'database_rows_created':False,'inventory_reads':0,'business_writes':False}))
asyncio.run(check())
'''
    link=json.loads(run(['docker','exec','-i',NAMES['backend'],'python','-B','-'],code.encode(),timeout=25))
    from urllib.error import HTTPError
    public='https://8.134.172.165:8000'
    key=environment(inspect(NAMES['backend']))['MAGICVVU_APP_API_KEY']
    import ssl
    # Match the existing Android Debug trust anchor; never disable certificate
    # or hostname verification and never change the production TLS files.
    tls=ssl.create_default_context(cadata=PAYLOAD['public_ca'])
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=tls))
    def status(path,with_key):
        request=urllib.request.Request(public+path,headers={'X-MagicVVu-App-Key':key} if with_key else {})
        try:
            with opener.open(request,timeout=10) as response:return response.status
        except HTTPError as error:return error.code
    probes={'health_with_app_key':status('/api/v1/health',True),
        'without_app_key':status('/api/v1/agent/execution-capabilities',False),
        'without_bearer':status('/api/v1/agent/execution-capabilities',True)}
    assert probes=={'health_with_app_key':200,'without_app_key':403,'without_bearer':401},'Public TLS/auth probe failed'
    return {'stage':'network_checked','release':'V1-P8.6','source_sha256':SIG,'public_origin':public,
        'tls_certificate_verified':True,'tls_trust_source':'existing Android Debug bundled CA',
        'public_ca_sha256':sha(PAYLOAD['public_ca'].encode()),'system_ca_trust_verified':False,
        'tls_configuration_changed':False,'http_probes':probes,'service_link':link,'app_joint_acceptance':False}


try:
    result={'audit':audit,'prepare':prepare,'switch':switch,'verify':verify,'model-check':model_check,
        'network-check':network_check,'capture':capture,'rollback':restore}[STAGE]()
    print(json.dumps(result,ensure_ascii=False))
except Exception as error:
    if SAVE.exists():
        import traceback
        private('exception.private.log',traceback.format_exc().encode())
    print(json.dumps({'stage':STAGE,'error_type':type(error).__name__,'reason':str(error) if isinstance(error,(AssertionError,RuntimeError)) else 'Details retained privately','formal_success':False}))
    raise SystemExit(1)
