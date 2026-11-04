"""Paired local authenticated HTTP evaluation using the actual P8.7 app factory."""
import argparse,asyncio,collections,inspect,json,os,sys,time
from datetime import timedelta
from pathlib import Path
from decimal import Decimal
from prepare import ROUND,HEAD,sha,write
sys.path.insert(0,str(ROUND/'.snapshot/agent'))
import httpx
import legacy as old
from telemetry import Recorder,CURRENT,network_guard
from conversation.autonomous.app import create_app
from conversation.autonomous import engine
from conversation.p85.schemas import P85Archive
from jev.config import Config
from jev.providers import LiveProvider,MockProvider
from jev.runtime import Router
from budget_pair import Combined,DeepSeekBudget,JevBudget

TOKEN='garin-isolated-synthetic-service-token'
HEADERS={'Authorization':'Bearer '+TOKEN,'X-User-ID':old.SCOPE.user_id,'X-Household-ID':old.SCOPE.household_id}

def state(profile,semantic):
    value=old.state('none' if profile=='empty_absent' else profile,semantic)
    owner,ctx,reader,clock,archive=value
    if profile=='empty_absent':reader.data.items=[];reader.data.pending=[]
    if profile=='archive':
        reference=ctx.reference.model_copy(update={'issued_at':old.NOW-timedelta(minutes=4),'expires_at':old.NOW+timedelta(minutes=11)})
        ctx.reference=reference
        for episode in archive:
            if episode.reference:episode.reference=reference.model_copy(deep=True)
    P85Archive(scope=old.SCOPE,conversation_id=ctx.conversation_id,revision=ctx.revision,episodes=archive)
    return value

def application(value,mode,router=None):
    original,ctx,reader,clock,archive=value
    os.environ['AI_SERVICE_TOKEN']=TOKEN
    app=create_app(jev_mode=mode,jev_router=router,engine=original.engine,reader=reader,now=lambda:clock[0])
    endpoint=next(route.endpoint for route in app.routes if getattr(route,'path',None)=='/agent/dialogue/run')
    owner=inspect.getclosurevars(endpoint).nonlocals['manager']
    assert (owner.jev_router is not None)==(mode=='assist'),'SWITCH_NOT_EFFECTIVE'
    return app,(owner,ctx,reader,clock,archive)

def frozen():
    source=json.loads((ROUND/'evidence/source.json').read_text(encoding='utf-8'))
    for row in source['snapshot']:
        if sha(ROUND/'.snapshot'/row['path'])!=row['sha256']:raise RuntimeError('FROZEN_SOURCE_CHANGED')
    for name,data in json.loads((ROUND/'datasets/manifest.json').read_text(encoding='utf-8'))['sets'].items():
        if sha(ROUND/'datasets'/f'{name}.jsonl')!=data['sha256']:raise RuntimeError('FROZEN_DATA_CHANGED')

async def question(row,value,app,rec,previous=None):
    owner,ctx,reader,clock,archive=value
    before=reader.data.model_dump(mode='json');index=len(rec.requests);start=time.perf_counter();out={};error=None;http_status=None
    payload={'text':row['text'],'request_id':row['id'],'context':ctx.model_dump(mode='json'),'archive':P85Archive(scope=old.SCOPE,conversation_id=ctx.conversation_id,revision=ctx.revision,episodes=archive).model_dump(mode='json'),'remaining_seconds':58}
    rec.append('inputs',{**CURRENT.get(),'payload':payload,'inventory':before,'initial_state_sha256':__import__('hashlib').sha256(json.dumps({'context':payload['context'],'archive':payload['archive'],'inventory':before},sort_keys=True,ensure_ascii=False).encode()).hexdigest()})
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://garin-local',headers=HEADERS,timeout=61) as client:
            async with asyncio.timeout(61):
                response=await client.post('/agent/dialogue/run',json=payload)
                http_status=response.status_code;out=response.json()
                if response.status_code!=200:error='LOCAL_HTTP_'+str(response.status_code)
    except Exception as exc:error=getattr(exc,'code',type(exc).__name__)
    unchanged=reader.data.model_dump(mode='json')==before
    checks=old.score(row['expected'],out,unchanged,previous)
    if http_status==422 and row['expected'].get('no_private_read'):
        checks={'cross_scope_http_422':True,'no_reads_or_model_calls':len(rec.requests)==index and getattr(reader,'reads',0)==0,'no_inventory_write':unchanged};error=None
    elif error:checks['no_exception']=False
    status='PASS' if all(checks.values()) else 'FAIL'
    wire=rec.requests[index:];providers=collections.Counter(w['provider'] for w in wire)
    audits=[s['jev'] for s in out.get('trace',[]) if s.get('jev')]
    if out.get('error_code') in {'BUDGET_EXCEEDED','MODEL_NOT_CONFIGURED','PRICING_NOT_VERIFIED'} or any(a.get('reason')=='BUDGET_EXCEEDED' for a in audits):status='BLOCKED'
    record={**CURRENT.get(),'id':row['id'],'group_id':row['group_id'],'category':row['category'],'text':row['text'],'expected':row['expected'],'checks':checks,'status':status,'output':out,'error_code':error,'local_http_status':http_status,'question_ms':(time.perf_counter()-start)*1000,'actual_http_calls':len(wire),'deepseek_http_calls':providers['deepseek'],'jev_http_calls':providers['jev'],'declared_model_invocations':out.get('model_calls'),'inventory_unchanged':unchanged,'jev_audit':audits,'wire_ids':[w['wire_id'] for w in wire],'human_review_status':'pending'}
    rec.append('questions',record)
    return record

def units():
    data=[]
    for kind in ['single','multi','jev_special']:
        for line in (ROUND/'datasets'/f'{kind}.jsonl').read_text(encoding='utf-8').splitlines():data.append((kind,json.loads(line)))
    # Distribute functional groups before Jev diagnostic stratum; both repeats have identical order.
    groups=list(dict.fromkeys(row['group_id'] for _,row in data))
    return [(kind,row) for group in groups for kind,row in data if row['group_id']==group]

async def unit(kind,row,mode,repeat,order,rec,deep_budget,jev_budget,offline=False):
    semantic=old.Oracle() if offline else old.DeepSeekEngine(deep_budget)
    provider=MockProvider() if offline else LiveProvider(Config.from_environment(),budget=jev_budget,recordings=ROUND/'.runtime/jev-recordings')
    app,value=application(state(row['profile'],semantic),mode,Router(provider) if mode=='assist' else None)
    result=[];previous=None
    turns=row['turns'] if kind=='multi' else [row]
    for index,t in enumerate(turns):
        current={**t,'id':row['id']+f'-t{index+1}' if kind=='multi' else row['id'],'group_id':row['group_id'],'category':row['category'],'profile':row['profile']}
        owner,ctx,reader,clock,archive=value
        clock[0]=old.NOW+timedelta(seconds=index*15);ctx.trusted_now=clock[0];ctx.revision=index
        for task in ctx.tasks:task.checked_at=clock[0]
        if offline:
            semantic.decision=old.oracle(current) if kind!='jev_special' else old.Decision(action='ask',clarification='object')
        with rec.case(mode=mode,repeat=repeat,order=order,scenario_id=row['id'],question_id=current['id'],stratum='主功能集' if kind!='jev_special' else 'Jev专项',turn=index+1):
            record=await question(current,value,app,rec,previous)
            saved=old.persist(value,current,record,index)
            if saved:previous=saved
        result.append(record)
        if record['status']=='BLOCKED':break
    return result

async def main(args):
    frozen();offline=args.phase=='preflight'
    if not offline:
        missing=[k for k in ['DEEPSEEK_API_KEY','TYPESAFE_API_KEY'] if not os.getenv(k)]
        if missing:raise SystemExit('MISSING_LOCAL_CREDENTIALS: '+','.join(missing)+'; no requests made')
        if args.phase=='formal':
            if list((ROUND/'runs').glob('formal-*/started.json')):raise SystemExit('FORMAL_ALREADY_STARTED; do not silently rerun')
            smokes=list((ROUND/'runs').glob('smoke-*/complete.json'))
            if not any(json.loads(p.read_text(encoding='utf-8')).get('infrastructure_ok') or (p.parent/'validated.json').is_file() and json.loads((p.parent/'validated.json').read_text(encoding='utf-8')).get('ready') for p in smokes):raise SystemExit('SMOKE_NOT_READY')
    combo=Combined() if not offline else None
    deep=DeepSeekBudget(combo) if combo else None;jev=JevBudget(combo) if combo else None
    target=ROUND/'runs'/f'{args.phase}-{time.strftime("%Y%m%dT%H%M%S")}';target.mkdir(parents=True)
    rec=Recorder(target,'offline_mock_not_accuracy' if offline else 'real_provider');records=[];stop=None
    work=units()
    if args.phase=='smoke':
        work=[work[i] for i in [0,8,24]]+[(k,r) for k,r in work if r['id'] in {'JEV-01','JEV-04','JEV-17'}]
    write(target/'started.json',{'source':HEAD,'phase':args.phase,'budget_before':combo.summary() if combo else None,'deepseek_before':deep.summary() if deep else None,'jev_before':jev.summary() if jev else None,'adapter_hashes':{p.name:sha(p) for p in (ROUND/'scripts').glob('*.py')},'dataset_manifest_sha256':sha(ROUND/'datasets/manifest.json'),'modes':['off','assist'],'locale':'zh-CN','server_access':False})
    original=engine.next_step;counts=collections.Counter()
    async def observed(owner,payload,seconds):
        key=tuple(CURRENT.get().get(k) for k in ['mode','repeat','question_id']);counts[key]+=1
        with rec.case(**{**CURRENT.get(),'decision_step':counts[key]}),rec.stage('deepseek_autonomous'):
            return await original(owner,payload,seconds)
    engine.next_step=observed
    try:
        with network_guard(not offline),rec.install():
            for repeat in ([0] if offline else [1] if args.phase=='smoke' else [1,2]):
                for i,(kind,row) in enumerate(work):
                    order=['off','assist'] if (i+repeat)%2==0 else ['assist','off']
                    for position,mode in enumerate(order):
                        values=await unit(kind,row,mode,repeat,position+1,rec,deep,jev,offline)
                        records.extend(values)
                        print(json.dumps({'phase':args.phase,'repeat':repeat,'mode':mode,'id':row['id'],'status':dict(collections.Counter(v['status'] for v in values)),'wire_total':len(rec.requests)},ensure_ascii=False),flush=True)
                        if any(v['status']=='BLOCKED' for v in values):raise RuntimeError('BUDGET_OR_CONFIG_STOP')
                        if any(w['http_status'] in {401,402,403} for w in rec.requests[-8:]):raise RuntimeError('PROVIDER_AUTH_OR_BALANCE_STOP')
                        # Missing/invalid Jev is never silently treated as a valid enabled run.
                        if not offline and any(a.get('reason')=='MODEL_NOT_CONFIGURED' for v in values for a in v['jev_audit']):raise RuntimeError('JEV_NOT_CONFIGURED')
    except Exception as exc:
        stop=getattr(exc,'code',str(exc));rec.append('infrastructure_errors',{'error_type':type(exc).__name__,'code':stop})
    finally:engine.next_step=original
    jev_success=[w for w in rec.requests if w['provider']=='jev' and w['http_status']==200 and w['returned_model']=='jev-1.13.0' and w.get('usage')]
    infrastructure_ok=not offline and stop is None and bool(jev_success) and any(w['provider']=='deepseek' and w['http_status']==200 and w.get('usage') for w in rec.requests) and not any(w['http_status'] in {401,402,403} for w in rec.requests)
    summary={'phase':args.phase,'complete':stop is None,'stop_reason':stop,'questions':len(records),'status_counts':dict(collections.Counter(v['status'] for v in records)),'actual_http_calls':len(rec.requests),'real_jev_successes':len(jev_success),'infrastructure_ok':infrastructure_ok,'offline_is_not_accuracy':offline,'budget_after':combo.summary() if combo else None,'deepseek_after':deep.summary() if deep else None,'jev_after':jev.summary() if jev else None,'human_review_status':'pending','app_acceptance':False}
    write(target/'complete.json',summary);print(json.dumps(summary,ensure_ascii=False));return 0 if stop is None else 1
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['preflight','smoke','formal']);sys.exit(asyncio.run(main(parser.parse_args())))
