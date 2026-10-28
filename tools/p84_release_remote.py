"""Server-only P8.4 overlay release. Private state stays under the AI workspace.

Executed with PAYLOAD and STAGE supplied by p84_release.py. No migrations,
inventory writes, volume operations, backend tree checkout or Git operations.
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
import time
import urllib.request
import urllib.error
import yaml

ROOT=Path('/home/magicvvu_ai/workspace/agent')
BASE=Path('/srv/magicvvu/magicvvu-starter/deploy')
CONFIG=BASE/'compose.yaml'
SERVICES={'agent':('magicvvu-starter-agent-1','/app/agent'),'backend':('magicvvu-starter-backend-1','/app')}
FILES={s:{p:base64.b64decode(v) for p,v in rows.items()} for s,rows in PAYLOAD['sources'].items()}
sha=lambda b:hashlib.sha256(b).hexdigest()
SIGNATURE=sha(json.dumps({s:{p:sha(b) for p,b in rows.items()} for s,rows in FILES.items()},sort_keys=True).encode())
ATTEMPT=PAYLOAD.get('attempt','r1')
SAVE=ROOT/'.releases'/('p84-20261027-'+SIGNATURE[:12]+'-'+ATTEMPT)
TAGS={s:'magicvvu/'+s+':p84-'+SIGNATURE[:12] for s in SERVICES}
FLAG='AI_CONVERSATION_DIALOGUE_PROTOCOL'


def safe(path):
    assert not ROOT.is_symlink() and path.resolve().is_relative_to(ROOT)
    assert not path.is_symlink()
    assert all(not p.is_symlink() for p in path.parents if p.is_relative_to(ROOT))
    return path


def directory(path,mode=0o755):
    safe(path)
    missing=[];part=path
    while not part.exists():missing.append(part);part=part.parent
    for part in reversed(missing):
        part.mkdir(mode=mode);os.chown(part,ROOT.stat().st_uid,ROOT.stat().st_gid)


def private(name,value):
    path=safe(SAVE/name);directory(path.parent,0o700)
    path.write_bytes(value if isinstance(value,bytes) else json.dumps(value,indent=2).encode()+b'\n')
    path.chmod(0o600)


def run(args,data=None,timeout=45):
    result=subprocess.run(args,input=data,capture_output=True,timeout=timeout)
    if result.returncode:
        if SAVE.exists():private('last-error.private.log',result.stdout+result.stderr)
        raise RuntimeError('Command failed: '+args[0]+'; private server diagnostic retained')
    return result.stdout


def inspect(name):return json.loads(run(['docker','inspect',name]))[0]


def project(item):
    return {'id':item['Id'],'image_id':item['Image'],'image':item['Config']['Image'],
        'started_at':item['State']['StartedAt'],'health':item['State'].get('Health',{}).get('Status'),
        'config_sha256':sha(json.dumps({k:item[k] for k in ['Config','HostConfig','Mounts']},sort_keys=True).encode())}


def identity(item):
    value={k:item['Config'].get(k) for k in ['Cmd','Entrypoint','WorkingDir','User','Healthcheck']}
    value.update(environment=dict(v.split('=',1) for v in item['Config']['Env']),
        mounts=sorted(item['Mounts'],key=lambda m:m['Destination']),networks=sorted(item['NetworkSettings']['Networks']),
        host={k:item['HostConfig'].get(k) for k in ['PortBindings','NetworkMode','ReadonlyRootfs','CapAdd','CapDrop',
            'SecurityOpt','Tmpfs','Memory','NanoCpus','RestartPolicy','PidsLimit','Dns','DnsSearch','DnsOptions']})
    for key in ['Dns','DnsSearch','DnsOptions']:value['host'][key]=value['host'][key] or []
    return value


def protected():
    ours={v[0] for v in SERVICES.values()}
    names=run(['docker','ps','--format','{{.Names}}']).decode().splitlines()
    return {n:project(inspect(n)) for n in names if n not in ours}


def source(name,root,paths,mounts=()):
    script='''import base64,hashlib,json,pathlib
r=pathlib.Path(ROOT);excluded=[pathlib.Path(p) for p in MOUNTS]
files={p:base64.b64encode((r/p).read_bytes()).decode() if (r/p).is_file() else None for p in PATHS}
code={}
for p in r.rglob('*.py'):
 if '.cache' in p.relative_to(r).parts or any(p==x or x in p.parents for x in excluded):continue
 code[p.relative_to(r).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
print(json.dumps({'files':files,'code':code}))
'''
    prelude='ROOT='+repr(root)+'\nPATHS='+repr(list(paths))+'\nMOUNTS='+repr(list(mounts))+'\n'
    return json.loads(run(['docker','exec',name,'python','-B','-c',prelude+script]))


def schema_revision():
    code="from app.database import engine\nfrom sqlalchemy import text\nimport json\nwith engine.connect() as c:\n c.execute(text('SET TRANSACTION READ ONLY'))\n print(json.dumps(c.execute(text('SELECT version_num FROM alembic_version')).scalars().all()))"
    return json.loads(run(['docker','exec',SERVICES['backend'][0],'python','-B','-c',code]))


def audit():
    values={}
    for service,(name,root) in SERVICES.items():
        obj=inspect(name)
        values[service]={'identity':project(obj),**source(name,root,FILES[service],(m['Destination'] for m in obj['Mounts']))}
    return {'compose_sha256':sha(CONFIG.read_bytes()),'services':values,'protected':protected(),
        'schema_revision':schema_revision(),'workspace_files':{p:sha(safe(ROOT/p).read_bytes()) if (ROOT/p).is_file() else None for p in FILES['agent']}}


def baseline():
    old=PAYLOAD['audit']
    assert sha(CONFIG.read_bytes())==old['compose_sha256'],'Concurrent Compose edit'
    assert protected()==old['protected'],'Protected services changed'
    assert schema_revision()==old['schema_revision'],'Schema revision changed'
    for service,(name,root) in SERVICES.items():
        obj=inspect(name)
        assert project(obj)==old['services'][service]['identity'],'Concurrent runtime change: '+service
        assert source(name,root,FILES[service],(m['Destination'] for m in obj['Mounts']))=={
            k:old['services'][service][k] for k in ['files','code']},'Concurrent code change'
    for path,digest in old['workspace_files'].items():
        assert (sha(safe(ROOT/path).read_bytes()) if (ROOT/path).is_file() else None)==digest,'Concurrent AI workspace edit'


def atomic(path,content):
    safe(path) if path.is_relative_to(ROOT) else None
    stat=path.stat() if path.exists() else None
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as stream:
        stream.write(content);stream.flush();os.fsync(stream.fileno());temp=Path(stream.name)
    temp.chmod(stat.st_mode&0o777 if stat else 0o644)
    os.chown(temp,stat.st_uid if stat else ROOT.stat().st_uid,stat.st_gid if stat else ROOT.stat().st_gid)
    temp.replace(path)


def compose(args,config=CONFIG):
    return ['docker','compose','--project-directory',str(BASE),'--env-file',str(BASE/'.env'),'-p','magicvvu-starter','-f',str(config),*args]


def images(raw,tags):
    expected=copy.deepcopy(yaml.safe_load(raw));lines=raw.decode().splitlines(keepends=True)
    for service,tag in tags.items():
        expected['services'][service]['image']=tag;inside=False;found=False
        for index,line in enumerate(lines):
            if re.match(r'^  '+re.escape(service)+r':\s*$',line.rstrip()):inside=True;continue
            if inside and re.match(r'^  [^ ]',line):inside=False
            if inside and re.match(r'^    image:',line):
                comment=' #'+line.rstrip('\r\n').split(' #',1)[1] if ' #' in line else ''
                lines[index]='    image: '+tag+comment+('\r\n' if line.endswith('\r\n') else '\n');found=True;break
        assert found,'Missing service image line'
    result=''.join(lines).encode();assert yaml.safe_load(result)==expected
    return result


def smoke(service,tag):
    args=['docker','run','--rm','--pull','never','--network','none','--read-only','--cap-drop','ALL',
        '--security-opt','no-new-privileges','--tmpfs','/tmp:rw,noexec,nosuid,size=32m','--memory','320m','--pids-limit','96',
        '-e','PYTHONDONTWRITEBYTECODE=1','-e','P3_ENGINE=rules','-e','AI_SERVICE_TOKEN=source-check-synthetic-token']
    if service=='backend':args+=['-e','DB_PASSWORD=synthetic-isolated-candidate-only',
        '-e','MAGICVVU_OPEN_EXECUTION=true','-e','MAGICVVU_DISCARD_EXECUTION=true']
    return json.loads(run([*args,'--entrypoint','python','-i',tag,'-B','-'],PAYLOAD['smoke_'+service].encode(),timeout=50))


def prepare():
    baseline();assert not SAVE.exists(),'Release directory already exists'
    directory(SAVE,0o700);SAVE.chmod(0o700)
    originals={s:inspect(v[0]) for s,v in SERVICES.items()}
    private('containers.before.private.json',originals)
    private('compose.before.private.yaml',CONFIG.read_bytes())
    private('audit.private.json',PAYLOAD['audit'])
    settings={str(p):sha(p.read_bytes()) for p in [BASE/'.env',ROOT/'.env.runtime'] if p.is_file()}
    private('configuration-digests.private.json',settings)
    checks={};candidates={}
    for service,rows in FILES.items():
        target=safe(ROOT/('candidates' if service=='agent' else 'backend_patches')/('p84-'+SIGNATURE[:12]+'-'+ATTEMPT))
        assert not target.exists(),'Candidate directory already exists'
        directory(target)
        for rel,raw in rows.items():
            if rel.endswith('.py'):ast.parse(raw.decode('utf-8-sig'),filename=rel)
            path=safe(target/rel);directory(path.parent);atomic(path,raw)
        candidates[service]=str(target)
        recipe='FROM '+originals[service]['Image']+'\nLABEL magicvvu.ai_adapter_release="V1-P8.4" magicvvu.p84_source_sha256="'+SIGNATURE+'"\n'
        if service=='backend':recipe+='ENV '+FLAG+'=p84-dialogue-1\n'
        recipe+='COPY source/ '+SERVICES[service][1]+'/\n'
        archive=io.BytesIO()
        with tarfile.open(fileobj=archive,mode='w') as tar:
            for rel,raw in [('Dockerfile',recipe.encode()),*[('source/'+p,b) for p,b in rows.items()]]:
                info=tarfile.TarInfo(rel);info.size=len(raw);info.mode=0o644;info.mtime=0
                tar.addfile(info,io.BytesIO(raw))
        result=subprocess.run(['docker','build','--pull=false','--network=none','-t',TAGS[service],'-'],input=archive.getvalue(),
            capture_output=True,timeout=180,env={**os.environ,'DOCKER_BUILDKIT':'0'})
        private(service+'-build.private.log',result.stdout+result.stderr)
        assert result.returncode==0,'Candidate build failed: '+service
        checks[service]=smoke(service,TAGS[service])
    baseline()
    value={'stage':'prepared','maintenance_release':'V1-P8.4','source_sha256':SIGNATURE,'tags':TAGS,'backup_directory':str(SAVE),
        'candidate_paths':candidates,'candidate_checks':checks,'overlay_files':{s:{p:sha(b) for p,b in rows.items()} for s,rows in FILES.items()},
        'database_migrations_executed':False,'formal_runtime_switched':False,'backend_base_preserved':'V1-P9'}
    private('prepare.json',value);return value


def wait_healthy(name):
    for _ in range(50):
        obj=inspect(name)
        if obj['State'].get('Health',{}).get('Status')=='healthy':return obj
        if obj['State']['Status'] in {'exited','dead'}:raise RuntimeError('Service exited: '+name)
        time.sleep(2)
    raise RuntimeError('Health deadline exceeded: '+name)


def deployed():
    before=json.loads((SAVE/'containers.before.private.json').read_text());values={}
    assert protected()==PAYLOAD['audit']['protected'],'Protected services changed'
    for service,(name,root) in SERVICES.items():
        obj=inspect(name);assert obj['Config']['Image']==TAGS[service]
        expected=identity(before[service])
        if service=='backend':expected['environment'][FLAG]='p84-dialogue-1'
        assert identity(obj)==expected,'Unrelated runtime settings changed: '+service
        actual=source(name,root,FILES[service],(m['Destination'] for m in obj['Mounts']))
        assert actual['files']=={p:base64.b64encode(b).decode() for p,b in FILES[service].items()}
        assert actual['code']=={**PAYLOAD['audit']['services'][service]['code'],**{p:sha(b) for p,b in FILES[service].items() if p.endswith('.py')}},'Unrelated source changed'
        assert obj['State'].get('Health',{}).get('Status')=='healthy'
        values[service]=project(obj)
    for path,digest in json.loads((SAVE/'configuration-digests.private.json').read_text()).items():assert sha(Path(path).read_bytes())==digest
    assert schema_revision()==PAYLOAD['audit']['schema_revision']
    return values


def fetch(url,headers=None,body=None):
    req=urllib.request.Request(url,headers=headers or {},data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=22) as response:return json.load(response)


def verify():
    services=deployed()
    backend=fetch('http://127.0.0.1:8001/api/v1/health')
    assert backend['maintenance_release']=='V1-P9'
    agent=inspect(SERVICES['agent'][0]);ip=next(iter(agent['NetworkSettings']['Networks'].values()))['IPAddress']
    origin='http://'+ip+':8767'
    health=fetch(origin+'/health')
    assert health['maintenance_release']=='V1-P8.4' and health['engine']=='deepseek'
    assert health['conversation_dialogue_protocol']=='p84-dialogue-1' and not health['inventory_writes'] and not health['shopping_writes']
    api=fetch(origin+'/openapi.json');assert all('/agent/dialogue/'+s in api['paths'] for s in ['understand','resolve','respond'])
    code="import json\nfrom app.routers.draft_execution import capabilities\nfrom app.main import app\nprint(json.dumps({'capabilities':capabilities(None),'paths':sorted(app.openapi()['paths'])}))"
    contract=json.loads(run(['docker','exec',SERVICES['backend'][0],'python','-B','-c',code]))
    caps=contract['capabilities'];assert caps['maintenance_release']=='V1-P9' and caps['conversation_dialogue_protocol']=='p84-dialogue-1'
    assert caps['automatic_planning_commit'] is False
    home='22222222-2222-4222-8222-222222222222'
    for route in ['/api/v1/agent/conversation?household_id='+home,'/api/v1/agent/execution-capabilities']:
        try:fetch('http://127.0.0.1:8001'+route)
        except urllib.error.HTTPError as error:assert error.code==401
        else:raise AssertionError('Unauthenticated route accepted')
    checks={s:smoke(s,TAGS[s]) for s in SERVICES}
    return {'stage':'verified','maintenance_release':'V1-P8.4','services':services,'agent_health':health,'backend_health':backend,
        'capabilities':caps,'candidate_checks':checks,'readiness':fetch('http://127.0.0.1:8001/api/v1/ready'),
        'database_revision':schema_revision(),'database_migrations_executed':False,'business_writes_performed':False,
        'unrelated_code_preserved':True,'configuration_preserved_except_dialogue_flag':True,'protected_services_unchanged':True,
        'android_joint_acceptance':False,'backup_directory':str(SAVE)}


def switch():
    assert (SAVE/'prepare.json').exists() and not (SAVE/'deployed.json').exists()
    baseline()
    code="""import json
from app.database import engine
from sqlalchemy import text
with engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'))
 print(json.dumps({'tasks':c.execute(text("SELECT count(*) FROM ai_tasks WHERE status='processing' AND lease_until>CURRENT_TIMESTAMP")).scalar(),
  'conversation_leases':c.execute(text('SELECT count(*) FROM ai_conversation_bindings WHERE processing_nonce IS NOT NULL AND lease_until>CURRENT_TIMESTAMP')).scalar()}))
"""
    inflight=json.loads(run(['docker','exec',SERVICES['backend'][0],'python','-B','-c',code]))
    assert not any(inflight.values()),'In-flight tasks must finish first'
    raw=CONFIG.read_bytes();candidate=images(raw,TAGS)
    private('compose.candidate.private.yaml',candidate)
    run(compose(['config','--quiet'],SAVE/'compose.candidate.private.yaml'))
    before=json.loads((SAVE/'containers.before.private.json').read_text())
    changed=False
    try:
        baseline()
        for rel,content in FILES['agent'].items():
            path=safe(ROOT/rel)
            if sha(path.read_bytes())!=sha(content):
                private('workspace-before/'+rel,path.read_bytes());atomic(path,content)
        atomic(CONFIG,candidate);changed=True
        # New AI keeps old endpoints, so replace it before enabling the backend protocol.
        for service in ['agent','backend']:
            run(compose(['up','-d','--no-deps','--no-build','--pull','never',service]),timeout=120)
            wait_healthy(SERVICES[service][0])
        value=verify();value.update(stage='deployed',tags=TAGS,inflight_before_switch=inflight,
            compose_changes=['services.agent.image','services.backend.image'],source_sha256=SIGNATURE)
        private('deployed.json',value);return value
    except Exception:
        if changed:
            current=CONFIG.read_bytes();parsed=yaml.safe_load(current)
            assert all(parsed['services'][s]['image']==TAGS[s] for s in SERVICES),'Concurrent deployment; manual reconciliation required'
            rollback=images(current,{s:before[s]['Config']['Image'] for s in SERVICES})
            atomic(CONFIG,rollback)
            for service in ['backend','agent']:
                run(compose(['up','-d','--no-deps','--no-build','--pull','never',service]),timeout=120)
                wait_healthy(SERVICES[service][0])
        private('rolled-back.json',{'rolled_back':True,'database_restored':False,'budget_restored':False})
        raise


if STAGE=='audit':result=audit()
elif STAGE=='prepare':result=prepare()
elif STAGE=='switch':result=switch()
elif STAGE=='verify':result=verify();private('verified.json',result)
else:raise RuntimeError('Invalid release stage')
print(json.dumps(result))
