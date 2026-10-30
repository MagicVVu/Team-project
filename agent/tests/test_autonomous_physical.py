from decimal import Decimal
import pytest
from conversation.autonomous.runner import run as process
from conversation.autonomous.schemas import RunRequest
from test_conversation import service,reference,run,SCOPE
from test_session_memory import context
from test_autonomous import Script


def execute(plan,text):
    owner,_,reader=service()
    owner.inventory_model="single-object-1"
    reader.data.items[0].batches[0].quantity=Decimal(1)
    owner.engine=Script([{"action":"resolve","plan":plan}])
    body=RunRequest(text=text,request_id="physical",context=context(reference=reference()))
    before=reader.data.model_dump_json()
    value=run(process(owner,body,SCOPE))
    assert before==reader.data.model_dump_json()
    return value,owner.engine,reader


@pytest.mark.parametrize("action",["CONSUME","DISCARD"])
def test_half_object_is_refused_before_tool_read(action):
    value,engine,reader=execute({"speech_act":"request","action":action,"write_count":1,
        "selector":{"use_reference":True},"amount_mode":"half"},"把它消耗一半" if action=="CONSUME" else "把它丢弃一半")
    assert value.status=="needs_input" and value.error_code=="SINGLE_OBJECT_CONSUMPTION_REQUIRED"
    assert value.resolved.result is None and reader.batch_reads==0 and engine.calls==1


@pytest.mark.parametrize("amount,unit",[("500","g"),("1.5","L"),("1","吨")])
def test_measured_intake_preserves_input_and_projects_one_portion(amount,unit):
    text=f"新增{amount}{unit}大米放厨房"
    plan={"speech_act":"request","action":"ADD","write_count":1,"fields":{
        "name":{"value":"大米","quote":"大米"},"quantity":{"value":amount,"quote":amount+unit},
        "unit":{"value":unit,"quote":amount+unit},"location":{"value":"厨房","quote":"厨房"}}}
    value,_,_=execute(plan,text)
    assert value.status=="needs_confirmation"
    draft=value.resolved.result["draft"];preview=value.resolved.result["preview"]
    assert Decimal(draft["quantity"])==Decimal(amount) and draft["unit"]==unit
    assert preview["after"]["quantity"]=="1" and preview["after"]["unit"]=="份"
    evidence=next(e for e in value.resolved.evidence if e["kind"]=="physical_intake_projection")
    assert evidence["created_count"]==1 and evidence["specification"]==amount+unit


@pytest.mark.parametrize("amount",["1.5","10001"])
def test_invalid_object_count_is_not_an_executable_draft(amount):
    text=f"新增{amount}件衣服放厨房"
    plan={"speech_act":"request","action":"ADD","write_count":1,"fields":{
        "name":{"value":"衣服","quote":"衣服"},"quantity":{"value":amount,"quote":amount+"件"},
        "unit":{"value":"件","quote":amount+"件"},"location":{"value":"厨房","quote":"厨房"}}}
    value,_,_=execute(plan,text)
    assert value.error_code=="OBJECT_COUNT_INVALID" and value.resolved.result is None


@pytest.mark.parametrize("text",["第二件","选第二份","第二份在哪里","第2件的位置"])
def test_piece_and_portion_ordinals_are_zero_model(text):
    owner,_,reader=service(multiple=True)
    owner.inventory_model="single-object-1";owner.engine=Script([])
    body=RunRequest(text=text,request_id="ordinal",context=context(choices=[reference(),reference(batch_id="b2")]))
    value=run(process(owner,body,SCOPE))
    assert value.model_calls==0 and value.status=="completed"
    assert value.resolved.result["facts"][0]["id"]=="b2" and value.original_text==text


@pytest.mark.parametrize("text,wrong,right",[("这件牛奶全部喝完了，登记消耗","DISCARD","CONSUME"),
    ("把这件牛奶全部丢弃","CONSUME","DISCARD")])
def test_semantic_action_conflict_is_repaired_before_draft(text,wrong,right):
    owner,_,reader=service();owner.inventory_model="single-object-1"
    reader.data.items[0].batches[0].quantity=Decimal(1)
    def step(action):return {"action":"resolve","plan":{"speech_act":"request","action":action,"write_count":1,
        "selector":{"use_reference":True},"amount_mode":"all"}}
    owner.engine=Script([step(wrong),step(right)])
    result=run(process(owner,RunRequest(text=text,request_id="semantic",context=context(reference=reference())),SCOPE))
    assert result.model_calls==2 and result.resolved.result["draft"]["action"]==right
    assert owner.engine.payloads[1]["observations"]["error_code"]=="ACTION_SEMANTIC_CONFLICT"
    assert reader.batch_reads==1


def test_described_expired_piece_is_zero_model_reselection():
    from datetime import timedelta
    from test_conversation import NOW
    owner,_,reader=service();owner.inventory_model="single-object-1";owner.engine=Script([])
    expired=reference(issued_at=NOW-timedelta(minutes=16),expires_at=NOW-timedelta(minutes=1))
    text="接着之前那一件，查它的位置"
    result=run(process(owner,RunRequest(text=text,request_id="expired-piece",context=context(reference=expired)),SCOPE))
    assert result.model_calls==0 and result.error_code=="REFERENCE_EXPIRED" and result.status=="needs_input"
    assert reader.batch_reads==0


def test_count_projection_cannot_answer_missing_capacity_specification():
    plan={"speech_act":"question","selector":{"use_reference":True},"reads":[{"kind":"quantity"}]}
    value,engine,reader=execute(plan,"这份牛奶具体有多少毫升")
    assert value.status=="needs_input" and value.error_code=="SPECIFICATION_READ_UNAVAILABLE"
    assert "登记数量 1" in value.reply
    assert Decimal(value.resolved.result["facts"][0]["quantity"])==1
    assert "没有提供重量或容量规格" in value.reply and engine.calls==1
