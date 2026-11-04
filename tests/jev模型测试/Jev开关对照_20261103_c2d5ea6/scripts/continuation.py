"""Complete only missing/budget-blocked work under user's updated authorization."""
import asyncio,collections,json,os,time
from decimal import Decimal
import ab
from prepare import ROUND,HEAD,sha,write
from budget_pair import Combined,DeepSeekBudget,JevBudget
from telemetry import Recorder,network_guard
from jev.config import Config
from jev.providers import LiveProvider
from jev.runtime import Router

class AuthorizedCombined(Combined):
    # Original ledger/policy remains intact. New authorization removes the old stop.
    limit=Decimal('Infinity')
    def summary(self):
        result=super().summary();result.update(original_limit_cny='10',limit_cny=None,active_authorization='2026-11-04 user: fees do not matter; complete planned experiment',cost_stop_enabled=False);return result

async def main():
    ab.frozen()
    if not all(os.getenv(k) for k in ['DEEPSEEK_API_KEY','TYPESAFE_API_KEY']):raise SystemExit('MISSING_LOCAL_CREDENTIALS')
    if list((ROUND/'runs').glob('continuation-*/started.json')):raise SystemExit('CONTINUATION_ALREADY_STARTED')
    original=next((ROUND/'runs').glob('formal-*/complete.json'))
    ended=json.loads(original.read_text(encoding='utf-8'))
    if ended['stop_reason']!='BUDGET_OR_CONFIG_STOP':raise SystemExit('Original run did not stop at budget; inspect before continuing')
    completed={}
    for line in (original.parent/'questions.jsonl').read_text(encoding='utf-8').splitlines():
        q=json.loads(line)
        if q['status'] in {'PASS','FAIL'}:completed[(q['mode'],q['repeat'],q['id'])]=q
    combo=AuthorizedCombined();deep=DeepSeekBudget(combo)
    # Large finite arithmetic sentinel avoids non-standard Infinity JSON in native summary.
    # The finite planned remainder is ~155 questions; this is not a new spending target.
    deep.limit=Decimal('1000000000');jev=JevBudget(combo)
    target=ROUND/'runs'/f'continuation-{time.strftime("%Y%m%dT%H%M%S")}';target.mkdir()
    rec=Recorder(target,'real_provider_authorized_continuation');records=[];stop=None
    write(target/'started.json',{'source':HEAD,'original_run':str(original.parent.relative_to(ROUND)),'authorization':'2026-11-04 user explicitly removed spending concern and prioritized completing experiment','original_completed_quality_executions':len(completed),'fee_ledger_not_reset':True,'budget_before':combo.summary(),'deepseek_before':deep.summary(),'jev_before':jev.summary(),'code_sha256':{p.name:sha(p) for p in (ROUND/'scripts').glob('*.py')},'same_dataset_and_gold':True,'no_rerun_of_completed_pass_or_fail':True})
    prior_next=ab.engine.next_step;counts=collections.Counter()
    async def observed(owner,payload,seconds):
        key=tuple(ab.CURRENT.get().get(k) for k in ['mode','repeat','question_id']);counts[key]+=1
        with rec.case(**{**ab.CURRENT.get(),'decision_step':counts[key]}),rec.stage('deepseek_autonomous'):
            return await prior_next(owner,payload,seconds)
    ab.engine.next_step=observed
    try:
        with network_guard(True),rec.install():
            for repeat in [1,2]:
                for i,(kind,row) in enumerate(ab.units()):
                    modes=['off','assist'] if (i+repeat)%2==0 else ['assist','off']
                    turns=row['turns'] if kind=='multi' else [row]
                    ids=[row['id']+f'-t{n+1}' if kind=='multi' else row['id'] for n in range(len(turns))]
                    for position,mode in enumerate(modes):
                        if all((mode,repeat,ident) in completed for ident in ids):continue
                        semantic=ab.old.DeepSeekEngine(deep)
                        provider=LiveProvider(Config.from_environment(),budget=jev,recordings=ROUND/'.runtime/jev-recordings')
                        app,current=ab.application(ab.state(row['profile'],semantic),mode,Router(provider) if mode=='assist' else None)
                        previous=None
                        for n,t in enumerate(turns):
                            value={**t,'id':ids[n],'group_id':row['group_id'],'category':row['category'],'profile':row['profile']}
                            owner,ctx,reader,clock,archive=current;clock[0]=ab.old.NOW+ab.timedelta(seconds=n*15);ctx.trusted_now=clock[0];ctx.revision=n
                            for task in ctx.tasks:task.checked_at=clock[0]
                            key=(mode,repeat,ids[n])
                            if key in completed:
                                old=completed[key];saved=ab.old.persist(current,value,old,n)
                                if saved:previous=saved
                                rec.append('local_state_replay',{'mode':mode,'repeat':repeat,'id':ids[n],'model_requests':0,'original_status':old['status']})
                                continue
                            with rec.case(mode=mode,repeat=repeat,order=position+1,scenario_id=row['id'],question_id=ids[n],stratum='主功能集' if kind!='jev_special' else 'Jev专项',turn=n+1):
                                record=await ab.question(value,current,app,rec,previous)
                                saved=ab.old.persist(current,value,record,n)
                                if saved:previous=saved
                            records.append(record);completed[key]=record
                            print(json.dumps({'phase':'continuation','repeat':repeat,'mode':mode,'id':ids[n],'status':record['status'],'wire_total':len(rec.requests)},ensure_ascii=False),flush=True)
                            if record['status']=='BLOCKED':raise RuntimeError('NATIVE_PROVIDER_OR_CONFIG_STOP')
                            if any(w['http_status'] in {401,402,403} for w in rec.requests[-8:]):raise RuntimeError('PROVIDER_AUTH_OR_BALANCE_STOP')
    except Exception as exc:
        stop=getattr(exc,'code',str(exc));rec.append('infrastructure_errors',{'type':type(exc).__name__,'code':stop})
    finally:ab.engine.next_step=prior_next
    result={'phase':'continuation','complete':stop is None,'stop_reason':stop,'questions':len(records),'status_counts':dict(collections.Counter(q['status'] for q in records)),'actual_http_calls':len(rec.requests),'all_planned_quality_executions':sum(q['status'] in {'PASS','FAIL'} for q in completed.values()),'budget_after':combo.summary(),'deepseek_after':deep.summary(),'jev_after':jev.summary(),'previous_budget_records_unchanged':True,'model_failure_retries':0,'human_review_status':'pending','app_acceptance':False}
    write(target/'complete.json',result);print(json.dumps(result,ensure_ascii=False));return 0 if stop is None else 1
if __name__=='__main__':raise SystemExit(asyncio.run(main()))
