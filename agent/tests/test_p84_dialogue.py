import asyncio
from datetime import timedelta
from decimal import Decimal
import pytest
from p0.domain import DomainError
from conversation.dialogue import understand, resolve, respond, validate_template
from conversation.dialogue_schemas import Request, ResolveRequest, RespondRequest, Plan
from test_conversation import service, reference, SCOPE, NOW, run
from test_session_memory import context


def resolution(text, plan, *, memory=None, manager=None):
    manager = manager or service()[0]
    body = ResolveRequest(text=text,request_id="p84",context=memory or context(),plan=plan)
    return run(resolve(manager,body,SCOPE))


def source(value, quote=None):
    return {"value":value,"quote":quote or value}


@pytest.mark.parametrize("mode,expected",[("half",Decimal("1.5")),("all",Decimal("3"))])
def test_half_and_all_use_fresh_stock_without_model(mode,expected):
    owner,engine,reader=service()
    reader.data.items[0].batches[0].quantity=Decimal("3")
    before=reader.data.model_dump_json()
    frame=resolution("我喝了一半" if mode=="half" else "把剩下全部记为消耗",dict(speech_act="request",action="CONSUME",write_count=1,
        selector={"use_reference":True},amount_mode=mode),memory=context(reference=reference()),manager=owner)
    assert frame.result["status"]=="needs_confirmation", frame
    assert Decimal(frame.result["draft"]["quantity"])==expected
    assert frame.field_sources["quantity"]["version"]==4
    assert reader.batch_reads==1 and engine.calls==0
    assert before==reader.data.model_dump_json()


@pytest.mark.parametrize("speech",["hypothesis","negation","discuss","question"])
def test_discussion_never_writes_even_if_model_proposes_action(speech):
    frame=resolution("如果把牛奶移到厨房会怎样",dict(speech_act=speech, action="MOVE",write_count=1,
        selector={"name":"牛奶"},fields={"to_location":source("厨房")},social_reply="可以先讨论你的安排。"))
    assert frame.result is None and frame.kind=="explain"


def test_compound_read_uses_one_snapshot_then_one_draft():
    owner,engine,reader=service()
    frame=resolution("牛奶多少，在哪，什么时候开封？帮我移到厨房",dict(speech_act="request",action="MOVE",write_count=1,
        selector={"name":"牛奶"},reads=[{"kind":k} for k in ("quantity","location","dates")],
        fields={"to_location":source("厨房")}),manager=owner)
    assert frame.result["draft"]["action"]=="MOVE" and len(frame.facts)==5
    assert reader.searches==1 and reader.batch_reads==0 and engine.calls==0


def test_multiple_writes_answer_reads_then_ask_priority():
    frame=resolution("牛奶还有多少？移到厨房然后丢弃",dict(speech_act="request",write_count=2,
        action="MOVE",selector={"name":"牛奶"},reads=[{"kind":"quantity"}]))
    assert frame.result is None and frame.error_code=="MULTIPLE_WRITES"
    assert "登记数量" in frame.reply and "先处理" in frame.reply


@pytest.mark.parametrize("field,value,quote",[("quantity","20","两盒"),("to_location","历史厨房","移到书房"),("opened_at","2026-10-01","昨天")])
def test_invented_fields_rejected(field,value,quote):
    frame=resolution(quote,dict(speech_act="request",action="MOVE",write_count=1,fields={field:source(value,quote)}))
    assert frame.error_code=="UNGROUNDED_FIELD" and frame.result is None


def test_expired_reference_does_not_renew_from_history():
    frame=resolution("它在哪里",dict(speech_act="question",selector={"use_reference":True},reads=[{"kind":"location"}]),
        memory=context(reference=reference(issued_at=NOW-timedelta(minutes=16),expires_at=NOW-timedelta(minutes=1))))
    assert frame.error_code=="REFERENCE_EXPIRED"


def test_location_disambiguation_reads_real_candidates():
    frame=resolution("厨房那盒放哪里",dict(speech_act="question",selector={"location":"厨房"},reads=[{"kind":"location"}]),
        manager=service(multiple=True)[0],memory=context(choices=[reference(),reference(batch_id="b2")]))
    assert [b["id"] for b in frame.result["facts"]]==["b2"]


def test_unknown_quantity_is_not_estimated():
    frame=resolution("我喝了一口",dict(speech_act="request",action="CONSUME",write_count=1,amount_mode="unknown",selector={"use_reference":True}),
        memory=context(reference=reference()))
    assert frame.result["status"]=="needs_clarification" and "quantity" in frame.result["missing_fields"]


def test_provider_understanding_called_once_not_old_extractor():
    owner,_,_=service()
    class Engine:
        calls=0
        async def dialogue_understand(self,text,ctx):
            self.calls+=1
            return Plan(speech_act="social",social_reply="你好，今天想整理家里的什么？")
    owner.engine=Engine()
    out=run(understand(owner,Request(text="你好",request_id="u",context=context()),SCOPE))
    assert owner.engine.calls==out.understanding_calls==1


@pytest.mark.parametrize("text",["它在哪","它在什么地方","这一批放在哪里"])
def test_explicit_location_followups_zero_understanding(text):
    owner,_,_=service()
    out=run(understand(owner,Request(text=text,request_id="u",context=context(reference=reference())),SCOPE))
    assert out.understanding_calls==0


def test_response_validates_evidence_and_falls_back_no_retry():
    owner,_,_=service()
    frame=resolution("牛奶在哪",dict(speech_act="question",selector={"name":"牛奶"},reads=[{"kind":"location"}]))
    class Engine:
        calls=0
        async def dialogue_respond(self,*args):
            self.calls+=1
            return "已经移动成功，库存99盒。"
    owner.engine=Engine()
    out=run(respond(owner,RespondRequest(text="牛奶在哪",resolved=frame)))
    assert out.fallback_used and out.reply==frame.reply and owner.engine.calls==1
    assert validate_template("好的，{{fact:f0}}",frame.facts)=="好的，"+frame.facts["f0"]


def test_cross_scope_cannot_read_or_understand():
    owner,engine,reader=service()
    from p0.schemas import Scope
    with pytest.raises(DomainError):
        run(understand(owner,Request(text="它在哪",request_id="u",context=context()),Scope(user_id="other",household_id="h1")))
    assert reader.batch_reads==engine.calls==0


@pytest.mark.parametrize("state",["committed","cancelled","unknown","conflict"])
def test_decided_or_unknown_drafts_cannot_be_corrected(state):
    from eval.dialogue.run import fixture,SCOPE as scoped
    owner,ctx,_=fixture(state,None)
    body=ResolveRequest(text="还是两盒",request_id="edit",context=ctx,plan={"speech_act":"correction",
        "fields":{"quantity":source("2","两盒"),"unit":source("盒","两盒")}})
    frame=run(resolve(owner,body,scoped))
    assert frame.kind=="needs_input" and frame.error_code=="DRAFT_NOT_EDITABLE"


@pytest.mark.parametrize("action,fields",[("MOVE",{"to_location":source("厨房")}),
    ("OPEN",{"opened_at":source("昨天")}), ("DISCARD",{"quantity":source("1","一盒"),"unit":source("盒","一盒")})])
def test_six_action_fields_and_noop_boundaries(action,fields):
    frame=resolution("这盒昨天开封，移到厨房，丢弃一盒",dict(speech_act="request",action=action,write_count=1,
        selector={"use_reference":True},fields=fields),memory=context(reference=reference()))
    assert frame.result["status"]=="needs_confirmation",frame
    command=frame.result["draft"]
    assert command["expected_version"]==4
    if action in {"MOVE","OPEN"}:assert "quantity" not in command


@pytest.mark.parametrize("quantity",["0.000001","0.000003"])
def test_half_never_silently_rounds(quantity):
    owner,_,reader=service();reader.data.items[0].batches[0].quantity=Decimal(quantity)
    frame=resolution("喝了一半，登记消耗",dict(speech_act="request",action="CONSUME",write_count=1,
        selector={"use_reference":True},amount_mode="half"),memory=context(reference=reference()),manager=owner)
    assert not (frame.result or {}).get("draft")


def test_unit_evidence_uses_longest_unit_token():
    frame=resolution("消耗一千克",dict(speech_act="request",action="CONSUME",fields={"quantity":source("1","一千克"),"unit":source("g","一千克")}))
    assert frame.error_code=="UNGROUNDED_FIELD"


@pytest.mark.parametrize("mode",["half","all"])
def test_model_cannot_invent_relative_amount(mode):
    frame=resolution("消耗一盒",dict(speech_act="request",action="CONSUME",write_count=1,
        selector={"use_reference":True},amount_mode=mode),memory=context(reference=reference()))
    assert frame.error_code=="UNGROUNDED_AMOUNT_MODE"


@pytest.mark.parametrize("template",["牛奶在储物柜{{fact:f0}}","做完啦{{fact:f0}}","{{fact:f9}}","{{fact:f0}}{{fact:f0}}","{{fact:f0}}今天到期"])
def test_free_factual_text_cannot_escape_anchors(template):
    with pytest.raises(ValueError):validate_template(template,{"f0":"已核实的事实。"})


def test_dataset_split_group_isolation_and_provenance():
    from eval.dialogue.generate import samples
    rows=samples()
    assert len(rows)==240 and sum(r["split"]=="dev" for r in rows)==144
    assert {r["group_id"] for r in rows if r["split"]=="dev"}.isdisjoint({r["group_id"] for r in rows if r["split"]=="holdout"})
    assert all(r["source"] and r["human_review_status"]=="pending" and r["synthetic"] for r in rows)


def test_http_stages_use_existing_internal_auth(monkeypatch):
    from fastapi.testclient import TestClient
    from conversation.app import create_app
    monkeypatch.setenv("AI_SERVICE_TOKEN","synthetic-dialogue-service-token")
    monkeypatch.setenv("P3_ENGINE","rules")
    owner,engine,reader=service()
    client=TestClient(create_app(engine=engine,reader=reader,now=lambda:NOW))
    payload=Request(text="它在哪里",request_id="auth",context=context(reference=reference())).model_dump(mode="json")
    assert client.post("/agent/dialogue/understand",json=payload).status_code==401
    headers={"Authorization":"Bearer synthetic-dialogue-service-token","X-User-Id":SCOPE.user_id,"X-Household-Id":SCOPE.household_id}
    assert client.post("/agent/dialogue/understand",json=payload,headers=headers).json()["understanding_calls"]==0


def test_context_overflow_does_not_truncate_candidate_order():
    owner,engine,_=service()
    ctx=context(choices=[reference(batch_id="b"+str(i)+"x"*80) for i in range(200)])
    with pytest.raises(DomainError,match="必要任务信息"):
        run(understand(owner,Request(text="第二个",request_id="big",context=ctx),SCOPE))
    assert engine.calls==0


@pytest.mark.parametrize("text",["我还需要确认什么才能生效","确认后到底有没有扣掉","我想核对刚才的执行结果","取消之后这笔还会执行吗"])
def test_task_state_phrasings_are_fresh_and_zero_model(text):
    from eval.dialogue.run import fixture,SCOPE as scoped
    owner,ctx,_=fixture("committed",None)
    parsed=run(understand(owner,Request(text=text,request_id="state",context=ctx),scoped))
    assert parsed.understanding_calls==0 and parsed.plan.speech_act=="status"
    frame=run(resolve(owner,ResolveRequest(text=text,request_id="state",context=ctx,plan=parsed.plan),scoped))
    assert "执行成功" in frame.reply


def test_missing_model_unit_is_missing_not_an_invented_unit():
    from conversation.dialogue_engine import parse_plan
    plan=parse_plan('{"speech_act":"request","action":"CONSUME","fields":{"unit":{"value":null,"quote":"2"}}}')
    assert plan.fields=={}


def test_question_with_known_task_selector_reads_status_not_social_text():
    from eval.dialogue.run import fixture,SCOPE as scoped
    owner,ctx,_=fixture("committed",None)
    frame=run(resolve(owner,ResolveRequest(text="我想核对那笔",request_id="state",context=ctx,
        plan={"speech_act":"question","task_index":0}),scoped))
    assert "执行成功" in frame.reply and frame.evidence[0]["kind"]=="fresh_task_read"


def test_reference_expiring_during_understanding_is_rejected_at_resolve():
    owner,_,_=service()
    owner.now=lambda:NOW+timedelta(seconds=2)
    frame=resolution("它在哪里",dict(speech_act="question",selector={"use_reference":True},reads=[{"kind":"location"}]),
        memory=context(reference=reference(expires_at=NOW+timedelta(seconds=1))),manager=owner)
    assert frame.error_code=="REFERENCE_EXPIRED"


def test_rules_configuration_cannot_silently_start_paid_model():
    from p0.engines import EngineError
    owner,_,_=service()
    with pytest.raises(EngineError) as failure:
        run(understand(owner,Request(text="聊聊厨房收纳",request_id="rules",context=context()),SCOPE))
    assert failure.value.code=="DIALOGUE_MODEL_NOT_CONFIGURED"
