"""Independent routing + workflow evaluation, with test-only data fixtures."""
import argparse
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import time

from p2.knowledge import RuleCatalog
from p3.engines import RuleEngine, DeepSeekEngine, PROMPT_VERSION
from p3.manager import Manager
from p3.schemas import PlanningMessage
from eval.p1.run import percentile
from .fixtures import NOW, SCOPE, FixtureReader, snapshot

ROOT = Path(__file__).resolve().parent


def data_for(state):
    data = snapshot()
    if state == "ambiguous":
        item = data.items[0].model_copy(deep=True)
        item.item_key = "other-milk"
        item.batches[0].id = "b2"
        for e in item.events:
            e.item_key = item.item_key
            e.id += "-other"
        data.items.append(item)
    elif state == "no_history": data.items[0].events.clear()
    elif state == "covered": data.pending[0].quantity = Decimal(5)
    elif state == "zero": data.items[0].batches[0].quantity = Decimal(0)
    elif state == "pending_unknown": data.pending_complete = False
    return data


async def run(args):
    path = ROOT/"samples.jsonl"
    samples = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    samples = [r for r in samples if r["split"] == args.split]
    if args.limit: samples = samples[:args.limit]
    engine = RuleEngine() if args.engine == "rules" else DeepSeekEngine()
    rows = []
    for sample in samples:
        if args.engine == "deepseek": engine.last_usage = {}
        reader = FixtureReader(data_for(sample["data_state"]))
        before = reader.data.model_dump_json()
        manager = Manager(engine, reader, RuleCatalog.load(), now=lambda:NOW)
        start = time.perf_counter()
        result = await manager.handle(PlanningMessage(text=sample["text"], request_id=sample["id"]), SCOPE)
        elapsed = time.perf_counter()-start
        output = result.model_dump(mode="json")
        checks = {"intent_ok":result.intent == sample["expected"]["intent"],
                  "status_ok":result.status == sample["expected"]["status"],
                  "no_writes":reader.data.model_dump_json() == before,
                  "draft_ok":((result.draft is not None) == (sample["expected"]["status"] == "needs_confirmation")) and
                      (result.draft is None or (result.draft.quantity == 1 and result.draft.name == "牛奶" and result.draft.unit == "盒" and result.planning_basis is not None))}
        rows.append({"id":sample["id"], "checks":checks, "latency_seconds":elapsed, "result":output,
                     "usage":getattr(engine,"last_usage",None)})
        if len(rows) % 10 == 0:
            print(json.dumps({"completed":len(rows), "total":len(samples)},ensure_ascii=False),flush=True)
    n = len(rows)
    clarification = [r for r,s in zip(rows,samples) if s["expected"]["status"] == "needs_clarification"]
    metrics = {"intent_accuracy":sum(r["checks"]["intent_ok"] for r in rows)/n,
        "status_accuracy":sum(r["checks"]["status_ok"] for r in rows)/n,
        "clarification_recall":sum(r["result"]["status"] == "needs_clarification" for r in clarification)/len(clarification) if clarification else None,
        "draft_field_accuracy":sum(r["checks"]["draft_ok"] for r in rows)/n,
        "all_checks_accuracy":sum(all(r["checks"].values()) for r in rows)/n,
        "inventory_or_shopping_mutations":sum(not r["checks"]["no_writes"] for r in rows),
        "p95_seconds":percentile([r["latency_seconds"] for r in rows],.95)}
    report = {"metadata":{"release_version":"V1-P3", "prompt_version":PROMPT_VERSION,
        "dataset_sha256":hashlib.sha256(path.read_bytes()).hexdigest(), "engine":args.engine, "split":args.split,
        "count":n, "run_at":datetime.now(timezone.utc).isoformat(), "human_reviewed":False,
        "data_source":"synthetic_fixtures", "formal_backend_verified":False, "real_forecast_efficacy_verified":False,
        "budget":engine.budget.summary() if args.engine == "deepseek" else None}, "metrics":metrics,
        "routing_workflow_acceptance_passed":args.split == "test" and n == 60 and metrics["all_checks_accuracy"] == 1 and metrics["p95_seconds"] <= 10,
        "rows":rows}
    directory = ROOT/"results"
    directory.mkdir(exist_ok=True)
    target = directory/f"{args.engine}-{args.split}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}.json"
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"report":str(target), "metrics":metrics, "accepted":report["routing_workflow_acceptance_passed"]},ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["rules","deepseek"], required=True)
    parser.add_argument("--split", choices=["dev","test"], required=True)
    parser.add_argument("--limit",type=int)
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0: parser.error("limit must be positive")
    asyncio.run(run(args))
