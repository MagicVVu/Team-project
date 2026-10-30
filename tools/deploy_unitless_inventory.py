"""Make inventory intake units optional; preserve product aggregation and DB schema."""
import hashlib, json, os, re, shutil, subprocess, time
from pathlib import Path
ROOT=Path('/srv/magicvvu/releases/unitless-inventory-20261030')
CONFIG=Path('/srv/magicvvu/magicvvu-starter/deploy/compose.yaml')
IMAGE='magicvvu/backend:unitless-inventory-20261030'
def run(args,timeout=120):
 p=subprocess.run(args,text=True,capture_output=True,timeout=timeout)
 if p.returncode: raise RuntimeError(p.stderr[-2000:])
 return p.stdout.strip()
def inspect():
 return {s:json.loads(run(['docker','inspect',f'magicvvu-starter-{s}-1']))[0] for s in ('backend','agent','db')}
def healthy():
 for _ in range(35):
  if inspect()['backend']['State'].get('Health',{}).get('Status')=='healthy': return
  time.sleep(2)
 raise RuntimeError('Backend failed health check')
assert os.geteuid()==0
ROOT.mkdir(mode=0o700,exist_ok=True)
before=inspect(); original=CONFIG.read_text()
shutil.copy2(CONFIG,ROOT/'compose.before.yaml')
run(['docker','cp','magicvvu-starter-backend-1:/app/app/inventory_schemas.py',str(ROOT/'inventory_schemas.before.py')])
assert hashlib.sha256((ROOT/'inventory_schemas.before.py').read_bytes()).hexdigest()=='7921ed74c39bdb38665d3fb33eb750f66f8cada91b237205026d8f9c22253ade','Source changed since review'
source=ROOT/'build/source/app';source.mkdir(parents=True,exist_ok=True)
shutil.copy2('/tmp/inventory_schemas.unitless.py',source/'inventory_schemas.py')
(source/'inventory_schemas.py').chmod(0o644)
(ROOT/'build/Dockerfile').write_text(f"FROM {before['backend']['Config']['Image']}\nCOPY source/ /app/\n")
run(['docker','build','--network=none','-t',IMAGE,str(ROOT/'build')])
old=before['backend']['Config']['Image']
candidate,n=re.subn(r'(?m)^(\s*image:\s*)'+re.escape(old)+r'(\s*)$',lambda m:m[1]+IMAGE+m[2],original)
assert n==1
staged=CONFIG.with_name('compose.grouping-confirmation.tmp.yaml');staged.write_text(candidate);shutil.copystat(CONFIG,staged)
run(['docker','compose','-f',str(staged),'config','--quiet'])
try:
 staged.replace(CONFIG)
 run(['docker','compose','-f',str(CONFIG),'up','-d','--no-deps','--no-build','--pull','never','backend'])
 healthy();after=inspect()
 checks={'agent_unchanged':before['agent']['Id']==after['agent']['Id'],'database_unchanged':before['db']['Id']==after['db']['Id'],
  'backend_image':after['backend']['Config']['Image']==IMAGE,
  'environment_unchanged':dict(v.split('=',1) for v in before['backend']['Config']['Env'])==dict(v.split('=',1) for v in after['backend']['Config']['Env']),
  'mounts_unchanged':before['backend']['Mounts']==after['backend']['Mounts'],
  'ports_unchanged':before['backend']['HostConfig']['PortBindings']==after['backend']['HostConfig']['PortBindings']}
 actual=run(['docker','exec','magicvvu-starter-backend-1','sha256sum','/app/app/inventory_schemas.py']).split()[0]
 checks['source_verified']=actual==hashlib.sha256((source/'inventory_schemas.py').read_bytes()).hexdigest()
 assert all(checks.values()),checks
 result={'deployed':True,'image':IMAGE,'checks':checks,'schema_migration':False,'backup_directory':str(ROOT)}
 (ROOT/'verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
except Exception:
 shutil.copy2(ROOT/'compose.before.yaml',CONFIG)
 run(['docker','compose','-f',str(CONFIG),'up','-d','--no-deps','--no-build','--pull','never','backend']);healthy();raise
