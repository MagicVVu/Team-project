"""Authenticated ASGI -> real AI stages -> SQLite task/draft persistence."""
from uuid import UUID, uuid4
from datetime import timedelta
from decimal import Decimal
import asyncio
import pytest
from sqlalchemy import select
from test_v09_execution import execution_state, headers, body as commit_body, post
from test_backend_p2_conversation import p7, multiple
from test_session_memory import start, send, ok, BASE
from app.models import AIDraft, AITask, InventoryItem
from app.conversation_models import ConversationTurn
from app.execution_models import DraftOperation
from app.services import dialogue


@pytest.fixture
def p84(p7,monkeypatch):
    from conversation.dialogue_schemas import Plan
    engine=p7[0]
    engine.understanding_calls=engine.response_calls=0
    async def understand(text,ctx):
        engine.understanding_calls+=1
        if text=="你好": return Plan(speech_act="social",social_reply="你好！今天想整理家里的什么？")
        if text=="先别改，我只是问问": return Plan(speech_act="negation",social_reply="可以先核对，不会因为讨论执行变更。")
        if text=="我喝了一半": return Plan(speech_act="request",action="CONSUME",write_count=1,amount_mode="half",selector={"use_reference":True})
        if text=="牛奶喝了一半，帮我登记": return Plan(speech_act="request",action="CONSUME",write_count=1,amount_mode="half",selector={"name":"牛奶"})
        if text=="还是两盒吧": return Plan(speech_act="correction",fields={"quantity":{"value":"2","quote":"两盒"},"unit":{"value":"盒","quote":"两盒"}})
        if text=="纸巾在哪": return Plan(speech_act="question",selector={"name":"纸巾"},reads=[{"kind":"location"}])
        if text=="牛奶多少放哪": return Plan(speech_act="question",selector={"name":"牛奶"},reads=[{"kind":"quantity"},{"kind":"location"}])
        return Plan(speech_act="request",action="MOVE",write_count=1,selector={"name":"牛奶"},fields={"to_location":{"value":"书房","quote":"书房"}})
    async def respond(text,frame):
        engine.response_calls+=1
        return "好的，"+"\n".join("{{fact:"+k+"}}" for k in frame.facts)
    monkeypatch.setattr(engine,"dialogue_understand",understand,raising=False)
    monkeypatch.setattr(engine,"dialogue_respond",respond,raising=False)
    monkeypatch.setenv("AI_CONVERSATION_DIALOGUE_PROTOCOL",dialogue.PROTOCOL)
    return engine


def test_new_flow_greeting_then_query_half_edit_and_state(execution_state,p84):
    client,Session,ids=execution_state
    with Session.begin() as db: db.get(InventoryItem,ids["batch"]).quantity=6
    session=ok(start(client,ids))
    social=ok(send(client,ids,session,"你好"))
    assert social["task"] is None and social["model_calls"]==2
    query=ok(send(client,ids,social,"牛奶多少放哪"))
    assert query["task"]["status"]=="answered" and "登记数量" in query["reply"]
    half=ok(send(client,ids,query,"我喝了一半"))
    assert Decimal(half["task"]["result"]["draft"]["quantity"])==3
    assert half["dialogue"]["calls"]=={"understanding":1,"response":1,"total":2}
    with Session() as db:
        original_expiry=db.get(AITask,UUID(half["task"]["task_id"])).expires_at
    edit=ok(send(client,ids,half,"还是两盒吧"))
    assert edit["kind"]=="edit" and edit["task"]["task_id"]==half["task"]["task_id"]
    assert edit["task"]["revision"]==half["task"]["revision"]+1
    assert Decimal(edit["task"]["result"]["draft"]["quantity"])==2
    explained=ok(send(client,ids,edit,"为什么还没移动"))
    assert explained["model_calls"]==0 and "待确认" in explained["reply"]
    chat=ok(send(client,ids,explained,"先别改，我只是问问"))
    assert chat["active_task"]["task"]["task_id"]==edit["task"]["task_id"]
    with Session() as db:
        assert db.get(InventoryItem,ids["batch"]).quantity==6
        assert db.query(DraftOperation).count()==0
        task=db.get(AITask,UUID(edit["task"]["task_id"]))
        assert timedelta(0)<=original_expiry-task.expires_at<timedelta(seconds=1)
        row=db.scalar(select(ConversationTurn).where(ConversationTurn.request_id==edit["request_id"]))
        assert row.binding_json["dialogue_v1"]["resolved"]["kind"]=="edit"
    receipt=ok(post(client,edit["task"]["draft_id"],commit_body(task_revision=edit["task"]["revision"],draft_revision=2)))
    assert receipt["status"]=="committed"
    done=ok(send(client,ids,chat,"执行了吗"))
    assert "执行成功" in done["reply"] and done["model_calls"]==0
    forbidden_edit=ok(send(client,ids,done,"还是两盒吧"))
    assert forbidden_edit["kind"]=="needs_input" and "执行成功" in forbidden_edit["reply"]


def test_duplicate_and_cloud_recovery_never_call_again(execution_state,p84):
    client,Session,ids=execution_state
    session=ok(start(client,ids)); request_id=uuid4().hex
    first=ok(send(client,ids,session,"牛奶多少放哪",request_id=request_id))
    count=(p84.understanding_calls,p84.response_calls)
    assert ok(send(client,ids,session,"牛奶多少放哪",request_id=request_id))==first
    recovered=ok(client.get(BASE+"conversation-turns/"+request_id,headers=headers(),params={"household_id":str(ids["home"])}))
    assert recovered["phase"]=="completed" and (p84.understanding_calls,p84.response_calls)==count


def test_pending_task_survives_other_item_query(execution_state,p84):
    client,Session,ids=execution_state
    moved=ok(send(client,ids,ok(start(client,ids)),"把牛奶移到书房"))
    other=ok(send(client,ids,moved,"纸巾在哪"))
    assert other["active_task"]["task"]["task_id"]==moved["task"]["task_id"]


def test_response_failure_delivers_saved_verified_result(execution_state,p84,monkeypatch):
    client,Session,ids=execution_state
    async def fail(*args): raise ValueError("synthetic rendering failure")
    monkeypatch.setattr(p84,"dialogue_respond",fail)
    result=ok(send(client,ids,ok(start(client,ids)),"把牛奶移到书房"))
    assert result["task"]["status"]=="needs_confirmation" and result["dialogue"]["fallback_used"]
    assert result["model_calls"]==2


def test_understood_crash_recovers_without_model(execution_state,p84,monkeypatch):
    client,Session,ids=execution_state
    original=dialogue.call
    async def crash(identity,home,stage,*args):
        if stage=="resolve": raise TimeoutError()
        return await original(identity,home,stage,*args)
    session=ok(start(client,ids)); request_id=uuid4().hex
    monkeypatch.setattr(dialogue,"call",crash)
    assert send(client,ids,session,"把牛奶移到书房",request_id=request_id).status_code==504
    count=p84.understanding_calls
    monkeypatch.setattr(dialogue,"call",original)
    result=ok(send(client,ids,session,"把牛奶移到书房",request_id=request_id))
    assert result["task"]["status"]=="needs_confirmation"
    assert result["dialogue"]["recovery_model_calls"]==0 and p84.understanding_calls==count and p84.response_calls==0


def test_opt_in_capability_and_public_input_is_unchanged(execution_state,p84):
    client,Session,ids=execution_state
    caps=ok(client.get(BASE+"execution-capabilities",headers=headers()))
    assert caps["conversation_dialogue_protocol"]==dialogue.PROTOCOL
    assert send(client,ids,ok(start(client,ids)),"你好",history=[]).status_code==422


def test_multi_batch_half_then_select_is_zero_model_and_exact(execution_state,p84):
    client,Session,ids=execution_state
    multiple(Session,ids)
    first=ok(send(client,ids,ok(start(client,ids)),"牛奶喝了一半，帮我登记"))
    assert first["task"]["status"]=="needs_clarification",first
    count=(p84.understanding_calls,p84.response_calls)
    chosen=ok(send(client,ids,first,"第二个"))
    assert chosen["kind"]=="clarify" and chosen["model_calls"]==0
    assert chosen["task"]["result"]["draft"]["batch_id"]==first["task"]["result"]["candidates"][1]["id"]
    assert Decimal(chosen["task"]["result"]["draft"]["quantity"])==Decimal(first["task"]["result"]["candidates"][1]["quantity"])/2
    assert count==(p84.understanding_calls,p84.response_calls)


def test_ordinal_followup_query_has_attested_reference(execution_state,p84):
    client,Session,ids=execution_state;multiple(Session,ids)
    query=ok(send(client,ids,ok(start(client,ids)),"牛奶多少放哪"))
    selected=ok(send(client,ids,query,"第二批在哪里"))
    assert selected["model_calls"]==0
    assert selected["task"]["result"]["facts"][0]["id"]==query["task"]["result"]["facts"][1]["id"]


def test_lost_understanding_never_retries_paid_request(execution_state,p84,monkeypatch):
    client,Session,ids=execution_state
    original=dialogue.call; calls=[]
    async def lost(identity,home,stage,*args):
        calls.append(stage)
        if stage=="understand":raise TimeoutError()
        return await original(identity,home,stage,*args)
    monkeypatch.setattr(dialogue,"call",lost)
    session=ok(start(client,ids)); request_id=uuid4().hex
    assert send(client,ids,session,"你好",request_id=request_id).status_code==504
    assert send(client,ids,session,"你好",request_id=request_id).status_code==409
    recovery=ok(client.get(BASE+"conversation-turns/"+request_id,headers=headers(),params={"household_id":str(ids["home"])}))
    assert recovery["phase"]=="result_unknown" and calls==["understand"]


def test_lost_expression_uses_saved_fallback(execution_state,p84,monkeypatch):
    import httpx
    client,Session,ids=execution_state
    original=dialogue.call
    async def lost(identity,home,stage,*args):
        if stage=="respond":raise httpx.ReadTimeout("synthetic timeout")
        return await original(identity,home,stage,*args)
    monkeypatch.setattr(dialogue,"call",lost)
    value=ok(send(client,ids,ok(start(client,ids)),"把牛奶移到书房"))
    assert value["task"]["status"]=="needs_confirmation" and value["dialogue"]["fallback_used"]
    assert value["model_calls"]==2
    with Session() as db:
        row=db.scalar(select(ConversationTurn).where(ConversationTurn.request_id==value["request_id"]))
        assert row.binding_json["dialogue_v1"]["response_started"] and row.phase=="completed"


def test_confirm_during_correction_never_overwrites_receipt(execution_state,p84,monkeypatch):
    client,Session,ids=execution_state
    client._transport.raise_server_exceptions=True
    with Session.begin() as db:db.get(InventoryItem,ids["batch"]).quantity=6
    queried=ok(send(client,ids,ok(start(client,ids)),"牛奶多少放哪"))
    half=ok(send(client,ids,queried,"我喝了一半"))
    original=dialogue.call
    async def confirm_first(identity,home,stage,payload,seconds):
        if stage=="respond" and payload["resolved"]["kind"]=="edit":
            receipt=ok(await asyncio.to_thread(post,client,half["task"]["draft_id"],commit_body(task_revision=half["task"]["revision"])))
            assert receipt["status"]=="committed"
        return await original(identity,home,stage,payload,seconds)
    monkeypatch.setattr(dialogue,"call",confirm_first)
    changed=ok(send(client,ids,half,"还是两盒吧"))
    assert changed["kind"]=="needs_input" and changed["active_task"]["execution"]["status"]=="committed"
    with Session() as db:
        assert db.get(InventoryItem,ids["batch"]).quantity==3
        assert db.query(DraftOperation).count()==1
        draft=db.scalar(select(AIDraft).where(AIDraft.task_id==UUID(half["task"]["task_id"])))
        assert draft.revision==1 and Decimal(draft.command_json["quantity"])==3
