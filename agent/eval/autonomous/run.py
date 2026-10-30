import argparse
import asyncio
import json
import math
import os
import time
from pathlib import Path
from conversation.engines import DeepSeekEngine
from conversation.autonomous.runner import run
from conversation.autonomous.schemas import RunRequest
from conversation.p85 import flow
from conversation.p85.schemas import P85Request,P85ResolveRequest,P85RespondRequest
from eval.dialogue.run import fixture,SCOPE

ROOT=Path(__file__).resolve().parents[3]
REPORT=ROOT/"reports/p86-autonomous/initial-20261029"

# Newly authored expressions, grouped by semantic family. No historical holdout
# is relabelled as blind. Expected outcomes were authored without model output.
FAMILIES=[
 ("compound","empty",["家里的牛奶我想核对一下，数量和放的位置一起告诉我","帮我看看牛奶还存了多少，顺便说一下放在哪儿"],"query"),
 ("quantity","reference",["接着这盒，能不能帮我核实一下目前的余量","前面那份牛奶还存着多少呢"],"query"),
 ("move","empty",["麻烦把牛奶这一整批挪去书房，给我看看要改什么","我决定把牛奶移到书房，帮我准备一下"],"MOVE"),
 ("half","reference",["这盒我刚喝了半盒的量，按现有剩下的一半帮我登记","我刚把它喝掉一半，帮我做个记录草稿"],"CONSUME"),
 ("open","reference",["这批是昨天开封的，麻烦登记下日期","帮我记录它的开封日期，就是昨天"],"OPEN"),
 ("missing","empty",["牛奶刚才用了一点，具体多少我还没数","帮我登记牛奶的消耗，但数量我得再核实"],"needs_input"),
 ("unknown_state","unknown",["刚才那件事究竟有没有办成，我还需要再点吗","原来那个记录现在执行结果确认了吗"],"unknown"),
 ("social","empty",["收拾厨房总是觉得累，有没有轻松一点的思路","你好呀，今天整理柜子有点烦，陪我理理思路"],"social"),
 ("negation","reference",["牛奶先不要改动，我只是想讨论怎么安排","先别登记消耗，我只是说说自己的打算"],"no_draft"),
 ("hypothesis","reference",["假如把这盒喝掉一半，还能剩多少？先不要记录","如果只用掉一半会怎么样，我现在只是问问"],"no_draft"),
 ("ambiguous","multiple",["牛奶有不同批次，帮我准备把牛奶移到书房","把牛奶移到书房，先让我选具体哪一批"],"needs_input"),
 ("expired","expired",["继续刚才那盒，请告诉我它现在在哪里","之前那一批的余量再核对一下"],"needs_input"),
]
HOLDOUT={"unknown_state","hypothesis","ambiguous","expired"}


def cases():
    result=[]
    for group,profile,texts,expected in FAMILIES:
        for i,text in enumerate(texts):
            result.append(dict(id=group+"-"+str(i),group=group,split="holdout" if group in HOLDOUT else "dev",
                profile=profile,text=text,expected=expected,source="authored_synthetic_2026-10-29",
                human_review_status="pending"))
    return result


def score(case,frame,status,reply):
    domain=(frame or {}).get("result") or {}
    draft=domain.get("draft")
    expected=case["expected"]
    if expected in {"MOVE","CONSUME","OPEN"}:
        if not draft or draft.get("action")!=expected or draft.get("batch_id")!="b1":return False
        if expected=="MOVE":return draft.get("to_location")=="书房"
        if expected=="CONSUME":return float(draft.get("quantity",-1))==3
        return bool(draft.get("opened_at"))
    if expected=="query":return domain.get("status")=="answered" and bool(domain.get("facts")) and (case["group"]!="compound" or "位置" in reply and "数量" in reply)
    if expected=="needs_input":return not draft and (status=="needs_input" or (frame or {}).get("kind")=="needs_input" or domain.get("status")=="needs_clarification")
    if expected=="unknown":return not draft and any(word in reply for word in ["待核实","不能确认","无法确认"])
    if expected=="no_draft":return not draft and bool(reply)
    if expected=="social":return not draft and bool(reply) and (frame or {}).get("kind")=="explain"
    return False


async def evaluate(case,variant):
    engine=DeepSeekEngine()
    owner,ctx,_=fixture(case["profile"],engine)
    start=time.monotonic()
    entry=dict(text=case["text"],request_id="synthetic-"+variant+"-"+case["id"],context=ctx)
    try:
        if variant=="autonomous":
            output=await run(owner,RunRequest(**entry),SCOPE)
            saved=output.model_dump(mode="json")
            frame=saved.get("resolved"); status=saved["status"]; reply=saved["reply"]; calls=saved["model_calls"]
        else:
            def left():return min(18,max(.001,18-(time.monotonic()-start)))
            request=P85Request(**entry,remaining_seconds=left())
            understood=await flow.understand(owner,request,SCOPE)
            frame=await flow.resolve(owner,P85ResolveRequest(**entry,remaining_seconds=left(),plan=understood.plan,plan_context_revision=ctx.revision),SCOPE)
            responded=await flow.respond(owner,P85RespondRequest(text=case["text"],resolved=frame,remaining_seconds=left()))
            calls=understood.understanding_calls+responded.response_calls
            reply=responded.reply; frame=frame.model_dump(mode="json")
            status="needs_input" if frame["kind"]=="needs_input" or (frame.get("result") or {}).get("status")=="needs_clarification" else "completed"
            saved=dict(plan=understood.plan.model_dump(mode="json"),resolved=frame,reply=reply,model_calls=calls)
        passed=score(case,frame,status,reply)
        return dict(case=case,variant=variant,passed=passed,elapsed_ms=(time.monotonic()-start)*1000,
                    calls=calls,output=saved)
    except Exception as error:
        return dict(case=case,variant=variant,passed=False,elapsed_ms=(time.monotonic()-start)*1000,
            error_code=getattr(error,"code",type(error).__name__))


async def main(args):
    REPORT.mkdir(parents=True,exist_ok=True)
    rows=cases()
    (REPORT/"cases.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if not os.getenv("DEEPSEEK_API_KEY"):
        raise SystemExit("MODEL_NOT_CONFIGURED; no provider request performed")
    path=REPORT/(args.label+".jsonl")
    if path.exists():raise SystemExit("Result exists; choose a new label, never overwrite evaluation evidence")
    output=[]
    with path.open("x",encoding="utf-8") as stream:
        for index,case in enumerate(rows):
            for variant in ("p85","autonomous"):
                value=await evaluate(case,variant); output.append(value)
                stream.write(json.dumps(value,ensure_ascii=False)+"\n");stream.flush()
                print(json.dumps(dict(index=index+1,total=len(rows),variant=variant,passed=value["passed"],calls=value.get("calls"),
                    milliseconds=round(value["elapsed_ms"])),ensure_ascii=False),flush=True)
    summary={"source":"real_deepseek_synthetic_only","production_inventory_accessed":False,
        "backend_or_app_joint_acceptance":False,"human_naturalness_review":"pending","variants":{}}
    for variant in ("p85","autonomous"):
        values=[v for v in output if v["variant"]==variant]
        times=sorted(v["elapsed_ms"] for v in values)
        summary["variants"][variant]={"cases":len(values),"passed":sum(v["passed"] for v in values),
            "p95_ms":times[math.ceil(len(times)*.95)-1],"calls":[v.get("calls") for v in values],
            "split":{split:{"cases":sum(v["case"]["split"]==split for v in values),
                "passed":sum(v["passed"] for v in values if v["case"]["split"]==split)} for split in ("dev","holdout")}}
    (REPORT/(args.label+"-summary.json")).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--label",default="real-first")
    asyncio.run(main(parser.parse_args()))
