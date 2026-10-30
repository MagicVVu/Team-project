"""Interoperate with the deployed P8.5 archive and single-object inventory."""
import copy
from uuid import UUID,uuid4
from decimal import Decimal
import pytest
from sqlalchemy import select
from autonomous_fixtures import execution_state,multiple
from test_autonomous import autonomous_ai,reading,moving
from test_p85_dialogue import p85,p84,p7
from test_session_memory import start,send,ok,BASE
from test_v09_execution import headers,body as commit_body,post
from app.services import autonomous,dialogue,session_memory,memory_archive
from app.routers import agent_gateway as gateway
from app.conversation_models import ConversationTurn
from app.models import AIDraft,InventoryItem
from app.execution_models import DraftOperation


def row(db,request_id):
    return db.scalar(select(ConversationTurn).where(ConversationTurn.request_id==request_id))


def test_p85_pending_task_continues_in_autonomous_with_piece_ordinal(execution_state,p85,monkeypatch):
    client,Session,ids=execution_state
    multiple(Session,ids)
    first=ok(send(client,ids,ok(start(client,ids)),"把牛奶移到书房"))
    assert first["task"]["status"]=="needs_clarification"
    monkeypatch.setenv("AI_CONVERSATION_DIALOGUE_PROTOCOL",autonomous.PROTOCOL)
    # Install the new AI factory over the same existing scoped reader/engine.
    import httpx
    from httpx._client import AsyncClient
    from conversation.autonomous.app import create_app
    from conversation.planning import RemoteReader
    from app.main import app
    from os import environ
    ai=create_app(engine=p85[0],reader=RemoteReader("http://backend:8000",environ["BACKEND_TOOL_TOKEN"]))
    transports={"agent":httpx.ASGITransport(app=ai),"backend":httpx.ASGITransport(app=app)}
    async def dispatch(request):return await transports[request.url.host].handle_async_request(request)
    def transport(*args,**kwargs):
        kwargs["transport"]=httpx.MockTransport(dispatch);return AsyncClient(*args,**kwargs)
    monkeypatch.setattr(httpx,"AsyncClient",transport)
    count=p85[0].understanding_calls
    value=ok(send(client,ids,first,"第二件"))
    assert value["dialogue"]["protocol_version"]==autonomous.PROTOCOL and value["model_calls"]==0
    assert value["task"]["task_id"]==first["task"]["task_id"]
    assert value["task"]["result"]["draft"]["batch_id"]==first["task"]["result"]["candidates"][1]["id"]
    assert count==p85[0].understanding_calls
    with Session() as db:
        assert memory_archive.EPISODE_KEY in row(db,value["request_id"]).binding_json


def test_saved_p85_recovery_remains_p85_after_flag_switch(execution_state,p85,monkeypatch):
    client,Session,ids=execution_state
    session=ok(start(client,ids)); request_id=uuid4().hex
    original=dialogue.call
    async def crash(identity,home,stage,*args):
        if stage=="p85/resolve":raise TimeoutError()
        return await original(identity,home,stage,*args)
    monkeypatch.setattr(dialogue,"call",crash)
    assert send(client,ids,session,"把牛奶移到书房",request_id=request_id).status_code==504
    count=p85[0].understanding_calls
    monkeypatch.setattr(dialogue,"call",original)
    monkeypatch.setenv("AI_CONVERSATION_DIALOGUE_PROTOCOL",autonomous.PROTOCOL)
    snapshot=ok(client.get(BASE+"conversation-turns/"+request_id,headers=headers(),params={"household_id":str(ids["home"])}))
    assert snapshot["phase"]=="prepared" and snapshot["conversation_id"]==session["conversation_id"]
    value=ok(send(client,ids,session,"把牛奶移到书房",request_id=request_id))
    assert value["dialogue"]["protocol_version"]==dialogue.P85_PROTOCOL
    assert value["dialogue"]["recovery_model_calls"]==0 and p85[0].understanding_calls==count
    with Session() as db:assert autonomous.KEY not in row(db,request_id).binding_json


def test_autonomous_saved_result_recovers_under_p85_flag(execution_state,autonomous_ai,monkeypatch):
    client,Session,ids=execution_state;engine,_=autonomous_ai
    engine.steps=[moving()];original=autonomous.call
    async def crash(identity,home,path,*args):
        if path.endswith("/resolve"):raise TimeoutError()
        return await original(identity,home,path,*args)
    monkeypatch.setattr(autonomous,"call",crash)
    session=ok(start(client,ids));request_id=uuid4().hex
    assert send(client,ids,session,"把牛奶移到书房",request_id=request_id).status_code==503
    snapshot=ok(client.get(BASE+"conversation-turns/"+request_id,headers=headers(),params={"household_id":str(ids["home"])}))
    assert snapshot["phase"]=="prepared" and snapshot["current_conversation_revision"]==1
    monkeypatch.setattr(autonomous,"call",original)
    monkeypatch.setenv("AI_CONVERSATION_DIALOGUE_PROTOCOL",dialogue.P85_PROTOCOL)
    value=ok(send(client,ids,session,"把牛奶移到书房",request_id=request_id))
    assert value["dialogue"]["protocol_version"]==autonomous.PROTOCOL and value["dialogue"]["recovery_model_calls"]==0
    assert engine.calls==1


def test_old_memory_prepared_turn_does_not_switch_to_autonomous(execution_state,autonomous_ai,monkeypatch):
    client,Session,ids=execution_state;engine,_=autonomous_ai
    monkeypatch.delenv("AI_CONVERSATION_DIALOGUE_PROTOCOL")
    original=gateway.run_message
    async def crash(*args,**kwargs):raise RuntimeError("synthetic interruption")
    monkeypatch.setattr(gateway,"run_message",crash)
    session=ok(start(client,ids));request_id=uuid4().hex
    assert send(client,ids,session,"牛奶在哪里",request_id=request_id).status_code==500
    monkeypatch.setattr(gateway,"run_message",original)
    monkeypatch.setenv("AI_CONVERSATION_DIALOGUE_PROTOCOL",autonomous.PROTOCOL)
    value=ok(send(client,ids,session,"牛奶在哪里",request_id=request_id))
    assert value.get("dialogue") is None and engine.calls==0
    with Session() as db:assert autonomous.KEY not in row(db,request_id).binding_json


def test_archive_completion_old_topic_and_original_reference_survive(execution_state,autonomous_ai):
    client,Session,ids=execution_state;engine,_=autonomous_ai
    engine.steps=[reading(finish_after_resolve=True)]
    first=ok(send(client,ids,ok(start(client,ids)),"核对牛奶数量"))
    state=first
    for _ in range(11):
        engine.steps=[{"action":"resolve","plan":{"speech_act":"discuss","social_reply":"可以先整理常用的台面。"}}]
        state=ok(send(client,ids,state,"暂时聊聊整理"))
    with Session.begin() as db:
        obj=db.get(InventoryItem,ids["batch"]);obj.storage_location="新层";obj.version+=1
    async def recall(payload):
        assert first["request_id"] not in {t["request_id"] for t in payload["context"]["history"]}
        ep=next(e for e in payload["retrieved_episodes"] if e["request_id"]==first["request_id"])
        return {"action":"resolve","finish_after_resolve":True,"plan":{"speech_act":"question","memory_id":ep["memory_id"],
            "selector":{"use_reference":True},"reads":[{"kind":"location"}]}}
    engine.steps=[recall]
    value=ok(send(client,ids,state,"回到最早的牛奶，现在放在哪里"))
    assert "新层" in value["reply"]
    with Session() as db:
        original=row(db,first["request_id"]).binding_json[memory_archive.EPISODE_KEY]
        current=row(db,value["request_id"])
        attested=next(e for e in current.binding_json["payload"]["archive"]["episodes"] if e["request_id"]==first["request_id"])
        assert original["reference"]==attested["reference"]
        episode=current.binding_json[memory_archive.EPISODE_KEY]
        assert episode["reply"]==value["reply"]
        assert gateway.datetime.fromisoformat(episode["created_at"])>=gateway.datetime.fromisoformat(episode["reference"]["issued_at"])


@pytest.mark.parametrize("field",["selected_ids","text","reference","source_text_sha256"])
def test_shared_archive_validator_rejects_forged_ai_memory(execution_state,autonomous_ai,monkeypatch,field):
    client,Session,ids=execution_state;engine,_=autonomous_ai
    engine.steps=[reading(finish_after_resolve=True)];original=autonomous.call
    async def forged(identity,home,path,*args):
        value=await original(identity,home,path,*args)
        if path.endswith("/run"):
            frame=value["resolved"]
            if field=="selected_ids":frame["memory"][field]=["foreign-memory"]
            elif field=="source_text_sha256":frame["memory_delta"][field]="0"*64
            else:frame["memory_delta"]["episode"][field]={"batch_id":"forged"} if field=="reference" else "forged"
        return value
    monkeypatch.setattr(autonomous,"call",forged)
    value=send(client,ids,ok(start(client,ids)),"核对牛奶数量")
    assert value.status_code==503
    with Session() as db:
        assert not db.query(ConversationTurn).filter(ConversationTurn.phase=="completed",ConversationTurn.original_text!="").count()


def test_partial_physical_consumption_stays_refused_during_recovery(execution_state,autonomous_ai,monkeypatch):
    client,Session,ids=execution_state;engine,requests=autonomous_ai
    engine.steps=[{"action":"resolve","plan":{"speech_act":"request","action":"CONSUME","write_count":1,
        "selector":{"name":"牛奶"},"amount_mode":"half"}}]
    original=session_memory.complete
    def crash(*args,**kwargs):raise RuntimeError("synthetic interruption before completion")
    monkeypatch.setattr(session_memory,"complete",crash)
    session=ok(start(client,ids));request_id=uuid4().hex
    assert send(client,ids,session,"牛奶喝了一半，记一下",request_id=request_id).status_code==500
    monkeypatch.setattr(session_memory,"complete",original)
    value=ok(send(client,ids,session,"牛奶喝了一半，记一下",request_id=request_id))
    assert value["kind"]=="needs_input" and value["error_code"]=="SINGLE_OBJECT_CONSUMPTION_REQUIRED"
    assert value["task"] is None and engine.calls==1
    assert not any(path.endswith("/resolve") for _,path in requests)
    with Session() as db:assert db.get(InventoryItem,ids["batch"]).status=="ACTIVE" and db.query(AIDraft).count()==0


def test_whole_object_consumption_and_verified_state(execution_state,autonomous_ai):
    client,Session,ids=execution_state;engine,_=autonomous_ai
    engine.steps=[{"action":"resolve","plan":{"speech_act":"request","action":"CONSUME","write_count":1,
        "selector":{"name":"牛奶"},"amount_mode":"all"}}]
    value=ok(send(client,ids,ok(start(client,ids)),"牛奶全部用完了，记消耗"))
    assert value["task"]["status"]=="needs_confirmation" and Decimal(value["task"]["result"]["draft"]["quantity"])==1
    assert ok(post(client,value["task"]["draft_id"],commit_body(task_revision=value["task"]["revision"])))['status']=="committed"
    status=ok(send(client,ids,value,"执行了吗"))
    assert "执行成功" in status["reply"] and status["model_calls"]==0
    with Session() as db:assert db.get(InventoryItem,ids["batch"]).quantity==0 and db.query(DraftOperation).count()==1


def test_measured_add_preview_specification_and_real_commit(execution_state,autonomous_ai):
    client,Session,ids=execution_state;engine,_=autonomous_ai
    text="新增500g肉放到冰箱"
    engine.steps=[{"action":"resolve","plan":{"speech_act":"request","action":"ADD","write_count":1,
        "fields":{"name":{"value":"肉","quote":"肉"},"quantity":{"value":"500","quote":"500g"},
        "unit":{"value":"g","quote":"500g"},"location":{"value":"冰箱","quote":"冰箱"}}}}]
    value=ok(send(client,ids,ok(start(client,ids)),text))
    result=value["task"]["result"]
    assert Decimal(result["draft"]["quantity"])==500 and result["draft"]["unit"]=="g"
    assert Decimal(result["preview"]["after"]["quantity"])==1 and result["preview"]["after"]["unit"]=="份"
    receipt=ok(post(client,value["task"]["draft_id"],commit_body(task_revision=value["task"]["revision"])))
    assert receipt["result"]["created_count"]==1
    with Session() as db:
        item=db.scalar(select(InventoryItem).where(InventoryItem.name=="肉"))
        assert item.unit=="份" and item.specification=="500g"


def test_current_contract_and_legacy_counter_validation(execution_state):
    from test_session_memory import test_local_memory_backend_contract_matches_factory
    test_local_memory_backend_contract_matches_factory(execution_state)


def test_model_failure_preserves_stopped_status_for_current_frontend(execution_state,autonomous_ai):
    from p0.engines import EngineError
    client,Session,ids=execution_state;engine,_=autonomous_ai
    engine.steps=[EngineError("MODEL_UNAVAILABLE")]
    value=ok(send(client,ids,ok(start(client,ids)),"核对牛奶数量"))
    assert value["dialogue"]["status"]=="stopped"
    assert value["dialogue"]["stop_reason"]=="ai_unavailable"
    assert value["dialogue"]["loop_stop_reason"]=="model_error" and engine.calls==1


def test_no_progress_reason_is_understood_by_current_frontend(execution_state,autonomous_ai):
    client,Session,ids=execution_state;engine,_=autonomous_ai
    engine.steps=[reading(),reading()]
    value=ok(send(client,ids,ok(start(client,ids)),"核对牛奶数量"))
    assert value["dialogue"]["status"]=="stopped"
    assert value["dialogue"]["stop_reason"]=="insufficient_information"
    assert value["dialogue"]["loop_stop_reason"]=="repeated_plan" and engine.calls==2
