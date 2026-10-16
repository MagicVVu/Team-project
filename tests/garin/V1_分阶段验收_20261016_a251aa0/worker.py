"""Rules-only worker; all writes stay in this round's copied checkout."""
import argparse, asyncio, hashlib, importlib, json, os, pathlib, socket, subprocess, sys, tempfile
ROOT=pathlib.Path(__file__).resolve().parent
SNAP=ROOT/'.snapshot'
def setup(mode):
    for key in list(os.environ):
        if any(part in key for part in ('API_KEY','TOKEN','BASE_URL','DATABASE_URL','DB_','PGPASSWORD','PGHOST','P0_','P1_','P2_','P3_','LLM_','APP_AI_ENGINE')):os.environ.pop(key,None)
    os.environ.update(P0_ENGINE='rules',P0_MODE='mock',P1_ENGINE='rules',P2_ENGINE='rules',P3_ENGINE='rules',APP_AI_ENGINE='rules',APP_API_TOKEN='local-development',DEMO_TOKEN='demo-local',DB_PASSWORD='garin-isolated-sqlite-only',DB_HOST='offline.invalid',DB_NAME='garin_local_test',PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
    scratch=ROOT/'.scratch'/mode;scratch.mkdir(parents=True,exist_ok=True)
    os.environ.update(TMP=str(scratch),TEMP=str(scratch));tempfile.tempdir=str(scratch)
    original=socket.socket.connect
    def denied(*a,**kw):raise RuntimeError('Garin offline worker blocks external network connections')
    def guarded(sock,address):
        frame=sys._getframe(1);fallback=getattr(socket,'_fallback_socketpair',None)
        if fallback and frame.f_code is fallback.__code__ and frame.f_locals.get('csock') is sock and address==frame.f_locals['lsock'].getsockname()[:2]:return original(sock,address)
        return denied(sock,address)
    socket.socket.connect=guarded;socket.socket.connect_ex=denied;socket.create_connection=denied
    sys.dont_write_bytecode=True
    sys.path[:0]=[str(SNAP),str(SNAP/'agent'),str(SNAP/'tests/garin/test_package/Agent_Regression_v1')]
    if mode in {'backend','backend-special'}:
        sys.path.insert(0,str(SNAP/'backend/server'))
        import sqlalchemy
        actual=sqlalchemy.create_engine
        def sqlite_only(url,*args,**kw):
            if not str(url).startswith('sqlite:'):raise RuntimeError('Only isolated SQLite is allowed by the local backend worker')
            return actual(url,*args,**kw)
        sqlalchemy.create_engine=sqlite_only

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['ai','backend','backend-special','legacy','native','supplemental']);p.add_argument('--phase');p.add_argument('--split');p.add_argument('--out',required=True);a=p.parse_args()
    out=pathlib.Path(a.out).resolve();out.mkdir(parents=True,exist_ok=False);setup(a.mode)
    if a.mode in {'ai','backend','backend-special','supplemental'}:
        import pytest
        targets=[SNAP/'agent/tests',SNAP/'backend/tests'] if a.mode=='ai' else [SNAP/'backend/server/tests'] if a.mode=='backend' else [ROOT/'backend_special_cases.py'] if a.mode=='backend-special' else [ROOT/'supplemental_cases.py']
        os.chdir(SNAP/'backend/server' if a.mode in {'backend','backend-special'} else SNAP)
        return pytest.main([*[str(t) for t in targets],'-q','--tb=short','-p','no:cacheprovider','--basetemp='+str(out/'temp'),'--junitxml='+str(out/'junit.xml')])
    if a.mode=='legacy':
        module=importlib.import_module('eval.p4.verify')
        baseline=json.loads((ROOT/'baseline.json').read_text(encoding='utf-8'))
        original=subprocess.check_output
        def frozen_git(command,*args,**kw):
            if command==['git','-C',str(SNAP),'rev-parse','HEAD']:
                data=baseline['commit']+'\n';return data if kw.get('text') or kw.get('encoding') else data.encode()
            return original(command,*args,**kw)
        module.subprocess.check_output=frozen_git
        return 0 if module.verify(out/'legacy') else 1
    module=importlib.import_module(f'eval.{a.phase}.run')
    results=module.ROOT/'results';before=set(results.glob('*.json'))
    from types import SimpleNamespace
    asyncio.run(module.run(SimpleNamespace(engine='rules',split=a.split,limit=None)))
    created=set(results.glob('*.json'))-before
    if len(created)!=1:raise RuntimeError('Expected one independent native result')
    target=created.pop();data=json.loads(target.read_text(encoding='utf-8'))
    (out/'result.json').write_bytes(target.read_bytes())
    rows=data['rows'];checks=[all(r.get('checks',{}).values()) and bool(r.get('checks')) for r in rows]
    required=90 if a.split=='dev' else 60
    summary={'phase':a.phase,'split':a.split,'count':len(rows),'pass':sum(checks),'fail':len(checks)-sum(checks),'all_checks_pass':len(rows)==required and all(checks),'engine':'rules','formal_acceptance':False}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False));return 0 if summary['all_checks_pass'] else 1
if __name__=='__main__':raise SystemExit(main())
