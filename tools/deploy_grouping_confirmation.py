"""Server-side single-file overlay, preserving the current P8.6 deployment."""
import hashlib, json, os, re, shutil, subprocess, time
from pathlib import Path
ROOT=Path('/srv/magicvvu/releases/grouping-confirmation-20261030')
CONFIG=Path('/srv/magicvvu/magicvvu-starter/deploy/compose.yaml')
IMAGE='magicvvu/backend:grouping-confirmation-20261030'
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
run(['docker','cp','magicvvu-starter-backend-1:/app/app/services/product_grouping.py',str(ROOT/'product_grouping.before.py')])
assert hashlib.sha256((ROOT/'product_grouping.before.py').read_bytes()).hexdigest()=='3f6d3404fd23660b5802cdd9deb99a2cfe5a8c7f639e00af1dc620bd1b799513','Source changed since review'
source=ROOT/'build/source/app/services';source.mkdir(parents=True,exist_ok=True)
shutil.copy2('/tmp/product_grouping.confirmation.py',source/'product_grouping.py')
(source/'product_grouping.py').chmod(0o644)
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
 actual=run(['docker','exec','magicvvu-starter-backend-1','sha256sum','/app/app/services/product_grouping.py']).split()[0]
 checks['source_verified']=actual==hashlib.sha256((source/'product_grouping.py').read_bytes()).hexdigest()
 assert all(checks.values()),checks
 result={'deployed':True,'image':IMAGE,'checks':checks,'schema_migration':False,'backup_directory':str(ROOT)}
 (ROOT/'verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
except Exception:
 shutil.copy2(ROOT/'compose.before.yaml',CONFIG)
 run(['docker','compose','-f',str(CONFIG),'up','-d','--no-deps','--no-build','--pull','never','backend']);healthy();raise
