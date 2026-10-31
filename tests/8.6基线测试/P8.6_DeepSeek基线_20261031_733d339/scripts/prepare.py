"""Freeze source and preserve other members' working files."""
import hashlib,json,shutil,subprocess,sys
from pathlib import Path
ROUND=Path(__file__).resolve().parents[1]
REPO=ROUND.parents[2]
HEAD='733d339ee5bbb73635413902cdd0d07d43a6075a'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
def main():
    if (ROUND/'evidence/source.json').exists():print('Frozen evidence retained');return
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()
    if head!=HEAD:raise RuntimeError('HEAD_CHANGED')
    paths=subprocess.check_output(['git','ls-files','-z'],cwd=REPO).decode('utf-8').split('\0')
    protected=[];snapshot=[]
    for name in filter(None,paths):
        src=REPO/name
        if not src.is_file():continue
        record={'path':name,'sha256':sha(src)}
        if not name.startswith(ROUND.relative_to(REPO).as_posix()+'/') and name!='tests/交接文件夹/README.md':protected.append(record)
        if name.startswith('agent/') or name=='tools/runtime_adaptation_model_check.py':
            if any(p in {'.cache','__pycache__','.env'} for p in Path(name).parts):continue
            dest=ROUND/'.snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest);snapshot.append(record)
    write(ROUND/'evidence/source.json',{'head':head,'snapshot':snapshot,'protected':protected})
    write(ROUND/'evidence/environment.json',{'python':sys.version,'interpreter':sys.executable,
        'packages':subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True).splitlines(),
        'business_clock':'2026-10-15T10:00:00+08:00','execution_date':'2026-10-31 Asia/Shanghai',
        'model':'deepseek-flash','thinking':'disabled','temperature':'omitted, production provider default',
        'stream':False,'concurrency':1,'extra_paid_retries':False,'inventory_model':'single-object-1',
        'protocol':'inventory-autonomous-1','ai_deadline_seconds':58,'whole_task_deadline_seconds':60,
        'new_budget_cap_cny':5,'fee_authorization':'user approved a separate new round capped at 5 CNY'})
    old=REPO/'tests/jev模型测试/DeepSeek单模型基线_20261029_3f007ba/scripts/telemetry.py'
    shutil.copy2(old,ROUND/'scripts/telemetry.py')
    print(json.dumps({'head':head,'snapshot_files':len(snapshot),'protected_files':len(protected)}))
if __name__=='__main__':main()
