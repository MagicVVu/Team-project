"""Reproducible P8 zero-model routing eval, separate from all P7 datasets."""
import argparse
import asyncio
from datetime import timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import time
from conversation.replies import BoundTask, resolve_reply
from conversation.tasks import parse_task
from conversation.manager import Manager
from conversation.engines import RuleEngine
from conversation.schemas import Message
from p0.domain import DomainError
from p2.knowledge import RuleCatalog
from eval.conversation.run import Reader, SCOPE, NOW, TASK_ID

ROOT = Path(__file__).resolve().parent


def binding(sample):
    allowed = sample.get("allowed", ["quantity", "unit"])
    until = NOW + timedelta(minutes=-1 if sample.get("expired") else 15)
    candidates = [{"id":f"b{i}","household_id":SCOPE.household_id,"name":"牛奶","quantity":"5","unit":"盒",
                   "location":"冰箱","status":"ACTIVE","version":i} for i in (1,2)]
    status = sample.get("status", "needs_clarification")
    result = {"status":status,"original_text":"合成聊天任务","trace_id":"synthetic-p8",
              "reply":"请补充资料。","candidates":candidates,
              "clarification":{"revision":3,"allowed_fields":allowed,"expires_at":until.isoformat()}}
    task = parse_task({"task_id":TASK_ID,"household_id":SCOPE.household_id,"status":status,"revision":3,
        "expires_at":until.isoformat(),"draft_id":None,"result":result,"inventory_written":False},SCOPE.household_id)
    return BoundTask(scope=SCOPE,task=task)


async def check(sample):
    start = time.perf_counter()
    if sample["kind"] == "message":
        reader = Reader("牛奶")
        before = reader.data.model_dump_json()
        result = await Manager(RuleEngine(),reader,RuleCatalog.load(),now=lambda:NOW).handle(
            Message(text=sample["text"],request_id=sample["id"]),SCOPE)
        passed = (result.status == "answered" and result.runtime.model_calls == 0 and result.draft is None
                  and not result.inventory_writes and not result.shopping_writes and result.original_text == sample["text"]
                  and reader.data.model_dump_json() == before)
        observed = {"status":result.status,"model_calls":result.runtime.model_calls}
    else:
        bound = binding(sample); before = bound.model_dump_json()
        try:
            scope = SCOPE.model_copy(update={"household_id":"foreign"}) if sample.get("foreign") else SCOPE
            result = resolve_reply(bound,sample["text"],scope,NOW,selected_batch_id=sample.get("selected"))
            expected = sample["expected"]
            passed = (result.kind != "clarify" and not result.answers) if expected == "reject" else result.kind == expected
            if "answers" in sample:
                actual = dict(result.answers); wanted = dict(sample["answers"])
                if "quantity" in wanted:
                    passed &= Decimal(actual.get("quantity","-1")) == Decimal(wanted.pop("quantity"))
                    actual.pop("quantity",None)
                passed &= actual == wanted
            if "error" in sample: passed &= result.error_code == sample["error"]
            passed &= result.model_calls == 0 and bound.model_dump_json() == before
            observed = result.model_dump()
        except DomainError as exc:
            passed = sample["expected"] == "forbidden" and exc.code == "HOUSEHOLD_FORBIDDEN"
            observed = {"error_code":exc.code,"model_calls":0}
    return {"id":sample["id"],"group_id":sample["group_id"],"passed":bool(passed),"observed":observed,
            "elapsed_seconds":time.perf_counter()-start}


async def evaluate(split, output):
    all_rows = [json.loads(s) for s in (ROOT/'samples.jsonl').read_text(encoding='utf-8').splitlines()]
    dev = {r['group_id'] for r in all_rows if r['split']=='dev'}
    holdout = {r['group_id'] for r in all_rows if r['split']=='test'}
    assert len(all_rows)==150 and not dev & holdout
    rows = [await check(s) for s in all_rows if s['split']==split]
    durations = sorted(r['elapsed_seconds'] for r in rows)
    result = {"split":split,"count":len(rows),"passed":sum(r['passed'] for r in rows),"failed_ids":[r['id'] for r in rows if not r['passed']],
              "engine":"literal_rules / synthetic reader","paid_model_calls":0,"scenario_groups_isolated":True,
              "human_reviewed":False,"source":"AI-constructed synthetic chat and binding fixtures",
              "p95_offline_seconds":durations[min(len(durations)-1,int(len(durations)*.95))],
              "latency_includes_network_model_database_or_android":False,"rows":rows}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=True))
    return result['passed']==len(rows)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--split',choices=['dev','test'],required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();raise SystemExit(0 if asyncio.run(evaluate(args.split,args.output)) else 1)
