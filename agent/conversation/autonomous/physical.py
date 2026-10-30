"""Projection of the current single-object backend contract, never a write."""
import re
from decimal import Decimal
from p0.domain import SCALES
from ..p85.schemas import P85Resolved

CONSUMPTION_MESSAGE="当前每条库存是一件实物，只能登记整件消耗或丢弃；重量和容量仅作规格，不能按半件扣减。请明确要处理哪一件，或核对是否已整件用完。尚未写入。"
REFERENCE_QUERY=re.compile(r"(?:接着|继续)?(?:之前|刚才)?(?:那|这)(?:一)?(?:件|份|个|批)[，, ]*(?:查|查询|核对|看看)?(?:它|这件|那件)?(?:的)?(位置|在哪|在哪里|在什么地方|数量|还剩多少)[?？。!！]?")


def refusal(body, memory, code, reply, filled):
    return P85Resolved(original_text=body.text,kind="needs_input",reply=reply,facts={"f0":reply},
        error_code=code,memory=memory,filled_fields=dict(filled),expression_required=False)


def precheck(body, plan, memory, filled):
    consumed=bool(re.search(r"消耗|喝(?:完|掉|了|光)|吃(?:完|掉|了|光)|用(?:完|掉|了|光)",body.text))
    discarded=bool(re.search(r"丢弃|扔掉|扔了|丢掉|报废",body.text))
    if (plan.action=="DISCARD" and consumed and not discarded or
            plan.action=="CONSUME" and discarded and not consumed):
        return refusal(body,memory,"ACTION_SEMANTIC_CONFLICT",
            "当前动作与原文的消耗/丢弃含义不一致，请按本轮原文重新核对动作；尚未生成变更。",filled)
    if plan.action in {"CONSUME","DISCARD"}:
        half=plan.amount_mode=="half" and re.search(r"一半|半数|50[%％]",body.text)
        specified=plan.fields.get("quantity")
        amount=Decimal(filled["quantity"]) if specified and "quantity" in filled else None
        if half or amount is not None and amount!=1:
            return refusal(body,memory,"SINGLE_OBJECT_CONSUMPTION_REQUIRED",CONSUMPTION_MESSAGE,filled)
    active=body.context.active.task if body.context.active else None
    command=active.result.draft if active and active.result else None
    if (plan.speech_act=="correction" and command and command.action in {"CONSUME","DISCARD"}
            and plan.action in {None,command.action} and set(plan.fields)&{"quantity","unit"}):
        return refusal(body,memory,"SINGLE_OBJECT_AMOUNT_PROTECTED",
            "整件消耗或丢弃草稿的数量和单位不能单独修改。请核对物品，若对象不对请重新选择；尚未执行。",filled)
    return None


def project(body, frame, plan):
    command=(frame.result or {}).get("draft")
    if not command:
        asks_measurement=re.search(r"多少\s*(?:克|千克|公斤|毫升|升|g\b|kg\b|ml\b|L\b)|(?:重量|容量|规格).*(?:多少|是什么|是多大)",body.text,re.I)
        rows=(frame.result or {}).get("facts",[])
        if plan.speech_act=="question" and asks_measurement and rows:
            note="当前AI读取接口只提供逐件登记信息，没有提供重量或容量规格，无法把物品数换算成克数或毫升。请查看物品详情的规格或补充标签；尚未生成变更。"
            frame.facts[f"f{len(frame.facts)}"]=note
            frame.reply="\n".join(frame.facts.values())
            frame.kind="needs_input";frame.error_code="SPECIFICATION_READ_UNAVAILABLE";frame.expression_required=False
        return frame
    action=command["action"]
    if action in {"CONSUME","DISCARD"} and Decimal(command["quantity"])!=1:
        return refusal(body,frame.memory,"SINGLE_OBJECT_CONSUMPTION_REQUIRED",CONSUMPTION_MESSAGE,frame.filled_fields)
    if action!="ADD": return frame
    quantity=Decimal(command["quantity"])
    measured=command["unit"] in SCALES
    if not measured and (quantity!=quantity.to_integral_value() or quantity>10000):
        return refusal(body,frame.memory,"OBJECT_COUNT_INVALID",
            "新增物品数须为1至10000的整数；重量或容量会作为一份物品的规格保存，请核对输入。尚未写入。",frame.filled_fields)
    count=1 if measured else int(quantity)
    unit="份" if measured else command["unit"]
    specification=format(quantity.normalize(),'f')+command["unit"] if measured else None
    if measured and frame.result.get("preview"):
        after=frame.result["preview"].get("after")
        if after: after.update(quantity="1",unit="份")
        frame.result["preview"]["quantity_delta"]="1"
    frame.evidence.append({"kind":"physical_intake_projection","created_count":count,
        "per_object_quantity":1,"inventory_unit":unit,"specification":specification,
        "input_quantity":str(quantity),"input_unit":command["unit"]})
    sentence=f"确认后将新增{count}件独立物品，单位为{unit}"+(f"，规格为{specification}" if specification else "")+"；尚未写入。"
    frame.facts[f"f{len(frame.facts)}"]=sentence
    frame.reply="\n".join(frame.facts.values())
    return frame
