"""Run with sudo on the server. Secrets and dumps stay in a mode-0700 release directory.

Explicit phases: inspect, build, rehearse, deploy, verify. No volume deletion,
firewall changes, AI image changes or automatic-planning enablement.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import time
import yaml

ROOT = Path('/srv/magicvvu/releases/backend-p9-20261026')
CONFIG = Path('/srv/magicvvu/magicvvu-starter/deploy/compose.yaml')
BACKEND, AGENT, DB = ['magicvvu-starter-'+s+'-1' for s in ('backend','agent','db')]
IMAGE = 'magicvvu/backend:p9-20261026'
RESTORE = 'magicvvu-p9-20261026-restore'
NETWORK = 'magicvvu-p9-20261026-rehearsal'


def run(args, *, data=None, timeout=120, check=True):
    p = subprocess.run(args, input=data, capture_output=True, timeout=timeout)
    if p.returncode and check:
        (ROOT/'last-command-error.log').write_bytes(p.stderr)
        raise RuntimeError('Command failed: '+args[0]+'; protected log saved')
    return p


def docker_json(*args):
    return json.loads(run(['docker',*args]).stdout)


def containers():
    return {c['Name'].lstrip('/'):c for c in docker_json('inspect',BACKEND,AGENT,DB)}


def environment(container):
    return dict(s.split('=',1) for s in container['Config']['Env'])


def save(name, value):
    (ROOT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2))


def db_python(source, *, image=None, isolated=False):
    if image:
        args = ['docker','run','--rm','-i','--network',NETWORK if isolated else state()['db_network'],
                '--env-file',str(ROOT/('restore-backend.env' if isolated else 'backend.env')),
                '--entrypoint','python',image,'-']
    else:
        args = ['docker','exec','-i',BACKEND,'python','-']
    return json.loads(run(args,data=source.encode()).stdout)


def state():
    return json.loads((ROOT/'private-state.json').read_text())


SNAPSHOT = r'''
import hashlib,json
from sqlalchemy import text
from app.database import engine
with engine.connect() as db:
 db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
 names=list(db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")).scalars())
 out={}
 for name in names:
  q='"'+name.replace('"','""')+'"'
  rows=list(db.execute(text('SELECT row_to_json(t)::text FROM '+q+' t')).scalars())
  out[name]={'count':len(rows),'sha256':hashlib.sha256(('\n'.join(sorted(rows))).encode()).hexdigest()}
 print(json.dumps(out,sort_keys=True))
'''

LEGACY_SNAPSHOT = r'''
import json,hashlib
from sqlalchemy import inspect,text
from app.database import engine
with engine.connect() as db:
 db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
 out={}
 for name in inspect(db).get_table_names():
  if name in {'products','product_batches','mutation_receipts','alembic_version'}:continue
  cols=[c['name'] for c in inspect(db).get_columns(name) if not(name=='business_events' and c['name'] in {'request_id','related_event_id','product_id','created_at'})]
  q=lambda x:'"'+x.replace('"','""')+'"'
  rows=list(db.execute(text('SELECT row_to_json(t)::text FROM (SELECT '+','.join(q(c) for c in cols)+' FROM '+q(name)+') t')).scalars())
  out[name]={'count':len(rows),'sha256':hashlib.sha256(('\n'.join(sorted(rows))).encode()).hexdigest()}
 print(json.dumps(out,sort_keys=True))
'''


def inspect_release():
    assert not (ROOT/'private-state.json').exists(), 'Release already prepared'
    cs = containers()
    assert all(c['State'].get('Health',{}).get('Status') == 'healthy' for c in cs.values())
    config = yaml.safe_load(CONFIG.read_text())
    assert config['services']['backend']['image'] == cs[BACKEND]['Config']['Image']
    db_env = environment(cs[DB])
    values = {'containers':cs,'compose_sha256':hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
        'db_network':next(iter(cs[DB]['NetworkSettings']['Networks'])),
        'db_user':db_env['POSTGRES_USER'],'db_name':db_env['POSTGRES_DB']}
    save('private-state.json',values)
    shutil.copy2(CONFIG,ROOT/'compose.before.yaml')
    shutil.copy2(CONFIG.parent/'.env',ROOT/'compose.env.before')
    (ROOT/'backend.env').write_text('\n'.join(cs[BACKEND]['Config']['Env'])+'\n')
    summary={'services':{k:{'id':c['Id'],'image':c['Config']['Image'],'health':c['State']['Health']['Status']}
        for k,c in cs.items()}, 'backend_cmd':cs[BACKEND]['Config']['Cmd'],
        'backend_entrypoint':cs[BACKEND]['Config']['Entrypoint'], 'backend_user':cs[BACKEND]['Config']['User'],
        'backup_directory':str(ROOT),'data':db_python(SNAPSHOT)}
    save('inspection.json',summary)
    return summary


def build():
    s=state()
    base=s['containers'][BACKEND]['Config']['Image']
    context=ROOT/'source/backend/server'
    digest=hashlib.sha256()
    for path in sorted([*context.joinpath('app').rglob('*.py'),*context.joinpath('alembic').rglob('*.py'),context/'alembic.ini']):
        digest.update(path.relative_to(context).as_posix().encode()+b'\0'+path.read_bytes().replace(b'\r\n',b'\n'))
    source_sha=digest.hexdigest()
    revision=(ROOT/'source-revision.txt').read_text().strip()
    assert re.fullmatch('[0-9a-f]{40}',revision)
    dockerfile=f'FROM {base}\nUSER root\nCOPY --chown=10001:10001 app/ /app/app/\nCOPY --chown=10001:10001 alembic/ /app/alembic/\nCOPY --chown=10001:10001 alembic.ini /app/alembic.ini\nLABEL magicvvu.maintenance_release="V1-P9" magicvvu.p9_source_sha256="{source_sha}" org.opencontainers.image.revision="{revision}"\nUSER 10001\n'
    (context/'Dockerfile.p9').write_text(dockerfile)
    p=run(['docker','build','--network','none','-f',str(context/'Dockerfile.p9'),'-t',IMAGE,str(context)],timeout=180)
    (ROOT/'build.log').write_bytes(p.stdout+p.stderr)
    candidate=docker_json('image','inspect',IMAGE)[0]
    old=docker_json('image','inspect',base)[0]
    for key in ('Cmd','Entrypoint','Env','WorkingDir','Healthcheck','ExposedPorts'):
        assert candidate['Config'].get(key)==old['Config'].get(key), 'Inherited runtime changed: '+key
    result={'image':IMAGE,'image_id':candidate['Id'],'base_image':base,
        'dependencies_reused':True,'runtime_entrypoint_preserved':True,'source_sha256':source_sha,'git_revision':revision}
    save('build.json',result)
    return result


def backup(prefix):
    s=state()
    args=['docker','exec',DB]
    dump=run(args+['pg_dump','-U',s['db_user'],'-d',s['db_name'],'-Fc'],timeout=120).stdout
    assert len(dump)>1000
    (ROOT/(prefix+'.dump')).write_bytes(dump)
    roles=run(args+['pg_dumpall','-U',s['db_user'],'--globals-only'],timeout=60).stdout
    (ROOT/(prefix+'.globals.sql')).write_bytes(roles)
    result={'custom_dump_bytes':len(dump),'sha256':hashlib.sha256(dump).hexdigest(),
        'roles_saved':True,'protected_server_only':True}
    save(prefix+'-backup.json',result)
    return result


def wait_db():
    for _ in range(60):
        # The image's bootstrap server uses only a Unix socket. Require TCP so
        # we do not race its shutdown before the final PostgreSQL process starts.
        p=run(['docker','exec',RESTORE,'pg_isready','-h','127.0.0.1','-U','p9_restore_admin','-d','postgres'],check=False)
        if not p.returncode:return
        time.sleep(1)
    raise RuntimeError('Isolated restore database not ready')


def start_restore():
    s=state()
    assert not run(['docker','ps','-aq','--filter','name=^/'+RESTORE+'$']).stdout.strip(), 'Restore name already used'
    run(['docker','network','create','--internal',NETWORK])
    (ROOT/'restore-db.env').write_text('POSTGRES_USER=p9_restore_admin\nPOSTGRES_PASSWORD='+secrets.token_hex(32)+'\n')
    run(['docker','run','-d','--name',RESTORE,'--network',NETWORK,'--env-file',str(ROOT/'restore-db.env'),
        '--tmpfs','/var/lib/postgresql/data:rw,nosuid,size=1g',s['containers'][DB]['Image']])
    wait_db()


def restore(prefix):
    s=state()
    run(['docker','exec','-i',RESTORE,'psql','-U','p9_restore_admin','-d','postgres','-v','ON_ERROR_STOP=1'],
        data=(ROOT/(prefix+'.globals.sql')).read_bytes())
    assert re.fullmatch(r'[a-zA-Z0-9_]+',s['db_name']) and re.fullmatch(r'[a-zA-Z0-9_]+',s['db_user'])
    sql='CREATE DATABASE "'+s['db_name']+'" OWNER "'+s['db_user']+'"'
    run(['docker','exec',RESTORE,'psql','-U','p9_restore_admin','-d','postgres','-v','ON_ERROR_STOP=1','-c',sql])
    run(['docker','exec','-i',RESTORE,'pg_restore','-U','p9_restore_admin','-d',s['db_name'],'--exit-on-error'],
        data=(ROOT/(prefix+'.dump')).read_bytes(),timeout=120)
    env=environment(s['containers'][BACKEND])
    env.update(DB_HOST=RESTORE,DB_NAME=s['db_name'],DB_USER=s['db_user'])
    (ROOT/'restore-backend.env').write_text('\n'.join(k+'='+v for k,v in env.items())+'\n')


def cleanup_restore():
    # Fixed, task-owned names only; never compose down or remove a volume.
    run(['docker','rm','-f',RESTORE],check=False)
    run(['docker','network','rm',NETWORK],check=False)


def rehearse():
    backup('online')
    start_restore()
    try:
        restore('online')
        old=state()['containers'][BACKEND]['Config']['Image']
        before=db_python(SNAPSHOT,image=old,isolated=True)
        migration=run(['docker','run','--rm','--network',NETWORK,'--env-file',str(ROOT/'restore-backend.env'),
            '-e','PGOPTIONS=-c lock_timeout=5s -c statement_timeout=60s','--entrypoint','python',IMAGE,
            '-m','alembic','upgrade','head'])
        (ROOT/'rehearsal-migration.log').write_bytes(migration.stdout+migration.stderr)
        # Compare every legacy column, not only row counts. The event table adds columns.
        projection=r'''
import json,hashlib
from sqlalchemy import inspect,text
from app.database import engine
with engine.connect() as db:
 out={}
 for name in inspect(db).get_table_names():
  if name in {'products','product_batches','mutation_receipts','alembic_version'}:continue
  cols=[c['name'] for c in inspect(db).get_columns(name) if not(name=='business_events' and c['name'] in {'request_id','related_event_id','product_id','created_at'})]
  q=lambda x:'"'+x.replace('"','""')+'"'
  sql='SELECT row_to_json(t)::text FROM (SELECT '+','.join(q(c) for c in cols)+' FROM '+q(name)+') t'
  rows=list(db.execute(text(sql)).scalars())
  out[name]={'count':len(rows),'sha256':hashlib.sha256(('\n'.join(sorted(rows))).encode()).hexdigest()}
 print(json.dumps(out,sort_keys=True))
'''
        after=db_python(projection,image=IMAGE,isolated=True)
        assert after=={k:v for k,v in before.items() if k!='alembic_version'}, 'Restored legacy data changed'
        schema=run(['docker','run','--rm','--network',NETWORK,'--env-file',str(ROOT/'restore-backend.env'),
            '--entrypoint','python',IMAGE,'-m','alembic','check'])
        (ROOT/'rehearsal-schema-check.log').write_bytes(schema.stdout+schema.stderr)
        result={'passed':True,'full_dump_restored':True,'roles_restored':True,
            'legacy_rows_preserved':True,'migration':'20261026_0011','schema_matches_models':True,
            'restore_tables':{k:v['count'] for k,v in before.items()},'production_access_from_candidate':False}
        save('rehearsal.json',result)
        return result
    finally:
        cleanup_restore()


def verify():
    cs=containers();s=state()
    checks={'backend_image':cs[BACKEND]['Config']['Image']==IMAGE,
        'all_healthy':all(c['State'].get('Health',{}).get('Status')=='healthy' for c in cs.values()),
        'agent_unchanged':cs[AGENT]['Id']==s['containers'][AGENT]['Id'],
        'database_container_unchanged':cs[DB]['Id']==s['containers'][DB]['Id'],
        'backend_environment_preserved':environment(cs[BACKEND])==environment(s['containers'][BACKEND]),
        'mounts_preserved':cs[BACKEND]['Mounts']==s['containers'][BACKEND]['Mounts'],
        'ports_preserved':cs[BACKEND]['HostConfig']['PortBindings']==s['containers'][BACKEND]['HostConfig']['PortBindings'],
        'secret_file_preserved':(CONFIG.parent/'.env').read_bytes()==(ROOT/'compose.env.before').read_bytes()}
    preflight=json.loads(run(['docker','exec',BACKEND,'python','-m','app.p9_preflight']).stdout)
    checks['p9_preflight']=preflight['preflight_passed']
    result={'passed':all(checks.values()),'checks':checks,'preflight':preflight,'image':IMAGE}
    save('verification.json',result)
    assert result['passed'],'Deployment verification failed'
    return result


def deploy():
    assert json.loads((ROOT/'rehearsal.json').read_text())['passed']
    assert hashlib.sha256(CONFIG.read_bytes()).hexdigest()==state()['compose_sha256'],'Compose changed since preparation'
    # Do not interrupt a leased conversation or an executing task.
    active=db_python("from app.database import engine\nfrom sqlalchemy import text\nimport json\nwith engine.connect() as c:\n print(json.dumps({'tasks':c.scalar(text(\"SELECT count(*) FROM ai_tasks WHERE status='processing' AND lease_until > now()\")), 'conversations':c.scalar(text(\"SELECT count(*) FROM ai_conversation_bindings WHERE processing_nonce IS NOT NULL AND lease_until > now()\"))}))")
    assert not any(active.values()),'Active AI work; retry after it completes'
    run(['docker','stop','--time','30',BACKEND])
    migrated=False;replaced=False
    try:
        backup('final')
        before=db_python(SNAPSHOT,image=state()['containers'][BACKEND]['Config']['Image'])
        save('final-data-before.json',before)
        # Lock timeout and a single Alembic transaction protect existing data.
        p=run(['docker','run','--rm','--network',state()['db_network'],'--env-file',str(ROOT/'backend.env'),
            '-e','PGOPTIONS=-c lock_timeout=5s -c statement_timeout=60s','--entrypoint','python',IMAGE,
            '-m','alembic','upgrade','head'])
        (ROOT/'production-migration.log').write_bytes(p.stdout+p.stderr)
        migrated=True
        after=db_python(LEGACY_SNAPSHOT,image=IMAGE)
        assert after=={k:v for k,v in before.items() if k!='alembic_version'}, 'Production legacy data changed during migration'
        save('migration-data-preserved.json',{'passed':True,'all_legacy_columns_unchanged':True,
            'tables':{k:v['count'] for k,v in after.items()}})
        original=(ROOT/'compose.before.yaml').read_text()
        expected=yaml.safe_load(original);candidate=copy.deepcopy(expected)
        candidate['services']['backend']['image']=IMAGE
        base=expected['services']['backend']['image']
        updated,n=re.subn(r'(?m)^(\s*image:\s*)'+re.escape(base)+r'(\s*(?:#.*)?)$',lambda m:m[1]+IMAGE+m[2],original)
        assert n==1 and yaml.safe_load(updated)==candidate,'Only backend image may change'
        staged=CONFIG.with_suffix('.p9.tmp');staged.write_text(updated)
        shutil.copystat(CONFIG,staged);os.chown(staged,CONFIG.stat().st_uid,CONFIG.stat().st_gid)
        run(['docker','compose','-f',str(staged),'config','--quiet'])
        staged.replace(CONFIG);replaced=True
        run(['docker','compose','-f',str(CONFIG),'up','-d','--no-deps','--no-build','--pull','never','backend'])
        for _ in range(60):
            if containers()[BACKEND]['State'].get('Health',{}).get('Status')=='healthy':break
            time.sleep(1)
        return verify()
    except Exception:
        # Before acceptance no P9 writes should exist. Never erase new evidence.
        if migrated:
            new_rows=db_python("from app.database import engine\nfrom sqlalchemy import text\nimport json\nwith engine.connect() as c: print(json.dumps({'count':c.scalar(text('SELECT count(*) FROM mutation_receipts'))}))",image=IMAGE)
            if new_rows['count']:
                save('deployment-failed.json',{'migration_applied':True,'application_rolled_back':False,
                    'reason':'P9 evidence exists; old-reader rollback requires reconciliation','database_restored':False})
                raise RuntimeError('New P9 evidence retained; automatic old-image rollback suppressed')
        if replaced:
            shutil.copy2(ROOT/'compose.before.yaml',CONFIG)
            run(['docker','compose','-f',str(CONFIG),'up','-d','--no-deps','--no-build','--pull','never','backend'])
        else:
            run(['docker','start',BACKEND])
        save('deployment-failed.json',{'migration_applied':migrated,'application_rolled_back':True,
                                      'database_restored':False,'schema_retained':True})
        raise


if __name__=='__main__':
    assert os.geteuid()==0
    ROOT.mkdir(mode=0o700,parents=True,exist_ok=True);os.chmod(ROOT,0o700);os.umask(0o077)
    functions={'inspect':inspect_release,'build':build,'rehearse':rehearse,'deploy':deploy,'verify':verify}
    result=functions[sys.argv[1]]()
    print(json.dumps(result,ensure_ascii=False))
