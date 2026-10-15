"""Standard-library runner. Adapter owns isolated fixtures and evidence collection."""
import argparse,collections,datetime,hashlib,importlib,json,pathlib,sys,time,platform,os,traceback
from decimal import Decimal, InvalidOperation
ROOT=pathlib.Path(__file__).resolve().parent

def same(a,b,key=''):
    if key in {'quantity','quantity_delta'}:
        try:return Decimal(str(a)).is_finite() and Decimal(str(a))==Decimal(str(b))
        except (InvalidOperation,ValueError):return False
    if isinstance(b,dict):return isinstance(a,dict) and set(a)==set(b) and all(same(a[k],v,k) for k,v in b.items())
    if isinstance(b,list):
        if not isinstance(a,list):return False
        if b and isinstance(b[0],dict) and 'id' in b[0]:
            if len({x.get('id') for x in a if isinstance(x,dict)})!=len(a):return False
            a=sorted(a,key=lambda x:x.get('id',''));b=sorted(b,key=lambda x:x['id'])
        return len(a)==len(b) and all(same(x,y) for x,y in zip(a,b))
    return type(a)==type(b) and a==b

def score(case,obs):
    errors=[]
    if case['kind']=='flow':return list(obs.get('failures',['missing flow evidence']))
    a=obs.get('result',{});e=case['expected']
    for k in ['status','intent','draft','facts']:
        if k in e and (k not in a or not same(a[k],e[k],k)):errors.append(f'{k}: expected={e[k]!r}; actual={a.get(k)!r}')
    if 'status_any' in e and a.get('status') not in e['status_any']:errors.append('status not in allowed set')
    if 'candidate_ids' in e:
        ids=[x.get('id') for x in a.get('candidates',[])]
        if sorted(ids)!=sorted(e['candidate_ids']):errors.append(f'candidate_ids: {ids!r}')
    if obs.get('before') is None or obs.get('after') is None:errors.append('missing independent state snapshots')
    elif not same(obs['before'],obs['after']):errors.append('state changed before user confirmation')
    if a.get('original_text')!=case['text']:errors.append('original_text missing/changed')
    if not a.get('trace_id'):errors.append('missing trace_id')
    if a.get('status')!='needs_confirmation' and a.get('draft') is not None:errors.append('unexpected executable draft')
    if a.get('status')=='needs_confirmation':
        for k in ['location','purchased_at','label_expiry']:
            if k in a.get('missing_fields',[]):errors.append('optional field incorrectly required: '+k)
    for k in ['facts','candidates']:
        if any(x.get('household_id')!=case['scope']['household_id'] for x in a.get(k,[])):errors.append('cross-household data in '+k)
    return errors

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',help='P0 source root containing p0/')
    p.add_argument('--adapter',default='adapters.local_p0',help='Python module with evaluate(case, config)')
    p.add_argument('--engine',choices=['rules','deepseek'],default='rules')
    p.add_argument('--allow-paid-model',action='store_true')
    p.add_argument('--version',required=True,help='software version or git commit')
    p.add_argument('--repeat',type=int,default=1)
    p.add_argument('--out',default=None)
    p.add_argument('--include-review',action='store_true')
    p.add_argument('--cases',nargs='+',default=['cases/baseline_150.jsonl','cases/extended.jsonl','cases/flows.jsonl'])
    args=p.parse_args()
    if args.repeat<1:p.error('--repeat must be positive')
    if args.engine=='deepseek' and not args.allow_paid_model:p.error('real model requires --allow-paid-model; may incur costs')
    if args.adapter=='adapters.local_p0' and not args.project:p.error('--project is required for local P0')
    if args.project:sys.path.insert(0,str(pathlib.Path(args.project).resolve()))
    adapter=importlib.import_module(args.adapter)
    cases=[];hashes={}
    for f in args.cases:
        path=pathlib.Path(f);path=path if path.is_absolute() else ROOT/path
        hashes[str(path.name)]=hashlib.sha256(path.read_bytes()).hexdigest()
        cases += [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]
    if len({c['id'] for c in cases})!=len(cases):raise ValueError('duplicate case IDs')
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out=pathlib.Path(args.out) if args.out else ROOT/'reports'/stamp
    out.mkdir(parents=True,exist_ok=False)
    records=[]
    with (out/'results.jsonl').open('w',encoding='utf-8') as log:
        for c in cases:
            for rep in range(args.repeat):
                r=dict(id=c['id'],category=c['category'],gate=c['gate'],repeat=rep+1)
                start=time.monotonic()
                if c['gate']=='review' and not args.include_review:r.update(status='REVIEW',failures=['gold label awaiting approval'])
                else:
                    try:
                        obs=adapter.evaluate(c,vars(args));errors=score(c,obs)
                        r.update(status='FAIL' if errors else 'PASS',failures=errors,evidence=obs)
                    except NotImplementedError as e:r.update(status='BLOCKED',failures=[str(e)])
                    except Exception as e:r.update(status='ERROR',failures=[f'{type(e).__name__}: {e}'],traceback=traceback.format_exc())
                r['seconds']=round(time.monotonic()-start,4);records.append(r)
                log.write(json.dumps(r,ensure_ascii=False)+'\n');log.flush()
    counts=dict(collections.Counter(r['status'] for r in records));required=[r for r in records if r['gate']=='required']
    passed=bool(required) and all(r['status']=='PASS' for r in required)
    summary=dict(suite_version='1.0.0',software_version=args.version,adapter=args.adapter,engine=args.engine,utc=stamp,repeat=args.repeat,case_hashes=hashes,counts=counts,required_pass=passed,required_pass_rate=sum(r['status']=='PASS' for r in required)/max(1,len(required)),meaning='Only declared required cases in this run; not production acceptance. REVIEW is excluded; BLOCKED/ERROR required cases prevent pass.')
    summary['environment']={'python':sys.version,'platform':platform.platform(),'model':os.getenv('LLM_MODEL','deepseek-flash') if args.engine=='deepseek' else None}
    project=pathlib.Path(args.project).resolve() if args.project else None
    relevant=list((project/'p0').glob('*.py'))+list((project/'p1').glob('*.py'))+list((project.parent/'backend').rglob('*.py')) if project else []
    summary['project_source_hashes']={str(f.relative_to(project.parent)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(relevant)}
    summary['suite_code_hashes']={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted({ROOT/'run.py',pathlib.Path(adapter.__file__)})}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 回归测试报告',f"版本：{args.version}；引擎：{args.engine}；适配器：{args.adapter}",f'结果：{counts}；本轮必测项全部通过：{passed}','', '## 失败、阻塞与待定项']
    for r in records:
        if r['status']!='PASS':lines.append(f"- {r['id']} [{r['status']}]："+'；'.join(r['failures']))
    (out/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2));print('Report:',out)
    return 0 if passed else 1
if __name__=='__main__':sys.exit(main())
