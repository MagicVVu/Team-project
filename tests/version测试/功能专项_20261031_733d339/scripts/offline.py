"""Run original tests in the frozen checkout with outbound connections blocked."""
import argparse,asyncio,importlib,json,os,pathlib,socket,subprocess,sys,tempfile
from prepare import ROUND,write
SNAP=ROUND/'.snapshot'
def setup(mode,out):
 for key in list(os.environ):
  if any(part in key for part in ('API_KEY','TOKEN','BASE_URL','DATABASE_URL','DB_','PGPASSWORD','PGHOST','P0_','P1_','P2_','P3_','LLM_','APP_AI_ENGINE')):os.environ.pop(key,None)
 os.environ.update(P0_ENGINE='rules',P0_MODE='mock',P1_ENGINE='rules',P2_ENGINE='rules',P3_ENGINE='rules',APP_AI_ENGINE='rules',APP_API_TOKEN='local-development',DEMO_TOKEN='demo-local',DATABASE_URL='sqlite:///'+str(out/'bootstrap.sqlite').replace('\\','/'),PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
 scratch=out/'temp';scratch.mkdir(exist_ok=True);os.environ.update(TEMP=str(scratch),TMP=str(scratch));tempfile.tempdir=str(scratch)
 orig=socket.socket.connect
 def denied(*a,**k):raise RuntimeError('VERSION_TEST_EXTERNAL_CONNECTION_BLOCKED')
 def guarded(sock,address):
  f=sys._getframe(1);fallback=getattr(socket,'_fallback_socketpair',None)
  if fallback and f.f_code is fallback.__code__ and f.f_locals.get('csock') is sock and address==f.f_locals['lsock'].getsockname()[:2]:return orig(sock,address)
  return denied(sock,address)
 socket.socket.connect=guarded;socket.socket.connect_ex=denied;socket.create_connection=denied
 sys.dont_write_bytecode=True;sys.path[:0]=[str(SNAP),str(SNAP/'agent'),str(SNAP/'tests/garin/test_package/Agent_Regression_v1')]
 if mode.startswith('backend'):
  sys.path.insert(0,str(SNAP/'backend/server'))
  import sqlalchemy
  original=sqlalchemy.create_engine
  def sqlite_only(url,*a,**kw):
   if not str(url).startswith('sqlite:'):raise RuntimeError('VERSION_TEST_NON_SQLITE_BLOCKED')
   return original(url,*a,**kw)
  sqlalchemy.create_engine=sqlite_only
def main():
 p=argparse.ArgumentParser();p.add_argument('mode',choices=['ai','backend','ai-special','backend-special','eval','eval-special','legacy']);p.add_argument('--phase');p.add_argument('--split',default='test');p.add_argument('--tag',default='initial');a=p.parse_args()
 out=ROUND/'runs'/f'{a.mode}-{a.phase or "all"}-{a.tag}';out.mkdir(parents=True,exist_ok=False);setup(a.mode,out)
 write(out/'environment.json',{'python':sys.version,'packages':subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True).splitlines(),'external_network':'blocked','database':'temporary SQLite only','model':'offline rules/scripted not real LLM'})
 if a.mode=='legacy':
  from eval.p4 import verify
  original=subprocess.check_output
  def frozen_head(command,*args,**kw):
   if command==['git','-C',str(SNAP),'rev-parse','HEAD']:
    from prepare import HEAD
    return HEAD+'\n' if kw.get('text') or kw.get('encoding') else (HEAD+'\n').encode()
   return original(command,*args,**kw)
  verify.subprocess.check_output=frozen_head
  return 0 if verify.verify(out/'legacy') else 1
 if a.mode=='eval-special':
  from types import SimpleNamespace
  module=importlib.import_module('eval.'+a.phase+'.run')
  if a.phase=='chat':return 0 if asyncio.run(module.evaluate('test',out/'result.json')) else 1
  if a.phase=='session_memory':
   result=asyncio.run(module.main('all',False));(out/'result.json').write_bytes((SNAP/'reports/session-memory/offline-all.json').read_bytes());return result
  if a.phase=='p85':
   asyncio.run(module.main(SimpleNamespace(real=False,baseline=False,replay_report=None,split='all',limit=None,concurrency=1,output=str(out/'result.json'))));return 0
 if a.mode!='eval':
  import pytest
  target=[SNAP/'agent/tests',SNAP/'backend/tests'] if a.mode=='ai' else [SNAP/'backend/server/tests'] if a.mode=='backend' else [ROUND/'scripts/test_special_ai.py'] if a.mode=='ai-special' else [ROUND/'scripts/test_special_backend.py']
  os.chdir(SNAP/'backend/server' if a.mode.startswith('backend') else SNAP)
  return pytest.main([*[str(t) for t in target],'-q','--tb=short','-p','no:cacheprovider','--basetemp='+str(out/'pytest-temp'),'--junitxml='+str(out/'junit.xml')])
 module=importlib.import_module('eval.'+a.phase+'.run');before=set(module.ROOT.rglob('*.json')) if hasattr(module,'ROOT') else set()
 from types import SimpleNamespace
 operation=getattr(module,'run',None) or getattr(module,'evaluate')
 result=asyncio.run(operation(SimpleNamespace(engine='rules',split=a.split,limit=None)))
 after=set(module.ROOT.rglob('*.json'));created=after-before
 for pth in created:
  (out/pth.name).write_bytes(pth.read_bytes())
 write(out/'created.json',{'files':[str(p.relative_to(SNAP)) for p in created],'return':result})
 return 0
if __name__=='__main__':raise SystemExit(main())
