"""Focused real-model check for the final multi-candidate source guard."""
import asyncio
import json
import time
from pathlib import Path
from .run import ROOT
from eval.dialogue.run import fixture, SCOPE
from p0.budget import Budget
from conversation.engines import DeepSeekEngine
from conversation.p85 import flow
from conversation.p85.schemas import P85Request, P85ResolveRequest

CASES = [
    ("厨房那盒牛奶现在在哪，有多少", "b2", None),
    ("第二批帮我核对一下数量", "b2", None),
    ("请帮我看看第二批的数量", "b2", None),
    ("把牛奶移到冷藏室", None, "clarify"),
    ("选厨房那盒，帮我移到冷藏室", "b2", "MOVE"),
    ("不要登记消耗，只查第二批的数量", "b2", None),
    ("它现在有多少", None, "reselect"),
    ("这一批在什么地方", None, "reselect"),
]


async def main():
    budget = Budget(ROOT.parents[1]/".cache/p0/budget.sqlite", ROOT.parents[1]/"eval/pricing.json")
    results = []
    for i, (text, target, action) in enumerate(CASES):
        owner, ctx, reader = fixture("multiple", DeepSeekEngine(budget))
        ctx.reference = None  # Multiple query results are not a selected first row.
        before = reader.data.model_dump_json()
        start = time.monotonic()
        calls = 1
        try:
            async with asyncio.timeout(20):
                req = P85Request(text=text, request_id=f"p85-final-boundary-{i}", context=ctx)
                understood = await flow.understand(owner, req, SCOPE)
                calls = understood.understanding_calls
                frame = await flow.resolve(owner, P85ResolveRequest(**req.model_dump(exclude={"remaining_seconds"}),
                    plan=understood.plan, plan_context_revision=understood.context_revision,
                    remaining_seconds=max(.001, 18-(time.monotonic()-start))), SCOPE)
                domain = frame.result or {}; draft = domain.get("draft") or {}; facts = domain.get("facts", [])
                if action == "MOVE": passed = draft.get("batch_id") == target and draft.get("to_location") == "冷藏室"
                elif action == "clarify": passed = not draft and domain.get("status") == "needs_clarification" and "batch_id" in domain.get("missing_fields", [])
                elif action == "reselect": passed = not draft and not facts and "请" in frame.reply
                else: passed = not draft and len(facts) == 1 and facts[0]["id"] == target
                results.append({"text": text, "passed": passed, "understanding_calls": calls, "latency_ms": (time.monotonic()-start)*1000,
                    "frame": frame.model_dump(mode="json"), "plan": understood.plan.model_dump(mode="json"),
                    "inventory_unchanged": reader.data.model_dump_json() == before})
        except Exception as error:
            results.append({"text": text, "passed": False, "understanding_calls": calls, "error_code": getattr(error, "code", type(error).__name__)})
    report = {"mode": "real_deepseek", "count": len(results), "passed": sum(r["passed"] for r in results),
              "synthetic": True, "human_review_status": "pending", "purpose": "final candidate guard, not a new blind benchmark",
              "results": results}
    path = ROOT.parents[2]/"reports/p85-memory/deepseek-final-boundary.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "results"}))


if __name__ == "__main__": asyncio.run(main())
