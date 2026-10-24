"""Local-only repairs over existing tables, including real AI/HTTP read paths."""
from uuid import uuid4, UUID
from sqlalchemy import select, func
import pytest

from test_v09_execution import execution_state, seed_draft, body, post, headers, url
from test_backend_p2_conversation import p7, legacy, multiple
from app.models import AITask, InventoryItem, ShoppingListItem, HouseholdMember
from app.execution_models import BusinessEvent, DraftOperation


def set_result(Session, task_id, **values):
    with Session.begin() as db:
        task = db.get(AITask, task_id)
        task.result_json = {**task.result_json, **values}


def test_all_consumption_is_protected_versioned_and_replayed(execution_state):
    client, Session, ids = execution_state
    draft, task = seed_draft(Session, ids, quantity="5")
    set_result(Session, task, consume_mode="all", quantity_source="current_batch")
    assert client.get(url(draft, "execution"), headers=headers()).json()["editable_fields"] == []
    denied = post(client, draft, body(edits={"quantity": "1"}))
    assert denied.status_code == 422 and denied.json()["detail"]["code"] == "PROTECTED_OR_UNKNOWN_FIELD"
    request = body()
    result = post(client, draft, request)
    assert result.status_code == 200, result.text
    assert post(client, draft, request).json() == result.json()
    with Session() as db:
        item = db.get(InventoryItem, ids["batch"])
        assert item.quantity == 0 and item.status == "FINISHED" and item.version == 2
        assert db.query(BusinessEvent).count() == db.query(DraftOperation).count() == 1
        assert db.scalar(select(BusinessEvent)).quantity == 5


@pytest.mark.parametrize("change,code", [("version", "INVENTORY_VERSION_CONFLICT"), ("quantity", "CONSUME_ALL_QUANTITY_CONFLICT")])
def test_finish_never_silently_changes_all_quantity(execution_state, change, code):
    client, Session, ids = execution_state
    draft, task = seed_draft(Session, ids, quantity="5")
    set_result(Session, task, consume_mode="all", quantity_source="current_batch")
    with Session.begin() as db:
        item = db.get(InventoryItem, ids["batch"])
        setattr(item, change, getattr(item, change)+1)
    result = post(client, draft, body())
    assert result.status_code == 409 and result.json()["detail"]["code"] == code
    with Session() as db: assert db.query(BusinessEvent).count() == 0


def test_manual_plan_preserves_validated_source_in_existing_foreign_key(execution_state):
    client, Session, ids = execution_state
    draft, task = seed_draft(Session, ids, "PLAN_ADD", name="牛奶", unit="盒")
    set_result(Session, task, procurement_source={"batch_id": str(ids["batch"]), "expected_version": 1})
    request = body()
    result = post(client, draft, request)
    assert result.status_code == 200, result.text
    assert post(client, draft, request).json() == result.json()
    assert result.json()["result"]["shopping_item"]["source_inventory_item_id"] == str(ids["batch"])
    with Session() as db:
        assert db.scalar(select(ShoppingListItem)).source_inventory_item_id == ids["batch"]
        assert db.get(InventoryItem, ids["batch"]).quantity == 5


@pytest.mark.parametrize("problem,code", [("version", "INVENTORY_VERSION_CONFLICT"), ("name", "INVENTORY_IDENTITY_CHANGED"),
    ("unit", "UNIT_MISMATCH"), ("foreign", "INVENTORY_NOT_FOUND")])
def test_procurement_source_cannot_bypass_scope_version_or_units(execution_state, problem, code):
    client, Session, ids = execution_state
    draft, task = seed_draft(Session, ids, "PLAN_ADD", name="牛奶" if problem != "name" else "纸巾",
                             unit="盒" if problem != "unit" else "kg")
    set_result(Session, task, procurement_source={"batch_id": str(ids["batch"]), "expected_version": 1 if problem != "version" else 2})
    if problem == "foreign":
        with Session.begin() as db: db.get(InventoryItem, ids["batch"]).household_id = ids["foreign_home"]
    result = post(client, draft, body())
    assert result.status_code in {404, 409, 422} and result.json()["detail"]["code"] == code
    with Session() as db: assert db.query(ShoppingListItem).count() == db.query(BusinessEvent).count() == 0


def test_shared_summary_preserves_private_receipt_permissions(execution_state):
    client, Session, ids = execution_state
    draft, _ = seed_draft(Session, ids)
    request = body()
    assert post(client, draft, request).status_code == 200
    with Session.begin() as db:
        db.add(HouseholdMember(household_id=ids["home"], user_id=ids["outsider"], role="member"))
    route = f'/api/v1/households/{ids["home"]}/operations/{request["operation_id"]}/summary'
    response = client.get(route, headers=headers("outsider"))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["name"] == "牛奶" and data["event_type"] == "Consumed"
    assert response.headers["cache-control"] == "no-store"
    assert not {"task_id", "draft_id", "scope", "original_text", "request_hash", "command_json"} & data.keys()
    assert "history_json" not in data["after"]
    assert client.get('/api/v1/operations/'+request["operation_id"], headers=headers("outsider")).status_code == 404
    assert client.get(route.replace(str(ids["home"]), str(ids["foreign_home"])), headers=headers("outsider")).status_code == 404


def test_archived_details_are_readable_without_changing_default_list(execution_state, monkeypatch):
    client, Session, ids = execution_state
    monkeypatch.setenv("MAGICVVU_DISCARD_EXECUTION", "true")
    draft, _ = seed_draft(Session, ids, "DISCARD", quantity="5", discard_mode="all")
    assert post(client, draft, body()).status_code == 200
    route = f'/api/v1/households/{ids["home"]}/inventory-items'
    assert client.get(route, headers=headers()).json()["total"] == 0
    archived = client.get(route+'?status=DISCARDED', headers=headers()).json()
    assert archived["total"] == 1 and archived["items"][0]["status"] == "DISCARDED"
    assert client.get(route+'/'+str(ids["batch"]), headers=headers()).json()["status"] == "DISCARDED"
    assert client.get(route+'/'+str(ids["batch"]), headers=headers("outsider")).status_code == 404
    assert client.get(route+'?status=garbage', headers=headers()).status_code == 422


BUTTONS = ["查看它最近28天的消费统计", "这批还能用多久？", "评估这批的风险和缺少的标签储存资料",
           "根据记录计算这批的补货建议，只展示建议，不提交采购", "这批已经全部用完"]


@pytest.mark.parametrize("text", BUTTONS)
def test_actual_android_text_real_ai_real_backend_reader(execution_state, p7, text):
    client, Session, ids = execution_state
    multiple(Session, ids)
    source = legacy(client, ids, "牛奶还有多少")
    count = p7[0].calls
    response = client.post('/api/v1/agent/reference-messages', headers=headers(), json={
        "household_id": str(ids["home"]), "text": text, "request_id": uuid4().hex,
        "source_task_id": source["task_id"], "source_revision": source["revision"], "batch_id": str(ids["batch"])})
    assert response.status_code == 200, response.text
    task = response.json()["task"]
    result = task["result"]
    assert task["status"] == ("needs_confirmation" if text == BUTTONS[-1] else "answered"), result
    assert result["reference_used"]["batch_id"] == str(ids["batch"])
    if text != BUTTONS[-1]: assert [b["id"] for b in result["facts"]] == [str(ids["batch"])]
    else:
        assert result["draft"]["quantity"] == "5.000000" and result["consume_mode"] == "all"
        assert post(client, UUID(task["draft_id"]), body(task_revision=task["revision"])).status_code == 200
    assert p7[0].calls == count
    with Session() as db:
        assert db.query(BusinessEvent).count() == (1 if text == BUTTONS[-1] else 0)


def test_post_commit_feedback_uses_real_proof_and_never_reexecutes(execution_state, p7):
    client, Session, ids = execution_state
    draft, _ = seed_draft(Session, ids)
    request = body()
    assert post(client, draft, request).status_code == 200
    count = p7[0].calls
    route = '/api/v1/operations/'+request["operation_id"]+'/feedback'
    response = client.post(route, headers=headers())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["business_committed"] and result["feedback_status"] in {"available", "partial"}, result
    assert result["result"]["feedback"]["operation_id"] == request["operation_id"]
    assert client.post(route, headers=headers("outsider")).status_code == 404
    assert p7[0].calls == count
    with Session() as db: assert db.query(BusinessEvent).count() == db.query(DraftOperation).count() == 1


def test_feedback_failure_does_not_repeat_or_hide_success(execution_state, monkeypatch):
    client, Session, ids = execution_state
    draft, _ = seed_draft(Session, ids)
    request = body()
    assert post(client, draft, request).status_code == 200
    monkeypatch.delenv("AI_SERVICE_TOKEN", raising=False)
    response = client.post('/api/v1/operations/'+request["operation_id"]+'/feedback', headers=headers())
    assert response.status_code == 200 and response.json()["business_committed"]
    assert response.json()["feedback_status"] == "unavailable"
    with Session() as db: assert db.query(BusinessEvent).count() == db.query(DraftOperation).count() == 1


def test_plan_feedback_is_pending_only_without_fake_batch_versions(execution_state):
    client, Session, ids = execution_state
    draft, _ = seed_draft(Session, ids, "PLAN_ADD")
    request = body()
    assert post(client, draft, request).status_code == 200
    result = client.post('/api/v1/operations/'+request["operation_id"]+'/feedback', headers=headers()).json()
    assert result["business_committed"] and result["feedback_status"] == "not_applicable" and result["result"] is None


def test_legacy_compatibility_reports_target_without_mutation(execution_state):
    client, Session, ids = execution_state
    with Session.begin() as db: db.get(InventoryItem, ids["batch"]).unit = "箱"
    route = f'/api/v1/households/{ids["home"]}/inventory-ai-compatibility'
    response = client.get(route, headers=headers())
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["scope"] == "page_only" and not page["page_compatible"] and page["next_offset"] is None
    assert page["issues"][0]["batch_id"] == str(ids["batch"]) and page["issues"][0]["field"] == "unit"
    assert client.get(route, headers=headers("outsider")).status_code == 404
    with Session() as db:
        assert db.get(InventoryItem, ids["batch"]).unit == "箱"
        assert db.query(BusinessEvent).count() == 0


def test_local_backend_openapi_exports_actual_routes(execution_state):
    import json
    from pathlib import Path
    from app.main import app
    contract = Path(__file__).resolve().parents[3]/"docs/versions/V1-P8.1/contracts/backend-openapi.json"
    exported = json.loads(contract.read_text(encoding="utf-8"))
    assert exported.pop("x-deployment-status") == "local_source_contract"
    assert exported == app.openapi()


@pytest.mark.parametrize("bad", [["invalid"], {"status": "answered", "inventory_writes": True},
    {"status": "answered", "inventory_writes": False, "shopping_writes": False,
     "feedback": {"operation_id": "different", "business_committed": True}}])
def test_invalid_feedback_is_not_trusted_or_retried(execution_state, monkeypatch, bad):
    import httpx
    client, Session, ids = execution_state
    draft, _ = seed_draft(Session, ids)
    request = body()
    assert post(client, draft, request).status_code == 200
    calls = []
    async def dispatch(req):
        calls.append(req.url.path)
        return httpx.Response(200, json=bad)
    original = httpx.AsyncClient
    def local_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(dispatch)
        return original(*args, **kwargs)
    monkeypatch.setattr(httpx, "AsyncClient", local_client)
    monkeypatch.setenv("AI_SERVICE_URL", "http://agent:8767")
    monkeypatch.setenv("AI_SERVICE_TOKEN", "synthetic-feedback-service-token-at-least-32")
    response = client.post('/api/v1/operations/'+request["operation_id"]+'/feedback', headers=headers())
    assert response.status_code == 200 and response.json()["feedback_status"] == "unavailable"
    assert response.json()["business_committed"] and calls == ["/feedback/after-commit"]
    with Session() as db: assert db.query(BusinessEvent).count() == db.query(DraftOperation).count() == 1


def test_referenced_plan_real_round_trip_retains_source_and_pending(execution_state, p7):
    client, Session, ids = execution_state
    source = legacy(client, ids, "牛奶还有多少")
    response = client.post('/api/v1/agent/reference-messages', headers=headers(), json={
        "household_id": str(ids["home"]), "text": "计划买它", "request_id": uuid4().hex,
        "source_task_id": source["task_id"], "source_revision": source["revision"], "batch_id": str(ids["batch"])})
    assert response.status_code == 200, response.text
    first = response.json()["task"]
    assert first["status"] == "needs_clarification", first
    count = p7[0].calls
    response = client.post('/api/v1/agent/clarifications/'+first["task_id"], headers=headers(),
        json={"revision": first["revision"], "answers": {"quantity": "2", "unit": "盒"}})
    assert response.status_code == 200, response.text
    task = response.json()
    assert task["status"] == "needs_confirmation" and p7[0].calls == count
    assert task["result"]["procurement_source"] == {"batch_id": str(ids["batch"]), "expected_version": 1}
    assert post(client, UUID(task["draft_id"]), body(task_revision=task["revision"])).status_code == 200
    tool_headers = {"Authorization": "Bearer synthetic-p2-tool-token-at-least-32",
        "X-User-Id": str(ids["user"]), "X-Household-Id": str(ids["home"])}
    response = client.get('/internal/v1/planning/context', headers=tool_headers,
        params={"item_key": str(ids["batch"])})
    assert response.status_code == 200, response.text
    snapshot = response.json()["data"]
    assert snapshot["pending_complete"] and len(snapshot["pending"]) == 1
    assert snapshot["pending"][0]["item_key"] == str(ids["batch"])
    assert snapshot["pending"][0]["quantity"] == "2.000"
    with Session() as db: assert db.get(InventoryItem, ids["batch"]).quantity == 5
