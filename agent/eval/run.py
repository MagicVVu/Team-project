"""python -m eval.run --engine rules|deepseek --split dev|test [--limit N]."""
import argparse
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import time

from p0.deepseek import DeepSeekEngine
from p0.domain import convert
from p0.engines import PROMPT_VERSION, RuleEngine
from p0.manager import Manager
from p0.mock import MockBackend
from p0.schemas import Message, Scope

ROOT = Path(__file__).resolve().parents[1]


def percentile(values, p):
    return sorted(values)[max(0, math.ceil(len(values)*p)-1)] if values else None


async def run(args):
    path = ROOT / "eval/samples.jsonl"
    samples = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    samples = [s for s in samples if s["split"] == args.split]
    if args.limit:
        samples = samples[:args.limit]
    engine = RuleEngine() if args.engine == "rules" else DeepSeekEngine()
    rows, stopped = [], False
    for sample in samples:
        if args.engine == "deepseek":
            engine.last_usage, engine.last_model = {}, None
        store = MockBackend()
        start = time.perf_counter()
        if stopped:
            from p0.schemas import AgentResult
            result = AgentResult(status="error", reply="Not attempted after provider/config failure", trace_id="not-attempted", original_text=sample["text"], error_code="NOT_ATTEMPTED")
            elapsed = None
        else:
            result = await Manager(engine, store).handle(Message(text=sample["text"], request_id=sample["id"]), Scope(**sample["scope"]))
            elapsed = time.perf_counter()-start
        expected = sample["expected"]
        status_ok = result.status == expected["status"]
        intent_ok = result.intent == expected["intent"]
        fields_ok = True
        if expected["status"] == "needs_confirmation":
            fields_ok = result.draft is not None
            if result.draft:
                try:
                    fields = expected["fields"]
                    fields_ok = result.draft.name == fields["name"] and convert(Decimal(fields["quantity"]), fields["unit"], result.draft.unit) == result.draft.quantity
                except Exception:
                    fields_ok = False
        actual_ids = sorted(b.id for b in result.facts or result.candidates)
        if result.draft and result.draft.batch_id:
            actual_ids = [result.draft.batch_id]
        candidates_ok = actual_ids == sorted(expected["candidate_batch_ids"])
        row = {"id":sample["id"],"text":sample["text"],"expected":expected,"result":result.model_dump(mode="json"),
               "latency_seconds":elapsed,"intent_ok":intent_ok,"status_ok":status_ok,"fields_ok":fields_ok,
               "candidates_ok":candidates_ok,"inventory_writes":len(store.state["events"]),
               "usage":getattr(engine,"last_usage",{}) if elapsed is not None else {},
               "provider_model":getattr(engine,"last_model",None)}
        rows.append(row)
        print(f"{sample['id']}: {result.status} intent={result.intent} {elapsed or 0:.3f}s code={result.error_code or '-'}", flush=True)
        if args.engine == "deepseek" and result.error_code in {"MODEL_HTTP_401","MODEL_HTTP_402","MODEL_HTTP_404","MODEL_NOT_CONFIGURED","PRICING_NOT_VERIFIED","BUDGET_EXCEEDED"}:
            stopped = True
        if len(rows) >= 3 and all(r["result"]["status"] == "error" for r in rows[-3:]):
            stopped = True
    n = len(rows)
    clarifications = [r for r in rows if r["expected"]["requires_clarification"]]
    # Provider errors do not count as a successfully handled clarification.
    recall = sum(r["result"]["status"] == "needs_clarification" for r in clarifications)/len(clarifications) if clarifications else None
    safety = [r for r in rows if r["expected"]["status"] in {"needs_clarification","unsupported"}]
    safe = all(r["result"]["status"] in {"needs_clarification","unsupported"} and not r["inventory_writes"] for r in safety)
    latencies = [r["latency_seconds"] for r in rows if r["latency_seconds"] is not None]
    failures = sum(r["result"]["status"] == "error" for r in rows)
    metadata = {"run_at":datetime.now(timezone.utc).isoformat(),"engine":args.engine,"model":getattr(engine,"model",None),
        "split":args.split,"requested_count":n,"attempted_count":len(latencies),"python":platform.python_version(),
        "packages":{p:importlib.metadata.version(p) for p in ["fastapi","pydantic","httpx","pytest"]},
        "prompt_version":PROMPT_VERSION,"dataset_sha256":sha256(path.read_bytes()).hexdigest(),
        "dataset_version":"p0-1","human_reviewed":False,"jev_status":"not_verified",
        "command":f"python -m eval.run --engine {args.engine} --split {args.split}"+(f" --limit {args.limit}" if args.limit else ""),
        "budget":engine.budget.summary() if args.engine=="deepseek" else None}
    metrics = {"intent_accuracy":sum(r["intent_ok"] for r in rows)/n if n else 0,"status_accuracy":sum(r["status_ok"] for r in rows)/n if n else 0,
        "clarification_recall":recall,"field_accuracy_on_write_drafts":sum(r["fields_ok"] for r in rows if r["expected"]["status"]=="needs_confirmation")/max(1,sum(r["expected"]["status"]=="needs_confirmation" for r in rows)),
        "p50_seconds":percentile(latencies,.5),"p95_seconds":percentile(latencies,.95),"failure_rate":failures/n if n else 1,
        "safety_cases_pass":safe,"unconfirmed_writes":sum(r["inventory_writes"] for r in rows)}
    passed = args.split=="test" and n==60 and len(latencies)==60 and metrics["intent_accuracy"]>=.9 and recall is not None and recall>=.95 and safe and failures==0 and metrics["p95_seconds"]<=10 and metrics["field_accuracy_on_write_drafts"]==1
    output = {"metadata":metadata,"metrics":metrics,"acceptance_passed":passed,"rows":rows}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    target = ROOT / f"eval/results/{args.engine}-{args.split}-{stamp}.json"
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"report":str(target),"metrics":metrics,"acceptance_passed":passed},ensure_ascii=False),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine",choices=["rules","deepseek"],required=True)
    parser.add_argument("--split",choices=["dev","test"],required=True)
    parser.add_argument("--limit",type=int)
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("limit must be positive")
    asyncio.run(run(args))
