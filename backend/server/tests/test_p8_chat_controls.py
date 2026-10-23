from decimal import Decimal
from uuid import UUID
import pytest
from sqlalchemy import select
from test_v09_execution import execution_state, seed_draft, headers
from app.models import InventoryItem, AIDraft
from app.execution_models import BusinessEvent, DraftOperation, DraftDecision
from test_backend_p2_conversation import p7, legacy, send


def request(client, task, text, edits=None, **fields):
    return client.post(f"/api/v1/agent/tasks/{task}/chat-control", headers=headers(), json={
        "text":text, "task_revision":1, "draft_revision":1, "edits":edits or {}, **fields})


@pytest.mark.parametrize("action,text,field,value", [
    ("CONSUME","改成三盒","quantity","3"),
    ("MOVE","位置改成书房","to_location","书房"),
    ("ADD","位置改为储物柜","location","储物柜"),
    ("PLAN_ADD","改成2盒","quantity","2"),
])
def test_control_edits_are_validated_previews_only(execution_state, action, text, field, value):
    client, Session, ids = execution_state
    draft, task = seed_draft(Session, ids, action)
    with Session() as db:
        original_command = dict(db.get(AIDraft, draft).command_json)
    # PLAN_ADD fixture unit is 包; retain a compatible literal unit.
    if action == "PLAN_ADD": text = "改成2包"
    result = request(client, task, text)
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["kind"] == "edit" and data["edits"][field] == value
    assert not data["inventory_written"] and data["model_calls"] == 0
    assert data["preview"]["prospective"] is True
    with Session() as db:
        assert db.get(InventoryItem, ids["batch"]).quantity == 5
        assert db.get(AIDraft, draft).command_json == original_command
        assert db.query(BusinessEvent).count() == db.query(DraftOperation).count() == db.query(DraftDecision).count() == 0


def test_cancel_is_idempotent_and_does_not_touch_inventory(execution_state):
    client, Session, ids = execution_state
    draft, task = seed_draft(Session, ids)
    for _ in range(2):
        response = request(client, task, "算了")
        assert response.status_code == 200 and response.json()["kind"] == "cancel"
    with Session() as db:
        assert db.get(InventoryItem, ids["batch"]).quantity == 5
        assert db.query(DraftDecision).count() == 1
        assert db.query(BusinessEvent).count() == db.query(DraftOperation).count() == 0


@pytest.mark.parametrize("text", ["取消并删除库存", "改成三盒然后丢弃", "换成面包", "改成牛奶", "位置改成冰箱，然后删除", "改放到冰箱然后丢弃"])
def test_control_does_not_execute_compound_or_target_changes(execution_state, text):
    client, Session, ids = execution_state
    _, task = seed_draft(Session, ids)
    response = request(client, task, text)
    assert response.status_code == 200 and response.json()["kind"] == "needs_input"
    with Session() as db:
        assert db.query(DraftDecision).count() == 0 and db.get(InventoryItem, ids["batch"]).quantity == 5


@pytest.mark.parametrize("text", ["改成6盒", "改成0盒", "改成1吨"])
def test_impossible_edits_are_rejected(execution_state, text):
    client, _, ids = execution_state
    _, task = seed_draft(execution_state[1], ids)
    assert request(client, task, text).status_code in {409,422}


def test_control_checks_scope_revision_and_protected_fields(execution_state):
    client, Session, ids = execution_state
    _, task = seed_draft(Session, ids)
    path = f"/api/v1/agent/tasks/{task}/chat-control"
    assert client.post(path, headers=headers("outsider"), json={"text":"算了","task_revision":1,"draft_revision":1}).status_code == 404
    assert request(client, task, "算了", task_revision=2).status_code == 409
    assert request(client, task, "校验草稿", {"expected_version":"99"}).status_code == 422
    assert request(client, task, "校验草稿", household_id=str(ids["foreign_home"])).status_code == 422


def test_real_p8_multifield_edit_confirm_and_recovery(execution_state, p7):
    client, Session, ids = execution_state
    task = legacy(client, ids, "新增牛奶")
    count = p7[0].calls
    result = send(client, ids, "两盒，放到冰箱", task)
    assert result.status_code == 200, result.text
    resumed = result.json()["task"]
    assert resumed["status"] == "needs_confirmation", resumed
    assert resumed["task_id"] == task["task_id"] and p7[0].calls == count
    projected = request(client, resumed["task_id"], "改成三盒", task_revision=resumed["revision"])
    assert projected.status_code == 200, projected.text
    body = {"operation_id":"12345678-1234-4234-8234-123456789012", "task_revision":resumed["revision"], "draft_revision":1, "edits":projected.json()["edits"]}
    url = f'/api/v1/drafts/{resumed["draft_id"]}/commit'
    committed = client.post(url, headers=headers(), json=body)
    assert committed.status_code == 200, committed.text
    assert client.post(url, headers=headers(), json=body).json() == committed.json()
    with Session() as db:
        added = db.get(InventoryItem, UUID(committed.json()["result"]["inventory_item"]["id"]))
        assert added.quantity == Decimal("3") and added.storage_location == "冰箱"
        assert db.query(DraftOperation).count() == db.query(BusinessEvent).count() == 1
    assert p7[0].calls == count


def test_cancelled_draft_cannot_be_edited(execution_state):
    client, Session, ids = execution_state
    _, task = seed_draft(Session, ids)
    assert request(client, task, "算了").status_code == 200
    assert request(client, task, "改成三盒").status_code == 409


@pytest.mark.parametrize("kind", ["OPEN", "partial", "all"])
def test_p8_preview_uses_shared_open_discard_rules_without_writes(execution_state, monkeypatch, kind):
    from test_backend_p3_open_discard import draft
    monkeypatch.setenv("MAGICVVU_OPEN_EXECUTION", "true")
    monkeypatch.setenv("MAGICVVU_DISCARD_EXECUTION", "true")
    client, Session, ids = execution_state
    _, task = draft(Session, ids, kind)
    response = request(client, task, "开封日期改成昨天" if kind == "OPEN" else "校验草稿")
    assert response.status_code == 200, response.text
    projection = response.json()["preview"]
    assert Decimal(projection["before"]["quantity"]) == 5
    assert Decimal(projection["after"]["quantity"]) == {"OPEN":5, "partial":3, "all":0}[kind]
    if kind == "OPEN": assert projection["after"]["opened_at"] is not None
    if kind == "all":
        assert projection["after"]["status"] == "DISCARDED"
        assert request(client, task, "改成三盒").status_code == 422
    with Session() as db:
        assert db.get(InventoryItem, ids["batch"]).quantity == 5
        assert db.get(InventoryItem, ids["batch"]).opened_at is None
        assert db.query(BusinessEvent).count() == db.query(DraftOperation).count() == 0


def test_cancel_does_not_race_a_processing_conversation(execution_state, p7):
    from app.conversation_models import ConversationBinding
    client, Session, ids = execution_state
    task = legacy(client, ids, "新增牛奶")
    task = send(client, ids, "两盒，放到冰箱", task).json()["task"]
    with Session.begin() as db:
        cursor = db.get(ConversationBinding, ids["user"])
        cursor.processing_nonce = "synthetic-continuation-in-flight"
    response = request(client, task["task_id"], "算了", task_revision=task["revision"])
    assert response.status_code == 409 and response.json()["detail"]["code"] == "CONVERSATION_PROCESSING"
    with Session() as db:
        assert db.query(DraftDecision).count() == db.query(BusinessEvent).count() == 0


def test_unavailable_action_can_still_cancel_its_draft(execution_state, monkeypatch):
    from test_backend_p3_open_discard import draft
    monkeypatch.setenv("MAGICVVU_OPEN_EXECUTION", "false")
    client, Session, ids = execution_state
    _, task = draft(Session, ids, "OPEN")
    assert request(client, task, "取消这次任务").status_code == 200
    with Session() as db:
        assert db.query(DraftDecision).one().status == "cancelled"
        assert db.get(InventoryItem, ids["batch"]).opened_at is None


def test_optional_add_dates_can_be_cleared_in_readonly_validation(execution_state):
    client, Session, ids = execution_state
    draft, task = seed_draft(Session, ids, "ADD", purchased_at="2026-10-01", label_expiry="2026-12-01")
    response = request(client, task, "校验草稿", {"purchased_at":None,"label_expiry":None})
    assert response.status_code == 200, response.text
    assert response.json()["preview"]["command"]["purchased_at"] is None
    assert response.json()["preview"]["command"]["label_expiry"] is None
    with Session() as db:
        assert db.get(AIDraft, draft).command_json["purchased_at"] == "2026-10-01"
        assert db.query(InventoryItem).count() == 1 and db.query(DraftOperation).count() == 0
