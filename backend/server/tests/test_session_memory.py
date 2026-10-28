"""Real authenticated HTTP -> internal AI -> DB gateway, using test-only inventory."""
from datetime import timedelta
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select

from test_v09_execution import execution_state, headers, body as commit_body, post
from test_backend_p2_conversation import p7, multiple
from app.conversation_models import ConversationTurn, ConversationBinding
from app.models import InventoryItem, AITask, AIDraft, AuthSession, HouseholdMember
from app.execution_models import DraftOperation
from app.routers import agent_gateway as gateway
from app.security import digest_token

BASE = "/api/v1/agent/"


def start(client, ids, previous=None, **updates):
    payload = dict(household_id=str(ids["home"]), request_id=uuid4().hex)
    if previous:
        payload.update(conversation_id=previous["conversation_id"], conversation_revision=previous["conversation_revision"])
    payload.update(updates)
    return client.post(BASE+"conversation/reset", headers=headers(), json=payload)


def send(client, ids, session, text, **updates):
    payload = dict(household_id=str(ids["home"]), request_id=uuid4().hex, text=text,
                   conversation_id=session["conversation_id"], conversation_revision=session["conversation_revision"])
    payload.update(updates)
    return client.post(BASE+"conversation-turns", headers=headers(), json=payload)


def ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def test_move_select_draft_explain_commit_refresh(execution_state, p7):
    client, Session, ids = execution_state
    multiple(Session, ids)
    session = ok(start(client, ids))
    moved = ok(send(client, ids, session, "把牛奶移到冷藏室"))
    assert moved["task"]["status"] == "needs_clarification"
    count = p7[0].calls
    chosen = ok(send(client, ids, moved, "第二个"))
    assert chosen["kind"] == "clarify" and chosen["model_calls"] == 0
    assert chosen["task"]["status"] == "needs_confirmation"
    target = chosen["task"]["result"]["draft"]["batch_id"]
    explained = ok(send(client, ids, chosen, "为什么还没移动"))
    assert "待确认" in explained["reply"] and explained["kind"] == "explain"
    assert explained["active_task"]["task"]["task_id"] == chosen["task"]["task_id"]
    assert p7[0].calls == count
    receipt = ok(post(client, chosen["task"]["draft_id"], commit_body(task_revision=chosen["task"]["revision"])))
    assert receipt["status"] == "committed"
    done = ok(send(client, ids, explained, "执行了吗"))
    assert "执行成功" in done["reply"] and done["model_calls"] == 0
    assert done["active_task"]["execution"]["status"] == "committed"
    with Session() as db:
        assert db.get(InventoryItem, UUID(target)).storage_location == "冷藏室"
        assert db.query(DraftOperation).count() == 1


def test_query_ordinal_then_pronoun_and_fresh_read(execution_state, p7):
    client, Session, ids = execution_state
    multiple(Session, ids)
    session = ok(start(client, ids))
    first = ok(send(client, ids, session, "牛奶还有多少"))
    facts = first["task"]["result"]["facts"]
    assert len(facts) == 3
    count = p7[0].calls
    second = ok(send(client, ids, first, "第二批在哪里"))
    assert second["task"]["result"]["facts"][0]["id"] == facts[1]["id"]
    with Session.begin() as db:
        item = db.get(InventoryItem, UUID(facts[1]["id"]))
        item.storage_location = "新位置"; item.version += 1
    where = ok(send(client, ids, second, "它在哪里"))
    assert where["task"]["result"]["facts"][0]["location"] == "新位置"
    assert p7[0].calls == count
    # The last displayed list now has one row; ordinal one is that selected row.
    selected_again = ok(send(client, ids, where, "第一个"))
    assert selected_again["task"]["result"]["facts"][0]["id"] == facts[1]["id"]


def test_replay_recovery_login_and_history_are_zero_model(execution_state, p7):
    client, Session, ids = execution_state
    session = ok(start(client, ids))
    request_id = uuid4().hex
    first = ok(send(client, ids, session, "把牛奶移到书房", request_id=request_id))
    count = p7[0].calls
    replay = ok(send(client, ids, session, "把牛奶移到书房", request_id=request_id))
    assert first == replay
    recovery = ok(client.get(BASE+"conversation-turns/"+request_id, headers=headers(), params={"household_id":str(ids["home"])}))
    assert recovery["phase"] == "completed"
    with Session.begin() as db:
        db.add(AuthSession(user_id=ids["user"], token_hash=digest_token("synthetic-second-login"),
                           expires_at=gateway.now()+timedelta(hours=1)))
    new_headers = {"Authorization":"Bearer synthetic-second-login"}
    page = ok(client.get(BASE+"conversation", headers=new_headers, params={"household_id":str(ids["home"])}))
    assert page["conversation_id"] == session["conversation_id"]
    assert page["active_task"]["task"]["task_id"] == first["task"]["task_id"]
    body = dict(household_id=str(ids["home"]), request_id=uuid4().hex, text="执行了吗",
                conversation_id=page["conversation_id"], conversation_revision=page["conversation_revision"])
    assert "待确认" in ok(client.post(BASE+"conversation-turns", headers=new_headers, json=body))["reply"]
    assert p7[0].calls == count
    assert send(client, ids, session, "不同内容", request_id=request_id).status_code == 409


def test_reset_is_separate_from_new_task_and_never_cancels(execution_state, p7):
    client, Session, ids = execution_state
    session = ok(start(client, ids))
    draft = ok(send(client, ids, session, "把牛奶移到书房"))
    task_reset = ok(send(client, ids, draft, "开始新任务"))
    assert task_reset["conversation_id"] == session["conversation_id"] and task_reset["active_task"] is None
    reset = ok(start(client, ids, task_reset))
    assert reset["conversation_id"] != session["conversation_id"]
    page = ok(client.get(BASE+"conversation", headers=headers(), params={"household_id":str(ids["home"])}))
    assert page["messages"] == []
    assert send(client, ids, task_reset, "执行了吗").status_code == 409
    with Session() as db:
        assert db.query(AIDraft).one().status == "pending"
        assert db.query(DraftOperation).count() == 0


def test_scope_forged_context_and_concurrency_revision(execution_state, p7):
    client, Session, ids = execution_state
    session = ok(start(client, ids))
    assert client.get(BASE+"conversation", headers=headers("outsider"), params={"household_id":str(ids["home"])}).status_code == 404
    assert send(client, ids, session, "它在哪里", history=[]).status_code == 422
    assert send(client, ids, session, "它在哪里", context={}).status_code == 422
    first = ok(send(client, ids, session, "牛奶在哪里"))
    assert send(client, ids, session, "它在哪里").status_code == 409
    with Session.begin() as db:
        db.delete(db.get(HouseholdMember, (ids["home"], ids["user"])))
    assert client.get(BASE+"conversation", headers=headers(), params={"household_id":str(ids["home"])}).status_code == 404


def test_state_changes_and_original_text_preserved(execution_state, p7):
    client, Session, ids = execution_state
    draft = ok(send(client, ids, ok(start(client, ids)), " 把牛奶移到书房 "))
    assert draft["original_text"] == " 把牛奶移到书房 "
    with Session.begin() as db:
        item = db.get(InventoryItem, ids["batch"]); item.version += 1
    conflict = ok(send(client, ids, draft, "执行了吗"))
    assert "冲突" in conflict["reply"]
    assert conflict["active_task"]["execution"]["status"] == "conflict"
    assert conflict["model_calls"] == 0


def test_unknown_ai_outcome_never_repeats_model(execution_state, p7, monkeypatch):
    from app.services import session_memory as service
    client, Session, ids = execution_state
    session = ok(start(client, ids))
    calls = []
    async def lost(*args):
        calls.append(1)
        raise TimeoutError()
    monkeypatch.setattr(service, "understand", lost)
    request_id = uuid4().hex
    response = send(client, ids, session, "牛奶在哪里", request_id=request_id)
    assert response.status_code == 504
    assert send(client, ids, session, "牛奶在哪里", request_id=request_id).status_code == 409
    recovered = ok(client.get(BASE+"conversation-turns/"+request_id, headers=headers(), params={"household_id":str(ids["home"])}))
    assert recovered["phase"] == "result_unknown" and recovered["original_text"] == "牛奶在哪里"
    current = ok(client.get(BASE+"conversation", headers=headers(), params={"household_id":str(ids["home"])}))
    # Unknown extraction never retries; explicit new conversation abandons only the old chat.
    assert start(client, ids, current).status_code == 200
    assert len(calls) == 1


def test_query_selection_move_then_temporary_question_keeps_draft(execution_state, p7):
    client, Session, ids = execution_state
    multiple(Session, ids)
    first = ok(send(client, ids, ok(start(client, ids)), "牛奶还有多少"))
    second = ok(send(client, ids, first, "第二批在哪里"))
    target = second["task"]["result"]["facts"][0]["id"]
    moved = ok(send(client, ids, second, "把它移到冷藏室"))
    assert moved["task"]["result"]["draft"]["batch_id"] == target
    greeting = ok(send(client, ids, moved, "谢谢"))
    why = ok(send(client, ids, greeting, "为什么没移动"))
    assert "待确认" in why["reply"]
    assert why["active_task"]["task"]["task_id"] == moved["task"]["task_id"]
    with Session() as db:
        assert db.query(DraftOperation).count() == 0


@pytest.mark.parametrize("change,expected", [("delete", "REFERENCE_NOT_FOUND"), ("terminal", "REFERENCE_TERMINAL"), ("expire", "REFERENCE_EXPIRED")])
def test_invalid_reference_never_rebinds_first_batch(execution_state, p7, change, expected):
    client, Session, ids = execution_state
    first = ok(send(client, ids, ok(start(client, ids)), "牛奶在哪里"))
    with Session.begin() as db:
        if change == "delete": db.delete(db.get(InventoryItem, ids["batch"]))
        elif change == "terminal":
            item = db.get(InventoryItem, ids["batch"]); item.status = "DISCARDED"; item.quantity = 0
        else:
            turn = db.scalar(select(ConversationTurn).where(ConversationTurn.request_id == first["request_id"]))
            saved = dict(turn.binding_json); info = dict(saved["memory_v1"]); reference = dict(info["reference"])
            reference["issued_at"] = (gateway.now()-timedelta(minutes=16)).isoformat()
            reference["expires_at"] = (gateway.now()-timedelta(minutes=1)).isoformat()
            info["reference"] = reference; saved["memory_v1"] = info; turn.binding_json = saved
    count = p7[0].calls
    result = ok(send(client, ids, first, "它在哪里"))
    assert result["kind"] == "needs_input" and result["error_code"] == expected
    assert p7[0].calls == count


def test_cancellation_then_status_and_missing_basis(execution_state, p7):
    client, Session, ids = execution_state
    draft = ok(send(client, ids, ok(start(client, ids)), "把牛奶移到书房"))
    task = draft["task"]
    ok(client.post("/api/v1/drafts/"+task["draft_id"]+"/cancel", headers=headers(), json={
        "task_revision":task["revision"], "draft_revision":1}))
    result = ok(send(client, ids, draft, "完成了吗"))
    assert "已取消" in result["reply"] and result["model_calls"] == 0
    basis = ok(send(client, ids, result, "依据是什么"))
    assert "没有保存足够" in basis["reply"] and basis["model_calls"] == 0


def test_thirty_day_read_window_keeps_business_and_idempotency(execution_state, p7):
    client, Session, ids = execution_state
    first = ok(send(client, ids, ok(start(client, ids)), "牛奶在哪里"))
    with Session.begin() as db:
        for row in db.scalars(select(ConversationTurn)):
            row.created_at = gateway.now()-timedelta(days=31)
    page = ok(client.get(BASE+"conversation", headers=headers(), params={"household_id":str(ids["home"])}))
    assert page["messages"] == [] and page["active_task"] is None
    assert client.get(BASE+"conversation-turns/"+first["request_id"], headers=headers(), params={"household_id":str(ids["home"])}).status_code == 404
    with Session() as db:
        assert db.query(AITask).count() == 1 and db.query(ConversationTurn).count() == 2


def test_pagination_and_textual_new_conversation(execution_state, p7):
    client, Session, ids = execution_state
    session = ok(start(client, ids))
    request_ids = []
    for _ in range(4):
        session = ok(send(client, ids, session, "你好")); request_ids.append(session["request_id"])
    first = ok(client.get(BASE+"conversation", headers=headers(), params={"household_id":str(ids["home"]), "limit":2}))
    second = ok(client.get(BASE+"conversation", headers=headers(), params={"household_id":str(ids["home"]), "limit":2,"cursor":first["next_cursor"]}))
    assert [r["request_id"] for r in second["messages"]+first["messages"]] == request_ids
    reset = ok(send(client, ids, session, "开始新会话"))
    assert reset["kind"] == "reset" and reset["original_text"] == "开始新会话"
    assert reset["conversation_id"] != session["conversation_id"] and p7[0].calls == 0


def test_separate_home_session_and_legacy_not_merged(execution_state, p7):
    client, Session, ids = execution_state
    first = ok(send(client, ids, ok(start(client, ids)), "牛奶在哪里"))
    with Session.begin() as db:
        db.add(HouseholdMember(household_id=ids["foreign_home"], user_id=ids["user"], role="member"))
    other = {**ids, "home": ids["foreign_home"]}
    foreign = ok(send(client, other, ok(start(client, other)), "你好"))
    original = ok(client.get(BASE+"conversation", headers=headers(), params={"household_id":str(ids["home"])}))
    assert original["conversation_id"] == first["conversation_id"]
    where = ok(send(client, ids, original, "它在哪里"))
    assert where["task"]["result"]["facts"][0]["id"] == str(ids["batch"])
    # Legacy tasks remain usable, but cannot inject turns into the opt-in session.
    ok(client.post(BASE+"messages", headers=headers(), json={"household_id":str(ids["home"]),"request_id":uuid4().hex,"text":"牛奶在哪里"}))
    again = ok(client.get(BASE+"conversation", headers=headers(), params={"household_id":str(ids["home"])}))
    assert len(again["messages"]) == 2 and foreign["conversation_id"] != original["conversation_id"]


def test_prepared_retry_reuses_understanding_and_atomic_task_finalization(execution_state, p7, monkeypatch):
    client, Session, ids = execution_state
    session = ok(start(client, ids)); request_id = uuid4().hex
    original = gateway.run_message
    async def lost(*args, **kwargs):
        raise RuntimeError("test interruption after understanding saved, before gateway")
    monkeypatch.setattr(gateway, "run_message", lost)
    assert send(client, ids, session, "把牛奶移到书房", request_id=request_id).status_code == 500
    count = p7[0].calls
    recovered = ok(client.get(BASE+"conversation-turns/"+request_id, headers=headers(), params={"household_id":str(ids["home"])}))
    assert recovered["phase"] == "prepared"
    with Session.begin() as db:
        item = db.get(InventoryItem, ids["batch"]); item.version += 1
    monkeypatch.setattr(gateway, "run_message", original)
    done = ok(send(client, ids, session, "把牛奶移到书房", request_id=request_id))
    assert done["task"]["status"] == "needs_confirmation" and p7[0].calls == count
    assert done["task"]["result"]["draft"]["expected_version"] == 2
    with Session() as db:
        assert db.query(AITask).count() == db.query(AIDraft).count() == 1


def test_reset_during_inflight_is_rejected(execution_state, p7):
    client, Session, ids = execution_state
    session = ok(start(client, ids))
    with Session.begin() as db:
        row = db.get(ConversationBinding, ids["user"])
        row.processing_nonce = "test-in-flight"; row.lease_until = gateway.now()+timedelta(seconds=30)
    assert start(client, ids, session).status_code == 409


def test_stale_candidates_finish_as_conflict_then_allow_new_task(execution_state, p7):
    client, Session, ids = execution_state
    multiple(Session, ids)
    first = ok(send(client, ids, ok(start(client, ids)), "把牛奶移到书房"))
    candidates = first["task"]["result"]["candidates"]
    with Session.begin() as db:
        db.get(InventoryItem, UUID(candidates[1]["id"])).version += 1
    count = p7[0].calls
    result = ok(send(client, ids, first, "第二个"))
    assert result["error_code"] == "CANDIDATES_CHANGED" and result["kind"] == "needs_input"
    assert result["model_calls"] == 0 and p7[0].calls == count
    restarted = ok(send(client, ids, result, "开始新任务"))
    fresh = ok(send(client, ids, restarted, "把牛奶移到书房"))
    assert fresh["task"]["status"] == "needs_clarification"
    with Session() as db:
        assert db.query(DraftOperation).count() == 0


def test_recover_old_turn_returns_latest_active_not_old_snapshot(execution_state, p7):
    client, Session, ids = execution_state
    first = ok(send(client, ids, ok(start(client, ids)), "牛奶在哪里"))
    second = ok(send(client, ids, first, "把牛奶移到书房"))
    recovery = ok(client.get(BASE+"conversation-turns/"+first["request_id"], headers=headers(), params={"household_id":str(ids["home"])}))
    assert recovery["response"]["task"]["task_id"] == first["task"]["task_id"]
    assert recovery["response"]["active_task"]["task"]["task_id"] == second["task"]["task_id"]


def test_status_mentions_action_after_query_locates_original_move(execution_state, p7):
    client, Session, ids = execution_state
    moved = ok(send(client, ids, ok(start(client, ids)), "把牛奶移到书房"))
    query = ok(send(client, ids, moved, "牛奶在哪里"))
    explained = ok(send(client, ids, query, "为什么还没移动"))
    assert "待确认" in explained["reply"]
    assert explained["evidence"][0]["task_id"] == moved["task"]["task_id"]
    assert explained["active_task"]["task"]["task_id"] == query["task"]["task_id"]


def test_local_memory_backend_contract_matches_factory(execution_state):
    import json
    from pathlib import Path
    from app.main import app
    from app.memory_schemas import Response
    root = Path(__file__).resolve().parents[3]/"docs/versions/V1-P8.4/contracts"
    exported = json.loads((root/'backend-openapi.json').read_text(encoding="utf-8"))
    assert exported.pop("x-deployment-status") == "local_source_contract_not_deployed"
    assert exported.pop("x-conversation-memory-protocol") == "conversation-memory-1"
    assert exported.pop("x-conversation-dialogue-protocol") == "p84-dialogue-1"
    from contract_compatibility import assert_backend_contract
    assert_backend_contract(exported, app.openapi())
    assert json.loads((root/"public-response.schema.json").read_text(encoding="utf-8")) == Response.model_json_schema()


def test_lost_clarification_response_recovers_atomic_completed_turn(execution_state, p7, monkeypatch):
    client, Session, ids = execution_state
    multiple(Session, ids)
    first = ok(send(client, ids, ok(start(client, ids)), "把牛奶移到书房"))
    original = gateway.run_clarification
    async def lost(*args, **kwargs):
        await original(*args, **kwargs)
        raise RuntimeError("test: commit done, response lost")
    monkeypatch.setattr(gateway, "run_clarification", lost)
    request_id = uuid4().hex; count = p7[0].calls
    assert send(client, ids, first, "第二个", request_id=request_id).status_code == 500
    replay = ok(send(client, ids, first, "第二个", request_id=request_id))
    assert replay["task"]["status"] == "needs_confirmation" and p7[0].calls == count
    with Session() as db:
        assert db.query(AIDraft).count() == 1 and db.query(DraftOperation).count() == 0
