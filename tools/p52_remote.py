"""Bounded nonproduction P5.2 jobs; private configuration stays in memory."""
import hashlib, importlib.util, json, os, subprocess, sys, time
from pathlib import Path

ROOT=Path('/home/admin/magicvvu-p7-p52-final-20261018')
PROJECT='magicvvu-p7-execution-20261017'
BACKEND=PROJECT+'-backend-1'; NET=PROJECT+'_test_net'
SOURCE=ROOT/'source'; RESULT=ROOT/'evidence'
RESULT.mkdir(parents=True,exist_ok=True)
action=sys.argv[1]
def run(args, **kw):
    return subprocess.run(args,capture_output=True,**kw)
def dock(*args, **kw): return run(['docker',*args],**kw)
def config(name):
    # Deliberately never serialize this projection to output or disk.
    p=dock('inspect','--format','{{json .Config.Env}}',name)
    assert p.returncode==0
    return dict(x.split('=',1) for x in json.loads(p.stdout))
def gate(min_available=300):
    mem=dict((x.split(':')[0],int(x.split()[1])*1024) for x in Path('/proc/meminfo').read_text().splitlines())
    assert mem['MemAvailable'] >= min_available*1024**2, 'Insufficient host memory budget'
    for name in ('magicvvu-starter-backend-1','magicvvu-starter-agent-1','magicvvu-starter-db-1',BACKEND,PROJECT+'-agent-1',PROJECT+'-db-1'):
        p=dock('inspect','--format','{{.State.Health.Status}} {{.State.Running}}',name)
        assert p.stdout.decode().strip()=='healthy true', 'Service health gate failed'
    p=dock('ps','--format','{{.Names}}')
    assert not any('p52-validation' in n for n in p.stdout.decode().splitlines()),'Validation already running'
    return mem['MemAvailable']
c=config(BACKEND)
assert c['DB_NAME']=='magicvvu_p7_execution_test' and c['DB_HOST']=='db' and c['ISOLATED_APP_TEST']=='yes'
env=dict(os.environ,**c)
envargs=sum((['-e',k] for k in c),[])
identity=(ROOT/'snapshot-id.txt').read_text().strip()
tag='p52-'+identity[:12]
backend_image='magicvvu/backend:'+tag
agent_image='magicvvu/agent:'+tag
def helper(code, name='helper'):
    gate()
    p=dock('run','--name','magicvvu-p52-validation-'+name,'--rm','-i','--memory','160m','--memory-swap','192m','--cpus','0.5','--network',NET,'--read-only','--tmpfs','/tmp:rw,nosuid,size=32m',*envargs,backend_image,'python','-',input=code,env=env)
    assert p.returncode==0, 'Bounded helper failed: '+p.stderr.decode(errors='replace')[:500]
    return p.stdout
if action=='build':
    available=gate()
    files=[]
    for component,base,directories,image in [
      ('backend','magicvvu/backend:p7-rc-04f930a',['app','alembic'],backend_image),
      ('agent','magicvvu/agent:p7-rc-04f930a-r2',['conversation','v1','p0','p1','p2','p3','interaction'],agent_image)]:
        context=SOURCE/('backend/server' if component=='backend' else 'agent')
        dockerfile=ROOT/('Dockerfile.'+component)
        dockerfile.write_text('FROM '+base+'\nLABEL org.magicvvu.candidate="'+identity+'"\n'+''.join('COPY '+d+'/ '+('/app/' if component=='backend' else '/app/agent/')+d+'/\n' for d in directories))
        p=dock('build','--network','none','-f',str(dockerfile),'-t',image,str(context))
        (RESULT/(component+'-build.log')).write_bytes(p.stdout+p.stderr)
        assert p.returncode==0,'COPY-only candidate build failed'
        info=dock('image','inspect','--format','{"id":{{json .Id}},"digests":{{json .RepoDigests}},"labels":{{json .Config.Labels}}}',image)
        files.append({'image':image,**json.loads(info.stdout)})
    (RESULT/'images.json').write_text(json.dumps(files,indent=2));print(json.dumps(files))
elif action=='postgres':
    available=gate(); start=time.time()
    # Only the new P5.2 output directory; runtime/source mounts stay read-only.
    os.chown(RESULT,10001,10001)
    validation_name='magicvvu-p52-validation-postgres-'+str(int(start))
    env.update(DRAFT_EXECUTION_PG_TEST='yes',PYTHONPATH='/repo/backend/server:/repo:/repo/agent',PYTHONDONTWRITEBYTECODE='1')
    cmd=['run','--name',validation_name,'--memory','192m','--memory-swap','256m','--cpus','0.5','--network',NET,'--read-only','--tmpfs','/tmp:rw,nosuid,size=64m','--mount','type=bind,src='+str(SOURCE)+',dst=/repo,readonly','--mount','type=bind,src='+str(RESULT)+',dst=/evidence','-w','/repo/backend/server',*envargs,'-e','DRAFT_EXECUTION_PG_TEST','-e','PYTHONPATH','-e','PYTHONDONTWRITEBYTECODE','magicvvu/backend:p7-rc-tests-04f930a','python','-m','pytest','tests/test_v09_execution.py','-q','-p','no:cacheprovider','--junitxml=/evidence/postgres.xml']
    p=dock(*cmd,env=env)
    (RESULT/'postgres.log').write_bytes(p.stdout+p.stderr)
    state=dock('inspect','--format','{"status":{{json .State.Status}},"oom":{{json .State.OOMKilled}},"exit":{{json .State.ExitCode}},"memory":{{json .HostConfig.Memory}}}',validation_name)
    value={'exit':p.returncode,'elapsed_s':time.time()-start,'available_before':available,'container':json.loads(state.stdout)}
    (RESULT/'postgres-status.json').write_text(json.dumps(value,indent=2));print(json.dumps(value))
elif action=='deploy':
    gate()
    spec=importlib.util.spec_from_file_location('operator_p52','/home/admin/'+PROJECT+'/operator.py')
    op=importlib.util.module_from_spec(spec);spec.loader.exec_module(op)
    override=ROOT/'candidate.override.json'
    override.write_text(json.dumps({'services':{'backend':{'image':backend_image,'mem_limit':'320m','memswap_limit':'512m'},'agent':{'image':agent_image}}}))
    p=run(['docker','compose','-p',PROJECT,'-f','/home/admin/'+PROJECT+'/compose.json','-f',str(override),'up','-d','--no-deps','--no-build','backend','agent'],env=op.environment())
    (RESULT/'isolated-switch.log').write_bytes(p.stdout+p.stderr)
    assert p.returncode==0,'Isolated switch failed'
    print(json.dumps({'exit':p.returncode,'backend':backend_image,'agent':agent_image}))
elif action=='seed':
    print(helper((SOURCE/'frontend/tools/seed_phase5.py').read_bytes(),'seed').decode())
elif action=='code':
    print(helper(sys.stdin.buffer.read(),'database').decode())
else: raise SystemExit('Unknown action')
