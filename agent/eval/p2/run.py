"""python -m eval.p2.run --engine rules|deepseek --split dev|test [--limit N]."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from p0.schemas import Scope
from p2.engines import DeepSeekEngine, PROMPT_VERSION, RuleEngine
from p2.knowledge import RuleCatalog
from p2.manager import Manager
from p2.schemas import RiskMessage
from eval.p1.run import percentile
from .fixtures import FixtureReader

ROOT=Path(__file__).resolve().parent


def rules_for(mode):
    catalog=RuleCatalog.load()
    if mode=='unreviewed':
        for rule in catalog.data.rules:
            rule.reviewed=False
    elif mode=='disabled':
        for rule in catalog.data.rules:
            rule.enabled=False
    elif mode=='conflict':
        duplicate=catalog.data.rules[0].model_copy(deep=True,update={'version':'2'})
        catalog.data.rules.append(duplicate)
    return RuleCatalog(catalog.data)


async def run(args):
    path=ROOT/'samples.jsonl'
    rows_in=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    samples=[row for row in rows_in if row['split']==args.split]
    if args.limit: samples=samples[:args.limit]
    engine=RuleEngine() if args.engine=='rules' else DeepSeekEngine()
    rows,stopped=[],False
    for sample in samples:
        if stopped:
            rows.append({'id':sample['id'],'attempted':False,'error_code':'NOT_ATTEMPTED'})
            continue
        if args.engine=='deepseek': engine.last_usage,engine.last_model={},None
        reader=FixtureReader(sample['batches'])
        before=reader.snapshot()
        catalog=rules_for(sample['rules_mode'])
        manager=Manager(engine,reader,catalog,now=lambda:datetime.fromisoformat(sample['now']))
        start=time.perf_counter()
        result=await manager.handle(RiskMessage(text=sample['text'],request_id=sample['id']),Scope(**sample['scope']))
        latency=time.perf_counter()-start
        expected=sample['expected']
        expected_risks=expected['risks']
        risk_ok=len(result.risks)==len(expected_risks)
        if risk_ok:
            for actual,wanted in zip(result.risks,expected_risks):
                risk_ok &= actual.batch_id==wanted['batch_id'] and actual.level==wanted['level']
                risk_ok &= set(actual.missing_information)==set(wanted['missing'])
                risk_ok &= set(wanted['required_reasons']).issubset(actual.reason_codes)
                risk_ok &= actual.safety_guaranteed is False
                risk_ok &= all(e.source is not None and e.rule_version for e in actual.evidence if e.rule_id)
        checks={'intent_ok':result.intent==expected['intent'],'status_ok':result.status==expected['status'],
            'risk_ok':bool(risk_ok),'draft_action_ok':getattr(result.draft,'action',None)==expected['draft_action'],
            'no_writes':reader.snapshot()==before}
        rows.append({'id':sample['id'],'text':sample['text'],'attempted':True,'expected':expected,
            'result':result.model_dump(mode='json'),'checks':checks,'latency_seconds':latency,
            'usage':getattr(engine,'last_usage',{}),'provider_model':getattr(engine,'last_model',None)})
        print(f"{sample['id']}: {result.status} all_checks={all(checks.values())} {latency:.3f}s code={result.error_code or '-'}",flush=True)
        if result.error_code in {'MODEL_HTTP_401','MODEL_HTTP_402','MODEL_HTTP_404','MODEL_NOT_CONFIGURED','PRICING_NOT_VERIFIED','BUDGET_EXCEEDED'}:
            stopped=True
        if len(rows)>=3 and all(r.get('result',{}).get('status')=='error' for r in rows[-3:]): stopped=True
    n=len(samples);attempted=[r for r in rows if r['attempted']]
    risk_rows=[r for r in attempted if r['expected']['intent']=='QUERY_RISK']
    clarification_ids={s['id'] for s in samples if s['expected']['status']=='needs_clarification'}
    latencies=[r['latency_seconds'] for r in attempted]
    metrics={'intent_accuracy':sum(r['checks']['intent_ok'] for r in attempted)/n,
        'status_accuracy':sum(r['checks']['status_ok'] for r in attempted)/n,
        'risk_output_accuracy':sum(r['checks']['risk_ok'] for r in risk_rows)/len(risk_rows) if risk_rows else None,
        'all_checks_accuracy':sum(all(r['checks'].values()) for r in attempted)/n,
        'clarification_recall':sum(r['result']['status']=='needs_clarification' for r in attempted if r['id'] in clarification_ids)/len(clarification_ids) if clarification_ids else None,
        'inventory_mutations':sum(not r['checks']['no_writes'] for r in attempted),
        'failure_rate':(n-len(attempted)+sum(r['result']['status']=='error' for r in attempted))/n,
        'p50_seconds':percentile(latencies,.5),'p95_seconds':percentile(latencies,.95)}
    passed=args.split=='test' and n==60 and len(attempted)==n and metrics['all_checks_accuracy']==1 and metrics['inventory_mutations']==0 and metrics['failure_rate']==0 and metrics['p95_seconds']<=10
    output={'metadata':{'release_version':'V1-P2','dataset_version':'p2-1','dataset_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'engine':args.engine,'split':args.split,'prompt_version':PROMPT_VERSION,'run_at':datetime.now(timezone.utc).isoformat(),
        'requested_count':n,'attempted_count':len(attempted),'source':'ai_constructed','human_reviewed':False,
        'ruleset_sha256':RuleCatalog.load().sha256,'source_expert_reviewed':False,'formal_backend_verified':False,
        'budget':engine.budget.summary() if args.engine=='deepseek' else None,
        'command':f'python -m eval.p2.run --engine {args.engine} --split {args.split}'+(f' --limit {args.limit}' if args.limit else '')},
        'metrics':metrics,'acceptance_passed':passed,'rows':rows}
    directory=ROOT/'results';directory.mkdir(exist_ok=True)
    target=directory/f"{args.engine}-{args.split}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}.json"
    target.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report':str(target),'metrics':metrics,'acceptance_passed':passed},ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--engine',choices=['rules','deepseek'],required=True)
    parser.add_argument('--split',choices=['dev','test'],required=True)
    parser.add_argument('--limit',type=int)
    args=parser.parse_args()
    if args.limit is not None and args.limit<=0: parser.error('limit must be positive')
    asyncio.run(run(args))
