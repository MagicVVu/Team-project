"""P3 real database execution + real P7/P2 HTTP chains, never production data."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from test_v09_execution import execution_state, seed_draft, body, post, headers, url, PG
from test_backend_p2_conversation import p7, legacy, send, multiple, unique
from app.models import AITask, AIDraft, InventoryItem, HouseholdMember
from app.conversation_models import ConversationBinding, ConversationTurn
from app.execution_models import BusinessEvent, DraftDecision, DraftOperation
from app.services import draft_execution as service, planning_context


@pytest.fixture
def enabled(execution_state, monkeypatch):
    monkeypatch.setenv("MAGICVVU_OPEN_EXECUTION", "true")
    monkeypatch.setenv("MAGICVVU_DISCARD_EXECUTION", "true")
    return execution_state


def yesterday():
    return (datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Shanghai")).date() - timedelta(days=1)).isoformat()


def draft(Session, ids, kind="OPEN", **updates):
    action = "OPEN" if kind == "OPEN" else "DISCARD"
    draft_id, task_id = seed_draft(Session, ids, action)
    with Session.begin() as db:
        record = db.get(AIDraft, draft_id)
        command = {"action": action, "name": "牛奶", "batch_id": str(ids["batch"]), "expected_version": 1}
        command.update({"opened_at": yesterday()} if action == "OPEN" else {
            "discard_mode": "all" if kind == "all" else "partial", "quantity": "5" if kind == "all" else "2", "unit": "盒"})
        command.update(updates)
        record.command_json = command
        db.get(AITask, task_id).result_json = {"status": "needs_confirmation", "draft": command}
    return draft_id, task_id


def preview(client, draft_id, **updates):
    return client.post(url(draft_id, "execution-preview"), headers=headers(), json={
        "draft_revision": 1, "task_revision": 1, "edits": {}, **updates})


def evidence(name, value):
    target = Path(os.getenv("BACKEND_TEST_EVIDENCE_DIR", str(Path(__file__).resolve().parents[3] / ".cache/backend-test-evidence"))) / (
        "backend-p3-postgres-examples.json" if PG else "backend-p3-sqlite-examples.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    previous = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    previous[name] = value
    target.write_text(json.dumps(previous, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.mark.parametrize("kind,remaining,event_type", [("OPEN", "5", "Opened"), ("partial", "3", "Discarded"), ("all", "0", "Discarded")])
def test_preview_commit_and_exact_recovery(enabled, kind, remaining, event_type):
    client, Session, ids = enabled
    draft_id, task_id = draft(Session, ids, kind)
    with Session() as db:
        original_time = db.get(AIDraft, draft_id).updated_at
        stored_command = db.get(AIDraft, draft_id).command_json
    projected = preview(client, draft_id)
    assert projected.status_code == 200, projected.text
    projection = projected.json()
    assert projection["event_type"] == event_type and projection["inventory_written"] is False
    assert Decimal(projection["before"]["quantity"]) == 5
    assert Decimal(projection["after"]["quantity"]) == Decimal(remaining)
    assert projection["after"]["version"] == 2
    assert projection["quantity_source"] == (None if kind == "OPEN" else "current_batch" if kind == "all" else "user_input")
    with Session() as db:
        assert db.get(InventoryItem, ids["batch"]).quantity == 5
        assert db.get(InventoryItem, ids["batch"]).opened_at is None
        assert db.get(AIDraft, draft_id).updated_at == original_time
        assert db.query(DraftOperation).count() == db.query(BusinessEvent).count() == 0
    request = body()
    result = post(client, draft_id, request)
    assert result.status_code == 200, result.text
    receipt = result.json()
    from app.execution_schemas import OperationReceipt
    assert OperationReceipt.model_validate(receipt).execution.event_type == event_type
    assert receipt["execution"]["event_type"] == event_type
    assert post(client, draft_id, request).json() == receipt
    assert client.get("/api/v1/operations/" + request["operation_id"], headers=headers()).json() == receipt
    assert client.get(url(draft_id, "execution"), headers=headers()).json()["receipt"] == receipt
    with Session() as db:
        item = db.get(InventoryItem, ids["batch"])
        event = db.scalar(select(BusinessEvent))
        assert item.quantity == Decimal(remaining) and item.version == 2 and item.storage_location == "冰箱"
        assert item.status == ("DISCARDED" if kind == "all" else "ACTIVE")
        assert event.event_type == event_type
        assert event.quantity == (None if kind == "OPEN" else Decimal(5) - Decimal(remaining))
        assert event.operation_id == UUID(request["operation_id"]) and event.inventory_item_id == item.id
        assert db.query(DraftOperation).count() == db.query(BusinessEvent).count() == 1
        assert db.get(DraftDecision, draft_id).status == "committed"
        assert receipt["result"]["inventory_item"]["opened_at"] == (yesterday() if kind == "OPEN" else None)
    evidence(kind, {"draft": stored_command, "preview_request": json.loads(projected.request.content),
        "preview_response": projection, "commit_request": request, "receipt": receipt})


@pytest.mark.parametrize("value,code", [(None, "INVALID_DRAFT_FIELDS"), ("2026-02-30", "INVALID_DRAFT_FIELDS"),
    ("2999-01-01", "OPEN_DATE_IN_FUTURE"), (True, "INVALID_DRAFT_FIELDS"),
    (0, "INVALID_DRAFT_FIELDS"), ("2026-10-20T00:00:00Z", "INVALID_DRAFT_FIELDS")])
def test_open_invalid_date_no_writes(enabled, value, code):
    client, Session, ids = enabled
    draft_id, _ = draft(Session, ids)
    result = post(client, draft_id, body(edits={"opened_at": value}))
    assert result.status_code == 422 and result.json()["detail"]["code"] == code, result.text
    with Session() as db:
        assert db.get(InventoryItem, ids["batch"]).opened_at is None
        assert db.get(InventoryItem, ids["batch"]).quantity == 5
        assert db.query(BusinessEvent).count() == 0


def test_open_missing_date_and_repeated_open_rule(enabled):
    client, Session, ids = enabled
    draft_id, task_id = draft(Session, ids)
    with Session.begin() as db:
        row = db.get(AIDraft, draft_id)
        raw = {k: v for k, v in row.command_json.items() if k != "opened_at"}
        row.command_json = raw
        db.get(AITask, task_id).result_json = {"status": "needs_confirmation", "draft": raw}
    assert post(client, draft_id, body()).status_code == 422
    assert post(client, draft_id, body(edits={"opened_at": yesterday()})).status_code == 200
    second, _ = draft(Session, ids, expected_version=2)
    result = post(client, second, body())
    assert result.status_code == 409 and result.json()["detail"]["code"] == "ALREADY_OPENED"
    with Session() as db:
        assert db.get(InventoryItem, ids["batch"]).version == 2
        assert db.query(BusinessEvent).count() == 1


def test_open_relative_edit_timezone_and_stable_anchor(enabled, monkeypatch):
    client, Session, ids = enabled
    draft_id, task_id = draft(Session, ids)
    anchor = datetime(2026, 10, 23, 0, 30, tzinfo=timezone.utc)  # LA is still Oct 22.
    with Session.begin() as db:
        task = db.get(AITask, task_id)
        task.household_timezone = "America/Los_Angeles"
        task.created_at = anchor
    monkeypatch.setattr(service, "now", lambda: anchor)
    assert post(client, draft_id, body(edits={"opened_at": "2026-10-23"})).json()["detail"]["code"] == "OPEN_DATE_IN_FUTURE"
    projected = preview(client, draft_id, edits={"opened_at": "昨天"})
    assert projected.status_code == 200 and projected.json()["command"]["opened_at"] == "2026-10-21", projected.text
    result = post(client, draft_id, body(edits={"opened_at": "昨天"}))
    assert result.status_code == 200, result.text
    assert result.json()["result"]["inventory_item"]["opened_at"] == "2026-10-21"


@pytest.mark.parametrize("updates", [{"quantity": "0"}, {"quantity": "-1"}, {"quantity": "6"},
    {"quantity": "0.0000001"}, {"quantity": True}, {"unit": "kg"}, {"discard_mode": "unknown"}])
def test_discard_validation_is_atomic(enabled, updates):
    client, Session, ids = enabled
    draft_id, _ = draft(Session, ids, "partial", **updates)
    assert post(client, draft_id, body()).status_code == 422
    with Session() as db:
        assert db.get(InventoryItem, ids["batch"]).quantity == 5
        assert db.query(DraftOperation).count() == db.query(BusinessEvent).count() == 0


@pytest.mark.parametrize("stock_unit,input_unit,amount,remaining", [("L", "ml", "500", "4.5"),
    ("盒", "盒", "5", "0"), ("盒", "盒", "0.000001", "4.999999")])
def test_discard_exact_conversion_and_partial_zero_terminal(enabled, stock_unit, input_unit, amount, remaining):
    client, Session, ids = enabled
    with Session.begin() as db:
        db.get(InventoryItem, ids["batch"]).unit = stock_unit
    draft_id, _ = draft(Session, ids, "partial", quantity=amount, unit=input_unit)
    result = post(client, draft_id, body())
    assert result.status_code == 200, result.text
    with Session() as db:
        item = db.get(InventoryItem, ids["batch"])
        event = db.scalar(select(BusinessEvent))
        assert item.quantity == Decimal(remaining)
        assert item.status == ("DISCARDED" if remaining == "0" else "ACTIVE")
        assert event.quantity == Decimal(5) - Decimal(remaining)
        assert event.unit == stock_unit and event.event_type == "Discarded"


def test_discard_conversion_subprecision_rejected(enabled):
    client, Session, ids = enabled
    with Session.begin() as db:
        db.get(InventoryItem, ids["batch"]).unit = "吨"
    draft_id, _ = draft(Session, ids, "partial", quantity="0.000001", unit="kg")
    result = post(client, draft_id, body())
    assert result.status_code == 422 and result.json()["detail"]["code"] == "CONVERTED_QUANTITY_INVALID"


@pytest.mark.parametrize("edits", [{"quantity": "10"}, {"quantity": "5"}, {"unit": "盒"},
    {"discard_mode": "partial"}, {"expected_version": 2}, {"batch_id": str(uuid4())}, {"action": "CONSUME"}])
def test_all_quantity_mode_and_targets_are_protected(enabled, edits):
    client, Session, ids = enabled
    draft_id, _ = draft(Session, ids, "all")
    assert client.get(url(draft_id, "execution"), headers=headers()).json()["editable_fields"] == []
    assert post(client, draft_id, body(edits=edits)).status_code == 422
    with Session() as db:
        assert db.query(BusinessEvent).count() == 0 and db.get(InventoryItem, ids["batch"]).quantity == 5


def test_all_amount_mismatch_even_without_version_change_rejected(enabled):
    client, Session, ids = enabled
    draft_id, _ = draft(Session, ids, "all", quantity="4")
    result = post(client, draft_id, body())
    assert result.status_code == 409 and result.json()["detail"]["code"] == "DISCARD_ALL_QUANTITY_CONFLICT"


@pytest.mark.parametrize("kind", ["OPEN", "partial", "all"])
@pytest.mark.parametrize("change", ["version", "membership", "terminal", "expired", "revision"])
def test_stale_or_unauthorized_drafts_never_write(enabled, kind, change):
    client, Session, ids = enabled
    draft_id, task_id = draft(Session, ids, kind)
    with Session.begin() as db:
        if change == "version":
            db.get(InventoryItem, ids["batch"]).version += 1
        elif change == "membership":
            db.delete(db.get(HouseholdMember, (ids["home"], ids["user"])))
        elif change == "terminal":
            db.get(InventoryItem, ids["batch"]).status = "DISCARDED"
        elif change == "expired":
            db.get(AITask, task_id).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        else:
            db.get(AITask, task_id).revision += 1
    result = post(client, draft_id, body())
    assert result.status_code == (404 if change == "membership" else 409), result.text
    with Session() as db:
        assert db.get(InventoryItem, ids["batch"]).quantity == 5
        assert db.query(BusinessEvent).count() == db.query(DraftOperation).count() == 0


@pytest.mark.parametrize("kind", ["OPEN", "partial", "all"])
def test_event_failure_rolls_back_everything(enabled, monkeypatch, kind):
    client, Session, ids = enabled
    draft_id, _ = draft(Session, ids, kind)
    request = body()
    def broken(*args, **kwargs):
        raise RuntimeError("synthetic event failure")
    with monkeypatch.context() as m:
        m.setattr(service, "persist_event", broken)
        assert post(client, draft_id, request).status_code == 500
    with Session() as db:
        item = db.get(InventoryItem, ids["batch"])
        assert item.quantity == 5 and item.version == 1 and item.opened_at is None
        assert db.query(BusinessEvent).count() == db.query(DraftOperation).count() == db.query(DraftDecision).count() == 0
    assert post(client, draft_id, request).status_code == 200


@pytest.mark.parametrize("kind", ["OPEN", "partial", "all"])
def test_response_loss_refresh_failure_recovery_and_operation_conflict(enabled, monkeypatch, kind):
    from starlette.responses import JSONResponse
    client, Session, ids = enabled
    draft_id, task_id = draft(Session, ids, kind)
    request = body()
    render = JSONResponse.render
    def lost(self, content):
        if isinstance(content, dict) and content.get("status") == "committed":
            raise RuntimeError("synthetic committed response loss")
        return render(self, content)
    with monkeypatch.context() as m:
        m.setattr(JSONResponse, "render", lost)
        assert post(client, draft_id, request).status_code == 500
    receipt = client.get("/api/v1/operations/" + request["operation_id"], headers=headers()).json()
    assert receipt["status"] == "committed"
    assert client.get(f"/api/v1/households/{uuid4()}/inventory-items", headers=headers()).status_code == 404
    with Session.begin() as db:
        db.get(AITask, task_id).expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    assert post(client, draft_id, request).json() == receipt
    assert post(client, draft_id, {**request, "edits": {"opened_at": yesterday()}}).status_code == 409
    assert post(client, draft_id, body()).status_code == 409
    with Session() as db:
        assert db.query(BusinessEvent).count() == db.query(DraftOperation).count() == 1


def test_independent_gates_enforced_by_commit_and_preview(enabled, monkeypatch):
    client, Session, ids = enabled
    opened, _ = draft(Session, ids)
    discarded, _ = draft(Session, ids, "all")
    monkeypatch.delenv("MAGICVVU_OPEN_EXECUTION")
    caps = client.get("/api/v1/agent/execution-capabilities", headers=headers()).json()
    assert caps["actions"]["OPEN"] is False and caps["actions"]["DISCARD"] is True
    assert preview(client, opened).status_code == 409
    assert post(client, opened, body()).json()["detail"]["code"] == "ACTION_NOT_EXECUTABLE"
    assert post(client, discarded, body()).status_code == 200
    monkeypatch.setenv("MAGICVVU_OPEN_EXECUTION", "true")
    monkeypatch.delenv("MAGICVVU_DISCARD_EXECUTION")
    caps = client.get("/api/v1/agent/execution-capabilities", headers=headers()).json()
    assert caps["actions"]["OPEN"] is True and caps["actions"]["DISCARD"] is False


@pytest.mark.parametrize("active", ["OPEN", "DISCARD"])
def test_each_action_gate_can_enable_only_its_own_writes(enabled, monkeypatch, active):
    client, Session, ids = enabled
    other = "DISCARD" if active == "OPEN" else "OPEN"
    monkeypatch.delenv(f"MAGICVVU_{other}_EXECUTION")
    first, _ = draft(Session, ids, "OPEN" if active == "OPEN" else "all")
    second, _ = draft(Session, ids, "all" if active == "OPEN" else "OPEN")
    assert post(client, second, body()).json()["detail"]["code"] == "ACTION_NOT_EXECUTABLE"
    request = body()
    receipt = post(client, first, request)
    assert receipt.status_code == 200, receipt.text
    monkeypatch.delenv(f"MAGICVVU_{active}_EXECUTION")
    assert post(client, first, request).json() == receipt.json()


def test_preview_validates_edited_date_and_is_read_only(enabled):
    client, Session, ids = enabled
    first, _ = draft(Session, ids)
    projected = preview(client, first, edits={"opened_at": "2000-01-01"})
    assert projected.status_code == 200, projected.text
    assert projected.json()["before"]["opened_at"] is None
    assert projected.json()["after"]["opened_at"] == "2000-01-01"
    assert client.post(url(first, "execution-preview"), json={"task_revision": 1, "draft_revision": 1}).status_code == 401
    assert client.post(url(first, "execution-preview"), headers=headers("outsider"),
        json={"task_revision": 1, "draft_revision": 1}).status_code == 404
    assert preview(client, first, task_revision=2).status_code == 409
    with Session() as db:
        assert db.get(InventoryItem, ids["batch"]).opened_at is None
        assert db.get(AIDraft, first).command_json["opened_at"] == yesterday()
        assert db.query(DraftOperation).count() == db.query(DraftDecision).count() == 0


def test_all_compatible_source_units_and_terminal_cannot_repeat(enabled):
    client, Session, ids = enabled
    with Session.begin() as db:
        db.get(InventoryItem, ids["batch"]).unit = "L"
    first, _ = draft(Session, ids, "all", quantity="5000", unit="ml")
    receipt = post(client, first, body())
    assert receipt.status_code == 200, receipt.text
    assert Decimal(receipt.json()["execution"]["quantity"]) == 5
    assert receipt.json()["execution"]["unit"] == "L"
    second, _ = draft(Session, ids, "all", expected_version=2)
    assert post(client, second, body()).json()["detail"]["code"] == "INVENTORY_NOT_ACTIVE"
    with Session() as db:
        assert db.get(InventoryItem, ids["batch"]).quantity == 0
        assert db.query(BusinessEvent).count() == 1


def test_p3_business_event_quantity_checks_remain_enforced(enabled):
    from sqlalchemy.exc import IntegrityError
    client, Session, ids = enabled
    opened, _ = draft(Session, ids)
    assert post(client, opened, body()).status_code == 200
    with pytest.raises(IntegrityError):
        with Session.begin() as db:
            db.scalar(select(BusinessEvent)).quantity = 1
    discarded, _ = draft(Session, ids, "partial", expected_version=2)
    assert post(client, discarded, body()).status_code == 200
    with pytest.raises(IntegrityError):
        with Session.begin() as db:
            db.scalar(select(BusinessEvent).where(BusinessEvent.event_type == "Discarded")).quantity = None


@pytest.mark.parametrize("kind", ["OPEN", "partial", "all"])
def test_inventory_constraint_failure_rolls_back_whole_operation(enabled, monkeypatch, kind):
    client, Session, ids = enabled
    draft_id, _ = draft(Session, ids, kind)
    request = body()
    original = service.stock_changes

    def violate_constraint(*args):
        quantity, changes = original(*args)
        changes["quantity"] = Decimal(-1)  # Test-only real DB failure at business flush.
        return quantity, changes

    monkeypatch.setattr(service, "stock_changes", violate_constraint)
    denied = post(client, draft_id, request)
    assert denied.status_code == 409 and denied.json()["detail"]["code"] == "EXECUTION_CONFLICT"
    with Session() as db:
        item = db.get(InventoryItem, ids["batch"])
        assert item.quantity == 5 and item.version == 1 and item.opened_at is None
        assert db.query(DraftOperation).count() == db.query(BusinessEvent).count() == db.query(DraftDecision).count() == 0
    monkeypatch.setattr(service, "stock_changes", original)
    assert post(client, draft_id, request).status_code == 200


@pytest.mark.parametrize("text,reply,kind", [("牛奶开封了", "昨天", "OPEN"),
    ("扔掉牛奶", "两盒", "partial"), ("扔掉剩下的牛奶", "第二个", "all")])
def test_real_p7_multiturn_confirm_and_receipt(enabled, p7, text, reply, kind):
    client, Session, ids = enabled
    if kind == "all":
        multiple(Session, ids)
    task = legacy(client, ids, text)
    assert task["status"] == "needs_clarification", task
    count = p7[0].calls
    resumed = send(client, ids, reply, task)
    assert resumed.status_code == 200, resumed.text
    pending = resumed.json()["task"]
    assert pending["task_id"] == task["task_id"] and pending["status"] == "needs_confirmation"
    assert p7[0].calls == count
    target = pending["result"]["draft"]["batch_id"]
    with Session() as db:
        before = db.get(InventoryItem, UUID(target)).quantity
        assert db.query(BusinessEvent).count() == 0
    projected = preview(client, pending["draft_id"], task_revision=pending["revision"])
    assert projected.status_code == 200, projected.text
    request = body(task_revision=pending["revision"])
    result = post(client, pending["draft_id"], request)
    assert result.status_code == 200, result.text
    assert post(client, pending["draft_id"], request).json() == result.json()
    with Session() as db:
        item = db.get(InventoryItem, UUID(target))
        assert item.quantity == (before if kind == "OPEN" else Decimal(0) if kind == "all" else before - 2)
        assert item.version == 2
        assert db.query(BusinessEvent).count() == 1
    evidence("p7_" + kind, {"initial_task": task, "reply_request": json.loads(resumed.request.content),
        "reply_response": resumed.json(), "preview": projected.json(), "commit_request": request, "receipt": result.json(),
        "extractions_before_reply": count, "extractions_after_commit": p7[0].calls})


def test_trusted_reference_deadline_is_persisted_for_final_draft(enabled, p7, monkeypatch):
    client, Session, ids = enabled
    initial = unique(client, ids)
    until = datetime.now(timezone.utc) + timedelta(seconds=5)
    with Session.begin() as db:
        current = db.get(ConversationBinding, ids["user"])
        current.reference_json = {**current.reference_json, "expires_at": until.isoformat()}
    result = send(client, ids, "它昨天开封了", initial["task"])
    assert result.status_code == 200, result.text
    pending = result.json()["task"]
    assert pending["status"] == "needs_confirmation", pending
    with Session() as db:
        stored = db.get(AITask, UUID(pending["task_id"]))
        assert service.aware(stored.expires_at) == until
    monkeypatch.setattr(service, "now", lambda: until + timedelta(seconds=1))
    denied = post(client, pending["draft_id"], body(task_revision=pending["revision"]))
    assert denied.status_code == 409 and denied.json()["detail"]["code"] == "DRAFT_EXPIRED"


def test_clarification_cannot_extend_persisted_reference_deadline(enabled, p7, monkeypatch):
    from app.routers import agent_gateway
    client, Session, ids = enabled
    initial = unique(client, ids)
    until = datetime.now(timezone.utc) + timedelta(seconds=30)
    with Session.begin() as db:
        binding = db.get(ConversationBinding, ids["user"])
        binding.reference_json = {**binding.reference_json, "expires_at": until.isoformat()}
    opened = send(client, ids, "它开封了", initial["task"])
    assert opened.status_code == 200, opened.text
    task = opened.json()["task"]
    assert task["status"] == "needs_clarification", task
    actual_call = agent_gateway._call_ai

    async def extending_response(path, user_id, household_id, payload):
        result = await actual_call(path, user_id, household_id, payload)
        if path == "/agent/clarification":
            # Test-only inconsistent internal continuation; backend must keep
            # its original persisted deadline even when an adapter extends it.
            context = {**payload["context"], "revision": payload["revision"] + 1,
                "expires_at": (until + timedelta(hours=1)).isoformat()}
            result = {**result, "clarification": context}
        return result

    monkeypatch.setattr(agent_gateway, "_call_ai", extending_response)
    clarified = send(client, ids, "昨天", task)
    assert clarified.status_code == 200, clarified.text
    pending = clarified.json()["task"]
    assert pending["status"] == "needs_confirmation", pending
    with Session() as db:
        assert service.aware(db.get(AITask, UUID(pending["task_id"])).expires_at) == until
    monkeypatch.setattr(service, "now", lambda: until + timedelta(seconds=1))
    rejected = post(client, pending["draft_id"], body(task_revision=pending["revision"]))
    assert rejected.status_code == 409 and rejected.json()["detail"]["code"] == "DRAFT_EXPIRED"


def test_no_unique_reference_cannot_invent_discard_target(enabled, p7):
    client, Session, ids = enabled
    result = send(client, ids, "扔掉剩下的它")
    assert result.status_code == 200, result.text
    assert result.json()["task"]["draft_id"] is None
    with Session() as db:
        assert db.query(BusinessEvent).count() == 0 and db.query(AIDraft).count() == 0


@pytest.mark.parametrize("text,kind", [("它开封了", "OPEN"), ("扔掉剩下的它", "all")])
def test_p2_trusted_reference_generates_and_executes_p3_action(enabled, p7, text, kind):
    client, Session, ids = enabled
    initial = unique(client, ids)
    requested = send(client, ids, text, initial["task"])
    assert requested.status_code == 200, requested.text
    task = requested.json()["task"]
    if kind == "OPEN":
        count = p7[0].calls
        resumed = send(client, ids, "昨天", task)
        assert resumed.status_code == 200, resumed.text
        assert p7[0].calls == count
        task = resumed.json()["task"]
    assert task["status"] == "needs_confirmation", task
    assert task["result"]["draft"]["batch_id"] == str(ids["batch"])
    result = post(client, task["draft_id"], body(task_revision=task["revision"]))
    assert result.status_code == 200, result.text
    with Session() as db:
        item = db.get(InventoryItem, ids["batch"])
        assert item.quantity == (5 if kind == "OPEN" else 0)
        assert item.opened_at == (date.fromisoformat(yesterday()) if kind == "OPEN" else None)


def test_consumption_and_planning_exclude_discard_and_open(enabled, p7):
    client, Session, ids = enabled
    consumed, _ = seed_draft(Session, ids)
    assert post(client, consumed, body()).status_code == 200
    discarded, _ = draft(Session, ids, "partial", quantity="1", expected_version=2)
    assert post(client, discarded, body()).status_code == 200
    opened, _ = draft(Session, ids, expected_version=3)
    assert post(client, opened, body()).status_code == 200
    response = client.get(f"/api/v1/households/{ids['home']}/consumption-events", headers=headers()).json()
    assert response["total"] == 1 and response["items"][0]["event_type"] == "Consumed"
    with Session() as db:
        snapshot = planning_context.snapshot(db, ids["user"], ids["home"])
    kinds = {event["kind"]: event["quantity"] for event in snapshot["items"][0]["events"]}
    assert Decimal(kinds["Consumed"]) == Decimal(kinds["Discarded"]) == 1
    assert Decimal(kinds["Opened"]) == 0
    from v1.schemas import PlanningSnapshot
    from p3.history import consumption
    parsed = PlanningSnapshot.model_validate(snapshot)
    # Synthetic completeness annotation solely tests netting of real exported event types.
    end = parsed.as_of.astimezone(ZoneInfo("Asia/Shanghai")).date()
    item = parsed.items[0]
    from p3.schemas import CoverageDay
    item.coverage = [CoverageDay(day=end - timedelta(days=n), records_complete=True, stockout=False) for n in range(1, 29)]
    item.recording_completeness_source = "synthetic test-only coverage"
    for event in item.events:
        event.occurred_at = event.occurred_at - timedelta(days=1)
    summary = consumption(item, parsed, "Asia/Shanghai")
    assert summary.effective_quantity == 1


def test_migration_preserves_ledger_and_p2_and_blocks_unsafe_downgrade(enabled, tmp_path):
    from unittest.mock import patch
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, event, inspect, text
    from sqlalchemy.orm import sessionmaker
    from test_v09_execution import app, get_db, database_url
    from app.models import User, Household, AuthSession
    from app.security import digest_token

    client, original_session, ids = enabled
    admin, schema = None, None
    if PG:
        # execution_state already verified the disposable database/data_directory.
        admin = original_session.kw["bind"]
        schema = "p3_migration_" + uuid4().hex
        with admin.begin() as db:
            db.execute(text('CREATE SCHEMA "' + schema + '"'))
        engine = create_engine(database_url(), connect_args={"options": "-csearch_path=" + schema})
    else:
        engine = create_engine(f"sqlite:///{tmp_path/'p3-migration.sqlite'}", connect_args={"check_same_thread": False})
        @event.listens_for(engine, "connect")
        def enforce_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    Session = sessionmaker(bind=engine, autoflush=False)
    original_override = app.dependency_overrides[get_db]

    def isolated():
        with Session() as db:
            yield db

    def migrate(direction, target):
        with patch("sqlalchemy.create_engine", return_value=engine):
            getattr(command, direction)(cfg, target)

    def snapshot():
        existing = set(inspect(engine).get_table_names())
        with engine.connect() as db:
            return {table.name: [dict(row) for row in db.execute(select(table).order_by(*table.primary_key.columns)).mappings()]
                for table in service.AITask.metadata.tables.values() if table.name in existing and table.name != "alembic_version"}

    try:
        migrate("upgrade", "20261023_0008")
        with Session.begin() as db:
            db.add(User(id=ids["user"], email="p3-migration@example.invalid", password_hash="fixture", display_name="P3"))
            db.flush()
            db.add(Household(id=ids["home"], name="P3", created_by_user_id=ids["user"]))
            db.flush()
            db.add(HouseholdMember(household_id=ids["home"], user_id=ids["user"], role="owner"))
            auth = AuthSession(user_id=ids["user"], token_hash=digest_token("synthetic-user"),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
            db.add(auth)
            db.add(InventoryItem(id=ids["batch"], household_id=ids["home"], name="牛奶", quantity=5,
                unit="盒", storage_location="冰箱", status="ACTIVE", version=1, created_by_user_id=ids["user"]))
            db.flush()
            session_id = auth.id
        old_draft, old_task = seed_draft(Session, ids)
        app.dependency_overrides[get_db] = isolated
        request = body()
        old_result = post(client, old_draft, request)
        assert old_result.status_code == 200, old_result.text
        with Session.begin() as db:
            db.add(ConversationBinding(user_id=ids["user"], household_id=ids["home"], session_id=session_id,
                task_id=old_task, reference_json={"fixture": "preserve exactly"}))
            db.add(ConversationTurn(user_id=ids["user"], household_id=ids["home"], request_id="p3-migration-fixture",
                request_hash="fixture", original_text="保留 P2 会话", task_id=old_task, source_revision=1,
                response_json={"task_id": str(old_task)}, phase="complete"))
        before = snapshot()
        if not PG:
            # Explicitly prove the local SQLite limitation preserves all data,
            # rather than turning off constraints to claim migration success.
            with pytest.raises(RuntimeError, match="Populated SQLite execution ledger"):
                migrate("upgrade", "20261023_0009")
            assert snapshot() == before
            with engine.connect() as db:
                assert db.scalar(text("SELECT version_num FROM alembic_version")) == "20261023_0008"
                assert db.scalar(text("PRAGMA foreign_keys")) == 1
                assert db.execute(text("PRAGMA foreign_key_check")).all() == []
            evidence("populated_migration", {"database": "sqlite", "result": "guarded_before_DDL",
                "data_preserved": True, "foreign_keys_enabled": True})
            return
        for direction, target in (("upgrade", "20261023_0009"), ("downgrade", "20261023_0008"), ("upgrade", "20261023_0009")):
            migrate(direction, target)
            assert snapshot() == before
        assert client.get("/api/v1/operations/" + request["operation_id"], headers=headers()).json() == old_result.json()
        new_draft, _ = draft(Session, ids, expected_version=2)
        new_result = post(client, new_draft, body())
        assert new_result.status_code == 200, new_result.text
        populated = snapshot()
        with pytest.raises(RuntimeError, match="OPEN/DISCARD audit data exists"):
            migrate("downgrade", "20261023_0008")
        assert snapshot() == populated
        with engine.connect() as db:
            assert db.scalar(text("SELECT version_num FROM alembic_version")) == "20261023_0009"
            assert not db.scalar(text("SELECT COUNT(*) FROM pg_constraint WHERE connamespace = current_schema()::regnamespace AND NOT convalidated"))
        assert "ai_conversation_turns" in inspect(engine).get_table_names()
        evidence("populated_migration", {"database": "postgresql", "p1_receipt_preserved": True,
            "p2_rows_preserved": True, "upgrade_downgrade_upgrade": True, "populated_downgrade_blocked": True,
            "constraints_validated": True})
    finally:
        app.dependency_overrides[get_db] = original_override
        engine.dispose()
        if schema:
            assert schema.startswith("p3_migration_") and len(schema) == 45
            with admin.begin() as db:
                db.execute(text('DROP SCHEMA "' + schema + '" CASCADE'))


@pytest.mark.skipif(not PG, reason="Real PostgreSQL row locks required")
@pytest.mark.parametrize("kind", ["OPEN", "partial", "all"])
@pytest.mark.parametrize("race", ["same_key", "different_keys", "different_drafts", "cancel"])
def test_postgres_open_discard_races(enabled, kind, race):
    client, Session, ids = enabled
    first, _ = draft(Session, ids, kind)
    request = body()
    if race == "different_drafts":
        second, _ = draft(Session, ids, kind)
        jobs = [(first, request), (second, body())]
    else:
        jobs = [(first, request if race == "same_key" else body()) for _ in range(4)]
    if race == "cancel":
        def invoke(n):
            if n == 0:
                return client.post(url(first, "cancel"), headers=headers(), json={"draft_revision": 1, "task_revision": 1})
            return post(client, first, request)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(invoke, [0, 1]))
        assert sorted(r.status_code for r in results) == [200, 409], [r.text for r in results]
    else:
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda job: post(client, *job), jobs))
        assert sum(r.status_code == 200 for r in results) == (4 if race == "same_key" else 1), [r.text for r in results]
        assert all(r.status_code in (200, 409) for r in results)
        if race == "same_key":
            assert all(r.json() == results[0].json() for r in results)
    with Session() as db:
        count = db.query(DraftOperation).count()
        assert count <= 1 and db.query(BusinessEvent).count() == count
        item = db.get(InventoryItem, ids["batch"])
        assert item.quantity == (5 if not count or kind == "OPEN" else 3 if kind == "partial" else 0)
        assert item.version == 1 + count
