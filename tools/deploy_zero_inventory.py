"""Server-only staged cleanup and code deployment, with a private DB backup."""
import hashlib,json,os,re,secrets,shutil,subprocess,tarfile,time
from pathlib import Path
ROOT=Path('/srv/magicvvu/releases/zero-inventory-20261030')
CONFIG=Path('/srv/magicvvu/magicvvu-starter/deploy/compose.yaml')
IMAGE='magicvvu/backend:zero-inventory-20261030'
NET='magicvvu-zero-cleanup-test'; DB=NET+'-db'

def run(args,timeout=180,input=None):
 p=subprocess.run(args,input=input,text=True,capture_output=True,timeout=timeout)
 if p.returncode:raise RuntimeError(p.stdout[-1200:]+'\n'+p.stderr[-1200:])
 return p.stdout.strip()

def inspect():
 return {s:json.loads(run(['docker','inspect',f'magicvvu-starter-{s}-1']))[0] for s in ('backend','agent','db')}

def save(name,value):
 (ROOT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2))

def backup(name):
 with (ROOT/name).open('wb') as out:
  subprocess.run(['docker','exec','magicvvu-starter-db-1','pg_dump','-U','magicvvu_admin','-d','magicvvu','-Fc'],
    stdout=out,stderr=subprocess.PIPE,check=True,timeout=120)
 (ROOT/name).chmod(0o600)

CLEANUP='''
import json
from sqlalchemy import text,select
from app.database import SessionLocal
from app.models import Household
from app.services.product_grouping import lock_household
from app.services.inventory_cleanup import sweep
def snapshot(db):
 return {
 'active':dict(db.execute(text("select count(*) as count,md5(coalesce(string_agg(row_to_json(t)::text,'' order by t.id),'')) as digest from (select * from inventory_items where status='ACTIVE') t")).mappings().one()),
 'inactive':db.execute(text("select count(*) from inventory_items where status<>'ACTIVE'")).scalar_one(),
 'products':db.execute(text('select count(*) from products')).scalar_one(),
 'events':db.execute(text('select count(*) from business_events')).scalar_one(),
 'receipts':db.execute(text('select count(*) from mutation_receipts')).scalar_one(),
 'empty_products':db.execute(text("select count(*) from products p where not exists(select 1 from product_batches b join inventory_items i on i.id=b.inventory_item_id where b.product_id=p.id and i.status='ACTIVE')")).scalar_one()}
with SessionLocal.begin() as db:
 before=snapshot(db)
 households=list(db.scalars(select(Household.id).order_by(Household.id)))
 for home in households:lock_household(db,home)
 for home in households:sweep(db,home)
 after=snapshot(db)
 assert before['active']==after['active'],'Active inventory changed'
 assert before['events']==after['events'] and before['receipts']==after['receipts'],'History or retries lost'
 assert after['inactive']==after['empty_products']==0
 for home in households:sweep(db,home)
 assert snapshot(db)==after,'Cleanup not idempotent'
 print(json.dumps({'passed':True,'before':before,'after':after,'deleted_inventory':before['inactive'],
  'deleted_products':before['products']-after['products'],'active_rows_unchanged':True,'idempotent':True}))
'''

def stage():
 ROOT.mkdir(mode=0o700)
 with tarfile.open('/tmp/magicvvu-zero-cleanup.tar.gz') as archive:archive.extractall(ROOT,filter='data')
 before=inspect();save('containers.private.json',before)
 shutil.copy2(CONFIG,ROOT/'compose.before.yaml')
 for name,expected in json.loads((ROOT/'manifest.json').read_text()).items():
  assert hashlib.sha256((ROOT/'source'/name).read_bytes()).hexdigest()==expected
  (ROOT/'source'/name).chmod(0o644)
 folder=ROOT/'build';folder.mkdir();shutil.copytree(ROOT/'source',folder/'source')
 (folder/'Dockerfile').write_text(f"FROM {before['backend']['Config']['Image']}\nCOPY source/ /app/\n")
 run(['docker','build','--network=none','-t',IMAGE,str(folder)])
 backup('database-staging.dump')
 run(['docker','network','create','--internal',NET]);password=secrets.token_hex(24)
 try:
  run(['docker','run','-d','--name',DB,'--network',NET,'--network-alias','db',
   '-e','POSTGRES_USER=magicvvu_admin','-e','POSTGRES_PASSWORD='+password,'-e','POSTGRES_DB=zero_cleanup_test',
   'public.ecr.aws/docker/library/postgres:17'])
  for _ in range(40):
   if subprocess.run(['docker','exec',DB,'pg_isready','-h','127.0.0.1','-U','magicvvu_admin'],capture_output=True).returncode==0:break
   time.sleep(1)
  with (ROOT/'database-staging.dump').open('rb') as stream:
   p=subprocess.run(['docker','exec','-i',DB,'pg_restore','-U','magicvvu_admin','-d','zero_cleanup_test',
     '--no-owner','--no-privileges','--exit-on-error'],stdin=stream,capture_output=True,timeout=120)
   assert p.returncode==0,p.stderr.decode()[-2000:]
  result=json.loads(run(['docker','run','--rm','-i','--network',NET,'-e','DB_HOST=db','-e','DB_PORT=5432',
   '-e','DB_NAME=zero_cleanup_test','-e','DB_USER=magicvvu_admin','-e','DB_PASSWORD='+password,
   '--entrypoint','python',IMAGE,'-'],input=CLEANUP))
  save('clone-verification.json',result);print(json.dumps(result),flush=True)
 finally:
  subprocess.run(['docker','rm','-f','-v',DB],capture_output=True)
  subprocess.run(['docker','network','rm',NET],capture_output=True)

def deploy():
 assert json.loads((ROOT/'clone-verification.json').read_text())['passed']
 before=inspect();original=(ROOT/'compose.before.yaml').read_text()
 assert CONFIG.read_text()==original,'Compose changed after staging'
 staged_before=json.loads((ROOT/'containers.private.json').read_text())
 assert all(before[s]['Image']==staged_before[s]['Image'] for s in before),'Running image changed'
 # New source must be readable by the actual non-root application user.
 for name,expected in json.loads((ROOT/'manifest.json').read_text()).items():
  actual=run(['docker','run','--rm','--network=none','--entrypoint','sha256sum',IMAGE,'/app/'+name]).split()[0]
  assert actual==expected,name
 env=dict(v.split('=',1) for v in before['backend']['Config']['Env'])
 args=[x for k,v in env.items() for x in ('-e',k+'='+v)]
 network=next(n for n in before['backend']['NetworkSettings']['Networks'] if n in before['db']['NetworkSettings']['Networks'])
 old=before['backend']['Config']['Image']
 candidate,n=re.subn(r'(?m)^(\s*image:\s*)'+re.escape(old)+r'(\s*)$',lambda m:m[1]+IMAGE+m[2],original)
 assert n==1
 staged=CONFIG.with_name('compose.zero-cleanup.tmp.yaml');staged.write_text(candidate);shutil.copystat(CONFIG,staged)
 run(['docker','compose','-f',str(staged),'config','--quiet'])
 run(['docker','compose','-f',str(CONFIG),'stop','-t','90','backend'],timeout=150)
 try:
  backup('database-before.dump')
  result=json.loads(run(['docker','run','--rm','-i','--network',network,*args,'--entrypoint','python',IMAGE,'-'],input=CLEANUP))
  save('production-cleanup.json',result)
  staged.replace(CONFIG)
  run(['docker','compose','-f',str(CONFIG),'up','-d','--no-deps','--no-build','--pull','never','backend'])
  for _ in range(40):
   if inspect()['backend']['State'].get('Health',{}).get('Status')=='healthy':break
   time.sleep(2)
  else:raise RuntimeError('Backend unhealthy')
  after=inspect()
  checks={'agent_unchanged':before['agent']['Id']==after['agent']['Id'],'database_unchanged':before['db']['Id']==after['db']['Id'],
   'backend_image_applied':after['backend']['Config']['Image']==IMAGE,
   'environment_unchanged':dict(v.split('=',1) for v in before['backend']['Config']['Env'])==dict(v.split('=',1) for v in after['backend']['Config']['Env']),
   'mounts_unchanged':before['backend']['Mounts']==after['backend']['Mounts'],
   'ports_unchanged':before['backend']['HostConfig']['PortBindings']==after['backend']['HostConfig']['PortBindings']}
  assert all(checks.values())
  run(['docker','exec','magicvvu-starter-db-1','vacuumdb','-U','magicvvu_admin','-d','magicvvu','--analyze',
       '-t','inventory_items','-t','product_batches','-t','products','-t','inventory_planning_facts','-t','planning_fact_writes'])
  verification={'deployed':True,'image':IMAGE,'checks':checks,'cleanup':result,'backup_directory':str(ROOT),'vacuum_analyze':True}
  save('verification.json',verification);print(json.dumps(verification),flush=True)
 except Exception:
  shutil.copy2(ROOT/'compose.before.yaml',CONFIG)
  run(['docker','compose','-f',str(CONFIG),'up','-d','--no-deps','--no-build','--pull','never','backend'])
  raise

if __name__=='__main__':
 import sys
 assert os.geteuid()==0
 {'stage':stage,'deploy':deploy}[sys.argv[1]]()
