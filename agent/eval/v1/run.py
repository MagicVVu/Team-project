import argparse
import asyncio
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import time
from eval.p1.run import percentile
from p0.budget import Budget
from v1.engines import DeepSeekEngine, RuleEngine, PROMPT_VERSION
from v1.manager import Manager
from v1.schemas import Message, ClarificationRequest
from .fixtures import FixtureReader, NOW, SCOPE, synthetic_reviewed_catalog

ROOT=Path(__file__).resolve().parent

class Counted:
    def __init__(self,engine): self.engine,self.calls=engine,0
    async def extract(self,text):
        self.calls+=1
        return await self.engine.extract(text)

def ratio(rows, key):
    return sum(r["checks"][key] for r in rows)/len(rows) if rows else None

async def evaluate(args):
    path=ROOT/"samples.jsonl"
    all_samples=[json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    samples=[r for r in all_samples if r["split"]==args.split]
    if args.limit: samples=samples[:args.limit]
    engine=DeepSeekEngine() if args.engine=="deepseek" else RuleEngine()
    before=engine.budget.summary() if args.engine=="deepseek" else None
    from integration.source_manifest import manifest
    runtime_hashes=manifest()["files"]
    rows=[]
    for sample in samples:
        counted=Counted(engine)
        reader=FixtureReader(**sample["fixture"])
        original=reader.data.model_dump_json()
        manager=Manager(counted,reader,synthetic_reviewed_catalog(),now=lambda:NOW)
        start=time.perf_counter()
        result=await manager.handle(Message(text=sample["text"],request_id=sample["id"]),SCOPE)
        expected=sample["expected"]
        checks={"intent":result.intent==expected["intent"],"status":result.status==expected["status"],
            "original_text":result.original_text==sample["text"],"single_extraction":counted.calls<=1,
            "no_writes":reader.data.model_dump_json()==original and not result.inventory_writes and not result.shopping_writes,
            "draft":(result.draft is not None)==(expected["status"]=="needs_confirmation"),
            "clarification_fields":set(expected.get("missing_fields",[]))<=set(result.missing_fields)}
        if result.draft:
            checks["draft"] &= result.draft.name==sample["fixture"]["name"] and result.draft.unit==sample["fixture"]["unit"] if hasattr(result.draft,"unit") else result.draft.name==sample["fixture"]["name"]
            for field,value in expected.get("draft",{}).items():
                checks["draft"] &= str(getattr(result.draft,field))==value
        # Resume with explicit fixture-labelled answers, not an AI-chosen default.
        resumed=None
        if result.status=="needs_clarification" and result.clarification and result.clarification.allowed_fields:
            permitted=result.clarification.allowed_fields
            labelled={"name":sample["fixture"]["name"],"quantity":"1","unit":sample["fixture"]["unit"],
                "opened_at":"2026-10-15","batch_id":"b1","location":"餐边柜"}
            answers={f:labelled[f] for f in permitted if f in labelled}
            if answers:
                calls=counted.calls
                resumed=await manager.clarify(ClarificationRequest(context=result.clarification,
                    revision=result.clarification.revision,answers=answers),SCOPE)
                checks["continuation_no_model"]=counted.calls==calls
                checks["continuation_text"]=resumed.original_text==sample["text"]
                checks["continuation_no_error"]=resumed.status!="error"
                checks["no_writes"] &= reader.data.model_dump_json()==original
        rows.append({"id":sample["id"],"checks":checks,"seconds":time.perf_counter()-start,"model_calls":counted.calls,
            "result":result.model_dump(mode="json"),"continuation":resumed.model_dump(mode="json") if resumed else None,
            "usage":getattr(engine,"last_usage",None) if counted.calls else None})
        if len(rows)%12==0: print(json.dumps({"completed":len(rows),"total":len(samples)}),flush=True)
    intents=[r for r,s in zip(rows,samples) if s["expected"]["intent"] is not None]
    clarify=[r for r,s in zip(rows,samples) if s["expected"]["status"]=="needs_clarification"]
    drafts=[r for r,s in zip(rows,samples) if s["expected"]["status"]=="needs_confirmation"]
    metrics={"count":len(rows),"all_checks_passed":sum(all(r["checks"].values()) for r in rows),
        "intent_accuracy":ratio(intents,"intent"),"clarification_recall":ratio(clarify,"status"),
        "draft_field_accuracy":ratio(drafts,"draft"),"draft_count":len(drafts),
        "format_errors":sum(r["result"]["error_code"]=="INVALID_MODEL_OUTPUT" for r in rows),
        "no_write_failures":sum(not r["checks"]["no_writes"] for r in rows),
        "p95_seconds":percentile([r["seconds"] for r in rows],.95)}
    report={"metadata":{"release_version":"V1-P6","prompt_version":PROMPT_VERSION,"policy_version":"v1-completion-1",
        "engine":args.engine,"split":args.split,"run_at":datetime.now(timezone.utc).isoformat(),
        "dataset_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"human_reviewed":False,
        "synthetic_rule_review_fixture":True,"real_audio":False,"formal_backend_verified":False,
        "runtime_hashes":runtime_hashes,"runtime_unchanged":manifest()["files"]==runtime_hashes,
        "budget_before":before,"budget_after":engine.budget.summary() if args.engine=="deepseek" else None},
        "metrics":metrics,"workflow_acceptance_passed":args.split=="test" and len(rows)==96 and metrics["all_checks_passed"]==96 and metrics["p95_seconds"]<=10,
        "rows":rows}
    target=ROOT/"results"/f"{args.engine}-{args.split}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"report":str(target),"metrics":metrics,"accepted":report["workflow_acceptance_passed"]},ensure_ascii=False))

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--engine",choices=["rules","deepseek"],required=True)
    parser.add_argument("--split",choices=["dev","test"],required=True)
    parser.add_argument("--limit",type=int)
    args=parser.parse_args()
    if args.limit is not None and args.limit<=0: parser.error("limit must be positive")
    asyncio.run(evaluate(args))
