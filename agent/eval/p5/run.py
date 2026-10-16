import argparse
import asyncio
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import time

from eval.p1.run import percentile
from eval.p3.fixtures import FixtureReader,NOW,SCOPE
from p2.knowledge import RuleCatalog
from interaction.engines import RuleEngine,DeepSeekEngine,PROMPT_VERSION
from interaction.manager import Manager
from interaction.schemas import InputProvenance,Message,POLICY_VERSION

ROOT=Path(__file__).resolve().parent


class Counted:
    def __init__(self,engine): self.engine,self.calls=engine,0
    async def extract(self,text):
        self.calls+=1
        return await self.engine.extract(text)


async def run(args):
    path=ROOT/"samples.jsonl"
    samples=[json.loads(line) for line in path.read_text(encoding="utf8").splitlines()]
    samples=[r for r in samples if r["split"]==args.split]
    if args.limit: samples=samples[:args.limit]
    engine=DeepSeekEngine() if args.engine=="deepseek" else RuleEngine()
    before_budget=engine.budget.summary() if args.engine=="deepseek" else None
    rows=[]
    for sample in samples:
        if args.engine=="deepseek": engine.last_usage={}
        counted,reader=Counted(engine),FixtureReader()
        before=reader.data.model_dump_json()
        expected=sample["expected"]
        manager=Manager(counted,reader,RuleCatalog.load(),now=lambda:NOW)
        message=Message(text=sample["text"],request_id=sample["id"],input=InputProvenance(source="voice",
            input_session_id=sample["id"],transcript_revision=1,user_confirmed=not expected.get("unreviewed",False)))
        start=time.perf_counter()
        result=await manager.handle(message,SCOPE)
        seconds=time.perf_counter()-start
        checks={"intent_ok":result.intent==expected["intent"],"status_ok":result.status==expected["status"],
            "no_writes":reader.data.model_dump_json()==before,"single_extraction":counted.calls<=1,
            "final_text_preserved":result.original_text==sample["text"],
            "draft_ok":(result.draft is not None)==(expected["status"]=="needs_confirmation")}
        if result.draft:
            for field in ("action","name","quantity"):
                if field in expected: checks["draft_ok"] &= str(getattr(result.draft,field))==expected[field]
        if expected["intent"] is None: checks["guard_no_model"]=counted.calls==0
        rows.append({"id":sample["id"],"checks":checks,"latency_seconds":seconds,"model_calls":counted.calls,
                     "result":result.model_dump(mode="json"),"usage":getattr(engine,"last_usage",None)})
        if len(rows)%10==0: print(json.dumps({"completed":len(rows),"total":len(samples)}),flush=True)
    eligible=[r for r,s in zip(rows,samples) if s["expected"]["intent"] is not None]
    clarify=[r for r,s in zip(rows,samples) if s["expected"]["status"]=="needs_clarification"]
    drafts=[r for r,s in zip(rows,samples) if s["expected"]["status"]=="needs_confirmation"]
    metrics={"intent_accuracy":sum(r["checks"]["intent_ok"] for r in eligible)/len(eligible),
        "intent_evaluable_count":len(eligible),"status_accuracy":sum(r["checks"]["status_ok"] for r in rows)/len(rows),
        "clarification_recall":sum(r["result"]["status"]=="needs_clarification" for r in clarify)/len(clarify),
        "draft_field_accuracy":sum(r["checks"]["draft_ok"] for r in drafts)/len(drafts),"draft_count":len(drafts),
        "all_checks_accuracy":sum(all(r["checks"].values()) for r in rows)/len(rows),
        "model_calls":sum(r["model_calls"] for r in rows),"inventory_or_shopping_mutations":sum(not r["checks"]["no_writes"] for r in rows),
        "p95_seconds":percentile([r["latency_seconds"] for r in rows],.95)}
    report={"metadata":{"release_version":"V1-P5","input_policy_version":POLICY_VERSION,"prompt_version":PROMPT_VERSION,
        "dataset_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"engine":args.engine,"split":args.split,
        "count":len(rows),"run_at":datetime.now(timezone.utc).isoformat(),"human_reviewed":False,
        "real_audio":False,"formal_backend_verified":False,"provider_budget_before":before_budget,
        "provider_budget_after":engine.budget.summary() if args.engine=="deepseek" else None},
        "metrics":metrics,"workflow_acceptance_passed":args.split=="test" and len(rows)==60 and metrics["all_checks_accuracy"]==1 and metrics["p95_seconds"]<=10,"rows":rows}
    out=ROOT/"results"
    out.mkdir(exist_ok=True)
    target=out/f"{args.engine}-{args.split}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}.json"
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print(json.dumps({"report":str(target),"metrics":metrics,"accepted":report["workflow_acceptance_passed"]},ensure_ascii=False),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--engine",choices=["rules","deepseek"],required=True)
    parser.add_argument("--split",choices=["dev","test"],required=True)
    parser.add_argument("--limit",type=int)
    args=parser.parse_args()
    if args.limit is not None and args.limit<=0: parser.error("limit must be positive")
    asyncio.run(run(args))
