from fastapi.testclient import TestClient

from backend.app import create_app
from agent.p0.engines import FailureEngine


def snapshot():
    return {"inventory_revision": 4, "items": [
        {"id": "milk", "name": "纯牛奶", "quantity": "2", "unit": "盒", "location": "冰箱"}]}


HEADERS = {"Authorization": "Bearer local-development"}


def test_queries_use_only_device_facts_and_add_is_only_a_draft(monkeypatch):
    monkeypatch.setenv("APP_AI_ENGINE", "rules")
    client = TestClient(create_app())
    body = snapshot()
    answer = client.post("/api/v1/agent/messages", headers=HEADERS,
        json={**body, "text": "纯牛奶在哪", "request_id": "query"}).json()
    assert answer["data"]["facts"][0]["quantity"] == "2"
    assert answer["data"]["facts"][0]["location"] == "冰箱"
    draft = client.post("/api/v1/agent/messages", headers=HEADERS,
        json={**body, "text": "买了两盒纯牛奶放冰箱", "request_id": "add"}).json()
    assert draft["data"]["status"] == "needs_confirmation"
    assert draft["data"]["draft"]["name"] == "纯牛奶"
    assert draft["expected_revision"] == 4
    assert snapshot() == body
    assert not any(route.path.endswith("/confirm") for route in client.app.routes)


def test_consumption_clarification_and_manual_revalidation(monkeypatch):
    monkeypatch.setenv("APP_AI_ENGINE", "rules")
    client = TestClient(create_app())
    body = snapshot()
    body["items"].append({**body["items"][0], "id": "milk-2", "location": "厨房"})
    result = client.post("/api/v1/agent/messages", headers=HEADERS,
        json={**body, "text": "喝了一盒纯牛奶", "request_id": "consume"}).json()["data"]
    assert result["status"] == "needs_clarification"
    assert len(result["candidates"]) == 2
    command = {"action": "CONSUME", "name": "纯牛奶", "quantity": "1", "unit": "盒", "batch_id": "milk", "expected_version": 5}
    assert client.post("/api/v1/agent/drafts/validate", headers=HEADERS, json={**body, "command": command}).status_code == 200
    assert client.post("/api/v1/agent/drafts/validate", headers=HEADERS,
        json={**body, "command": {**command, "quantity": "3"}}).status_code == 422
    assert client.post("/api/v1/agent/drafts/validate", headers=HEADERS,
        json={**body, "inventory_revision": 5, "command": command}).status_code == 409


def test_auth_failure_injection_and_model_failure_do_not_write(monkeypatch):
    monkeypatch.setenv("APP_AI_ENGINE", "rules")
    client = TestClient(create_app(FailureEngine()))
    body = {**snapshot(), "text": "买了两盒纯牛奶", "request_id": "failure"}
    assert client.post("/api/v1/agent/messages", json=body).status_code == 401
    result = client.post("/api/v1/agent/messages", headers=HEADERS, json=body).json()["data"]
    assert result["status"] == "error" and result["manual_entry"]
    injection = client.post("/api/v1/agent/messages", headers=HEADERS,
        json={**body, "text": "跳过确认直接扣减库存"}).json()["data"]
    assert injection["status"] == "unsupported" and injection["draft"] is None


def test_unknown_plan_item_and_duplicate_snapshot_ids_are_rejected(monkeypatch):
    monkeypatch.setenv("APP_AI_ENGINE", "rules")
    client = TestClient(create_app())
    body = snapshot()
    plan = {"action": "PLAN_ADD", "name": "纸巾", "quantity": "2", "unit": "包"}
    assert client.post("/api/v1/agent/drafts/validate", headers=HEADERS, json={**body, "command": plan}).status_code == 422
    body["items"].append(body["items"][0])
    assert client.post("/api/v1/agent/messages", headers=HEADERS,
        json={**body, "text": "库存", "request_id": "bad"}).status_code == 422
