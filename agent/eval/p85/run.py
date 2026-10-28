"""Sequential turns per scenario; no production inventory, DB, or runtime service.

The caller fixture saves returned deltas and stages just as the future business
adapter must. This does not test production persistence or Android integration.
"""
import argparse
import asyncio
import json
import math
import os
import time
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from p0.budget import Budget
from p1.domain import make_draft
from p1.schemas import Parsed
from conversation.engines import DeepSeekEngine
from conversation.schemas import AgentResult
from conversation.tasks import Task
from conversation.replies import BoundTask
from conversation.memory_schemas import HistoryTurn, TaskEvidence
from conversation.p85 import flow
from conversation.p85.schemas import (P85Request, P85ResolveRequest, P85RespondRequest,
                                      P85Plan, P85Episode, P85Archive)
from conversation import dialogue as baseline
from conversation.dialogue_schemas import Request, ResolveRequest, RespondRequest
from eval.dialogue.run import fixture, NOW, SCOPE, TASK, DRAFT
from .generate import scenarios

ROOT = Path(__file__).resolve().parent


class FixtureSemantic:
    """Expected plans, used only by the explicitly-labelled offline workflow run."""
    def __init__(self): self.next = None
    async def p85_understand(self, *args): return self.next
    async def p85_respond(self, text, resolved):
        return {"opening": "focus", "fact_order": list(resolved.facts), "closing": "none"}


def expected_plan(row, step, first_id):
    if step == 0:
        return P85Plan(speech_act="question", selector={"name": "牛奶"}, reads=[{"kind": "quantity"}, {"kind": "location"}])
    if step == 1:
        return P85Plan(speech_act="discuss", social_reply="整理得累了可以先休息，之后只收拾常用的台面。")
    if step == 2:
        return P85Plan(speech_act="question", memory_id=first_id, reads=[{"kind": "quantity"}, {"kind": "location"}])
    if step == 3:
        if row["group"] in {7, 8}: return P85Plan(speech_act="hypothesis" if row["group"] == 7 else "negation", social_reply="可以先讨论，聊天不会替你执行操作。")
        fields = {"to_location": {"value": "厨房", "quote": "厨房"}} if row["action"] == "MOVE" else {"opened_at": {"value": "昨天", "quote": "昨天"}} if row["action"] == "OPEN" else {}
        return P85Plan(speech_act="request", action=row["action"], write_count=1, selector={"use_reference": True},
                       amount_mode="half" if row["action"] == "CONSUME" else "literal", fields=fields)
    if step == 4:
        fields = {"to_location": {"value": "储物柜", "quote": "储物柜"}} if row["action"] == "MOVE" else {"opened_at": {"value": "今天", "quote": "今天"}} if row["action"] == "OPEN" else {"quantity": {"value": "2", "quote": "两盒"}, "unit": {"value": "盒", "quote": "两盒"}}
        return P85Plan(speech_act="request" if row["group"] in {7, 8} else "correction", action=row["action"], write_count=1,
                       selector={"use_reference": True}, fields=fields)
    return P85Plan(speech_act="status")


def verify(row, step, frame, stock, previous_draft):
    domain = frame.result or {}
    draft = domain.get("draft")
    if step == 0:
        facts = domain.get("facts", [])
        return not draft and len(facts) == 1 and facts[0]["id"] == "b1" and Decimal(facts[0]["quantity"]) == Decimal(row["stock"])
    if step == 1 or step == 3 and row["group"] in {7, 8}:
        return not draft and frame.preserve_active and (frame.kind == "explain" or
            domain.get("status") == "answered" and bool(domain.get("facts")))
    if step == 2:
        facts = domain.get("facts", [])
        return not draft and len(facts) == 1 and facts[0]["id"] == "b1" and Decimal(facts[0]["quantity"]) == stock and (
            not row["change_stock"] or facts[0]["location"] == "冷藏室下层")
    if step in {3, 4}:
        if not draft or domain.get("status") != "needs_confirmation" or draft.get("batch_id") != "b1" or draft["action"] != row["action"]:
            return False
        if row["action"] == "CONSUME":
            if Decimal(draft["quantity"]) != (stock/2 if step == 3 else 2) or draft["unit"] != "盒": return False
        elif row["action"] == "MOVE":
            if "quantity" in draft or draft["to_location"] != ("厨房" if step == 3 else "储物柜"): return False
        elif row["action"] == "OPEN":
            if "quantity" in draft or draft["opened_at"] != (NOW.date()-timedelta(days=1 if step == 3 else 0)).isoformat(): return False
        if step == 4 and row["group"] not in {7, 8}:
            return frame.kind == "edit" and previous_draft == frame.edit.get("draft_id")
        return True
    return not draft and frame.kind == "explain" and "尚未执行" in frame.reply


async def scenario(row, budget=None, real=False, use_baseline=False, saved_plans=None):
    semantic = DeepSeekEngine(budget) if real else FixtureSemantic()
    owner, ctx, reader = fixture("reference", semantic)
    clock = [NOW]
    owner.now = lambda: clock[0]
    reader.data.items[0].batches[0].quantity = Decimal(row["stock"])
    original = reader.data.model_dump_json()
    archive, history, outputs = [], [], []
    first_ref = ctx.reference
    first_id = ""
    previous_draft = None
    for step, text in enumerate(row["turns"]):
        clock[0] = NOW+timedelta(seconds=step*15)
        ctx.trusted_now = clock[0]
        ctx.revision = step
        ctx.history = history[-10:]
        for task in ctx.tasks: task.checked_at = clock[0]
        start = time.monotonic()
        counts = {"understanding": 0, "response": 0}
        result = None
        if not real: semantic.next = P85Plan.model_validate(saved_plans[step]) if saved_plans else expected_plan(row, step, first_id)
        req = P85Request(text=text, request_id=f"{row['id']}-{step}", context=ctx,
            archive=P85Archive(scope=SCOPE, conversation_id=ctx.conversation_id, revision=ctx.revision, episodes=archive))
        try:
            async with asyncio.timeout(20):
                if use_baseline:
                    old = Request(**req.model_dump(exclude={"archive"}))
                    counts["understanding"] = 1
                    understood = await baseline.understand(owner, old, SCOPE)
                    counts["understanding"] = understood.understanding_calls
                    result = await baseline.resolve(owner, ResolveRequest(**old.model_dump(exclude={"remaining_seconds"}), plan=understood.plan,
                        remaining_seconds=max(.001, 18-(time.monotonic()-start))), SCOPE)
                    if counts["understanding"] and time.monotonic()-start < 18:
                        counts["response"] = 1
                        response = await baseline.respond(owner, RespondRequest(text=text, resolved=result, remaining_seconds=18-(time.monotonic()-start)))
                    else: response = None
                else:
                    counts["understanding"] = 1
                    understood = await flow.understand(owner, req, SCOPE)
                    counts["understanding"] = understood.understanding_calls
                    result = await flow.resolve(owner, P85ResolveRequest(**req.model_dump(exclude={"remaining_seconds"}),
                        plan=understood.plan, plan_context_revision=understood.context_revision,
                        remaining_seconds=max(.001, 18-(time.monotonic()-start))), SCOPE)
                    # Explicit/deterministic continuations use the verified reply.
                    if counts["understanding"] and result.expression_required and time.monotonic()-start < 18:
                        counts["response"] = 1
                        response = await flow.respond(owner, P85RespondRequest(text=text, resolved=result, remaining_seconds=18-(time.monotonic()-start)))
                    else: response = None
                stock = reader.data.items[0].batches[0].quantity
                passed = verify(row, step, result, stock, previous_draft)
                outputs.append({"turn": step, "text": text, "passed": passed, "calls": counts,
                    "latency_ms": (time.monotonic()-start)*1000,
                    "plan": understood.plan.model_dump(mode="json"), "resolved": result.model_dump(mode="json"),
                    "reply": response.reply if response else result.reply,
                    "fallback_used": response.fallback_used if response else False})
        except Exception as error:
            outputs.append({"turn": step, "text": text, "passed": False, "calls": counts,
                            "latency_ms": (time.monotonic()-start)*1000,
                            "error_code": getattr(error, "code", type(error).__name__)})
        # Synthetic trusted caller: save history/delta, bind IDs only after saving
        # a task, refresh task evidence separately; never execute inventory writes.
        if result is not None:
            if use_baseline:
                saved = P85Episode(memory_id=f"baseline-{row['id']}-{step}", request_id=req.request_id, text=text,
                    reply=result.reply, created_at=clock[0], subjects=[{"name": "牛奶", "quote": "牛奶"}] if "牛奶" in text else [])
            else:
                saved = result.memory_delta.episode.model_copy(deep=True) if result.memory_delta else P85Episode(
                    memory_id=f"error-{row['id']}-{step}", request_id=req.request_id, text=text, created_at=clock[0])
            domain = result.result or {}
            if domain.get("facts") or domain.get("draft"):
                ref = first_ref.model_copy(deep=True)
                # Retain original TTL, including on memory retrieval.
                ctx.reference = ref
                saved.reference = ref
            archive.append(saved)
            if step == 0: first_id = saved.memory_id
            if domain.get("draft"):
                revision = (ctx.active.task.revision+1) if ctx.active else 1
                ctx.active = BoundTask(scope=SCOPE, task=Task(task_id=TASK, household_id=SCOPE.household_id,
                    status="needs_confirmation", revision=revision, expires_at=NOW+timedelta(minutes=15), draft_id=DRAFT,
                    result=AgentResult.model_validate(domain).model_dump(mode="json"), inventory_written=False))
                ctx.tasks = [TaskEvidence(task_id=UUID(TASK), revision=revision, status="needs_confirmation", action=row["action"],
                    execution_status="pending", draft_id=UUID(DRAFT), checked_at=clock[0])]
                previous_draft = DRAFT
        history.append(HistoryTurn(request_id=req.request_id, text=text, reply=outputs[-1].get("reply", "未完成"), created_at=clock[0]))
        if step == 1:
            for i in range(10):
                created = clock[0]+timedelta(seconds=i+1)
                ident = f"background-{row['id']}-{i}"
                history.append(HistoryTurn(request_id=ident, text="先聊聊整理心情", reply="可以慢慢来。", created_at=created))
                archive.append(P85Episode(memory_id=ident, request_id=ident, text="先聊聊整理心情", created_at=created))
            if row["switch_object"]:
                reader.data.items[0].batches.append(reader.data.items[0].batches[0].model_copy(update={"id": "b2", "name": "鸡蛋"}))
                ctx.reference = first_ref.model_copy(update={"batch_id": "b2"})
            if row["change_stock"]:
                reader.data.items[0].batches[0].quantity += 2
                reader.data.items[0].batches[0].location = "冷藏室下层"
                reader.data.items[0].batches[0].version += 1
    # Scripted external stock changes are part of fixture setup, not AI writes.
    expected = json.loads(original)
    actual = reader.data.model_dump(mode="json")
    if row["switch_object"]: actual["items"][0]["batches"].pop()
    if row["change_stock"]:
        actual["items"][0]["batches"][0].update(quantity=row["stock"], location="冰箱", version=4)
    return {"id": row["id"], "group_id": row["group_id"], "split": row["split"],
            "passed": all(t["passed"] for t in outputs), "inventory_unchanged_by_ai": actual == expected,
            "turns": outputs, "human_review_status": "pending"}


async def main(args):
    if args.baseline and not args.real: raise SystemExit("Baseline requires --real; no fake NLU comparison")
    rows = [r for r in scenarios() if args.split == "all" or r["split"] == args.split]
    saved = {}
    if args.replay_report:
        if args.real or args.baseline: raise SystemExit("Replay must not call a model or baseline")
        loaded = json.loads(Path(args.replay_report).read_text(encoding="utf-8"))
        saved = {s["id"]: [t["plan"] for t in s["turns"]] for s in loaded["results"]}
        rows = [r for r in rows if r["id"] in saved]
    if args.limit: rows = rows[:args.limit]
    if args.real and not os.getenv("DEEPSEEK_API_KEY"): raise SystemExit("MODEL_NOT_CONFIGURED; no provider calls made")
    agent = ROOT.parents[1]
    budget = Budget(agent/".cache/p0/budget.sqlite", agent/"eval/pricing.json") if args.real else None
    gate = asyncio.Semaphore(args.concurrency)
    async def one(row):
        async with gate:
            value = await scenario(row, budget, args.real, args.baseline, saved.get(row["id"]))
            print(json.dumps({"id": value["id"], "passed_turns": sum(t["passed"] for t in value["turns"])}), flush=True)
            return value
    results = await asyncio.gather(*(one(row) for row in rows))
    turns = [t for r in results for t in r["turns"]]
    times = sorted(t["latency_ms"] for t in turns)
    report = {"protocol": "p84-dialogue-1" if args.baseline else "p85-dialogue-1", "mode": "real_deepseek" if args.real else "saved_real_plans_replayed_without_model" if saved else "fixture_workflow_not_model",
        "split": args.split, "scenario_count": len(results), "turn_count": len(turns),
        "scenario_success_rate": sum(r["passed"] for r in results)/len(results), "turn_success_rate": sum(t["passed"] for t in turns)/len(turns),
        "max_model_calls": max(sum(t["calls"].values()) for t in turns) if args.real else 0,
        "max_stage_call_slots": max(sum(t["calls"].values()) for t in turns), "p95_ms": times[math.ceil(len(times)*.95)-1],
        "discussion_natural_replies": sum("non_factual_household_discussion" in t.get("resolved",{}).get("memory",{}).get("summary",{}).get("plan_normalizations",[]) for t in turns),
        "discussion_fallbacks": sum("non_factual_discussion_fallback" in t.get("resolved",{}).get("memory",{}).get("summary",{}).get("plan_normalizations",[]) for t in turns),
        "fallback_turns": sum(t.get("fallback_used", False) for t in turns),
        "inventory_unchanged_by_ai": all(r["inventory_unchanged_by_ai"] for r in results),
        "model": os.getenv("LLM_MODEL", "deepseek-flash") if args.real else None,
        "human_review_status": "pending", "production_data_accessed": False, "app_acceptance": "not_run",
        "latency_scope": "AI stages only, excludes business DB save and Android", "results": results}
    path = Path(args.output); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--real", action="store_true"); parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--replay-report", type=Path)
    parser.add_argument("--split", choices=["dev", "holdout", "all"], default="all")
    parser.add_argument("--limit", type=int); parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--output", required=True)
    asyncio.run(main(parser.parse_args()))
