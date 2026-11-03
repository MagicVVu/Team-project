"""Separate paid correction of invalid test-fixture timestamps; gold is unchanged."""
import argparse,asyncio,collections,json,os,time
from datetime import timedelta
from decimal import Decimal
import live
from prepare import ROUND,HEAD,write,sha
from telemetry import Recorder,CURRENT,network_guard
original_state=live.state
def corrected_state(profile,semantic):
 current=original_state(profile,semantic)
 if profile=='archive':
  owner,ctx,reader,clock,archive=current
  ref=ctx.reference.model_copy(update={'issued_at':live.NOW-timedelta(minutes=4),'expires_at':live.NOW+timedelta(minutes=11)})
  ctx.reference=ref
  for episode in archive:
   if episode.reference:episode.reference=ref.model_copy(deep=True)
  # Validate the complete envelope before any paid attempt.
  live.P85Archive(scope=live.SCOPE,conversation_id=ctx.conversation_id,revision=ctx.revision,episodes=archive)
 return current
async def main():
 live.verify()
 originals=list((ROUND/'runs').glob('formal-*/complete.json'))
 if len(originals)!=1 or not json.loads(originals[0].read_text(encoding='utf-8'))['complete']:raise RuntimeError('ORIGINAL_FORMAL_NOT_COMPLETED')
 if list((ROUND/'runs').glob('archive-recheck-*/started.json')):raise RuntimeError('ARCHIVE_RECHECK_ALREADY_STARTED')
 if not os.getenv('DEEPSEEK_API_KEY'):raise RuntimeError('MODEL_NOT_CONFIGURED')
 b,pol=live.budget();target=ROUND/'runs'/f'archive-recheck-{time.strftime("%Y%m%dT%H%M%S")}';target.mkdir()
 rec=Recorder(target,'real_deepseek_corrected_fixture');before=b.summary()
 write(target/'started.json',{'source':HEAD,'policy':pol,'budget_before':before,'reason':'Archive source reference was issued at NOW, later than its episode created NOW-4m; fix only fixture provenance, preserve all gold and original records.','correction':'issued_at=NOW-4m, expires_at=NOW+11m; still original 15-minute lifetime','script_sha256':sha(__import__('pathlib').Path(__file__)),'dataset_manifest_sha256':sha(ROUND/'datasets/manifest.json')})
 live.state=corrected_state;original_next=live.engine.next_step;steps=collections.Counter()
 async def observed(owner,payload,seconds):
  key=(CURRENT.get().get('repeat'),CURRENT.get().get('question_id'));steps[key]+=1
  with rec.case(**{**CURRENT.get(),'decision_step':steps[key]}),rec.stage('autonomous_decision'):return await original_next(owner,payload,seconds)
 live.engine.next_step=observed;records=[];stop=None
 try:
  with network_guard(True),rec.install():
   for repeat in [1,2]:
    for kind in ['single','multi']:
     for row in live.readrows(kind):
      if row['profile']!='archive':continue
      with rec.case(batch='夹具修正补测',repeat=repeat,scenario_id=row['id'],question_id=row['id']):
       values=await live.scenario(row,b,rec,False) if kind=='multi' else [(await live.question(row,b,rec,False))[0]]
      records.extend(values);print(json.dumps({'id':row['id'],'repeat':repeat,'questions':len(values),'counts':dict(collections.Counter(q['status'] for q in values)),'actual_http':len(rec.requests)},ensure_ascii=False),flush=True)
      if any(q['status']=='BLOCKED' for q in values):raise RuntimeError('BUDGET_OR_CONFIG_STOP')
      if any(r['http_status'] in {401,402,403} for r in rec.requests[-8:]):raise RuntimeError('PROVIDER_AUTH_OR_BALANCE_STOP')
 except RuntimeError as e:stop=str(e)
 finally:live.state=original_state;live.engine.next_step=original_next
 after=b.summary();write(target/'complete.json',{'mode':'archive_fixture_recheck','complete':stop is None,'stop_reason':stop,'questions':len(records),'counts':dict(collections.Counter(q['status'] for q in records)),'actual_http_calls':len(rec.requests),'budget_after':after,'new_conservative_cost_cny':float(Decimal(str(after['conservative_cost_cny']))-Decimal(pol['initial_cny'])),'same_frozen_expectations':True,'original_failures_preserved':True})
 print(json.dumps({'complete':stop is None,'questions':len(records),'calls':len(rec.requests),'round_conservative':float(Decimal(str(after['conservative_cost_cny']))-Decimal(pol['initial_cny']))},ensure_ascii=False))
if __name__=='__main__':asyncio.run(main())
