"""Freeze current tracked inputs. Never write teammate source or copy secrets."""
import hashlib,json,pathlib,shutil,subprocess
ROUND=pathlib.Path(__file__).resolve().parents[1]
REPO=ROUND.parents[2]
HEAD='c2d5ea6d5a5dc69d894a2547ce8a4529d38ecade'
OLD=REPO/'tests/version测试/功能专项_20261031_733d339'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,data):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
def main():
    if (ROUND/'evidence/source.json').exists():print('Existing frozen snapshot retained');return
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()==HEAD
    assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=REPO,text=True).strip(),'Tracked changes: review before freeze'
    paths=subprocess.check_output(['git','ls-files','-z'],cwd=REPO).decode().split('\0')
    frozen=[];protected=[]
    for name in filter(None,paths):
        src=REPO/name
        if not src.is_file():continue
        protected.append({'path':name,'sha256':sha(src)})
        if not name.startswith(('agent/','backend/','docs/versions/')):continue
        if any(t in {'.env','.cache','__pycache__','node_modules','.git','credentials'} for t in pathlib.Path(name).parts):continue
        dest=ROUND/'.snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)
        frozen.append({'path':name,'sha256':sha(src)})
    for folder in ['datasets','runs','reports','evidence','.runtime']:(ROUND/folder).mkdir(exist_ok=True)
    for name in ['single','multi']:
        shutil.copy2(OLD/'datasets'/f'{name}.jsonl',ROUND/'datasets'/f'{name}.jsonl')
    # Preserve evaluator/scorer as a read-only historical input. Adapt only in ab.py.
    shutil.copy2(OLD/'scripts/live.py',ROUND/'scripts/legacy.py')
    write(ROUND/'evidence/source.json',{'head':HEAD,'snapshot':frozen,'protected':protected,'working_tree_clean_at_freeze':True})
    write(ROUND/'evidence/reused_inputs.json',{'original_round':str(OLD),'files':{name:sha(OLD/name) for name in ['scripts/live.py','datasets/single.jsonl','datasets/multi.jsonl']},'historical_scores_not_comparison':True})
    (ROUND/'.gitignore').write_text('.snapshot/\n.runtime/\n.qa/\nnode_modules/\n__pycache__/\n*.pyc\n.pytest_cache/\n',encoding='utf-8')
    write(ROUND/'evidence/authorization.json',{'date':'2026-11-03','new_combined_budget_cny':'10','includes_smoke':True,'usd_budget_conversion_cny':'8','conversion_is_budget_allowance_not_invoice_fx':True,'keep_original_deepseek_20_cny_and_jev_1_usd_limits':True,'repeats_per_mode':2,'concurrency':1,'human_review_status':'pending'})
    write(ROUND/'evidence/pricing.json',{'checked_on':'2026-11-03','deepseek':{'model':'deepseek-flash','returned_version_expected':'DeepSeek-V4.1-Flash-1017','currency':'CNY','per_million_peak':{'cache_hit':'.04','cache_miss':'2','output':'8'},'per_million_offpeak':{'cache_hit':'.02','cache_miss':'1','output':'4'},'source':'https://api-docs.deepseek.com/zh-cn/quick_start/pricing/'},'jev':{'model':'jev-1.13.0','currency':'USD','input_per_million':'.042','output_per_million':'0','source':'https://docs.typesafe.ai/models'},'platform_invoice_verified':False,'unknown_usage_is_not_zero':True})
    print(json.dumps({'snapshot_files':len(frozen),'protected_files':len(protected),'head':HEAD}))
if __name__=='__main__':main()
