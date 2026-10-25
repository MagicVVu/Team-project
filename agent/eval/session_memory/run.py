"""Offline memory workflow regression. No paid model, network, stock writes or mock service."""
import argparse
import asyncio
import hashlib
import json
import time
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from eval.p3.fixtures import FixtureReader, NOW, snapshot
from p0.schemas import Scope
from p0.domain import DomainError
from p2.knowledge import RuleCatalog
from p3.schemas import Parsed
from conversation.manager import Manager
from conversation.engines import RuleEngine
from conversation.tasks import parse_task
from conversation.replies import BoundTask
from conversation.schemas import ObjectReference
from conversation.memory import safe_turn
from conversation.memory_schemas import MemoryContext, TurnRequest, TaskEvidence, HistoryTurn, Understanding

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
HOME = "22222222-2222-4222-8222-222222222222"
TASK = "11111111-1111-4111-8111-111111111111"
DRAFT = "44444444-4444-4444-8444-444444444444"
SCOPE = Scope(user_id="33333333-3333-4333-8333-333333333333", household_id=HOME)
SESSION = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


class Reader(FixtureReader):
    def __init__(self, variant):
        super().__init__(snapshot())
        self.data.scope = SCOPE
        self.data.items[0].name = f"评测物品{variant}"
        self.data.items[0].batches[0].name = self.data.items[0].name
        self.data.items[0].batches[0].household_id = HOME
        self.data.items[0].batches[0].location = f"位置{variant}"
        self.data.items[0].batches[0].quantity = Decimal(variant+1)
        self.batch_reads = 0
    async def get_batch(self, scope, batch_id):
        self.batch_reads += 1
        rows = [b for item in self.data.items for b in item.batches if b.id == batch_id]
        if not rows: raise DomainError("BATCH_NOT_FOUND", "评测夹具：批次不存在", 404)
        return rows[0].model_copy(deep=True)


def reference(batch="b1", **updates):
    return ObjectReference(scope=SCOPE, source_task_id=TASK, source_revision=1, batch_id=batch,
        issued_at=updates.get("issued_at", NOW), expires_at=updates.get("expires_at", NOW+timedelta(minutes=15)))


def binding():
    task = parse_task(dict(task_id=TASK, household_id=HOME, revision=1, status="needs_confirmation",
        expires_at=NOW+timedelta(minutes=15), draft_id=DRAFT, inventory_written=False,
        result=dict(status="needs_confirmation", original_text="把牛奶移到厨房", reply="待确认，尚未写入。", trace_id="fixture",
                    draft=dict(action="MOVE", name="牛奶", batch_id="b1", expected_version=4, to_location="厨房"))), HOME)
    return BoundTask(scope=SCOPE, task=task)


async def case(row, live=False):
    scenario, i = row["scenario"], row["variant"]
    reader = Reader(i)
    class Engine(RuleEngine):
        calls = 0
        async def understand_turn(self, text, context):
            self.calls += 1
            if scenario == "context_once":
                assert context.history[0].request_id == "earlier"
                return Understanding(parsed=Parsed(intent="QUERY_INVENTORY"))
            return await super().understand_turn(text, context)
    engine = Engine()
    if live and scenario == "context_once":
        from conversation.engines import DeepSeekEngine
        class LiveEngine(DeepSeekEngine):
            calls = 0
            async def understand_turn(self, text, memory):
                self.calls += 1
                return await super().understand_turn(text, memory)
        engine = LiveEngine()
    manager = Manager(engine, reader, RuleCatalog.load(), now=lambda:NOW)
    kwargs = dict(reference=reference())
    if scenario == "ordinal":
        base = reader.data.items[0].batches[0]
        reader.data.items[0].batches = [base.model_copy(update={"id": f"b{n+1}"}) for n in range(10)]
        kwargs = dict(choices=[reference(f"b{n+1}") for n in range(10)])
    elif scenario in {"pending", "committed", "unverified_receipt"}:
        evidence = TaskEvidence(task_id=TASK, revision=1, status="needs_confirmation", draft_id=DRAFT,
            execution_status="pending" if scenario=="pending" else "committed",
            action="PLAN_ADD" if i%3==0 and "移动" not in row["text"] else "MOVE",
            receipt_verified=scenario=="committed", operation_id=UUID(SESSION) if scenario=="committed" else None, checked_at=NOW)
        kwargs.update(active=binding(), tasks=[evidence])
    elif scenario == "missing_reference": kwargs = {}
    elif scenario == "expired": kwargs = dict(reference=reference(issued_at=NOW-timedelta(minutes=16), expires_at=NOW-timedelta(minutes=1)))
    elif scenario == "terminal":
        reader.data.items[0].batches[0].status = ["FINISHED", "DISCARDED", "REVERSED"][i%3]
    elif scenario == "deleted": kwargs = dict(reference=reference(f"deleted-{i}"))
    elif scenario == "cross_scope":
        kwargs = dict(scope=Scope(user_id=f"other-{i}", household_id=HOME))
    elif scenario == "truncated":
        kwargs.update(history=[HistoryTurn(request_id=f"h{n}", text="之前的移动草稿还没确认", reply="草稿尚未执行"*(400+i*10), created_at=NOW) for n in range(10)])
    elif scenario == "context_once":
        kwargs.update(history=[HistoryTurn(request_id="earlier", text=f"评测物品{i}在哪里", reply="以前的位置；已明确选中这一批", created_at=NOW)])
    scope = kwargs.pop("scope", SCOPE)
    memory = MemoryContext(scope=scope, conversation_id=SESSION, revision=0, trusted_now=NOW, **kwargs)
    before = reader.data.model_dump_json()
    started = time.perf_counter()
    result = None
    try:
        result = await safe_turn(manager, TurnRequest(text=row["text"], request_id=row["id"], context=memory), SCOPE)
        valid = result.original_text == row["text"] and result.model_calls == (1 if scenario=="context_once" else 0)
        if scenario in {"location", "quantity", "ordinal", "context_once"}:
            expected = f"b{i+1}" if scenario=="ordinal" else "b1"
            valid &= result.kind == "task" and bool(result.result.facts) and result.result.facts[0].id == expected and reader.batch_reads > 0
        elif scenario == "pending": valid &= result.kind == "explain" and "待确认" in result.reply
        elif scenario == "committed": valid &= result.kind == "explain" and ("待购" if kwargs["tasks"][0].action=="PLAN_ADD" else "执行成功") in result.reply
        elif scenario == "unverified_receipt": valid &= result.kind == "explain" and "待核实" in result.reply
        elif scenario == "missing_reference": valid &= result.kind == "task" and result.result.status == "needs_clarification" and not result.result.draft
        elif scenario in {"expired", "terminal", "deleted", "injection"}: valid &= result.kind == "needs_input" and result.result is None
        elif scenario == "new_task": valid &= result.kind == "clear_reference"
        elif scenario == "truncated": valid &= result.kind == "explain" and result.truncated and "历史讨论" in result.reply
        else: valid = False
    except DomainError as error:
        valid = scenario=="cross_scope" and error.code=="HOUSEHOLD_FORBIDDEN" and engine.calls==0
    valid &= reader.data.model_dump_json() == before
    return dict(id=row["id"], scenario=scenario, split=row["split"], passed=bool(valid),
                fixture_elapsed_ms=round((time.perf_counter()-started)*1000, 3),
                simulated_model_calls=0 if live and scenario=="context_once" else engine.calls,
                actual_provider_calls=engine.calls if live and scenario=="context_once" else 0,
                provider_model=getattr(engine, "last_model", None),
                error_code=result.error_code if result else None,
                result_kind=result.kind if result else "scope_rejected")


async def main(split, live=False):
    rows = [json.loads(line) for line in (ROOT/"samples.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows)==150
    assert {r["group_id"] for r in rows if r["split"]=="dev"}.isdisjoint({r["group_id"] for r in rows if r["split"]=="holdout"})
    results = []
    for row in rows:
        if split!="all" and row["split"]!=split: continue
        result = await case(row, live)
        results.append(result)
        if live and result["actual_provider_calls"]:
            print(json.dumps({k:result[k] for k in ("id", "passed", "actual_provider_calls", "fixture_elapsed_ms", "error_code")}))
            if result["error_code"] in {"MODEL_HTTP_401", "MODEL_HTTP_402", "MODEL_NOT_CONFIGURED", "MODEL_UNAVAILABLE", "MODEL_TIMEOUT"}:
                break
    elapsed = sorted(r["fixture_elapsed_ms"] for r in results)
    measured = [r for r in results if r["actual_provider_calls"]]
    provider_times = sorted(r["fixture_elapsed_ms"] for r in measured)
    report = dict(mode="real_provider_with_synthetic_read_fixtures" if live else "offline_synthetic_fixture_regression",
        paid_model_calls=sum(r["actual_provider_calls"] for r in results), real_model_verified=bool(measured) and all(r["passed"] for r in measured),
        human_review_status="pending", intent_accuracy=None, clarification_recall=None, production_p95_ms=None,
        provider_context_accuracy=sum(r["passed"] for r in measured)/len(measured) if measured else None,
        provider_context_cases=len(measured), provider_context_intent_scope="QUERY_INVENTORY follow-ups only; not full intent acceptance",
        provider_fixture_flow_p95_ms=provider_times[min(len(provider_times)-1, int(len(provider_times)*.95))] if measured else None,
        passed=sum(r["passed"] for r in results), total=len(results),
        fixture_elapsed_p95_ms=elapsed[min(len(elapsed)-1, int(len(elapsed)*.95))],
        dataset_sha256=hashlib.sha256((ROOT/"samples.jsonl").read_bytes()).hexdigest(),
        holdout_status="evaluated for this increment; not an unseen set for future tuning" if split in {"all","holdout"} else "not run",
        results=results)
    target = REPO/"reports/session-memory"
    target.mkdir(parents=True, exist_ok=True)
    (target/(("provider-" if live else "offline-")+split+".json")).write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="results"}, ensure_ascii=True))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--split", choices=["dev", "holdout", "all"], default="all")
    parser.add_argument("--live-provider", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.split, args.live_provider)))
