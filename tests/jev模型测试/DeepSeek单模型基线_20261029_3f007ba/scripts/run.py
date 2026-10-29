"""Reproducible DeepSeek-only evaluation against a frozen source snapshot."""
import argparse, asyncio, contextlib, hashlib, json, os, shutil, subprocess, sys, time
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

ROUND=Path(__file__).resolve().parents[1]
AGENT=ROUND/'.snapshot/agent'
sys.path.insert(0,str(AGENT))
from telemetry import Recorder,network_guard,CURRENT
from scoring import checks,classify
from p0.budget import Budget
from p0.engines import EngineError
from conversation.engines import DeepSeekEngine
from conversation import dialogue as p84
from conversation.dialogue_schemas import Request,ResolveRequest,RespondRequest,Plan
from conversation.schemas import AgentResult
from conversation.tasks import Task
from conversation.replies import BoundTask
from conversation.memory_schemas import HistoryTurn,TaskEvidence
from eval.dialogue.run import fixture,NOW,SCOPE,TASK,DRAFT,score as legacy_score
from eval.p85 import run as p85run
from prepare import write,sha

def rows(name): return [json.loads(s) for s in (ROUND/'datasets'/f'{name}.jsonl').read_text(encoding='utf-8').splitlines()]
def verify_frozen():
    info=json.loads((ROUND/'evidence/source-manifest.json').read_text(encoding='utf-8'))
    changed=[x['path'] for x in info['snapshot_files'] if sha(ROUND/'.snapshot'/x['path'])!=x['sha256']]
    for name,data in json.loads((ROUND/'datasets/manifest.json').read_text(encoding='utf-8'))['sets'].items():
        if sha(ROUND/'datasets'/f'{name}.jsonl')!=data['sha256']: changed.append(name)
    if changed: raise RuntimeError('FROZEN_INPUTS_CHANGED')

def make_budget():
    # Keep the persistent limit and any earlier account usage. Never reset it.
    original=ROUND.parents[2]/'agent/.cache/p0/budget.sqlite'
    private=Path(os.environ['LOCALAPPDATA'])/'GarinAIModelTest/baselines/3f007ba/budget.sqlite'
    private.parent.mkdir(parents=True,exist_ok=True)
    if not private.exists() and original.exists():
        import sqlite3
        src=sqlite3.connect(f'file:{original.as_posix()}?mode=ro',uri=True)
        dst=sqlite3.connect(private); src.backup(dst); dst.close(); src.close()
    budget=Budget(private,AGENT/'eval/pricing.json')
    policy=private.parent/'garin-20261029-five-cny.json'
    if not policy.exists():
        write(policy,{'initial_conservative_cost_cny':str(budget.summary()['conservative_cost_cny']),
            'new_cost_cap_cny':'5','original_cumulative_cap_cny':'20','authorization':'user 2026-10-29 maximum 5 CNY; includes smoke and formal; never reset'})
    saved=json.loads(policy.read_text(encoding='utf-8'))
    budget.limit=min(Decimal('20'),Decimal(saved['initial_conservative_cost_cny'])+Decimal(saved['new_cost_cap_cny']))
    return budget

class OracleEngine:
    """Explicit synthetic plan injection, used only for offline harness checks."""
    plan=None
    async def dialogue_understand(self,*args): return self.plan
    async def dialogue_respond(self,text,frame):
        return ''.join('{{fact:'+key+'}}' for key in frame.facts)

def oracle(row):
    exp=row['expected']; text=row['text']; draft=exp.get('draft',{})
    if draft:
        action=draft['action']; fields={}
        for k,v in draft.items():
            if k in {'action','batch_id','expected_version','discard_mode'}: continue
            if k=='opened_at': v='昨天' if '昨天' in text else '今天'
            fields[k]={'value':str(v),'quote':text}
        amount='half' if row.get('category')=='一半消耗' else 'all' if row.get('category') in {'全部消耗','全部丢弃'} else 'literal'
        if amount!='literal': fields.pop('quantity',None); fields.pop('unit',None)
        selector={'use_reference':action not in {'ADD','PLAN_ADD'}}
        return Plan(speech_act='correction' if exp.get('kind')=='edit' else 'request',action=action,write_count=1,
            fields=fields,amount_mode=amount,selector=selector)
    if exp.get('reads'): return Plan(speech_act='question',reads=[{'kind':k} for k in exp['reads']],selector={'use_reference':True})
    if row.get('category')=='多批次选择':
        return Plan(speech_act='question',selector={'choice_index':1},reads=[{'kind':'location' if any(w in text for w in ['哪','位置']) else 'quantity'}])
    if exp.get('fact_contains'):
        if any('尚未执行' in s for s in exp['fact_contains']): return Plan(speech_act='status')
        return Plan(speech_act='question',selector={'use_reference':True},reads=[{'kind':'quantity'},{'kind':'location'}])
    if exp.get('error_code')=='MULTIPLE_WRITES': return Plan(speech_act='request',action='MOVE',write_count=2,selector={'use_reference':True})
    if exp.get('clarification'):
        fields={}
        import re
        quantity=re.search(r'消耗(?:了)?(\d+)',text)
        if quantity: fields['quantity']={'value':quantity[1],'quote':text}
        if '盒' in text: fields['unit']={'value':'盒','quote':text}
        if '千克' in text: fields['unit']={'value':'千克','quote':text}
        return Plan(speech_act='request',action='CONSUME',write_count=1,fields=fields,selector={'use_reference':True},amount_mode='literal' if fields else 'unknown')
    return Plan(speech_act='negation',preserve_active=True,social_reply='可以，我们先讨论，草稿继续保留。')

async def stage(rec,name,awaitable):
    start=time.perf_counter()
    with rec.stage(name):
        try:
            value=await awaitable
            rec.append('stages',{**CURRENT.get(),'stage':name,'latency_ms':(time.perf_counter()-start)*1000,
                'output':value.model_dump(mode='json') if hasattr(value,'model_dump') else value})
            return value
        except BaseException as error:
            rec.append('stages',{**CURRENT.get(),'stage':name,'latency_ms':(time.perf_counter()-start)*1000,'error_code':getattr(error,'code',type(error).__name__)})
            raise

async def single(row,budget,rec,offline=False,state=None):
    engine=OracleEngine() if offline else DeepSeekEngine(budget)
    if state is None:
        owner,ctx,reader=fixture(row.get('profile','reference'),engine)
        for batch in reader.data.items[0].batches: batch.quantity=Decimal(row.get('stock','6'))
    else: owner,ctx,reader=state; engine=owner.engine
    if offline: engine.plan=oracle(row)
    before=reader.data.model_dump(mode='json'); start=time.perf_counter(); frame={}; error=None; plan=None
    n=len(rec.requests); excn=len(rec.extractions)
    rec.append('inputs',{**CURRENT.get(),'text':row['text'],'context':ctx.model_dump(mode='json'),'fixture':before})
    try:
        async with asyncio.timeout(20):
            req=Request(text=row['text'],request_id=row['id'],context=ctx)
            understood=await stage(rec,'understanding',p84.understand(owner,req,SCOPE)); plan=understood.plan
            resolved=await stage(rec,'resolve',p84.resolve(owner,ResolveRequest(**req.model_dump(exclude={'remaining_seconds'}),plan=plan,remaining_seconds=max(.001,18-(time.perf_counter()-start))),SCOPE))
            frame=resolved.model_dump(mode='json'); frame['plan']=plan.model_dump(mode='json')
            if understood.understanding_calls and frame['kind']!='clarify' and time.perf_counter()-start<18:
                response=await stage(rec,'response',p84.respond(owner,RespondRequest(text=row['text'],resolved=resolved,remaining_seconds=18-(time.perf_counter()-start))))
                frame.update(reply=response.reply,fallback_used=response.fallback_used,response_error=response.error_code)
    except Exception as e: error=getattr(e,'code',type(e).__name__)
    unchanged=reader.data.model_dump(mode='json')==before
    if isinstance(row.get('expected'),dict):
        checked=checks(row['expected'],frame,unchanged,row.get('previous_draft'))
        if error: checked['no_exception']=False
    else:
        checked={'legacy_oracle':bool(not error and legacy_score(row,frame)),'inventory_unchanged':unchanged}
    status,kind=classify(row,frame,checked,error)
    record={'id':row['id'],'group_id':row['group_id'],'category':row.get('category',row['group_id']),**CURRENT.get(),
        'text':row['text'],'expected':row.get('expected'),'status':status,'issue_category':kind,'checks':checked,
        'frame':frame,'error_code':error,'latency_ms':(time.perf_counter()-start)*1000,
        'actual_http_attempts':len(rec.requests)-n,'engine_invocations':len(rec.extractions)-excn,
        'inventory_unchanged_by_ai':unchanged,'human_review_status':'pending','score_is_provisional':True,
        'clarification_expected':row.get('expected',{}).get('clarification',False) if isinstance(row.get('expected'),dict) else row.get('expected') in {'clarify','expired','blocked','multiple'},
        'clarification_actual':frame.get('kind') in {'needs_input','clarify'} or (frame.get('result') or {}).get('status')=='needs_clarification',
        'naturalness':'REVIEW; no human score','provenance':'fixture_workflow_not_model' if offline else 'live_deepseek',
        'state_before_sha256':hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest(),
        'state_after_sha256':hashlib.sha256(json.dumps(reader.data.model_dump(mode='json'),sort_keys=True).encode()).hexdigest()}
    rec.append('cases',record)
    if error in {'BUDGET_EXCEEDED','MODEL_NOT_CONFIGURED','PRICING_NOT_VERIFIED'}: raise EngineError(error)
    return record,(owner,ctx,reader)

def bind(ctx,frame,text,index):
    domain=frame.get('result') or {}; draft=domain.get('draft')
    if draft:
        revision=ctx.active.task.revision+1 if ctx.active else 1
        ctx.active=BoundTask(scope=SCOPE,task=Task(task_id=TASK,household_id=SCOPE.household_id,status='needs_confirmation',revision=revision,
            expires_at=NOW+timedelta(minutes=15),draft_id=DRAFT,result=AgentResult.model_validate(domain).model_dump(mode='json'),inventory_written=False))
        ctx.tasks=[TaskEvidence(task_id=UUID(TASK),revision=revision,status='needs_confirmation',action=draft['action'],execution_status='pending',draft_id=UUID(DRAFT),checked_at=ctx.trusted_now)]
    history=HistoryTurn(request_id=f'h-{index}',text=text,reply=frame.get('reply','未完成'),created_at=ctx.trusted_now)
    ctx.history=[*ctx.history,history][-10:]
    return DRAFT if draft else None

async def multi(row,budget,rec,offline=False):
    owner,ctx,reader=fixture('reference',OracleEngine() if offline else DeepSeekEngine(budget))
    reader.data.items[0].batches[0].quantity=Decimal(row['stock']); clock=[NOW]; owner.now=lambda:clock[0]
    previous=None; results=[]
    for index,turn in enumerate(row['turns']):
        clock[0]=NOW+timedelta(seconds=index*15); ctx.trusted_now=clock[0]; ctx.revision=index
        reader.data.as_of=clock[0]
        for t in ctx.tasks: t.checked_at=clock[0]
        if index==5 and row['external_change_before_turn6']:
            reader.data.items[0].batches[0].quantity+=2; reader.data.items[0].batches[0].version+=1
        value={**turn,'id':f"{row['id']}-t{index+1}",'group_id':row['group_id'],'category':row['category'],'previous_draft':previous}
        with rec.case(**CURRENT.get(),turn_id=value['id']):
            record,_=await single(value,budget,rec,offline,(owner,ctx,reader)); results.append(record)
        saved=bind(ctx,record['frame'],turn['text'],index)
        if saved: previous=saved
    return results

async def legacy_p85(row,budget,rec,offline=False):
    # Reuse the team's existing flow and oracle; observe individual stage boundaries.
    originals={name:getattr(p85run.flow,name) for name in ('understand','resolve','respond')}
    def wrapped(name):
        async def call(owner,body,*args):
            text=getattr(body,'text',''); idx=row['turns'].index(text) if text in row['turns'] else -1
            with rec.case(**CURRENT.get(),turn_id=f"{row['id']}-t{idx+1}"):
                if name=='understand': rec.append('inputs',{**CURRENT.get(),'text':text,'context':body.model_dump(mode='json')})
                return await stage(rec,{'understand':'understanding','respond':'response','resolve':'resolve'}[name],originals[name](owner,body,*args))
        return call
    for name in originals: setattr(p85run.flow,name,wrapped(name))
    try: scenario=await p85run.scenario(row,budget,real=not offline)
    finally:
        for name,fn in originals.items(): setattr(p85run.flow,name,fn)
    results=[]
    for t in scenario['turns']:
        ident=f"{row['id']}-t{t['turn']+1}"
        reqs=[r for r in rec.requests if r.get('turn_id')==ident and r.get('batch')==CURRENT.get().get('batch')]
        passed=t['passed'] and scenario['inventory_unchanged_by_ai']
        blocked=t.get('error_code') in {'BUDGET_EXCEEDED','MODEL_NOT_CONFIGURED','PRICING_NOT_VERIFIED'}
        record={'id':ident,'turn_id':ident,**CURRENT.get(),'group_id':row['group_id'],'category':'P8.5六轮记忆',
            'text':t['text'],'status':'BLOCKED' if blocked else 'PASS' if passed else 'FAIL','issue_category':None if passed else '环境问题：调用前保护停止' if blocked else '程序或模型问题待定位',
            'checks':{'legacy_p85_oracle':t['passed'],'inventory_unchanged':scenario['inventory_unchanged_by_ai']},
            'frame':{**t.get('resolved',{}),'plan':t.get('plan',{}),'fallback_used':t.get('fallback_used',False)},
            'error_code':t.get('error_code'),'latency_ms':t['latency_ms'],'actual_http_attempts':len(reqs),
            'inventory_unchanged_by_ai':scenario['inventory_unchanged_by_ai'],'human_review_status':'pending',
            'score_is_provisional':True,'provenance':'fixture_workflow_not_model' if offline else 'live_deepseek'}
        rec.append('cases',record); results.append(record)
    if any(t.get('error_code') in {'BUDGET_EXCEEDED','MODEL_NOT_CONFIGURED','PRICING_NOT_VERIFIED'} for t in scenario['turns']): raise EngineError('BUDGET_OR_CONFIGURATION_STOP')
    return results

def batches(command):
    old=[json.loads(s) for s in (AGENT/'eval/dialogue/samples.jsonl').read_text(encoding='utf-8').splitlines()]
    p85=p85run.scenarios()
    if command=='smoke': return [('smoke-single','p84',old[::40][:6]),('smoke-multi','p85',[p85[0],p85[-1]])]
    if command=='offline': return [('offline-new-single','single',rows('new-single')),('offline-new-multi','multi',rows('new-multi')),('offline-p85','p85',p85)]
    values=[('p84-regression','p84',old),('p85-regression','p85',p85)]
    for repeat in range(1,4):
        values += [(f'new-single-r{repeat}','single',rows('new-single')),(f'new-multi-r{repeat}','multi',rows('new-multi'))]
    return values

async def main(args):
    verify_frozen(); live=args.command!='offline'
    if live and not os.environ.get('DEEPSEEK_API_KEY'):
        write(ROUND/'evidence/live-status.json',{'status':'BLOCKED','reason':'MODEL_NOT_CONFIGURED','actual_http_attempts':0,
            'browser_login_is_not_api_credentials':True,'all_formal_batches':'NOT_RUN'})
        print('BLOCKED: MODEL_NOT_CONFIGURED; no HTTP calls'); return 2
    if args.command=='formal':
        if list((ROUND/'runs').glob('formal-*/started.json')): raise SystemExit('FORMAL_ALREADY_STARTED; original evidence retained; do not silently repeat paid batches')
        smoke=sorted((ROUND/'runs').glob('smoke-*/complete.json'))
        if not smoke: raise SystemExit('SMOKE_REQUIRED')
        last=json.loads(smoke[-1].read_text(encoding='utf-8'))
        if last.get('actual_http_attempts',0)==0 or last.get('infrastructure_ok') is not True: raise SystemExit('SMOKE_INFRASTRUCTURE_NOT_READY')
    stamp=time.strftime('%Y%m%dT%H%M%S'); out=ROUND/'runs'/f'{args.command}-{stamp}'
    if out.exists(): raise SystemExit('OUTPUT_ALREADY_EXISTS')
    rec=Recorder(out,'live' if live else 'offline_fixture'); budget=make_budget() if live else None
    before=budget.summary() if budget else None
    write(out/'started.json',{'command':args.command,'source':'3f007ba','budget_before':before,'paid_calls':live,'complete':False,
        'adapter_sha256':{p.name:sha(p) for p in (ROUND/'scripts').glob('*.py')},
        'dataset_manifest_sha256':sha(ROUND/'datasets/manifest.json'),
        'prompt_sources_sha256':{str(p.relative_to(AGENT)):sha(p) for p in [AGENT/'conversation/dialogue_engine.py',AGENT/'conversation/p85/engine.py',AGENT/'p0/deepseek.py']}})
    results=[]; stopped=None
    try:
        with network_guard(live),rec.install():
            for batch,kind,data in batches(args.command):
                for row in data:
                    with rec.case(batch=batch,scenario_id=row['id'],version='P8.5' if kind=='p85' else 'P8.4',group_id=row['group_id']):
                        if kind=='p85': values=await legacy_p85(row,budget,rec,not live)
                        elif kind=='multi': values=await multi(row,budget,rec,not live)
                        else:
                            result,_=await single(row,budget,rec,not live); values=[result]
                    results.extend(values)
                    print(json.dumps({'batch':batch,'id':row['id'],'pass':sum(x['status']=='PASS' for x in values),'turns':len(values),'http':len(rec.requests)},ensure_ascii=False),flush=True)
    except (EngineError,RuntimeError) as error: stopped=getattr(error,'code',str(error))
    infrastructure_ok=bool(rec.requests) and all(r['http_status']==200 and r['complete_body'] for r in rec.requests) and not stopped
    summary={'command':args.command,'complete':stopped is None,'stopped_reason':stopped,'executed_turns':len(results),
        'pass':sum(x['status']=='PASS' for x in results),'fail':sum(x['status']=='FAIL' for x in results),'review':sum(x['status']=='REVIEW' for x in results),
        'actual_http_attempts':len(rec.requests),'budget_before':before,'budget_after':budget.summary() if budget else None,
        'infrastructure_ok':infrastructure_ok,'provenance':'live_deepseek' if live else 'fixture_workflow_not_model',
        'human_review_status':'pending','production_database_accessed':False,'app_acceptance':'NOT_RUN'}
    write(out/'complete.json',summary)
    if live: write(ROUND/'evidence/live-status.json',{'status':'EXECUTED' if not stopped else 'STOPPED','latest_run':str(out),'summary':summary})
    print(json.dumps(summary,ensure_ascii=False)); return 1 if stopped else 0

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('command',choices=['offline','smoke','formal']); args=p.parse_args()
    sys.exit(asyncio.run(main(args)))
