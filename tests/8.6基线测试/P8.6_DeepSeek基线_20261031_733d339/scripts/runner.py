"""Current P8.6 AI pipeline with synthetic read-only state and actual wire logs."""
import argparse,asyncio,collections,json,os,sys,time
from datetime import timedelta
from decimal import Decimal,InvalidOperation
from pathlib import Path
from uuid import UUID
from prepare import ROUND,REPO,HEAD,sha,write
AGENT=ROUND/'.snapshot/agent';sys.path.insert(0,str(AGENT))
from telemetry import Recorder,network_guard,CURRENT
from p0.budget import Budget
from p0.engines import EngineError
from p0.domain import DomainError
from conversation.engines import DeepSeekEngine
from conversation.autonomous import runner,engine
from conversation.autonomous.schemas import RunRequest,Decision
from conversation.p85.schemas import P85Archive,P85Episode,P85Plan
from conversation.memory_schemas import HistoryTurn,TaskEvidence
from conversation.schemas import AgentResult
from conversation.tasks import Task
from conversation.replies import BoundTask
from eval.dialogue.run import fixture,NOW,SCOPE,TASK,DRAFT

def readrows(name):return [json.loads(s) for s in (ROUND/'datasets'/f'{name}.jsonl').read_text(encoding='utf-8').splitlines()]
def budget():
    # One existing cumulative ledger, a separate five-yuan allowance for this round.
    path=Path(os.environ['LOCALAPPDATA'])/'GarinAIModelTest/baselines/3f007ba/budget.sqlite'
    if not path.exists():raise RuntimeError('ORIGINAL_LEDGER_MISSING; do not reset prior spending')
    b=Budget(path,AGENT/'eval/pricing.json');policy=path.parent/'p86-20261031-733d339-five-cny.json'
    if not policy.exists():write(policy,{'initial_cny':str(b.summary()['conservative_cost_cny']),'initial_reservations':b.summary()['calls'],'new_cap_cny':'5','cumulative_original_cap_cny':'20','authorization':'user approved separate new 5 CNY 2026-10-31'})
    p=json.loads(policy.read_text(encoding='utf-8'));b.limit=min(Decimal('20'),Decimal(p['initial_cny'])+Decimal(p['new_cap_cny']))
    return b,p

def equal(a,b):
    if a is None:return b is None
    try:return Decimal(str(a))==Decimal(str(b))
    except (InvalidOperation,ValueError,TypeError):return a==b
def score(expected,result,unchanged,previous):
    frame=result.get('resolved') or {};domain=frame.get('result') or {};draft=domain.get('draft') or {}
    checks={'no_inventory_write':unchanged and result.get('inventory_writes') is False and result.get('shopping_writes') is False}
    if expected.get('no_draft'):checks['no_draft']=not draft
    if 'status' in expected:checks['status']=result.get('status')==expected['status']
    if 'reason' in expected:checks['stop_reason']=result.get('stop_reason')==expected['reason']
    if 'error' in expected:checks['error_code']=result.get('error_code')==expected['error']
    for field,value in expected.get('draft',{}).items():checks['draft.'+field]=equal(draft.get(field),value)
    for field in expected.get('absent',[]):checks['absent.'+field]=field not in draft
    facts='\n'.join(str(v) for v in frame.get('facts',{}).values())
    for fact in expected.get('facts',[]):checks['fact.'+fact]=fact in facts
    if expected.get('batch_id'):
        rows=domain.get('facts') or [];checks['target_batch']=len(rows)==1 and rows[0].get('id')==expected['batch_id']
    if expected.get('same_draft'):checks['same_draft']=bool(previous) and (frame.get('edit') or {}).get('draft_id')==previous
    if expected.get('created_count'):
        evidence=[e for e in frame.get('evidence',[]) if e.get('kind')=='physical_intake_projection']
        checks['created_count']=len(evidence)==1 and evidence[0].get('created_count')==expected['created_count']
        if expected.get('portion'):
            after=(domain.get('preview') or {}).get('after') or {};checks['one_portion']=after.get('unit')=='份' and equal(after.get('quantity'),1)
    if expected.get('risk_unknown'):
        risks=[r for e in frame.get('evidence',[]) for r in (e.get('result') or {}).get('risks',[])]
        checks['risk_unknown']=bool(risks) and all(r.get('level')=='unknown' and bool(r.get('missing_information')) for r in risks)
    if expected.get('unknown_receipt'):checks['unknown_receipt']=any(s in result.get('reply','') for s in ['待核实','不能确认','无法确认','未知'])
    return checks

def oracle(row):
    exp=row['expected'];text=row['text'];d=exp.get('draft')
    if d:
        fields={}
        for k,v in d.items():
            if k in {'action','batch_id','expected_version','discard_mode'}:continue
            if k=='opened_at':v='昨天' if '昨天' in text else '今天'
            fields[k]={'value':str(v),'quote':text}
        amount='all' if d['action'] in {'CONSUME','DISCARD'} else 'literal'
        if amount=='all':fields.pop('quantity',None);fields.pop('unit',None)
        plan={'speech_act':'correction' if '更正' in text or '说错' in text else 'request','action':d['action'],
            'selector':{'use_reference':d['action'] not in {'ADD','PLAN_ADD'}},'fields':fields,'write_count':1,'amount_mode':amount}
        # All-mode grounding must occur literally in the same source text.
        if d['action'] in {'CONSUME','DISCARD'} and not any(s in text for s in ['全部','都','喝完','用完','喝光']):
            plan['amount_mode']='literal';plan['fields'].update(quantity={'value':'1','quote':text},unit={'value':'盒','quote':text})
    elif exp.get('risk_unknown'):plan={'speech_act':'question','selector':{'use_reference':True},'reads':[{'kind':'risk'}]}
    elif row.get('profile')=='no_planning':plan={'speech_act':'question','selector':{'use_reference':True},'reads':[{'kind':'forecast'}]}
    elif exp.get('error')=='SINGLE_OBJECT_CONSUMPTION_REQUIRED' or row.get('category')=='规格不能扣余量':
        action='DISCARD' if '丢' in text else 'CONSUME'
        plan={'speech_act':'request','action':action,'selector':{'use_reference':True},'amount_mode':'half','write_count':1}
        if not any(s in text for s in ['一半','半数','50%']):
            import re
            amount=re.search(r'(\d+(?:\.\d+)?)(盒|毫升|升|克)',text)
            if amount:
                plan['amount_mode']='literal';plan['fields']={'quantity':{'value':amount[1],'quote':amount[0]},'unit':{'value':{'毫升':'ml','升':'L','克':'g'}.get(amount[2],amount[2]),'quote':amount[0]}}
    elif exp.get('error')=='OBJECT_COUNT_INVALID':
        import re
        q=re.search(r'\d+\.\d+',text)[0];plan={'speech_act':'request','action':'ADD','write_count':1,'fields':{k:{'value':v,'quote':text} for k,v in {'name':'衣服','quantity':q,'unit':'件','location':'厨房'}.items()}}
    elif exp.get('error')=='SPECIFICATION_READ_UNAVAILABLE':plan={'speech_act':'question','selector':{'use_reference':True},'reads':[{'kind':'quantity'}]}
    elif row.get('category')=='多操作先澄清':return Decision(action='ask',clarification='priority')
    elif row.get('category')=='多件选择':return Decision(action='ask',clarification='object')
    elif row.get('profile')=='expired':plan={'speech_act':'question','selector':{'use_reference':True},'reads':[{'kind':'location'}]}
    elif exp.get('unknown_receipt') or any('尚未执行' in v for v in exp.get('facts',[])):plan={'speech_act':'status'}
    elif row.get('category')=='日期缺失降级':plan={'speech_act':'question','selector':{'use_reference':True},'reads':[{'kind':'dates'}]}
    elif exp.get('facts') or exp.get('batch_id'):
        plan={'speech_act':'question','selector':{'choice_index':1} if exp.get('batch_id')=='b2' else {'use_reference':True},
            'reads':[{'kind':'quantity'},{'kind':'location'}]}
    else:plan={'speech_act':'discuss','social_reply':'可以慢慢整理，把常用物品放在方便拿取的地方。','preserve_active':True}
    return Decision(action='resolve',plan=P85Plan.model_validate(plan),finish_after_resolve=True)

class Oracle:
    decision=None
    async def autonomous_step(self,payload):return self.decision

def state(profile,semantic):
    owner,ctx,reader=fixture('none' if profile=='empty' else 'reference' if profile=='no_planning' else profile,semantic)
    owner.inventory_model='single-object-1'
    for item in reader.data.items:
        for batch in item.batches:batch.quantity=Decimal(1)
    if profile=='no_planning':
        async def unavailable(*args,**kwargs):raise DomainError('PLANNING_CONTEXT_UNAVAILABLE','合成夹具明确缺少规划资料。',503)
        reader.planning_context=unavailable
    clock=[NOW];owner.now=lambda:clock[0]
    return owner,ctx,reader,clock,[]

def classify(row,result,checks,error):
    if error in {'BUDGET_EXCEEDED','MODEL_NOT_CONFIGURED','PRICING_NOT_VERIFIED'}:return 'BLOCKED','环境或预算限制'
    if error:return 'FAIL','环境问题' if any(t in error for t in ['TIMEOUT','HTTP','UNAVAILABLE']) else '模型输出或测试适配问题待定位'
    if all(checks.values()):return 'PASS',None
    if result.get('error_code') in {'PLANNING_CONTRACT_INVALID','ITEM_NOT_FOUND'}:return 'FAIL','版本契约或适配问题'
    return 'FAIL','程序或模型问题待定位'

async def question(row,b,rec,offline=False,current=None,previous=None):
    if current is None:current=state(row['profile'],Oracle() if offline else DeepSeekEngine(b))
    owner,ctx,reader,clock,archive=current
    if offline:owner.engine.decision=oracle(row)
    before=reader.data.model_dump(mode='json');n=len(rec.requests);start=time.perf_counter();result={};error=None
    rec.append('inputs',{**CURRENT.get(),'text':row['text'],'context':ctx.model_dump(mode='json'),'archive':[e.model_dump(mode='json') for e in archive],'inventory':before})
    try:
        async with asyncio.timeout(60):
            body=RunRequest(text=row['text'],request_id=row['id'],context=ctx,archive=P85Archive(scope=SCOPE,conversation_id=ctx.conversation_id,revision=ctx.revision,episodes=archive),remaining_seconds=58)
            result=(await runner.run(owner,body,SCOPE)).model_dump(mode='json')
    except Exception as e:error=getattr(e,'code',type(e).__name__)
    check=score(row['expected'],result,reader.data.model_dump(mode='json')==before,previous)
    if error:check['no_exception']=False
    status,kind=classify(row,result,check,error)
    declared=result.get('model_calls');actual=len(rec.requests)-n
    # A declared invocation can fail before sending HTTP (e.g. budget gate).
    record={**CURRENT.get(),'id':row['id'],'group_id':row['group_id'],'category':row['category'],'text':row['text'],'expected':row['expected'],
        'status':status,'issue_category':kind,'checks':check,'output':result,'error_code':error,
        'question_ms':(time.perf_counter()-start)*1000,'actual_http_calls':actual,'declared_model_invocations':declared,
        'inventory_unchanged':check['no_inventory_write'],'human_review_status':'pending',
        'provenance':'offline_oracle_not_model' if offline else 'live_deepseek'}
    if result.get('error_code') in {'BUDGET_EXCEEDED','MODEL_NOT_CONFIGURED','PRICING_NOT_VERIFIED'}:
        record.update(status='BLOCKED',issue_category='预算或配置保护停止')
    rec.append('questions',record)
    return record,current

def persist(current,row,record,index):
    owner,ctx,reader,clock,archive=current;out=record['output'];frame=out.get('resolved') or {};domain=frame.get('result') or {};draft=domain.get('draft')
    if draft:
        rev=ctx.active.task.revision+1 if ctx.active else 1
        ctx.active=BoundTask(scope=SCOPE,task=Task(task_id=TASK,household_id=SCOPE.household_id,status='needs_confirmation',revision=rev,
            expires_at=NOW+timedelta(minutes=15),draft_id=DRAFT,result=AgentResult.model_validate(domain).model_dump(mode='json'),inventory_written=False))
        ctx.tasks=[TaskEvidence(task_id=UUID(TASK),revision=rev,status='needs_confirmation',action=draft['action'],execution_status='pending',draft_id=UUID(DRAFT),checked_at=clock[0])]
    if frame.get('kind')=='clear_reference':ctx.reference=None
    episode=(frame.get('memory_delta') or {}).get('episode')
    if episode:archive.append(P85Episode.model_validate(episode))
    else:archive.append(P85Episode(memory_id=f"memory-{row['id']}",request_id=row['id'],text=row['text'],reply=out.get('reply','未完成'),created_at=clock[0]))
    ctx.history=[*ctx.history,HistoryTurn(request_id=row['id'],text=row['text'],reply=out.get('reply','未完成'),created_at=clock[0])][-10:]
    return DRAFT if draft else None

async def scenario(row,b,rec,offline):
    current=state(row['profile'],Oracle() if offline else DeepSeekEngine(b));previous=None;output=[]
    for index,t in enumerate(row['turns']):
        owner,ctx,reader,clock,_=current;clock[0]=NOW+timedelta(seconds=index*15);ctx.trusted_now=clock[0];ctx.revision=index
        for task in ctx.tasks:task.checked_at=clock[0]
        if index==5 and row['external_location_change']:
            reader.data.items[0].batches[0].location='冷藏室下层';reader.data.items[0].batches[0].version+=1
        value={**t,'id':row['id']+f'-t{index+1}','group_id':row['group_id'],'category':row['category'],'profile':row['profile']}
        with rec.case(**{**CURRENT.get(),'question_id':value['id']}):record,_=await question(value,b,rec,offline,current,previous)
        saved=persist(current,value,record,index)
        if saved:previous=saved
        output.append(record)
        if record['status']=='BLOCKED':break
    return output

def verify():
    source=json.loads((ROUND/'evidence/source.json').read_text(encoding='utf-8'))
    for row in source['snapshot']:
        if sha(ROUND/'.snapshot'/row['path'])!=row['sha256']:raise RuntimeError('FROZEN_SOURCE_CHANGED')
    for name,data in json.loads((ROUND/'datasets/manifest.json').read_text(encoding='utf-8'))['sets'].items():
        if sha(ROUND/'datasets'/f'{name}.jsonl')!=data['sha256']:raise RuntimeError('FROZEN_DATA_CHANGED')

async def main(args):
    verify();offline=args.mode=='offline'
    if not offline and not os.getenv('DEEPSEEK_API_KEY'):raise SystemExit('MODEL_NOT_CONFIGURED; no calls made')
    if args.mode=='formal' and list((ROUND/'runs').glob('formal-*/started.json')):raise SystemExit('FORMAL_ALREADY_STARTED; do not repeat paid batch silently')
    if args.mode=='formal':
        smoke=sorted((ROUND/'runs').glob('smoke-*/complete.json'))
        if not smoke or not json.loads(smoke[-1].read_text(encoding='utf-8'))['infrastructure_ok']:raise SystemExit('SMOKE_NOT_READY')
    b,policy=budget() if not offline else (None,None)
    target=ROUND/'runs'/f"{args.mode}-{time.strftime('%Y%m%dT%H%M%S')}";target.mkdir(parents=True,exist_ok=False)
    rec=Recorder(target,'live' if not offline else 'offline')
    original_next=engine.next_step;stepcounts=collections.Counter()
    async def observed_next(owner,payload,seconds):
        key=CURRENT.get().get('question_id');stepcounts[key]+=1;metadata={**CURRENT.get(),'decision_step':stepcounts[key]}
        with rec.case(**metadata),rec.stage('autonomous_decision'):
            return await original_next(owner,payload,seconds)
    write(target/'started.json',{'source':HEAD,'mode':args.mode,'policy':policy,'budget_before':b.summary() if b else None,
        'adapter_sha256':{p.name:sha(p) for p in (ROUND/'scripts').glob('*.py')},'dataset_sha256':sha(ROUND/'datasets/manifest.json')})
    groups=[]
    if args.mode=='smoke':groups=[('连通检查',0,'single',[readrows('single')[i] for i in [0,15,25,40,60,95]])]
    else:
        for r in ([0] if offline else [1,2,3]):groups += [('单轮',r,'single',readrows('single')),('六轮场景',r,'multi',readrows('multi'))]
    records=[];stop=None
    engine.next_step=observed_next
    try:
        with network_guard(not offline),rec.install():
            for batch,repeat,kind,data in groups:
                for row in data:
                    with rec.case(batch=batch,repeat=repeat,scenario_id=row['id'],question_id=row['id']):
                        if kind=='multi':values=await scenario(row,b,rec,offline)
                        else:
                            one,_=await question(row,b,rec,offline);values=[one]
                    records.extend(values)
                    print(json.dumps({'batch':batch,'repeat':repeat,'id':row['id'],'pass':sum(v['status']=='PASS' for v in values),'questions':len(values),'actual_http':len(rec.requests)},ensure_ascii=False),flush=True)
                    if any(r['status']=='BLOCKED' for r in values):raise RuntimeError('BUDGET_OR_CONFIG_STOP')
                    if any(r['http_status'] in {401,402,403} for r in rec.requests[-8:]):raise RuntimeError('PROVIDER_AUTH_OR_BALANCE_STOP')
    except (RuntimeError,EngineError) as e:stop=getattr(e,'code',str(e))
    finally:engine.next_step=original_next
    result={'mode':args.mode,'complete':stop is None,'stop_reason':stop,'questions':len(records),'counts':dict(collections.Counter(r['status'] for r in records)),
        'actual_http_calls':len(rec.requests),'budget_after':b.summary() if b else None,'new_conservative_cost_cny':float(Decimal(str(b.summary()['conservative_cost_cny']))-Decimal(policy['initial_cny'])) if b else 0,
        'infrastructure_ok':bool(rec.requests) and all(r['http_status']==200 and r['complete_body'] for r in rec.requests) and stop is None,
        'provenance':'offline_oracle_not_model' if offline else 'real_deepseek','human_review_status':'pending','app_joint_acceptance':False}
    write(target/'complete.json',result);print(json.dumps(result,ensure_ascii=False));return 1 if stop else 0
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['offline','smoke','formal']);sys.exit(asyncio.run(main(p.parse_args())))
