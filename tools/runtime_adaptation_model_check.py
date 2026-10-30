"""Synthetic current-contract model checks; no server inventory or business I/O."""
import asyncio
import argparse
import json
import math
import os
from pathlib import Path
import sys
from decimal import Decimal

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"agent"))
from conversation.autonomous.runner import run
from conversation.autonomous.schemas import RunRequest
from conversation.engines import DeepSeekEngine
from eval.dialogue.run import fixture,SCOPE

CASES=[
 ("quantity","reference","这件牛奶现在还在吗，登记数量是多少","query"),
 ("location","reference","接着刚才那一件，它现在放在哪里","query"),
 ("compound","empty","核对牛奶的数量，也告诉我存放位置","query"),
 ("half","reference","这件我喝掉了一半，帮我记消耗","partial"),
 ("discard_half","reference","把这一件丢掉一半，帮我记录","partial"),
 ("half_literal","reference","我喝了0.5盒牛奶，记录一下","partial"),
 ("consume","reference","这件牛奶已经全部喝完了，请记录整件消耗","CONSUME"),
 ("move","reference","把这一件牛奶移动到书房","MOVE"),
 ("measured_g","empty","新增500g肉放冰箱","ADD_PORTION"),
 ("measured_L","empty","我买了1.5L牛奶放冰箱，请登记","ADD_PORTION"),
 ("counted","empty","新增2件衣服放在储物柜","ADD_COUNT"),
 ("bad_count","empty","新增1.5个苹果放厨房","invalid_count"),
 ("ordinal","multiple","第二件在哪里","query"),
 ("choices","multiple","牛奶有好几件，帮我把牛奶移到书房，先让我选择","needs_input"),
 ("social","empty","整理这些东西真累，有没有轻松点的办法","social"),
 ("expired","expired","接着之前那一件，查它的位置","needs_input"),
]


def check(expected,result):
    domain=result.resolved.result if result.resolved else None
    domain=domain or {};command=domain.get("draft") or {}
    if expected=="query":return domain.get("status")=="answered" and bool(domain.get("facts"))
    if expected=="partial":return not command and result.status=="needs_input"
    if expected=="invalid_count":return not command and result.status=="needs_input"
    if expected=="needs_input":return not command and result.status=="needs_input"
    if expected=="social":return not command and result.status=="completed"
    if expected=="ADD_PORTION":return command.get("action")=="ADD" and (domain.get("preview") or {}).get("after",{}).get("unit")=="份"
    if expected=="ADD_COUNT":return command.get("action")=="ADD" and Decimal(command.get("quantity",0))==2
    return command.get("action")==expected and (expected!="CONSUME" or Decimal(command.get("quantity",0))==1)


async def main(label):
    if not os.getenv("DEEPSEEK_API_KEY"):raise SystemExit("MODEL_NOT_CONFIGURED; no request made")
    target=ROOT/"reports/p86-autonomous/adaptation-20261030"/(label+".jsonl")
    if target.exists():raise SystemExit("Existing real model evidence will not be overwritten")
    target.parent.mkdir(parents=True,exist_ok=True)
    rows=[]
    with target.open('x',encoding='utf-8') as stream:
        for ident,profile,text,expected in CASES:
            engine=DeepSeekEngine()
            owner,ctx,reader=fixture(profile,engine)
            owner.inventory_model="single-object-1"
            for item in reader.data.items:
                for batch in item.batches:batch.quantity=Decimal(1)
            body=RunRequest(text=text,request_id="synthetic-current-"+ident,context=ctx)
            try:
                result=await run(owner,body,SCOPE)
                record={"id":ident,"text":text,"expected":expected,"passed":check(expected,result),"result":result.model_dump(mode='json')}
            except Exception as error:record={"id":ident,"text":text,"expected":expected,"passed":False,"error":getattr(error,'code',type(error).__name__)}
            rows.append(record);stream.write(json.dumps(record,ensure_ascii=False)+'\n');stream.flush()
            print(json.dumps({"id":ident,"passed":record['passed'],"calls":(record.get('result') or {}).get('model_calls')}),flush=True)
    times=sorted(r['result']['elapsed_ms'] for r in rows if 'result' in r)
    summary={"inventory_model":"single-object-1","source":"new_synthetic_current_contract_cases",
        "cases":len(rows),"passed":sum(r['passed'] for r in rows),"human_review":"pending","independent_blind_eval":False,
        "calls":sum(r.get('result',{}).get('model_calls',0) for r in rows),"p95_ms":times[math.ceil(len(times)*.95)-1] if times else None,
        "production_inventory_accessed":False,"server_modified":False,"app_joint_acceptance":False}
    (target.parent/(label+'-summary.json')).write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--label',default='current-model')
    asyncio.run(main(parser.parse_args().label))
