"""Real P7.3 adapter, backend HTTP, DB cursor/receipts, and counted extraction."""
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select

from test_v09_execution import execution_state, headers, body as commit_body, post, PG
from app.main import app
from app.models import AITask, AIDraft, InventoryItem, HouseholdMember, AuthSession
from app.conversation_models import ConversationBinding, ConversationTurn
from app.execution_models import DraftOperation
from app.routers import agent_gateway

ENDPOINT = "/api/v1/agent/conversation-messages"
REFERENCE = "/api/v1/agent/reference-messages"


@pytest.fixture
def p7(execution_state, monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "agent"))
    from conversation.app import create_app
    from conversation.engines import RuleEngine
    from v1.tools import RemoteReader

    class Counted(RuleEngine):
        calls = 0

        async def extract(self, text):
            self.calls += 1
            return await super().extract(text)

    engine = Counted()
    token, tool = "synthetic-p2-agent-token-at-least-32", "synthetic-p2-tool-token-at-least-32"
    for key, value in {"AI_SERVICE_URL": "http://agent:8767", "AI_SERVICE_TOKEN": token,
                       "BACKEND_TOOL_TOKEN": tool, "P3_ENGINE": "deepseek",
                       "MAGICVVU_TRUSTED_REFERENCE_MESSAGES": "true"}.items():
        monkeypatch.setenv(key, value)
    ai = create_app(engine=engine, reader=RemoteReader("http://backend:8000", tool))
    transports = {"agent": httpx.ASGITransport(app=ai), "backend": httpx.ASGITransport(app=app)}
    calls = []
    original = httpx.AsyncClient

    async def dispatch(request):
        calls.append((request.url.host, request.url.path))
        return await transports[request.url.host].handle_async_request(request)

    def local_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(dispatch)
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", local_client)
    return engine, calls, ai, dispatch


def send(client, ids, text, task=None, **updates):
    payload = dict(household_id=str(ids["home"]), text=text, request_id=uuid4().hex)
    if task:
        payload.update(task_id=task["task_id"], revision=task["revision"])
    payload.update(updates)
    return client.post(ENDPOINT, headers=headers(), json=payload)


def legacy(client, ids, text):
    response = client.post("/api/v1/agent/messages", headers=headers(), json={
        "household_id": str(ids["home"]), "text": text, "request_id": uuid4().hex})
    assert response.status_code == 200, response.text
    return response.json()


def multiple(Session, ids):
    with Session.begin() as db:
        for location in ("厨房", "储物柜"):
            db.add(InventoryItem(household_id=ids["home"], name="牛奶", quantity=2,
                unit="盒", storage_location=location, status="ACTIVE", version=1, created_by_user_id=ids["user"]))


@pytest.mark.parametrize("text", ["第二个", "就第二个吧"])
def test_ordinal_real_chain_and_exact_replay(execution_state, p7, text):
    client, Session, ids = execution_state
    multiple(Session, ids)
    task = legacy(client, ids, "把牛奶移到冰箱上层")
    candidates = task["result"]["candidates"]
    assert len(candidates) == 3
    before = p7[0].calls
    request_id = uuid4().hex
    response = send(client, ids, text, task, request_id=request_id)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["resolution"]["kind"] == "clarify"
    assert result["resolution"]["answers"] == {"batch_id": candidates[1]["id"]}
    assert result["task"]["task_id"] == task["task_id"]
    assert result["task"]["revision"] == task["revision"] + 1
    assert result["task"]["result"]["draft"]["batch_id"] == candidates[1]["id"]
    assert result["reference"]["batch_id"] == candidates[1]["id"]
    assert p7[0].calls == before
    assert send(client, ids, text, task, request_id=request_id).json() == result
    assert send(client, ids, text, task).status_code == 409
    with Session() as db:
        assert db.query(AITask).count() == db.query(AIDraft).count() == db.query(ConversationTurn).count() == 1
        assert db.query(DraftOperation).count() == 0
        assert db.get(InventoryItem, UUID(candidates[1]["id"])).storage_location == candidates[1]["location"]
        turn = db.scalar(select(ConversationTurn))
        assert turn.original_text == text and turn.source_revision == task["revision"]
    execution = client.get("/api/v1/drafts/" + result["task"]["draft_id"] + "/execution", headers=headers()).json()
    committed = post(client, result["task"]["draft_id"], commit_body(
        task_revision=execution["task_revision"], draft_revision=execution["draft_revision"]))
    assert committed.status_code == 200, committed.text


def test_amount_missing_fields_and_allowed_fields(execution_state, p7):
    client, Session, ids = execution_state
    task = legacy(client, ids, "新增牛奶")
    before = p7[0].calls
    result = send(client, ids, "两盒", task)
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["resolution"]["answers"] == {"quantity": "2", "unit": "盒"}
    assert data["task"]["task_id"] == task["task_id"]
    assert data["task"]["status"] == "needs_clarification"
    assert "location" in data["task"]["result"]["clarification"]["allowed_fields"]
    assert p7[0].calls == before
    result = send(client, ids, "第三个", data["task"])
    assert result.status_code == 200 and result.json()["resolution"]["kind"] == "needs_input"
    injected = client.post("/api/v1/agent/clarifications/" + task["task_id"], headers=headers(), json={
        "revision": data["task"]["revision"], "answers": {"expected_version": 99}})
    assert injected.status_code == 422
    with Session() as db:
        assert db.query(AITask).count() == 1 and db.query(AIDraft).count() == 0


def test_yesterday_uses_server_context_date_not_client_clock(execution_state, p7):
    client, Session, ids = execution_state
    task = legacy(client, ids, "牛奶开封了")
    before = p7[0].calls
    response = send(client, ids, "昨天", task)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["resolution"]["answers"] == {"opened_at": "昨天"}
    with Session() as db:
        turn = db.scalar(select(ConversationTurn))
        from zoneinfo import ZoneInfo
        context = db.get(AITask, UUID(task["task_id"])).context_json
        while "delegate" in context:
            context = context["delegate"]
        anchored = datetime.fromisoformat(context["created_at"]).astimezone(ZoneInfo(turn.binding_json["timezone"]))
        assert result["task"]["result"]["draft"]["opened_at"] == (anchored.date() - timedelta(days=1)).isoformat()
    assert p7[0].calls == before
    assert client.post(ENDPOINT, headers=headers(), json={
        "household_id": str(ids["home"]), "text": "昨天", "request_id": "forged-time",
        "trusted_now": "2000-01-01T00:00:00Z"}).status_code == 422
    # OPEN remains unexecutable in P2.
    assert post(client, result["task"]["draft_id"], commit_body(task_revision=result["task"]["revision"])).status_code == 409


def test_ambiguity_never_defaults_first_candidate(execution_state, p7):
    client, Session, ids = execution_state
    multiple(Session, ids)
    task = legacy(client, ids, "把牛奶移到冰箱")
    count = p7[0].calls
    for text in ("这个", "第四个"):
        result = send(client, ids, text, task)
        assert result.status_code == 200, result.text
        assert result.json()["resolution"]["kind"] == "needs_input"
        assert result.json()["task"]["revision"] == task["revision"]
        assert result.json()["reference"] is None
    assert p7[0].calls == count
    with Session() as db:
        assert db.query(AITask).count() == 1 and db.query(AIDraft).count() == 0


def unique(client, ids):
    result = send(client, ids, "牛奶在哪里")
    assert result.status_code == 200, result.text
    assert result.json()["reference"] is not None, result.text
    return result.json()


def test_reference_rereads_location_preserves_original_and_ttl(execution_state, p7):
    client, Session, ids = execution_state
    initial = unique(client, ids)
    before = p7[0].calls
    with Session.begin() as db:
        item = db.get(InventoryItem, ids["batch"])
        item.storage_location = "书房"
        item.version += 1
    result = send(client, ids, " 它在哪里？ ", initial["task"])
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["original_text"] == " 它在哪里？ "
    assert data["task"]["result"]["original_text"] == data["original_text"]
    assert data["task"]["result"]["facts"][0]["location"] == "书房"
    assert data["task"]["result"]["facts"][0]["version"] == 2
    assert data["reference"] == initial["reference"]
    assert p7[0].calls == before
    assert ("backend", "/internal/v1/inventory/batches/" + str(ids["batch"])) in p7[1] or any(
        host == "backend" and str(ids["batch"]) in path for host, path in p7[1])


@pytest.mark.parametrize("change,code", [("expired", "REFERENCE_EXPIRED"),
    ("deleted", "REFERENCE_NOT_FOUND"), ("terminal", "REFERENCE_TERMINAL"),
    ("revision", "TASK_REVISION_CONFLICT"), ("membership", "DRAFT_NOT_FOUND")])
def test_reference_invalidations(execution_state, p7, change, code):
    client, Session, ids = execution_state
    initial = unique(client, ids)
    with Session.begin() as db:
        if change == "expired":
            binding = db.get(ConversationBinding, ids["user"])
            binding.reference_json = {**binding.reference_json,
                "expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()}
        elif change == "deleted":
            db.delete(db.get(InventoryItem, ids["batch"]))
        elif change == "terminal":
            db.get(InventoryItem, ids["batch"]).status = "FINISHED"
        elif change == "revision":
            db.get(AITask, UUID(initial["task"]["task_id"])).revision += 1
        else:
            db.delete(db.get(HouseholdMember, (ids["home"], ids["user"])))
    result = send(client, ids, "它在哪里", initial["task"])
    assert result.status_code in (404, 409), result.text
    assert result.json()["detail"]["code"] == code
    with Session() as db:
        assert db.query(DraftOperation).count() == 0


def ref_body(ids, task, batch_id=None, **updates):
    return dict(household_id=str(ids["home"]), text="它在哪里", request_id=uuid4().hex,
        source_task_id=task["task_id"], source_revision=task["revision"],
        batch_id=str(batch_id or ids["batch"]), **updates)


def test_reserved_reference_endpoint_now_real_but_feature_gated(execution_state, p7, monkeypatch):
    client, Session, ids = execution_state
    task = legacy(client, ids, "牛奶在哪里")
    payload = ref_body(ids, task)
    assert client.post(REFERENCE, json=payload).status_code == 401
    response = client.post(REFERENCE, headers=headers(), json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["task"]["result"]["facts"][0]["id"] == str(ids["batch"])
    assert client.post(REFERENCE, headers=headers(), json=payload).json() == response.json()
    assert client.get("/api/v1/agent/execution-capabilities", headers=headers()).json()["trusted_reference_messages"] is True
    monkeypatch.delenv("MAGICVVU_TRUSTED_REFERENCE_MESSAGES")
    assert client.post(REFERENCE, headers=headers(), json=payload).status_code == 503
    assert client.get("/api/v1/agent/execution-capabilities", headers=headers()).json()["trusted_reference_messages"] is False


@pytest.mark.parametrize("change", ["batch", "scope", "owner", "revision"])
def test_reference_untrusted_selectors(execution_state, p7, change):
    client, Session, ids = execution_state
    task = legacy(client, ids, "牛奶在哪里")
    payload = ref_body(ids, task)
    if change == "batch":
        payload["batch_id"] = str(uuid4())
    if change == "scope":
        payload["household_id"] = str(ids["foreign_home"])
    if change == "revision":
        payload["source_revision"] += 1
    result = client.post(REFERENCE, headers=headers("outsider" if change == "owner" else "user"), json=payload)
    assert result.status_code in (404, 409, 422), result.text


def test_clear_new_topic_and_household_switch_invalidate_old_binding(execution_state, p7):
    client, Session, ids = execution_state
    initial = unique(client, ids)
    before = p7[0].calls
    reset = send(client, ids, "开始新任务", initial["task"])
    assert reset.status_code == 200 and reset.json()["resolution"]["kind"] == "clear_reference", reset.text
    assert reset.json()["reference"] is None and reset.json()["task"] is None
    with Session() as db:
        assert db.query(AITask).count() == 1
        assert db.get(ConversationBinding, ids["user"]).task_id is None
    assert client.post(REFERENCE, headers=headers(), json=ref_body(ids, initial["task"])).status_code == 409
    assert p7[0].calls == before
    second = send(client, ids, "计划买2包纸巾")
    assert second.status_code == 200 and second.json()["task"]["task_id"] != initial["task"]["task_id"]
    assert send(client, ids, "它在哪里", initial["task"]).status_code == 409
    with Session.begin() as db:
        db.add(HouseholdMember(household_id=ids["foreign_home"], user_id=ids["user"], role="member"))
    switched = send(client, ids, "库存有什么", household_id=str(ids["foreign_home"]))
    assert switched.status_code == 200, switched.text
    assert client.post(REFERENCE, headers=headers(), json=ref_body(ids, initial["task"])).status_code == 409


def test_request_conflict_and_private_context_rejected(execution_state, p7):
    client, Session, ids = execution_state
    response = send(client, ids, "牛奶在哪里", request_id="stable")
    assert response.status_code == 200
    assert send(client, ids, "纸巾在哪里", request_id="stable").status_code == 409
    assert send(client, ids, "第二个", response.json()["task"], revision=99).status_code == 409
    for field in ("binding", "expected_version", "allowed_fields", "selected_batch_id", "trusted_now"):
        assert send(client, ids, "两盒", **{field: {}}).status_code == 422


def test_candidates_changed_since_question_rejected(execution_state, p7):
    client, Session, ids = execution_state
    multiple(Session, ids)
    task = legacy(client, ids, "把牛奶移到书房")
    with Session.begin() as db:
        db.get(InventoryItem, UUID(task["result"]["candidates"][0]["id"])).version += 1
    result = send(client, ids, "第二个", task)
    assert result.status_code == 409 and result.json()["detail"]["code"] == "CANDIDATES_CHANGED"
    with Session() as db:
        assert db.query(AIDraft).count() == 0


def test_fast_candidate_then_amount_requires_new_revision(execution_state, p7):
    client, Session, ids = execution_state
    multiple(Session, ids)
    task = legacy(client, ids, "喝了牛奶")
    before = p7[0].calls
    first = send(client, ids, "第二个", task)
    assert first.status_code == 200, first.text
    next_task = first.json()["task"]
    assert next_task["task_id"] == task["task_id"] and next_task["revision"] == task["revision"] + 1
    assert send(client, ids, "两盒", task).status_code == 409
    second = send(client, ids, "两盒", next_task)
    assert second.status_code == 200, second.text
    assert second.json()["task"]["status"] == "needs_confirmation"
    assert second.json()["reference"]["source_revision"] == second.json()["task"]["revision"]
    assert second.json()["reference"]["expires_at"] == first.json()["reference"]["expires_at"]
    located = send(client, ids, "它在哪里", second.json()["task"])
    assert located.status_code == 200, located.text
    assert located.json()["task"]["result"]["facts"][0]["id"] == first.json()["resolution"]["answers"]["batch_id"]
    assert p7[0].calls == before
    with Session() as db:
        assert db.query(AITask).count() == 2  # Original task plus the explicit location query.
        assert db.query(AIDraft).count() == 1
        assert db.query(DraftOperation).count() == 0


def test_clarification_response_loss_retries_same_turn_without_extraction(execution_state, p7, monkeypatch):
    client, Session, ids = execution_state
    task = legacy(client, ids, "新增牛奶")
    before = p7[0].calls
    original = httpx.AsyncClient
    lost = []

    async def transport(request):
        response = await p7[3](request)
        if request.url.path == "/agent/clarification" and not lost:
            lost.append(True)
            raise httpx.ReadTimeout("synthetic lost clarification response", request=request)
        return response

    def local(*args, **kwargs):
        result = original(*args, **kwargs)
        result._transport = httpx.MockTransport(transport)
        return result

    monkeypatch.setattr(httpx, "AsyncClient", local)
    request_id = uuid4().hex
    first = send(client, ids, "两盒", task, request_id=request_id)
    assert first.status_code == 503, first.text
    second = send(client, ids, "两盒", task, request_id=request_id)
    assert second.status_code == 200, second.text
    assert second.json()["task"]["task_id"] == task["task_id"]
    assert p7[0].calls == before
    with Session() as db:
        assert db.query(AITask).count() == db.query(ConversationTurn).count() == 1


def test_new_task_unknown_outcome_never_reextracts_on_retry(execution_state, p7, monkeypatch):
    client, Session, ids = execution_state
    original = httpx.AsyncClient

    async def transport(request):
        response = await p7[3](request)
        if request.url.path == "/agent/message":
            raise httpx.ReadTimeout("synthetic response lost after extraction", request=request)
        return response

    def local(*args, **kwargs):
        result = original(*args, **kwargs)
        result._transport = httpx.MockTransport(transport)
        return result

    monkeypatch.setattr(httpx, "AsyncClient", local)
    key = uuid4().hex
    assert send(client, ids, "新增2盒牛奶放冰箱", request_id=key).status_code == 503
    count = p7[0].calls
    assert count == 1
    repeated = send(client, ids, "新增2盒牛奶放冰箱", request_id=key)
    assert repeated.status_code == 409 and repeated.json()["detail"]["code"] == "AI_OUTCOME_UNKNOWN"
    task_id = repeated.json()["detail"]["task_id"]
    assert task_id is not None
    assert client.get("/api/v1/agent/tasks/" + task_id, headers=headers()).status_code == 200
    assert p7[0].calls == count
    with Session() as db:
        assert db.query(AITask).count() == db.query(ConversationTurn).count() == 1
        assert db.query(AIDraft).count() == 0
        assert db.query(InventoryItem).count() == 1
        assert db.get(ConversationBinding, ids["user"]).task_id is None


def test_atomic_turn_receipt_survives_public_response_failure(execution_state, p7, monkeypatch):
    from starlette.responses import JSONResponse
    client, Session, ids = execution_state
    task = legacy(client, ids, "新增牛奶")
    key = uuid4().hex
    render = JSONResponse.render

    def broken(self, content):
        if isinstance(content, dict) and content.get("protocol_version") == "backend-conversation-1":
            raise RuntimeError("synthetic response loss after task and turn commit")
        return render(self, content)

    with monkeypatch.context() as patcher:
        patcher.setattr(JSONResponse, "render", broken)
        assert send(client, ids, "两盒", task, request_id=key).status_code == 500
    count = p7[0].calls
    recovered = send(client, ids, "两盒", task, request_id=key)
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["task"]["revision"] == task["revision"] + 1
    assert p7[0].calls == count


def test_logout_and_new_login_do_not_reuse_old_context(execution_state, p7):
    from app.security import digest_token
    client, Session, ids = execution_state
    initial = unique(client, ids)
    with Session.begin() as db:
        old = db.scalar(select(AuthSession).where(AuthSession.user_id == ids["user"]))
        old.revoked_at = datetime.now(timezone.utc)
        db.add(AuthSession(user_id=ids["user"], token_hash=digest_token("synthetic-new-session"),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
    assert send(client, ids, "它在哪里", initial["task"]).status_code == 401
    payload = dict(household_id=str(ids["home"]), text="它在哪里", request_id=uuid4().hex,
        task_id=initial["task"]["task_id"], revision=initial["task"]["revision"])
    result = client.post(ENDPOINT, json=payload, headers={"Authorization": "Bearer synthetic-new-session"})
    assert result.status_code == 409, result.text


def test_logout_during_adapter_call_cannot_persist_reply(execution_state, p7, monkeypatch):
    client, Session, ids = execution_state
    task = legacy(client, ids, "新增牛奶")
    original = httpx.AsyncClient

    async def transport(request):
        response = await p7[3](request)
        if request.url.path == "/agent/reply-resolution":
            with Session.begin() as db:
                session = db.scalar(select(AuthSession).where(AuthSession.user_id == ids["user"]))
                session.revoked_at = datetime.now(timezone.utc)
        return response

    def local(*args, **kwargs):
        result = original(*args, **kwargs)
        result._transport = httpx.MockTransport(transport)
        return result

    monkeypatch.setattr(httpx, "AsyncClient", local)
    response = send(client, ids, "两盒", task)
    assert response.status_code == 401, response.text
    with Session() as db:
        assert db.get(AITask, UUID(task["task_id"])).revision == task["revision"]
        assert db.query(AIDraft).count() == 0


def test_new_migration_retains_tasks_and_refuses_populated_downgrade(tmp_path):
    from unittest.mock import patch
    from sqlalchemy import create_engine, inspect
    from sqlalchemy.orm import sessionmaker
    from alembic import command
    from alembic.config import Config
    from test_v09_execution import seed_draft
    from app.models import User, Household
    engine = create_engine(f"sqlite:///{tmp_path/'conversation-migration.sqlite'}")
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    with patch("sqlalchemy.create_engine", return_value=engine):
        command.upgrade(cfg, "20261017_0007")
    Session = sessionmaker(bind=engine)
    ids = dict(user=uuid4(), home=uuid4())
    with Session.begin() as db:
        db.add(User(id=ids["user"], email="p2@example.invalid", password_hash="fixture", display_name="P2"))
        db.flush()
        db.add(Household(id=ids["home"], name="P2", created_by_user_id=ids["user"]))
    draft_id, task_id = seed_draft(Session, ids, "ADD")
    with patch("sqlalchemy.create_engine", return_value=engine):
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "20261017_0007")
        command.upgrade(cfg, "head")
        with Session.begin() as db:
            assert db.get(AIDraft, draft_id) is not None
            db.add(ConversationBinding(user_id=ids["user"], household_id=ids["home"],
                session_id=uuid4(), task_id=task_id))
        with pytest.raises(RuntimeError, match="Conversation evidence exists"):
            command.downgrade(cfg, "20261017_0007")
    assert "ai_conversation_bindings" in inspect(engine).get_table_names()
    engine.dispose()


def test_adapter_missing_is_unavailable_never_model_fallback(execution_state, p7, monkeypatch):
    client, Session, ids = execution_state
    task = legacy(client, ids, "新增牛奶")
    before = p7[0].calls
    original = httpx.AsyncClient

    async def missing(request):
        if request.url.path == "/agent/reply-resolution":
            return httpx.Response(404)
        return await p7[3](request)

    # p7 already patched AsyncClient; use its own transport factory directly.
    def client_with_missing(*args, **kwargs):
        value = original(*args, **kwargs)
        value._transport = httpx.MockTransport(missing)
        return value

    monkeypatch.setattr(httpx, "AsyncClient", client_with_missing)
    response = send(client, ids, "两盒", task)
    assert response.status_code == 503 and response.json()["detail"]["code"] == "REPLY_ADAPTER_UNAVAILABLE"
    assert p7[0].calls == before


def test_internal_adapter_auth_and_zero_model_calls(execution_state, p7):
    from fastapi.testclient import TestClient
    client, _, ids = execution_state
    task = legacy(client, ids, "新增牛奶")
    before = p7[0].calls
    payload = {"binding": {"scope": {"user_id": str(ids["user"]), "household_id": str(ids["home"])},
        "task": task, "household_timezone": "Asia/Shanghai"}, "text": "两盒",
        "trusted_now": datetime.now(timezone.utc).isoformat()}
    with TestClient(p7[2]) as ai:
        assert ai.post("/agent/reply-resolution", json=payload).status_code == 401
        valid = {"Authorization": "Bearer synthetic-p2-agent-token-at-least-32",
                 "X-User-Id": str(ids["user"]), "X-Household-Id": str(ids["home"])}
        assert ai.post("/agent/reply-resolution", headers=valid, json=payload).json()["model_calls"] == 0
        valid["X-User-Id"] = str(ids["outsider"])
        assert ai.post("/agent/reply-resolution", headers=valid, json=payload).status_code == 403
    assert p7[0].calls == before


def test_expired_task_and_old_turn_cannot_advance_state(execution_state, p7):
    from app.services.conversation import complete
    from app.conversation_schemas import Resolution
    from fastapi import HTTPException
    client, Session, ids = execution_state
    task = legacy(client, ids, "新增牛奶")
    with Session.begin() as db:
        db.get(AITask, UUID(task["task_id"])).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    result = send(client, ids, "两盒", task)
    assert result.status_code == 200, result.text
    assert result.json()["resolution"]["error_code"] == "CLARIFICATION_EXPIRED"
    with Session() as db:
        from app.dependencies import Identity
        from app.models import User
        turn = db.scalar(select(ConversationTurn))
        session = db.scalar(select(AuthSession).where(AuthSession.user_id == ids["user"]))
        identity = Identity(user=db.get(User, ids["user"]), session_id=session.id)
        with pytest.raises(HTTPException) as error:
            complete(db, identity, turn.id, "old-worker", Resolution(kind="clear_reference", clear_reference=True).model_dump())
        assert error.value.status_code == 409
        assert db.get(AITask, UUID(task["task_id"])).revision == task["revision"]


def test_model_call_evidence(execution_state, p7):
    import json
    client, Session, ids = execution_state
    phases = [{"phase": "initial", "extractions": p7[0].calls}]
    initial = unique(client, ids)
    phases.append({"phase": "new_named_query", "extractions": p7[0].calls})
    response = send(client, ids, "它在哪里", initial["task"])
    assert response.status_code == 200, response.text
    phases.append({"phase": "trusted_location_reference", "extractions": p7[0].calls})
    reset = send(client, ids, "开始新任务", response.json()["task"])
    assert reset.status_code == 200, reset.text
    phases.append({"phase": "reset", "extractions": p7[0].calls})
    task = legacy(client, ids, "新增牛奶")
    phases.append({"phase": "new_add_request", "extractions": p7[0].calls})
    response = send(client, ids, "两盒", task)
    assert response.status_code == 200, response.text
    phases.append({"phase": "structured_amount", "extractions": p7[0].calls})
    assert [p["extractions"] for p in phases] == [0, 1, 1, 1, 2, 2]
    target = Path(__file__).resolve().parents[3] / "reports" / (
        "backend-p2-postgres-model-calls.json" if PG else "backend-p2-sqlite-model-calls.json")
    target.write_text(json.dumps({"engine": "counted project RuleEngine", "configured_mode": "deepseek",
        "paid_provider_calls": 0, "phases": phases, "http_calls": p7[1]}, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.mark.skipif(not PG, reason="Real PostgreSQL row locks required")
@pytest.mark.parametrize("same_request", [False, True])
def test_concurrent_same_revision_is_recoverable(execution_state, p7, same_request):
    client, Session, ids = execution_state
    multiple(Session, ids)
    task = legacy(client, ids, "把牛奶移到书房")
    key = uuid4().hex
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda n: send(client, ids, "第二个", task,
            request_id=key if same_request else key + str(n)), range(2)))
    assert all(result.status_code in (200, 409) for result in results), [r.text for r in results]
    assert any(r.status_code == 200 for r in results), [r.text for r in results]
    with Session() as db:
        assert db.query(AIDraft).count() == db.query(AITask).count() == 1
        assert db.get(AITask, UUID(task["task_id"])).revision == task["revision"] + 1


def test_openapi_routes_and_strict_dtos():
    schema = app.openapi()
    assert ENDPOINT in schema["paths"] and REFERENCE in schema["paths"]
    model = schema["components"]["schemas"]["ConversationMessage"]
    assert model["additionalProperties"] is False
    assert set(model["properties"]) == {"household_id", "text", "request_id", "task_id", "revision"}
    routes = [(method, route.path) for route in app.routes for method in getattr(route, "methods", [])]
    assert len(routes) == len(set(routes))
