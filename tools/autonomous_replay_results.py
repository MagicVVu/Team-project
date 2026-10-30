"""Replay saved synthetic provider plans against final code, with zero API calls."""
import asyncio
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"agent"))
from conversation.autonomous.runner import run,digest,QUESTIONS
from conversation.autonomous.schemas import RunRequest
from eval.autonomous.run import score
from eval.dialogue.run import fixture,SCOPE


class Replay:
    def __init__(self,steps): self.steps=list(steps)
    async def autonomous_step(self,payload): return self.steps.pop(0)


async def main():
    rows=[json.loads(line) for line in (ROOT/"reports/p86-autonomous/initial-20261029/real-first.jsonl").read_text(encoding="utf-8").splitlines()]
    checks=[]
    for row in rows:
        if row["variant"]!="autonomous": continue
        case,saved=row["case"],row["output"]
        plans={digest(p):p for p in [*saved["verified_plans"],*([saved["plan"]] if saved["plan"] else [])]}
        steps=[]
        for step in saved["trace"]:
            if not step["model_call"]:continue
            action=step["action"]
            value={"action":action}
            if action=="resolve": value["plan"]=plans[step["plan_sha256"]]
            if action=="ask":
                value["clarification"]=next(k for k,v in QUESTIONS.items() if saved["reply"].endswith(v))
            steps.append(value)
        if steps and steps[-1]["action"]=="resolve" and saved["status"]=="completed":
            steps[-1]["finish_after_resolve"]=True
        engine=Replay(steps);owner,ctx,_=fixture(case["profile"],engine)
        result=await run(owner,RunRequest(text=case["text"],request_id="replay-"+case["id"],context=ctx),SCOPE)
        passed=score(case,result.resolved.model_dump(mode="json") if result.resolved else None,result.status,result.reply)
        checks.append({"case_id":case["id"],"passed":passed,"stop_reason":result.stop_reason})
    value={"source":"saved_real_provider_decisions_replayed","actual_new_model_calls":0,
        "cases":len(checks),"passed":sum(c["passed"] for c in checks),"checks":checks,
        "independent_blind_evaluation":False,"production_accessed":False}
    (ROOT/"reports/p86-autonomous/initial-20261029/final-plan-replay.json").write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in value.items() if k!="checks"}))
    if not all(c["passed"] for c in checks): raise SystemExit(1)


if __name__=="__main__":asyncio.run(main())
