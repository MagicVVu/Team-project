"""Authenticated HTTP -> real autonomous AI -> existing task/draft gateway."""
import asyncio
import sys
from pathlib import Path
from uuid import uuid4, UUID
from datetime import timedelta
from decimal import Decimal
import httpx
import pytest
from sqlalchemy import select
from test_v09_execution import headers, body as commit_body, post
from autonomous_fixtures import execution_state, multiple
from test_session_memory import start, send, ok, BASE
from app.main import app
from app.models import AITask, AIDraft, InventoryItem, HouseholdMember
from app.conversation_models import ConversationTurn, ConversationBinding
from app.execution_models import DraftOperation
from app.services import autonomous
from app.routers import agent_gateway as gateway


@pytest.fixture
def autonomous_ai(execution_state, monkeypatch):
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"agent"))
    from conversation.autonomous.app import create_app
    from conversation.engines import RuleEngine
    from conversation.planning import RemoteReader
    class Engine(RuleEngine):
        calls=0
        steps=[]
        async def autonomous_step(self,payload):
            self.calls+=1
            step=self.steps.pop(0)
            if isinstance(step,Exception): raise step
            if callable(step):return await step(payload)
            return step
    engine=Engine()
    token,tool="synthetic-autonomous-service-token","synthetic-autonomous-tool-token"
    for key,value in {"AI_SERVICE_URL":"http://agent:8767","AI_SERVICE_TOKEN":token,
        "BACKEND_TOOL_TOKEN":tool,"P3_ENGINE":"deepseek","AI_CONVERSATION_DIALOGUE_PROTOCOL":autonomous.PROTOCOL,
        "MAGICVVU_TRUSTED_REFERENCE_MESSAGES":"true"}.items(): monkeypatch.setenv(key,value)
    ai=create_app(engine=engine,reader=RemoteReader("http://backend:8000",tool))
    transports={"agent":httpx.ASGITransport(app=ai),"backend":httpx.ASGITransport(app=app)}
    requests=[]; original=httpx.AsyncClient
    async def dispatch(request):
        requests.append((request.method,request.url.path))
        return await transports[request.url.host].handle_async_request(request)
    def client(*args,**kwargs):
        kwargs["transport"]=httpx.MockTransport(dispatch)
        return original(*args,**kwargs)
    monkeypatch.setattr(httpx,"AsyncClient",client)
    return engine,requests


def reading(kind="quantity", **updates):
    value={"action":"resolve","plan":{"speech_act":"question","selector":{"name":"牛奶"},"reads":[{"kind":kind}]}}
    value.update(updates)
    return value


def moving():
    return {"action":"resolve","plan":{"speech_act":"request","action":"MOVE","write_count":1,
        "selector":{"name":"牛奶"},"fields":{"to_location":{"value":"书房","quote":"书房"}}}}


def test_four_calls_persist_replay_and_original_request_recovery(execution_state,autonomous_ai):
    client,Session,ids=execution_state; engine,requests=autonomous_ai
    with Session.begin() as db:
        item=db.get(InventoryItem,ids["batch"])
        from datetime import date
        item.opened_at=date(2026,10,1); item.expires_on=date(2026,12,1)
    engine.steps=[reading(),reading("location"),reading("dates"),{"action":"finish"}]
    session=ok(start(client,ids)); request_id=uuid4().hex
    value=ok(send(client,ids,session,"核对牛奶数量、位置和日期",request_id=request_id))
    assert value["model_calls"]==engine.calls==4
    assert value["dialogue"]["calls"]=={"decision":4,"response":0,"total":4}
    assert "登记数量" in value["reply"] and "位置" in value["reply"]
    assert sum(path=="/agent/dialogue/run" for _,path in requests)==1
    replay=ok(send(client,ids,session,"核对牛奶数量、位置和日期",request_id=request_id))
    recovery=ok(client.get(BASE+"conversation-turns/"+request_id,headers=headers(),params={"household_id":str(ids["home"])}))
    assert replay==value and recovery["phase"]=="completed" and engine.calls==4
    with Session() as db:
        turn=db.scalar(select(ConversationTurn).where(ConversationTurn.request_id==request_id))
        assert turn.binding_json[autonomous.KEY]["result"]["model_calls"]==4
        assert "dialogue_v1" not in turn.binding_json
        assert db.query(AITask).count()==1 and db.query(DraftOperation).count()==0


def test_draft_revalidated_and_status_followup_zero_calls(execution_state,autonomous_ai):
    client,Session,ids=execution_state; engine,requests=autonomous_ai
    engine.steps=[moving()]
    draft=ok(send(client,ids,ok(start(client,ids)),"把牛奶移到书房"))
    assert draft["task"]["status"]=="needs_confirmation" and engine.calls==1
    assert any(path=="/agent/dialogue/p85/resolve" for _,path in requests)
    state=ok(send(client,ids,draft,"为什么还没移动"))
    assert state["model_calls"]==0 and "待确认" in state["reply"] and engine.calls==1
    with Session() as db:
        assert db.get(InventoryItem,ids["batch"]).storage_location=="冰箱"
        assert db.query(DraftOperation).count()==0


def test_multi_batch_select_resumes_original_task_without_model(execution_state,autonomous_ai):
    client,Session,ids=execution_state; engine,_=autonomous_ai
    multiple(Session,ids); engine.steps=[moving()]
    first=ok(send(client,ids,ok(start(client,ids)),"把牛奶移到书房"))
    assert first["task"]["status"]=="needs_clarification"
    chosen=ok(send(client,ids,first,"第二个"))
    assert chosen["kind"]=="clarify" and chosen["task"]["status"]=="needs_confirmation"
    assert chosen["task"]["result"]["draft"]["batch_id"]==first["task"]["result"]["candidates"][1]["id"]
    assert engine.calls==1


def test_response_unknown_is_not_reexecuted(execution_state,autonomous_ai,monkeypatch):
    client,Session,ids=execution_state; engine,_=autonomous_ai
    session=ok(start(client,ids)); request_id=uuid4().hex; calls=[]
    async def lost(*args): calls.append(args[2]); raise TimeoutError()
    monkeypatch.setattr(autonomous,"call",lost)
    assert send(client,ids,session,"核对牛奶数量",request_id=request_id).status_code==504
    assert send(client,ids,session,"核对牛奶数量",request_id=request_id).status_code==409
    recovery=ok(client.get(BASE+"conversation-turns/"+request_id,headers=headers(),params={"household_id":str(ids["home"])}))
    assert recovery["phase"]=="result_unknown" and calls==["/agent/dialogue/run"]


def test_saved_ai_result_recovers_without_models_after_crash(execution_state,autonomous_ai,monkeypatch):
    client,Session,ids=execution_state; engine,_=autonomous_ai
    engine.steps=[moving()]; original=autonomous.call
    async def crash(identity,home,path,*args):
        if path.endswith("/resolve"): raise TimeoutError()
        return await original(identity,home,path,*args)
    monkeypatch.setattr(autonomous,"call",crash)
    session=ok(start(client,ids)); request_id=uuid4().hex
    assert send(client,ids,session,"把牛奶移到书房",request_id=request_id).status_code==503
    count=engine.calls; monkeypatch.setattr(autonomous,"call",original)
    recovered=ok(send(client,ids,session,"把牛奶移到书房",request_id=request_id))
    assert recovered["task"]["status"]=="needs_confirmation"
    assert engine.calls==count and recovered["dialogue"]["recovery_model_calls"]==0


def test_inventory_change_after_ai_draft_is_conflict_not_rewrite(execution_state,autonomous_ai,monkeypatch):
    client,Session,ids=execution_state; engine,_=autonomous_ai
    engine.steps=[moving()]; original=autonomous.call
    async def changed(identity,home,path,*args):
        value=await original(identity,home,path,*args)
        if path.endswith("/run"):
            with Session.begin() as db: db.get(InventoryItem,ids["batch"]).version+=1
        return value
    monkeypatch.setattr(autonomous,"call",changed)
    value=ok(send(client,ids,ok(start(client,ids)),"把牛奶移到书房"))
    assert value["kind"]=="needs_input" and value["error_code"]=="INVENTORY_VERSION_CONFLICT"
    with Session() as db: assert db.query(AIDraft).count()==0 and db.query(DraftOperation).count()==0


def test_permissions_revoked_while_model_working_no_result_saved(execution_state,autonomous_ai,monkeypatch):
    client,Session,ids=execution_state; engine,_=autonomous_ai
    engine.steps=[reading(finish_after_resolve=True)]; original=autonomous.call
    async def revoke(identity,home,path,*args):
        value=await original(identity,home,path,*args)
        if path.endswith("/run"):
            with Session.begin() as db:
                db.query(HouseholdMember).filter_by(user_id=ids["user"],household_id=ids["home"]).delete()
        return value
    monkeypatch.setattr(autonomous,"call",revoke)
    value=send(client,ids,ok(start(client,ids)),"核对牛奶数量")
    assert value.status_code in {401,403,404}
    with Session() as db: assert db.query(AITask).count()==0


def test_public_phone_cannot_inject_history_or_raise_legacy_limit(execution_state,autonomous_ai):
    from app.memory_schemas import Response
    from pydantic import ValidationError
    client,Session,ids=execution_state
    assert send(client,ids,ok(start(client,ids)),"你好",history=[]).status_code==422
    sample=dict(conversation_id=uuid4(),conversation_revision=1,request_id="x",original_text="x",reply="x",kind="explain",model_calls=3)
    with pytest.raises(ValidationError): Response.model_validate(sample)
    with pytest.raises(ValidationError): Response.model_validate({**sample,"dialogue":{"protocol_version":"p84-dialogue-1",
        "calls":{"understanding":2,"response":1,"total":3},"fallback_used":False}})
    caps=ok(client.get(BASE+"execution-capabilities",headers=headers()))
    assert caps["conversation_dialogue_protocol"]==autonomous.PROTOCOL
    assert caps["conversation_request_timeout_seconds"]==90


def test_processing_retry_reset_and_lease_do_not_start_second_loop(execution_state,autonomous_ai,monkeypatch):
    client,Session,ids=execution_state; engine,requests=autonomous_ai
    session=ok(start(client,ids)); request_id=uuid4().hex
    engine.steps=[moving()]; original=autonomous.call
    async def inspect_running(identity,home,path,*args):
        if path.endswith("/run"):
            with Session() as db:
                binding=db.get(ConversationBinding,ids["user"])
                assert 100 < (gateway.as_aware(binding.lease_until)-gateway.now()).total_seconds() <= 120
            retry=await asyncio.to_thread(send,client,ids,session,"把牛奶移到书房",request_id=request_id)
            assert retry.status_code==409
            assert (await asyncio.to_thread(start,client,ids,session)).status_code==409
        return await original(identity,home,path,*args)
    monkeypatch.setattr(autonomous,"call",inspect_running)
    value=ok(send(client,ids,session,"把牛奶移到书房",request_id=request_id))
    assert value["task"]["status"]=="needs_confirmation" and engine.calls==1
    assert sum(path=="/agent/dialogue/run" for _,path in requests)==1


def test_confirm_during_edit_preserves_receipt_and_original_draft(execution_state,autonomous_ai,monkeypatch):
    client,Session,ids=execution_state; engine,_=autonomous_ai
    engine.steps=[moving()]
    draft=ok(send(client,ids,ok(start(client,ids)),"把牛奶移到书房"))
    original=autonomous.call
    async def confirm_first(identity,home,path,*args):
        result=await original(identity,home,path,*args)
        if path.endswith("/run"):
            receipt=ok(await asyncio.to_thread(post,client,draft["task"]["draft_id"],commit_body(task_revision=draft["task"]["revision"])))
            assert receipt["status"]=="committed"
        return result
    monkeypatch.setattr(autonomous,"call",confirm_first)
    changed=ok(send(client,ids,draft,"还是移到储物柜吧"))
    assert changed["kind"]=="needs_input" and changed["active_task"]["execution"]["status"]=="committed"
    with Session() as db:
        assert db.get(InventoryItem,ids["batch"]).quantity==Decimal(1)
        assert db.get(InventoryItem,ids["batch"]).storage_location=="书房"
        assert db.query(DraftOperation).count()==1
        row=db.scalar(select(AIDraft).where(AIDraft.task_id==UUID(draft["task"]["task_id"])))
        assert row.revision==1 and row.command_json["to_location"]=="书房"


def test_stale_task_snapshot_is_refreshed_without_model(execution_state,autonomous_ai,monkeypatch):
    client,Session,ids=execution_state; engine,_=autonomous_ai
    engine.steps=[moving()]
    draft=ok(send(client,ids,ok(start(client,ids)),"把牛奶移到书房"))
    original=autonomous.call
    async def needs_refresh(identity,home,path,*args):
        value=await original(identity,home,path,*args)
        if path.endswith("/run"):
            value.update(status="needs_input",stop_reason="context_refresh_required",resolved=None,verified_plans=[])
        return value
    monkeypatch.setattr(autonomous,"call",needs_refresh)
    value=ok(send(client,ids,draft,"执行了吗"))
    assert value["model_calls"]==0 and "待确认" in value["reply"]
    assert value["dialogue"]["status"]=="completed" and value["dialogue"]["revalidation_calls"]==1
    assert engine.calls==1


def test_expired_reference_after_read_completes_as_reselection(execution_state,autonomous_ai,monkeypatch):
    from app.services import conversation as routing,draft_execution as execution
    client,Session,ids=execution_state;engine,_=autonomous_ai
    engine.steps=[reading(finish_after_resolve=True)]
    first=ok(send(client,ids,ok(start(client,ids)),"核对牛奶数量"))
    after=[False]; original_call=autonomous.call; original_validate=routing.validate_reference
    async def expires(identity,home,path,*args):
        value=await original_call(identity,home,path,*args)
        if path.endswith("/run"):after[0]=True
        return value
    def validate(*args,**kwargs):
        if after[0]:execution.fail("REFERENCE_EXPIRED")
        return original_validate(*args,**kwargs)
    monkeypatch.setattr(autonomous,"call",expires);monkeypatch.setattr(routing,"validate_reference",validate)
    value=ok(send(client,ids,first,"它在哪里"))
    assert value["kind"]=="needs_input" and value["error_code"]=="REFERENCE_EXPIRED"
    assert value["dialogue"]["status"]=="needs_input" and engine.calls==1
    with Session() as db:
        turn=db.scalar(select(ConversationTurn).where(ConversationTurn.request_id==value["request_id"]))
        assert turn.phase=="completed"


def test_unrelated_expired_reference_does_not_block_new_object(execution_state,autonomous_ai,monkeypatch):
    from app.services import conversation as routing,draft_execution as execution
    client,Session,ids=execution_state;engine,_=autonomous_ai
    engine.steps=[reading(finish_after_resolve=True)]
    first=ok(send(client,ids,ok(start(client,ids)),"核对牛奶数量"))
    # New literal object does not inherit or validate an unrelated old target.
    with Session.begin() as db:
        db.add(InventoryItem(household_id=ids["home"],name="纸巾",unit="包",
            storage_location="柜子",status="ACTIVE",version=1,created_by_user_id=ids["user"]))
    def invalid(*args,**kwargs):execution.fail("REFERENCE_EXPIRED")
    monkeypatch.setattr(routing,"validate_reference",invalid)
    engine.steps=[{"action":"resolve","finish_after_resolve":True,
        "plan":{"speech_act":"question","selector":{"name":"纸巾"},"reads":[{"kind":"quantity"}]}}]
    value=ok(send(client,ids,first,"纸巾有多少"))
    assert value["task"]["result"]["facts"][0]["name"]=="纸巾" and value.get("error_code") is None
