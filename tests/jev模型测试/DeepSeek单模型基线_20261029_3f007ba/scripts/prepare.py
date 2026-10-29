"""Freeze read-only team sources. All generated files stay in the Garin round."""
import hashlib, json, os, shutil, subprocess, sys
from pathlib import Path

ROUND = Path(__file__).resolve().parents[1]
REPO = ROUND.parents[2]
EXPECTED = '3f007ba830539f57b15ef5711865a5ef70a2b22a'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
def main():
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
    if head!=EXPECTED: raise SystemExit('SOURCE_CHANGED: start a separate round')
    if (ROUND/'evidence/source-manifest.json').exists():
        print('Already frozen; original manifest retained'); return
    paths=subprocess.check_output(['git','ls-files','-z'],cwd=REPO).decode('utf-8').split('\0')
    snapshot=[]; outside=[]
    for name in filter(None,paths):
        src=REPO/name
        if not src.is_file(): continue
        record={'path':name,'sha256':sha(src)}
        if not name.startswith(('tests/garin/','tests/交接文件夹/','tests/jev模型测试/','tests/后端逻辑与数据测试/')): outside.append(record)
        if name.startswith('agent/') and not any(p in {'.cache','.env','__pycache__'} for p in Path(name).parts):
            dest=ROUND/'.snapshot'/name
            dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dest)
            snapshot.append(record)
    write(ROUND/'evidence/source-manifest.json',{'head':head,'snapshot_files':snapshot,'outside_owned_files':outside,
        'git_status_before':subprocess.check_output(['git','status','--short'],cwd=REPO,text=True,encoding='utf-8')})
    write(ROUND/'evidence/environment.json',{'python':sys.version,'interpreter':sys.executable,
        'packages':subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True).splitlines(),
        'timezone':'Asia/Shanghai','concurrency':1,'automatic_retry':False,'jev_enabled':False,
        'model':'deepseek-flash','thinking':'disabled','stream':False,
        'temperature':'omitted as in production; provider default','top_p':'omitted as in production; provider default'})
    print(json.dumps({'frozen_source_files':len(snapshot),'protected_files':len(outside),'head':head}))
if __name__=='__main__': main()
