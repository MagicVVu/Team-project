import asyncio
from datetime import timedelta
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from p0.domain import DomainError
from p0.engines import EngineError
from conversation.autonomous.runner import run as process
from conversation.autonomous.schemas import RunRequest, Decision
from conversation.autonomous.reads import ReadOnly
from conversation.autonomous.app import create_app
from test_conversation import service, reference, run, SCOPE, NOW
from test_session_memory import context


class Script:
    def __init__(self, steps): self.steps, self.calls, self.payloads = list(steps), 0, []
    async def autonomous_step(self, payload):
        self.calls += 1; self.payloads.append(payload)
        value = self.steps.pop(0)
        if isinstance(value, Exception): raise value
        if callable(value): return await value(payload)
        return value


def req(text="牛奶现在数量、位置和日期都帮我核对", **updates):
    return RunRequest(text=text, request_id="autonomous-test", context=context(), **updates)


def read(kind, **changes):
    plan = {"speech_act":"question", "selector":{"name":"牛奶"}, "reads":[{"kind":kind}]}
    plan.update(changes)
    return {"action":"resolve", "plan":plan}


def execute(steps, body=None, known_dates=False, **service_args):
    owner, _, reader = service(**service_args)
    if known_dates:
        from datetime import date
        reader.data.items[0].batches[0].opened_at = date(2026,10,1)
        reader.data.items[0].batches[0].label_expiry = date(2026,11,1)
    owner.engine = engine = Script(steps)
    before = reader.data.model_dump_json()
    result = run(process(owner, body or req(), SCOPE))
    assert reader.data.model_dump_json() == before
    return result, engine, reader


def test_more_than_two_calls_shared_stock_and_verified_finish():
    result, engine, reader = execute([read("quantity"),read("location"),read("dates"),{"action":"finish"}],known_dates=True)
    assert result.model_calls == engine.calls == 4
    assert result.status == "completed" and result.stop_reason == "completed"
    assert reader.searches == result.tool_reads == 1
    assert "登记数量" in result.reply and "位置" in result.reply and "开封日期" in result.reply
    assert len(result.verified_plans) == 3 and not result.inventory_writes


@pytest.mark.parametrize("text", ["它在哪", "它在什么地方", "这批放在哪里", "它还有多少", "第一个在哪里"])
def test_literal_followups_are_zero_calls(text):
    body = req().model_copy(update={"text":text,"context":context(reference=reference(),choices=[reference()])})
    result, engine, reader = execute([],body)
    assert result.model_calls == engine.calls == 0
    assert result.status == "completed" and reader.batch_reads == 1


def test_missing_quantity_returns_immediately_without_second_call():
    result, engine, _ = execute([{"action":"resolve","plan":{"speech_act":"request","action":"CONSUME",
        "write_count":1,"selector":{"name":"牛奶"},"amount_mode":"unknown"}}],req("牛奶喝了一点，记一下"))
    assert result.status == "needs_input" and result.stop_reason == "user_input_required"
    assert engine.calls == 1 and "quantity" in result.resolved.result["missing_fields"]


def test_pending_draft_ends_loop_without_execution():
    result, engine, _ = execute([{"action":"resolve","plan":{"speech_act":"request","action":"MOVE",
        "write_count":1,"selector":{"name":"牛奶"},"fields":{"to_location":{"value":"书房","quote":"书房"}}}}],req("把牛奶移到书房"))
    assert result.status == "needs_confirmation" and engine.calls == 1
    assert result.resolved.result["draft"]["to_location"] == "书房"
    assert result.resolved.result["draft"]["expected_version"] == 4


def test_multiple_batches_requires_user_choice_without_model_loop():
    step = {"action":"resolve","plan":{"speech_act":"request","action":"MOVE","write_count":1,
        "selector":{"name":"牛奶"},"fields":{"to_location":{"value":"书房","quote":"书房"}}}}
    result, engine, _ = execute([step],req("把牛奶移到书房"),multiple=True)
    assert result.status == "needs_input" and engine.calls == 1
    assert "batch_id" in result.resolved.result["missing_fields"]


def test_repeated_plan_and_alternating_cycle_stop_before_repeated_tool():
    result, engine, reader = execute([read("quantity"),read("location"),read("quantity")])
    assert engine.calls == 3 and result.stop_reason == "repeated_plan" and reader.searches == 1
    assert "登记数量" in result.reply and "位置" in result.reply


def test_different_plan_with_same_information_is_no_progress():
    result, engine, _ = execute([read("quantity"),read("quantity",preserve_active=False)])
    assert engine.calls == 2 and result.stop_reason == "no_progress"


def test_semantic_error_can_be_corrected_but_fields_not_invented():
    wrong = read("quantity",fields={"quantity":{"value":"99","quote":"核对"}})
    result, engine, _ = execute([wrong,read("quantity"),{"action":"finish"}])
    assert engine.calls == 3 and result.status == "completed"
    assert "quantity" not in result.filled_fields and "99" not in result.reply
    assert engine.payloads[1]["observations"]["error_code"] == "UNGROUNDED_FIELD"
    assert "quantity" not in engine.payloads[1]["observations"]["filled_fields"]


def test_failed_model_returns_partial_results_without_retry():
    result, engine, _ = execute([read("quantity"),EngineError("MODEL_UNAVAILABLE")])
    assert result.stop_reason == "model_error" and engine.calls == result.model_calls == 2
    assert "登记数量" in result.reply and result.fallback_used


def test_deadline_preserves_original_and_does_not_retry():
    async def slow(_): await asyncio.sleep(.2)
    result, engine, _ = execute([slow],req(remaining_seconds=.02))
    assert result.stop_reason == "deadline" and result.original_text == req().text
    assert engine.calls == 1 and result.elapsed_ms < 180


def test_tool_failure_stops_and_no_further_model_request():
    owner, _, reader = service(); owner.engine = Script([read("quantity")])
    async def fail(*_): raise DomainError("TOOL_UNAVAILABLE","工具暂不可用。",503)
    reader.search = fail
    result = run(process(owner,req(),SCOPE))
    assert result.stop_reason == "data_unavailable" and owner.engine.calls == 1


def test_permission_failure_does_not_expose_partial_facts():
    owner, _, reader = service(); owner.engine = Script([read("quantity")])
    async def forbidden(*_): raise DomainError("HOUSEHOLD_FORBIDDEN","禁止读取。",403)
    reader.search = forbidden
    with pytest.raises(DomainError) as caught:
        run(process(owner,req(),SCOPE))
    assert caught.value.code=="HOUSEHOLD_FORBIDDEN"


def test_reference_expiry_and_deleted_object_stop_without_guessing():
    owner, _, reader = service(); owner.engine=Script([])
    expired = reference(issued_at=NOW-timedelta(minutes=16),expires_at=NOW-timedelta(minutes=1))
    body = req().model_copy(update={"text":"它在哪里","context":context(reference=expired)})
    result=run(process(owner,body,SCOPE))
    assert result.status=="needs_input" and result.error_code=="REFERENCE_EXPIRED"
    assert reader.batch_reads==0 and result.model_calls==0


def test_cross_household_rejected_before_model():
    from p0.schemas import Scope
    owner,_,_=service(); owner.engine=Script([])
    with pytest.raises(DomainError): run(process(owner,req(),Scope(user_id="other",household_id="foreign")))
    assert owner.engine.calls==0


def test_invalid_expression_uses_verified_reply_without_another_call():
    result,engine,_=execute([read("quantity"),{"action":"finish","expression":{
        "fact_order":["invented"],"opening":"none","layout":"lines","closing":"none"}}])
    assert result.fallback_used and engine.calls==2 and "登记数量" in result.reply


def test_model_cannot_supply_arbitrary_tools_urls_or_claim_completion():
    for value in [{"action":"execute","url":"http://example.invalid"},
                  {"action":"finish","reply":"已经移动成功"},
                  {"action":"resolve","plan":{"speech_act":"request","batch_id":"invented"}}]:
        with pytest.raises(ValidationError): Decision.model_validate(value)
    result,engine,_=execute([{"action":"finish"}])
    assert result.status=="needs_input" and engine.calls==1


def test_auth_capabilities_and_legacy_factory_are_distinct(monkeypatch):
    from conversation.p85.app import create_app as old
    monkeypatch.setenv("AI_SERVICE_TOKEN","synthetic-autonomous-token")
    owner,_,reader=service()
    client=TestClient(create_app(engine=owner.engine,reader=reader,now=lambda:NOW))
    legacy=TestClient(old(engine=owner.engine,reader=reader,now=lambda:NOW))
    health=client.get("/health").json()
    assert health["maintenance_release"]=="V1-P8.6"
    assert client.get("/openapi.json").json()["info"]["version"]=="0.8.6"
    assert health["dialogue_max_model_calls"] is None and health["dialogue_deadline_seconds"]==60
    assert legacy.get("/health").json()["maintenance_release"]=="V1-P8.5"
    assert legacy.get("/health").json()["dialogue_max_model_calls"]==2
    assert "/agent/dialogue/run" not in legacy.get("/openapi.json").json()["paths"]
    assert client.post("/agent/dialogue/run",json=req().model_dump(mode="json")).status_code==401


def test_read_adapter_exposes_only_explicit_reads_and_conflict_detection():
    import time
    _,_,reader=service()
    adapter=ReadOnly(reader,SCOPE,time.monotonic()+5)
    assert not hasattr(adapter,"execute") and not hasattr(adapter,"confirm")
    row=run(adapter.get_batch(SCOPE,"b1"))
    changed=row.model_copy(update={"version":row.version+1})
    with pytest.raises(DomainError): adapter.remember(changed)


def test_simple_read_can_finish_in_one_call():
    step=read("quantity"); step["finish_after_resolve"]=True
    result,engine,_=execute([step])
    assert result.status=="completed" and result.model_calls==engine.calls==1


@pytest.mark.parametrize("profile",["committed","cancelled","unknown"])
def test_status_and_retry_controls_are_zero_model(profile):
    from eval.dialogue.run import fixture,SCOPE as scoped
    owner,ctx,_=fixture(profile,Script([]))
    result=run(process(owner,RunRequest(text="再试一下" if profile!="cancelled" else "执行了吗",request_id="state",context=ctx),scoped))
    assert result.model_calls==0 and result.resolved.result is None
    assert "执行成功" in result.reply if profile=="committed" else "已取消" in result.reply if profile=="cancelled" else "待核实" in result.reply


@pytest.mark.parametrize("action,text,extra",[
    ("OPEN","这批昨天开封，记一下",{"fields":{"opened_at":{"value":"昨天","quote":"昨天"}}}),
    ("DISCARD","这批剩下全部丢弃",{"amount_mode":"all"}),
    ("CONSUME","这批喝了一半，记一下",{"amount_mode":"half"}),
])
def test_lifecycle_reuses_exact_quantity_date_and_version(action,text,extra):
    step={"action":"resolve","plan":{"speech_act":"request","action":action,"write_count":1,
        "selector":{"use_reference":True},**extra}}
    body=req(text).model_copy(update={"context":context(reference=reference())})
    result,engine,reader=execute([step],body)
    assert result.status=="needs_confirmation" and engine.calls==(0 if action=="OPEN" else 1)
    draft=result.resolved.result["draft"]
    assert draft["expected_version"]==reader.data.items[0].batches[0].version
    if action=="OPEN": assert "quantity" not in draft
    else:
        assert Decimal(draft["quantity"])==reader.data.items[0].batches[0].quantity/(2 if action=="CONSUME" else 1)


def test_unknown_dates_stop_without_repeat_or_invented_date():
    result,engine,_=execute([read("dates")])
    assert result.stop_reason=="data_unavailable" and engine.calls==1 and "未知" in result.reply


def test_task_snapshot_is_not_renewed_during_long_loop():
    from eval.dialogue.run import fixture,SCOPE as scoped
    clock=[NOW]
    async def long_understanding(payload):
        clock[0]=NOW+timedelta(seconds=35)
        return {"action":"resolve","plan":{"speech_act":"status"}}
    owner,ctx,_=fixture("pending",Script([long_understanding]));owner.now=lambda:clock[0]
    result=run(process(owner,RunRequest(text="原来那件事究竟办好了没有呀",request_id="long",context=ctx),scoped))
    assert result.stop_reason=="context_refresh_required" and result.model_calls==1
    assert ctx.tasks[0].checked_at==NOW and ctx.trusted_now==NOW


def test_large_required_context_stops_without_dropping_candidates():
    refs=[reference(batch_id="batch-"+str(i)+"x"*40) for i in range(100)]
    body=req().model_copy(update={"context":context(choices=refs)})
    owner,_,_=service();owner.engine=Script([])
    try:
        result=run(process(owner,body,SCOPE))
        assert result.stop_reason=="context_limit" and result.model_calls==0
    except DomainError as error:
        assert error.code=="MEMORY_CONTEXT_TOO_LARGE"
    assert len(body.context.choices)==100 and owner.engine.calls==0
