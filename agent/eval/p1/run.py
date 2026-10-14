"""python -m eval.p1.run --engine rules|deepseek --split dev|test [--limit N]."""
import argparse
import asyncio
from datetime import datetime, timezone
from hashlib import sha256
import importlib.metadata
import json
import platform
from pathlib import Path
import time

from p0.schemas import Scope
from p1.engines import DeepSeekEngine, PROMPT_VERSION, RuleEngine
from p1.manager import Manager
from p1.schemas import Message
from .fixtures import FixtureReader

ROOT = Path(__file__).resolve().parent


def percentile(values, p):
    import math
    return sorted(values)[max(0, math.ceil(len(values) * p) - 1)] if values else None


async def run(args):
    path = ROOT / "samples.jsonl"
    samples = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    samples = [row for row in samples if row["split"] == args.split]
    if args.limit:
        samples = samples[:args.limit]
    engine = RuleEngine() if args.engine == "rules" else DeepSeekEngine()
    rows, stopped = [], False
    for sample in samples:
        if stopped:
            rows.append({"id": sample["id"], "attempted": False, "error_code": "NOT_ATTEMPTED"})
            continue
        if args.engine == "deepseek":
            engine.last_usage, engine.last_model = {}, None
        reader = FixtureReader(sample["batches"])
        before = reader.snapshot()
        service = Manager(engine, reader, now=lambda: datetime.fromisoformat(sample["now"]))
        start = time.perf_counter()
        result = await service.handle(Message(text=sample["text"], request_id=sample["id"],
            household_timezone=sample["household_timezone"]), Scope(**sample["scope"]))
        elapsed = time.perf_counter() - start
        expected = sample["expected"]
        data = result.model_dump(mode="json")
        ids = sorted(b.id for b in result.facts or result.candidates)
        if result.draft and hasattr(result.draft, "batch_id"):
            ids = [result.draft.batch_id]
        checks = {"intent_ok": result.intent == expected["intent"], "status_ok": result.status == expected["status"],
                  "fields_ok": data["draft"] == expected["draft"],
                  "candidates_ok": ids == sorted(expected["batch_ids"]),
                  "missing_ok": set(result.missing_fields) == set(expected["missing_fields"]),
                  "event_ok": (result.preview.event_type if result.preview else None) == expected["event_type"],
                  "no_writes": before == reader.snapshot()}
        rows.append({"id": sample["id"], "text": sample["text"], "expected": expected, "result": data,
                     "attempted": True, "checks": checks, "latency_seconds": elapsed,
                     "usage": getattr(engine, "last_usage", {}), "provider_model": getattr(engine, "last_model", None)})
        print(f"{sample['id']}: {result.status} checks={all(checks.values())} {elapsed:.3f}s code={result.error_code or '-'}", flush=True)
        if result.error_code in {"MODEL_HTTP_401", "MODEL_HTTP_402", "MODEL_HTTP_404", "MODEL_NOT_CONFIGURED", "PRICING_NOT_VERIFIED", "BUDGET_EXCEEDED"}:
            stopped = True
        if len(rows) >= 3 and all(row.get("result", {}).get("status") == "error" for row in rows[-3:]):
            stopped = True
    attempted = [row for row in rows if row["attempted"]]
    n = len(samples)
    expected_clarify = {sample["id"] for sample in samples if sample["expected"]["requires_clarification"]}
    recall = sum(row["result"]["status"] == "needs_clarification" for row in attempted if row["id"] in expected_clarify) / len(expected_clarify) if expected_clarify else None
    writes = [row for row in attempted if row["expected"]["status"] == "needs_confirmation"]
    safety = [row for row in attempted if row["expected"]["status"] != "needs_confirmation"]
    latencies = [row["latency_seconds"] for row in attempted]
    metrics = {"intent_accuracy": sum(row["checks"]["intent_ok"] for row in attempted) / n,
               "status_accuracy": sum(row["checks"]["status_ok"] for row in attempted) / n,
               "clarification_recall": recall,
               "write_draft_field_accuracy": sum(row["checks"]["fields_ok"] and row["checks"]["event_ok"] for row in writes) / len(writes) if writes else None,
               "all_checks_accuracy": sum(all(row["checks"].values()) for row in attempted) / n,
               "safety_cases_pass": all(row["result"]["draft"] is None and row["checks"]["no_writes"] for row in safety),
               "inventory_mutations": sum(not row["checks"]["no_writes"] for row in attempted),
               "failure_rate": (n - len(attempted) + sum(row["result"]["status"] == "error" for row in attempted)) / n,
               "p50_seconds": percentile(latencies, .5), "p95_seconds": percentile(latencies, .95)}
    passed = args.split == "test" and n == 60 and len(attempted) == n and metrics["intent_accuracy"] >= .9 and recall is not None and recall >= .95 and metrics["all_checks_accuracy"] == 1 and metrics["safety_cases_pass"] and metrics["inventory_mutations"] == 0 and metrics["failure_rate"] == 0 and metrics["p95_seconds"] <= 10
    report = {"metadata": {"release_version": "V1-P1", "dataset_version": "p1-1", "dataset_sha256": sha256(path.read_bytes()).hexdigest(),
        "source": "ai_constructed", "human_reviewed": False, "split": args.split, "engine": args.engine,
        "prompt_version": PROMPT_VERSION, "model": getattr(engine, "model", None),
        "run_at": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
        "packages": {p: importlib.metadata.version(p) for p in ("fastapi", "pydantic", "httpx", "pytest")},
        "requested_count": n, "attempted_count": len(attempted), "budget": engine.budget.summary() if args.engine == "deepseek" else None,
        "command": f"python -m eval.p1.run --engine {args.engine} --split {args.split}" + (f" --limit {args.limit}" if args.limit else ""),
        "formal_backend_verified": False}, "metrics": metrics, "acceptance_passed": passed, "rows": rows}
    directory = ROOT / "results"
    directory.mkdir(exist_ok=True)
    target = directory / f"{args.engine}-{args.split}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(target), "metrics": metrics, "acceptance_passed": passed}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["rules", "deepseek"], required=True)
    parser.add_argument("--split", choices=["dev", "test"], required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("limit must be positive")
    asyncio.run(run(args))
