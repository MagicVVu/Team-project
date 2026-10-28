"""Freeze a repository checkout without touching member-owned files."""
import argparse, datetime, hashlib, json, pathlib, shutil, subprocess

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def capture(source, target):
    source=pathlib.Path(source).resolve();target=pathlib.Path(target).resolve()
    allowed=source/'tests'/'garin'
    if not target.is_relative_to(allowed) or target==allowed:raise ValueError('New round must be below tests/garin')
    if target.exists():raise FileExistsError('Refuse to overwrite an existing round')
    def git(*args):return subprocess.check_output(['git','--no-optional-locks','-c','safe.directory='+source.as_posix(),'-c','core.quotepath=false','-C',str(source),*args],encoding='utf-8').strip()
    tracked=subprocess.check_output(['git','--no-optional-locks','-c','safe.directory='+source.as_posix(),'-C',str(source),'ls-files','-z']).decode('utf-8').split('\0')
    outside={r:sha(source/r) for r in tracked if r and not r.startswith('tests/garin/') and (source/r).is_file()}
    historical={r:sha(source/r) for r in tracked if r.startswith('tests/garin/') and (source/r).is_file()}
    selected=[]
    for rel in tracked:
        if not rel or not (source/rel).is_file():continue
        p=pathlib.PurePosixPath(rel)
        if p.name.startswith('.env') or p.name=='local.properties':continue
        if any(x in {'.git','.cache','.gradle','build','__pycache__','.venv','results'} for x in p.parts):continue
        if rel.startswith(('agent/','backend/','frontend/','deploy/','docs/versions/','tests/garin/test_package/')) or rel=='tests/garin/失败清单.json':selected.append(rel)
    target.mkdir(parents=True)
    snapshot=target/'.snapshot';snapshot.mkdir()
    hashes={}
    for rel in selected:
        dest=snapshot/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/rel,dest);hashes[rel]=sha(dest)
    sdk=source/'frontend/local.properties'
    if sdk.exists():
        shutil.copy2(sdk,snapshot/'frontend/local.properties')
        hashes['frontend/local.properties']=sha(sdk)
    for f in pathlib.Path(__file__).parent.glob('*.py'):
        if f.name not in {'build_record.py','make_report.py'}:shutil.copy2(f,target/f.name)
    for f in pathlib.Path(__file__).parent.glob('*.ps1'):shutil.copy2(f,target/f.name)
    (target/'evidence').mkdir();(target/'results').mkdir()
    metadata={'captured_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source':str(source),'commit':git('rev-parse','HEAD'),'branch':git('branch','--show-current'),'initial_status':git('status','--short'),'snapshot_sha256':hashes,'outside_round_tracked_hashes':outside,'historical_garin_hashes':historical,'rules_only':True,'production_access_authorized':False,'human_signoff':False}
    (target/'baseline.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    (target/'.gitignore').write_text('.snapshot/\n.runtime/\n.scratch/\n__pycache__/\n*.pyc\nevidence/**/temp/\n!evidence/**/*.log\n',encoding='utf-8')
    print(json.dumps({'round':str(target),'commit':metadata['commit'],'snapshot_files':len(hashes),'outside_files_recorded':len(outside),'historical_files_recorded':len(historical)},ensure_ascii=False,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--out',required=True);a=p.parse_args();capture(a.source,a.out)
