"""Real shipped P7 ASGI + backend HTTP + isolated database, no model calls."""
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select

from test_v09_execution import (
    app, execution_state, headers, body, post, seed_draft, url,
)
from app.models import AIDraft, AITask, HouseholdMember, InventoryItem, ShoppingListItem
from app.execution_models import BusinessEvent, DraftOperation
from app.routers import agent_gateway
from app.services import planning_context


@pytest.fixture
def real_p7(execution_state, monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "agent"))
    from conversation.app import create_app
    from conversation.engines import RuleEngine
    from v1.tools import RemoteReader

    service_token = "synthetic-p1-service-token-at-least-32"
    tool_token = "synthetic-p1-tool-token-at-least-32"
    for key, value in {"AI_SERVICE_URL": "http://agent:8767", "AI_SERVICE_TOKEN": service_token,
                       "BACKEND_TOOL_TOKEN": tool_token, "P3_ENGINE": "rules"}.items():
        monkeypatch.setenv(key, value)
    ai = create_app(engine=RuleEngine(), reader=RemoteReader("http://backend:8000", tool_token))
    transports = {"agent": httpx.ASGITransport(app=ai), "backend": httpx.ASGITransport(app=app)}
    calls = []

    async def dispatch(request):
        calls.append((request.url.host, request.url.path))
        return await transports[request.url.host].handle_async_request(request)

    original = httpx.AsyncClient

    def local_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(dispatch)
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", local_client)
    return calls


@pytest.mark.parametrize("action,text,answers", [
    ("ADD", "买了2包纸巾", {"location": "储物柜"}),
    ("MOVE", "把牛奶移动", {"to_location": "书房"}),
    ("CONSUME", "喝了牛奶", {"quantity": "1", "unit": "盒"}),
    ("PLAN_ADD", "计划买纸巾", {"quantity": "2", "unit": "包"}),
])
def test_real_message_clarification_commit_recovery(execution_state, real_p7, action, text, answers):
    client, Session, ids = execution_state
    message = {"household_id": str(ids["home"]), "text": text, "request_id": uuid4().hex,
               "household_timezone": "Asia/Shanghai"}
    response = client.post("/api/v1/agent/messages", headers=headers(), json=message)
    assert response.status_code == 200, response.text
    initial = response.json()
    assert initial["status"] == "needs_clarification", initial
    task_id = initial["task_id"]
    # Only currently requested fields are sent; some units are known from stock.
    allowed = initial["result"]["clarification"]["allowed_fields"]
    continued = client.post("/api/v1/agent/clarifications/" + task_id, headers=headers(),
        json={"revision": initial["revision"], "answers": {k: v for k, v in answers.items() if k in allowed}})
    assert continued.status_code == 200, continued.text
    task = continued.json()
    assert task["task_id"] == task_id and task["status"] == "needs_confirmation", task
    draft_id = task["draft_id"]
    with Session() as db:
        stored = db.get(AITask, UUID(task_id))
        assert stored.request_id == message["request_id"]
        assert stored.revision == task["revision"]
        assert db.get(AIDraft, UUID(draft_id)).task_id == stored.id
        assert db.get(InventoryItem, ids["batch"]).quantity == 5
        assert db.get(InventoryItem, ids["batch"]).version == 1
        assert db.query(InventoryItem).count() == 1
        assert db.query(ShoppingListItem).count() == db.query(BusinessEvent).count() == 0
    draft = client.get("/api/v1/drafts/" + draft_id, headers=headers()).json()
    request = body(draft_revision=draft["revision"], task_revision=task["revision"])
    committed = post(client, draft_id, request)
    assert committed.status_code == 200, committed.text
    receipt = committed.json()
    assert receipt["action"] == action and receipt["task_id"] == task_id
    # Simulate loss of the HTTP response and a failed inventory refresh.
    assert client.get("/api/v1/households/" + str(uuid4()) + "/inventory-items", headers=headers()).status_code == 404
    recovered = client.get("/api/v1/agent/tasks/" + task_id, headers=headers()).json()
    assert recovered["draft_id"] == draft_id
    assert client.get(url(draft_id, "execution"), headers=headers()).json()["receipt"] == receipt
    assert client.get("/api/v1/operations/" + request["operation_id"], headers=headers()).json() == receipt
    assert post(client, draft_id, request).json() == receipt
    count = len(real_p7)
    assert client.post("/api/v1/agent/messages", headers=headers(), json=message).json()["task_id"] == task_id
    assert len(real_p7) == count
    assert ("agent", "/agent/message") in real_p7 and ("agent", "/agent/clarification") in real_p7
    with Session() as db:
        event = db.scalar(select(BusinessEvent))
        assert db.query(BusinessEvent).count() == db.query(DraftOperation).count() == 1
        if action == "PLAN_ADD":
            row = db.scalar(select(ShoppingListItem))
            assert row.name == "纸巾" and row.quantity == 2
            assert receipt["result"]["shopping_item"]["id"] == str(row.id)
        elif action == "ADD":
            row = db.get(InventoryItem, UUID(receipt["result"]["inventory_item"]["id"]))
            assert row.name == "纸巾" and row.quantity == 2 and row.storage_location == "储物柜"
        else:
            row = db.get(InventoryItem, ids["batch"])
            assert row.version == 2
            assert Decimal(receipt["result"]["inventory_item"]["quantity"]) == row.quantity
            if action == "CONSUME":
                assert row.quantity == 4 and event.event_type == "Consumed" and event.quantity == 1
            else:
                assert row.quantity == 5 and row.storage_location == "书房"


def test_message_timeout_reuses_original_task(execution_state, monkeypatch):
    client, Session, ids = execution_state
    monkeypatch.setenv("AI_SERVICE_URL", "http://agent:8767")
    monkeypatch.setenv("AI_SERVICE_TOKEN", "synthetic-internal-token-at-least-32")
    original = httpx.AsyncClient
    attempts = []

    async def dispatch(request):
        attempts.append(request)
        if len(attempts) == 1:
            raise httpx.ReadTimeout("synthetic response loss", request=request)
        import json
        payload = json.loads(request.content)
        return httpx.Response(200, json={"status": "answered", "original_text": payload["text"],
                                         "trace_id": "synthetic", "facts": []})

    def local_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(dispatch)
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", local_client)
    message = dict(household_id=str(ids["home"]), text="库存有什么", request_id="timeout-recovery")
    assert client.post("/api/v1/agent/messages", headers=headers(), json=message).status_code == 503
    with Session() as db:
        stored = db.scalar(select(AITask))
        task_id = stored.id
        assert stored.status == "processing" and db.query(AIDraft).count() == 0
    result = client.post("/api/v1/agent/messages", headers=headers(), json=message)
    assert result.status_code == 200 and result.json()["task_id"] == str(task_id)
    monkeypatch.delenv("AI_SERVICE_TOKEN")
    assert client.post("/api/v1/agent/messages", headers=headers(), json=message).json() == result.json()
    with Session() as db:
        assert db.query(AITask).count() == 1 and db.query(DraftOperation).count() == 0
        assert db.get(InventoryItem, ids["batch"]).quantity == 5


def test_committed_operation_recovers_after_response_render_failure(execution_state, monkeypatch):
    from starlette.responses import JSONResponse
    client, Session, ids = execution_state
    draft_id, task_id = seed_draft(Session, ids)
    request = body()
    operation_path = "/api/v1/operations/" + request["operation_id"]
    assert client.get(operation_path, headers=headers()).status_code == 404
    render = JSONResponse.render

    def lost_response(self, content):
        if isinstance(content, dict) and content.get("status") == "committed":
            raise RuntimeError("synthetic response failure after durable commit")
        return render(self, content)

    with monkeypatch.context() as patcher:
        patcher.setattr(JSONResponse, "render", lost_response)
        assert post(client, draft_id, request).status_code == 500
    # Neither a prior 404 nor a failed POST response means the operation failed.
    receipt = client.get(operation_path, headers=headers()).json()
    assert receipt["status"] == "committed" and receipt["task_id"] == str(task_id)
    assert post(client, draft_id, request).json() == receipt
    with Session() as db:
        assert db.get(InventoryItem, ids["batch"]).quantity == 4
        assert db.query(DraftOperation).count() == db.query(BusinessEvent).count() == 1


def test_clarification_timeout_and_abandoned_lease_keep_original_task(execution_state, real_p7, monkeypatch):
    from fastapi import HTTPException
    client, Session, ids = execution_state
    initial = client.post("/api/v1/agent/messages", headers=headers(), json={
        "household_id": str(ids["home"]), "text": "喝了牛奶", "request_id": "clarification-timeout"}).json()
    task_id = initial["task_id"]
    path = "/api/v1/agent/clarifications/" + task_id
    allowed = initial["result"]["clarification"]["allowed_fields"]
    request = {"revision": initial["revision"],
               "answers": {k: v for k, v in {"quantity": "1", "unit": "盒"}.items() if k in allowed}}

    async def timeout(*args, **kwargs):
        raise HTTPException(503, "AI service unavailable")

    with monkeypatch.context() as patcher:
        patcher.setattr(agent_gateway, "_call_ai", timeout)
        assert client.post(path, headers=headers(), json=request).status_code == 503
    with Session.begin() as db:
        task = db.get(AITask, UUID(task_id))
        assert task.status == "needs_clarification" and task.revision == initial["revision"]
        assert task.context_json is not None
        task.status = "processing"
        task.processing_nonce = str(uuid4())
        task.lease_until = datetime.now(timezone.utc) + timedelta(seconds=30)
    assert client.post(path, headers=headers(), json=request).status_code == 409
    with Session.begin() as db:
        db.get(AITask, UUID(task_id)).lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    response = client.post(path, headers=headers(), json=request)
    assert response.status_code == 200, response.text
    assert response.json()["task_id"] == task_id and response.json()["status"] == "needs_confirmation"
    with Session() as db:
        assert db.query(AITask).count() == db.query(AIDraft).count() == 1
        assert db.query(DraftOperation).count() == 0
        assert db.get(InventoryItem, ids["batch"]).quantity == 5


@pytest.mark.parametrize("action", ["MOVE", "CONSUME"])
def test_version_change_after_draft_never_mutates(execution_state, action):
    client, Session, ids = execution_state
    draft_id, _ = seed_draft(Session, ids, action)
    with Session.begin() as db:
        db.get(InventoryItem, ids["batch"]).version = 2
    result = post(client, draft_id, body())
    assert result.status_code == 409 and result.json()["detail"]["code"] == "INVENTORY_VERSION_CONFLICT"
    with Session() as db:
        assert db.get(InventoryItem, ids["batch"]).quantity == 5
        assert db.get(InventoryItem, ids["batch"]).storage_location == "冰箱"
        assert db.query(DraftOperation).count() == db.query(BusinessEvent).count() == 0


@pytest.mark.parametrize("marker", [
    {"planning_basis": {"snapshot_id": "stale"}},
    {"quantity_source": "planning_calculation"}, {"intent": "SUGGEST_PURCHASE"},
])
def test_automatic_plan_never_commits(execution_state, marker):
    client, Session, ids = execution_state
    draft_id, task_id = seed_draft(Session, ids, "PLAN_ADD")
    with Session.begin() as db:
        task = db.get(AITask, task_id)
        task.result_json = {**task.result_json, **marker}
    assert client.get(url(draft_id, "execution"), headers=headers()).json()["status"] == "unavailable"
    assert post(client, draft_id, body(edits={"quantity": "3"})).json()["detail"]["code"] == "PLANNING_REVALIDATION_UNAVAILABLE"
    with Session() as db:
        assert db.query(ShoppingListItem).count() == db.query(DraftOperation).count() == 0


@pytest.mark.parametrize("committed", [False, True])
def test_removed_member_cannot_read_or_execute_old_work(execution_state, committed):
    client, Session, ids = execution_state
    draft_id, task_id = seed_draft(Session, ids)
    request = body()
    if committed:
        assert post(client, draft_id, request).status_code == 200
    with Session.begin() as db:
        db.delete(db.get(HouseholdMember, (ids["home"], ids["user"])))
    for path in ("/api/v1/agent/tasks/" + str(task_id), "/api/v1/drafts/" + str(draft_id),
                 url(draft_id, "execution"), "/api/v1/operations/" + request["operation_id"]):
        assert client.get(path, headers=headers()).status_code == 404
    assert post(client, draft_id, request).status_code == 404
    assert client.post(url(draft_id, "cancel"), headers=headers(),
                       json={"task_revision": 1, "draft_revision": 1}).status_code == 404
    assert client.post("/api/v1/agent/clarifications/" + str(task_id), headers=headers(),
                       json={"revision": 1, "answers": {"quantity": "1"}}).status_code == 404
    with Session() as db:
        # The authorized operation remains durable even though queries now return 404.
        assert db.query(DraftOperation).count() == int(committed)
        assert db.get(InventoryItem, ids["batch"]).quantity == (4 if committed else 5)


def test_membership_removed_while_waiting_for_ai(execution_state, monkeypatch):
    client, Session, ids = execution_state
    monkeypatch.setenv("AI_SERVICE_URL", "http://agent:8767")
    monkeypatch.setenv("AI_SERVICE_TOKEN", "synthetic-internal-token-at-least-32")

    async def upstream(path, user, home, payload):
        with Session.begin() as db:
            db.delete(db.get(HouseholdMember, (home, user)))
        return {"status": "needs_confirmation", "trace_id": "synthetic", "original_text": payload["text"],
                "draft": {"action": "ADD", "name": "纸巾", "quantity": "1", "unit": "包", "location": "柜子"}}

    monkeypatch.setattr(agent_gateway, "_call_ai", upstream)
    result = client.post("/api/v1/agent/messages", headers=headers(), json={
        "household_id": str(ids["home"]), "text": "买了1包纸巾放柜子", "request_id": "removed-inflight"})
    assert result.status_code == 404
    with Session() as db:
        assert db.query(AIDraft).count() == db.query(DraftOperation).count() == 0


def test_planning_snapshot_uses_commit_time_and_unknown_minimum(execution_state):
    client, Session, ids = execution_state
    draft_id, _ = seed_draft(Session, ids)
    receipt = post(client, draft_id, body()).json()
    with Session.begin() as db:
        operation = db.get(DraftOperation, UUID(receipt["operation_id"]))
        operation.committed_at += timedelta(minutes=1)
    with Session() as db:
        snapshot = planning_context.snapshot(db, ids["user"], ids["home"])
        item = snapshot["items"][0]
        event = item["events"][0]
        assert event["kind"] == "Consumed" and event["committed"] is True
        assert datetime.fromisoformat(event["recorded_at"]) > datetime.fromisoformat(event["occurred_at"])
        assert item["preferences"]["minimum_stock"] is None


def test_unique_routes_and_unchanged_public_fields():
    keys = [(method, route.path) for route in app.routes for method in getattr(route, "methods", [])]
    assert len(keys) == len(set(keys))
    assert set(agent_gateway.NewMessage.model_fields) == {"household_id", "text", "request_id", "household_timezone"}
    assert agent_gateway.ALLOWED_ANSWERS == {
        "name", "quantity", "unit", "location", "purchased_at", "label_expiry", "opened_at", "to_location", "batch_id"}


@pytest.mark.parametrize("expiry", ["invalid", "2026-10-23T10:00:00", "2000-01-01T00:00:00+00:00"])
def test_invalid_ai_expiry_cannot_persist_context(execution_state, monkeypatch, expiry):
    client, Session, ids = execution_state
    monkeypatch.setenv("AI_SERVICE_URL", "http://agent:8767")
    monkeypatch.setenv("AI_SERVICE_TOKEN", "synthetic-internal-token-at-least-32")

    async def upstream(path, user, home, payload):
        return {"status": "needs_clarification", "trace_id": "synthetic", "original_text": payload["text"],
                "clarification": {"scope": {"user_id": str(user), "household_id": str(home)},
                    "revision": 1, "expires_at": expiry, "allowed_fields": ["quantity"]}}

    monkeypatch.setattr(agent_gateway, "_call_ai", upstream)
    response = client.post("/api/v1/agent/messages", headers=headers(), json={
        "household_id": str(ids["home"]), "text": "喝了牛奶", "request_id": "invalid-expiry"})
    assert response.status_code == 503
    with Session() as db:
        task = db.scalar(select(AITask))
        assert task.status == "processing" and task.context_json is None and task.result_json is None
        assert db.query(AIDraft).count() == 0


def test_superseded_worker_cannot_publish_or_restore(execution_state):
    from fastapi import HTTPException
    _, Session, ids = execution_state
    _, task_id = seed_draft(Session, ids)
    with Session.begin() as db:
        task = db.get(AITask, task_id)
        task.status = "processing"
        task.processing_nonce = "new-worker"
    with Session() as db:
        task = db.get(AITask, task_id)
        with pytest.raises(HTTPException) as error:
            agent_gateway.save_result(db, task, "old-worker", {"status": "answered"})
        assert error.value.status_code == 409
        db.rollback()
        agent_gateway.restore_after_failure(db, task, "old-worker", "error")
    with Session() as db:
        task = db.get(AITask, task_id)
        assert task.status == "processing" and task.processing_nonce == "new-worker"
