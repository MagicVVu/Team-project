"""Real provider evaluation over synthetic inventory. No server or business writes.

Each sample is a single measured turn under a 20s deadline. Multi-turn recovery
and transactional execution are validated separately by authenticated tests.
"""
import argparse
import asyncio
import json
import math
import os
import time
from datetime import timedelta, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from p0.schemas import Scope
from p0.deepseek import DeepSeekEngine as Transport
from p0.budget import Budget
from p1.domain import make_draft
from p1.schemas import Parsed
from p2.knowledge import RuleCatalog
from eval.p3.fixtures import snapshot, FixtureReader, NOW
from conversation.manager import Manager
from conversation.engines import DeepSeekEngine
from conversation.schemas import ObjectReference, AgentResult
from conversation.tasks import Task
from conversation.replies import BoundTask
from conversation.memory_schemas import MemoryContext, HistoryTurn, TaskEvidence, TurnRequest
from conversation.memory import safe_turn
from conversation.dialogue import understand, resolve, respond
from conversation.dialogue_schemas import Request, ResolveRequest, RespondRequest

ROOT=Path(__file__).resolve().parent
HOME="22222222-2222-4222-8222-222222222222"
TASK="11111111-1111-4111-8111-111111111111"
DRAFT="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
SCOPE=Scope(user_id="33333333-3333-4333-8333-333333333333",household_id=HOME)


def fixture(profile,engine):
    data=snapshot(); data.scope=SCOPE
    data.items[0].batches[0].household_id=HOME
    data.items[0].batches[0].quantity=Decimal(6)
    if profile=="multiple":
        data.items[0].batches.append(data.items[0].batches[0].model_copy(update={"id":"b2","location":"厨房"}))
    reader=FixtureReader(data)
    owner=Manager(engine,reader,RuleCatalog.load(),now=lambda:NOW)
    ctx=MemoryContext(scope=SCOPE,conversation_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",revision=0,trusted_now=NOW)
    ref=ObjectReference(scope=SCOPE,source_task_id=TASK,source_revision=1,batch_id="b1",issued_at=NOW,expires_at=NOW+timedelta(minutes=15))
    if profile in {"reference","expired","multiple"}:ctx.reference=ref
    if profile=="expired":
        ctx.reference=ref.model_copy(update={"issued_at":NOW-timedelta(minutes=16),"expires_at":NOW-timedelta(minutes=1)})
    if profile=="multiple":ctx.choices=[ref,ref.model_copy(update={"batch_id":"b2"})]
    if profile in {"pending","move_pending","committed","cancelled","unknown","conflict","basis"}:
        parsed=Parsed(intent="MOVE",name="牛奶",to_location="厨房") if profile=="move_pending" else Parsed(intent="CONSUME",name="牛奶",quantity=1,unit="盒")
        command,preview=make_draft(parsed,data.items[0].batches[0],{})
        result=AgentResult(status="needs_confirmation",trace_id="synthetic",original_text="之前的库存任务",reply="待确认草稿，尚未执行。",draft=command,preview=preview)
        task=Task(task_id=TASK,household_id=HOME,status="needs_confirmation",revision=1,expires_at=NOW+timedelta(minutes=15),draft_id=DRAFT,result=result.model_dump(),inventory_written=False)
        ctx.active=BoundTask(scope=SCOPE,task=task)
        ctx.reference=ref
        state=profile if profile in {"committed","cancelled","unknown","conflict"} else "pending"
        ctx.tasks=[TaskEvidence(task_id=TASK,revision=1,status="needs_confirmation",action=command.action,execution_status=state,
            draft_id=DRAFT,operation_id=UUID(DRAFT) if state=="committed" else None,receipt_verified=state=="committed",
            basis=["缺少完整待购资料，原建议需要核对"] if profile=="basis" else [],checked_at=NOW)]
    if profile=="history":ctx.history=[HistoryTurn(request_id="old",text="牛奶放在哪里",reply="讨论了牛奶位置，未执行。",created_at=NOW-timedelta(minutes=2))]
    return owner,ctx,reader


def score(row,frame):
    result=frame.get("result") or {}
    command=result.get("draft") or {}
    expected=row["expected"]
    draft=bool(command)
    action=command.get("action")
    if expected in {"social","no_write"}:return not draft and frame["kind"] in {"explain","needs_input"}
    if expected=="new_task":return frame["kind"]=="clear_reference"
    if expected=="multiple":return not draft and frame.get("error_code")=="MULTIPLE_WRITES"
    if expected=="expired":return not draft and frame.get("error_code") in {"REFERENCE_EXPIRED","REFERENCE_REQUIRED"}
    if expected=="clarify":return not draft and (result.get("status")=="needs_clarification" or frame["kind"]=="needs_input")
    if expected=="blocked":return not draft and frame["kind"] in {"needs_input","explain"}
    if expected=="edit":return frame["kind"]=="edit" and draft
    if expected in {"status","basis","recall"}:return frame["kind"]=="explain" and not draft
    if expected=="query":return not draft and (result.get("status")=="answered" or frame["kind"]=="explain")
    if expected=="half":return action=="CONSUME" and Decimal(command["quantity"])==3
    if expected=="all_consume":return action=="CONSUME" and Decimal(command["quantity"])==6
    if expected=="all_discard":return action=="DISCARD" and command.get("discard_mode")=="all" and Decimal(command["quantity"])==6
    return action=={"consume":"CONSUME","move":"MOVE","open":"OPEN","discard":"DISCARD","add":"ADD","plan":"PLAN_ADD"}.get(expected)


async def one(row, budget, baseline=False):
    owner,ctx,reader=fixture(row["profile"],DeepSeekEngine(budget))
    start=time.monotonic(); counts={"understanding":0,"response":0}; frame={}
    try:
        async with asyncio.timeout(20):
            if baseline:
                result=await safe_turn(owner,TurnRequest(text=row["text"],request_id=row["id"],context=ctx),SCOPE)
                frame=result.model_dump(mode="json"); counts["understanding"]=result.model_calls
            else:
                request=Request(text=row["text"],request_id=row["id"],context=ctx)
                counts["understanding"]=1 # attempted paid calls count even on timeout
                understood=await understand(owner,request,SCOPE)
                counts["understanding"]=understood.understanding_calls
                remaining=18-(time.monotonic()-start)
                frame=(await resolve(owner,ResolveRequest(**request.model_dump(exclude={"remaining_seconds"}),plan=understood.plan,
                    remaining_seconds=max(.001,remaining)),SCOPE)).model_dump(mode="json")
                if counts["understanding"] and frame["kind"]!="clarify" and time.monotonic()-start<18:
                    counts["response"]=1
                    rendered=await respond(owner,RespondRequest(text=row["text"],resolved=frame,remaining_seconds=18-(time.monotonic()-start)))
                    frame["reply"]=rendered.reply
                    frame["fallback_used"]=rendered.fallback_used
                frame["plan"]=understood.plan.model_dump(mode="json")
            valid=score(row,frame)
            return dict(id=row["id"],group_id=row["group_id"],split=row["split"],passed=valid,latency_ms=(time.monotonic()-start)*1000,
                        calls=counts,frame=frame,human_review_status="pending")
    except Exception as error:
        return dict(id=row["id"],group_id=row["group_id"],split=row["split"],passed=False,latency_ms=(time.monotonic()-start)*1000,
                    calls=counts,error_code=getattr(error,"code",type(error).__name__),human_review_status="pending")


async def main(args):
    rows=[json.loads(line) for line in (ROOT/"samples.jsonl").read_text(encoding="utf-8").splitlines()]
    if args.split!="all":rows=[r for r in rows if r["split"]==args.split]
    if args.limit:rows=rows[:args.limit]
    if not os.getenv("DEEPSEEK_API_KEY"):raise SystemExit("MODEL_NOT_CONFIGURED; no provider calls made")
    agent=ROOT.parents[1]
    budget=Budget(agent/".cache/p0/budget.sqlite",agent/"eval/pricing.json")
    gate=asyncio.Semaphore(args.concurrency)
    async def limited(row):
        async with gate:
            value=await one(row,budget,args.baseline)
            print(json.dumps({k:value[k] for k in ("id","passed","latency_ms")}),flush=True)
            return value
    results=await asyncio.gather(*(limited(row) for row in rows))
    times=sorted(r["latency_ms"] for r in results)
    success=sum(r["passed"] for r in results)
    intended=[(row,r) for row,r in zip(rows,results) if row["expected"] not in {"clarify","expired","blocked","multiple"}]
    unnecessary=sum((r.get("frame",{}).get("result") or {}).get("status")=="needs_clarification" or r.get("frame",{}).get("kind")=="needs_input" for _,r in intended)
    report=dict(protocol="p83-baseline" if args.baseline else "p84-dialogue-1",split=args.split,count=len(results),success_rate=success/len(results),
        unnecessary_clarification_rate=unnecessary/len(intended),p95_ms=times[math.ceil(.95*len(times))-1],
        max_model_calls=max(sum(r["calls"].values()) for r in results),model=os.getenv("LLM_MODEL","deepseek-flash"),
        synthetic_data_only=True,production_inventory_accessed=False,human_review_status="pending",app_acceptance="not_run",
        measurements="AI stages only; excludes business database save and Android latency",budget_summary=budget.summary(),results=results)
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="results"},ensure_ascii=False),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--split",choices=["all","dev","holdout"],default="all")
    parser.add_argument("--limit",type=int);parser.add_argument("--concurrency",type=int,default=3)
    parser.add_argument("--baseline",action="store_true");parser.add_argument("--output",required=True)
    asyncio.run(main(parser.parse_args()))
