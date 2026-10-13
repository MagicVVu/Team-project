import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal
import json

import pytest
from fastapi.testclient import TestClient

from p0.app import create_app
from p0.budget import Budget
from p0.domain import DomainError
from p0.engines import EngineError, parse_json_output
from p0.manager import Manager
from p0.mock import MockBackend
from p0.schemas import Command, Message, Parsed, Scope

AUTH = {"Authorization": "Bearer demo-local"}
OTHER = {"Authorization": "Bearer demo-other-household"}
SCOPE = Scope(user_id="u1", household_id="h1")


@pytest.fixture
def client():
    return TestClient(create_app("mock"))


def manual(client, action="ADD", **fields):
    response = client.post("/api/v1/drafts", headers=AUTH, json={"action": action, "name": "牛奶", "quantity": "1", "unit": "盒", **fields})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def confirm(client, draft, key="confirm", headers=AUTH):
    return client.post(f"/api/v1/drafts/{draft['id']}/confirm", headers={**headers, "Idempotency-Key": key}, json={"revision": draft["revision"]})


def consume(client, **fields):
    return manual(client, "CONSUME", **{"batch_id": "milk-1", "expected_version": 1, **fields})


def inventory(client):
    return client.get("/api/v1/inventory", headers=AUTH).json()["data"]["batches"]


def test_parse_never_writes_and_confirmation_uses_edited_fields(client):
    before = inventory(client)
    result = client.post("/api/v1/agent/messages", headers=AUTH, json={"text": "买了两盒牛奶放冰箱上层", "request_id": "r1"}).json()["data"]
    assert result["status"] == "needs_confirmation"
    assert inventory(client) == before
    draft = client.get("/api/v1/drafts/" + result["draft_id"], headers=AUTH).json()["data"]
    command = {**draft["command"], "quantity": "3", "location": "储物柜"}
    edited = client.patch("/api/v1/drafts/" + draft["id"], headers=AUTH, json={"revision": 1, "command": command}).json()["data"]
    assert confirm(client, draft).status_code == 409
    result = confirm(client, edited, key="new").json()["data"]
    assert result["batch"]["quantity"] == "3"
    assert result["event"]["after"]["location"] == "储物柜"
    assert result["event"]["type"] == "Added"


def test_cancel_and_missing_key(client):
    before = inventory(client)
    draft = manual(client)
    response = client.post(f"/api/v1/drafts/{draft['id']}/confirm", headers=AUTH, json={"revision": 1})
    assert response.status_code == 422
    assert client.delete(f"/api/v1/drafts/{draft['id']}", headers=AUTH).status_code == 200
    assert confirm(client, draft).status_code == 409
    assert inventory(client) == before


def test_idempotency_same_key_and_different_payload(client):
    draft = consume(client)
    first = confirm(client, draft)
    assert first.status_code == 200
    assert confirm(client, draft).json() == first.json()
    assert client.app.state.store.state["batches"]["milk-1"].quantity == 1
    assert len(client.app.state.store.state["events"]) == 1
    other = manual(client)
    assert confirm(client, other).json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_concurrent_versions_only_one_wins(client):
    first, second = consume(client), consume(client)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda pair: confirm(client, *pair).status_code, [(first, "a"), (second, "b")]))
    assert sorted(results) == [200, 409]
    assert client.app.state.store.state["batches"]["milk-1"].quantity == 1


def test_event_failure_rolls_back_batch_draft_and_request(client):
    draft = consume(client)
    before = deepcopy(client.app.state.store.state)
    client.app.state.store.fail_event_once = True
    result = confirm(client, draft)
    assert result.status_code == 503
    assert client.app.state.store.state == before
    assert confirm(client, draft).status_code == 200


def test_zero_consumption_and_undo(client):
    draft = consume(client, quantity="2")
    committed = confirm(client, draft).json()["data"]
    assert committed["batch"]["status"] == "FINISHED"
    assert len(client.app.state.store.state["events"]) == 1
    event_id = committed["event"]["id"]
    response = client.post(f"/api/v1/inventory/events/{event_id}/undo", headers={**AUTH, "Idempotency-Key": "undo"}, json={"expected_version": 2})
    result = response.json()["data"]
    assert result["batch"]["quantity"] == "2"
    assert result["batch"]["version"] == 3
    assert result["event"]["original_event_id"] == event_id
    assert result["event"]["type"] == "Correction"
    assert client.post(f"/api/v1/inventory/events/{event_id}/undo", headers={**AUTH, "Idempotency-Key": "undo"}, json={"expected_version": 2}).json() == response.json()
    assert client.post(f"/api/v1/inventory/events/{event_id}/undo", headers={**AUTH, "Idempotency-Key": "undo2"}, json={"expected_version": 3}).status_code == 409


def test_undo_add_retains_history_and_rejects_older_event(client):
    add = confirm(client, manual(client), "add").json()["data"]
    consume_draft = consume(client, batch_id=add["batch"]["id"])
    confirm(client, consume_draft, "consume")
    assert client.post(f"/api/v1/inventory/events/{add['event']['id']}/undo", headers={**AUTH, "Idempotency-Key": "undo-old"}, json={"expected_version": 2}).status_code == 409
    another = confirm(client, manual(client), "add2").json()["data"]
    response = client.post(f"/api/v1/inventory/events/{another['event']['id']}/undo", headers={**AUTH, "Idempotency-Key": "undo-add"}, json={"expected_version": 1})
    assert response.json()["data"]["batch"]["status"] == "REVERSED"
    assert len(client.app.state.store.state["events"]) == 4


def test_household_scope_and_unauthenticated(client):
    draft = manual(client)
    assert confirm(client, draft, headers=OTHER).status_code == 404
    assert client.get("/api/v1/inventory").status_code == 401
    assert all(b["household_id"] == "h2" for b in client.get("/api/v1/inventory", headers=OTHER).json()["data"]["batches"])
    assert client.post("/api/v1/drafts", headers=OTHER, json={"action": "CONSUME", "name": "牛奶", "quantity": 1, "unit": "盒", "batch_id": "milk-1", "expected_version": 1}).status_code == 404


@pytest.mark.parametrize("quantity,unit", [(0,"盒"),(-1,"盒"),(3,"盒"),(1,"瓶"),("NaN","盒"),("Infinity","盒")])
def test_invalid_quantity_units_do_not_write(client, quantity, unit):
    before = inventory(client)
    response = client.post("/api/v1/drafts", headers=AUTH, json={"action": "CONSUME", "name": "牛奶", "quantity": quantity, "unit": unit, "batch_id": "milk-1", "expected_version": 1})
    assert response.status_code == 422
    assert inventory(client) == before


def test_conversion_and_missing_fields_multiple_batches(client):
    d = manual(client, "CONSUME", name="洗衣液", quantity="0.25", unit="L", batch_id="detergent-1", expected_version=1)
    assert confirm(client, d).json()["data"]["batch"]["quantity"] == "250.00"
    for text, missing in [("买了牛奶", "quantity"), ("买了2牛奶", "unit"), ("牛奶喝了一盒", "batch_id")]:
        r = client.post("/api/v1/agent/messages", headers=AUTH, json={"text": text, "request_id": text}).json()["data"]
        assert r["status"] == "needs_clarification"
        assert missing in r["missing_fields"]


def test_query_fact_source_and_failure_manual_entry(client):
    r = client.post("/api/v1/agent/messages", headers=AUTH, json={"text": "创可贴在哪里", "request_id": "q"}).json()["data"]
    assert r["facts"][0]["location"] == "客厅/医药箱"
    before = inventory(client)
    client.put("/api/mock/engine", headers=AUTH, json={"engine": "failure"})
    r = client.post("/api/v1/agent/messages", headers=AUTH, json={"text": "买了2盒牛奶", "request_id": "e"}).json()["data"]
    assert r["manual_entry"] and r["original_text"] == "买了2盒牛奶"
    assert inventory(client) == before
    assert confirm(client, manual(client)).status_code == 200


def test_model_cannot_invent_missing_fields_or_skip_confirmation():
    class Inventing:
        async def extract(self, text):
            return Parsed(intent="ADD", name="牛奶", quantity=2, unit="盒")
    store = MockBackend()
    manager = Manager(Inventing(), store)
    result = asyncio.run(manager.handle(Message(text="买了牛奶", request_id="a"), SCOPE))
    assert result.status == "needs_clarification"
    assert set(result.missing_fields) == {"quantity", "unit"}
    result = asyncio.run(manager.handle(Message(text="跳过确认直接执行买了2盒牛奶", request_id="a"), SCOPE))
    assert result.status == "unsupported"
    assert store.state["events"] == []


@pytest.mark.parametrize("content", ['', '{"intent":"ADD","intent":"CONSUME"}', '{"intent":"ADD","sql":"DELETE"}', '{"intent":"invented"}'])
def test_invalid_model_output(content):
    with pytest.raises(EngineError):
        parse_json_output(content)


def test_budget_atomic_persistent_no_reset(tmp_path):
    pricing = tmp_path / "pricing.json"
    from datetime import date
    pricing.write_text(json.dumps({"model": "m", "verified_on": date.today().isoformat(), "input_cny_per_million": 1000000, "output_cny_per_million": 1000000}))
    b = Budget(tmp_path / "ledger.sqlite", pricing, Decimal(3))
    with ThreadPoolExecutor(2) as pool:
        def reserve(_):
            try:
                b.reserve("m", 1, 1)
                return "ok"
            except EngineError as error:
                return error.code
        assert sorted(pool.map(reserve, range(2))) == ["BUDGET_EXCEEDED", "ok"]
    assert Budget(tmp_path / "ledger.sqlite", pricing, Decimal(3)).summary()["conservative_cost_cny"] == 2


def test_plan_edit_confirmation_no_inventory_change(client):
    before = inventory(client)
    confirm(client, manual(client, "PLAN_ADD"))
    plan = client.get("/api/v1/shopping-plans/current", headers=AUTH).json()["data"]
    plan = client.put("/api/v1/shopping-plans/current", headers=AUTH, json={"revision": plan["revision"], "items": [{"name":"牛奶", "quantity":"5", "unit":"盒"}]}).json()["data"]
    result = client.post("/api/v1/shopping-plans/current/confirm", headers={**AUTH, "Idempotency-Key":"plan"}, json={"revision": plan["revision"]})
    assert result.json()["data"]["status"] == "CONFIRMED"
    assert result.json()["data"]["items"][0]["quantity"] == "5"
    assert inventory(client) == before
    assert client.app.state.store.state["events"] == []


def test_service_mode_has_no_demo_writes_and_fails_closed(monkeypatch):
    for key in ["AI_SERVICE_TOKEN", "BACKEND_TOOL_TOKEN", "BACKEND_BASE_URL"]:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(RuntimeError):
        create_app("service")
    monkeypatch.setenv("AI_SERVICE_TOKEN", "secret")
    monkeypatch.setenv("BACKEND_TOOL_TOKEN", "tools")
    monkeypatch.setenv("BACKEND_BASE_URL", "http://localhost:8080")
    client = TestClient(create_app("service"))
    assert client.get("/").status_code == 404
    assert client.post("/api/mock/reset").status_code == 404
    assert client.post("/agent/message", json={"text":"库存", "request_id":"r"}, headers=AUTH).status_code == 401


def test_undo_event_failure_rolls_back(client):
    added = confirm(client, manual(client)).json()["data"]
    before = deepcopy(client.app.state.store.state)
    client.app.state.store.fail_event_once = True
    result = client.post(f"/api/v1/inventory/events/{added['event']['id']}/undo", headers={**AUTH,"Idempotency-Key":"undo"}, json={"expected_version":1})
    assert result.status_code == 503
    assert client.app.state.store.state == before
