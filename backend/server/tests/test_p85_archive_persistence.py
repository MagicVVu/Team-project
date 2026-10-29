"""Backend-owned real completed rows, attested archive and atomic episode save."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import select
from test_p85_dialogue import p85
from test_p84_dialogue import p84
from test_backend_p2_conversation import p7
from test_v09_execution import execution_state, headers
from test_session_memory import start, send, ok, BASE
from app.models import InventoryItem
from app.conversation_models import ConversationTurn
from app.routers import agent_gateway as gateway
from app.services import dialogue, session_memory, memory_archive


def row_for(db, request_id):
    return db.scalar(select(ConversationTurn).where(ConversationTurn.request_id == request_id))


def test_old_topic_after_recent_window_uses_original_reference_and_fresh_stock(execution_state, p85, monkeypatch):
    from conversation.p85.schemas import P85Plan
    client, Session, ids = execution_state
    first = ok(send(client, ids, ok(start(client, ids)), "牛奶多少放哪"))
    state = first
    for _ in range(11): state = ok(send(client, ids, state, "你好"))
    with Session.begin() as db:
        item = db.get(InventoryItem, ids["batch"]); item.quantity = 7; item.version += 1
    original = p85[0].p85_understand
    async def recall(text, context, episodes, memory):
        if text == "回到最早的牛奶，现在还剩多少":
            assert first["request_id"] not in {e.request_id for e in context.history}
            episode = next(e for e in episodes if e.request_id == first["request_id"])
            return P85Plan(speech_act="question", memory_id=episode.memory_id,
                selector={"use_reference": True}, reads=[{"kind": "quantity"}])
        return await original(text, context, episodes, memory)
    monkeypatch.setattr(p85[0], "p85_understand", recall)
    result = ok(send(client, ids, state, "回到最早的牛奶，现在还剩多少"))
    assert Decimal(result["task"]["result"]["facts"][0]["quantity"]) == 7
    with Session() as db:
        before = row_for(db, first["request_id"])
        after = row_for(db, result["request_id"])
        episode = before.binding_json[memory_archive.EPISODE_KEY]
        assert gateway.datetime.fromisoformat(episode["created_at"]) >= gateway.datetime.fromisoformat(episode["reference"]["issued_at"])
        supplied = next(e for e in after.binding_json["payload"]["archive"]["episodes"] if e["request_id"] == first["request_id"])
        assert supplied["reference"] == episode["reference"]
        returned = deepcopy(after.resolution_json["reference"])
        attested = deepcopy(episode["reference"])
        for ref in (returned, attested):
            for key in ("issued_at", "expires_at"): ref[key] = gateway.datetime.fromisoformat(ref[key])
        assert returned == attested
        assert after.binding_json[memory_archive.EPISODE_KEY]["reply"] == result["reply"]


def test_final_expression_and_completion_time_saved_atomically_and_replay_immutable(execution_state, p85, monkeypatch):
    client, Session, ids = execution_state
    async def expression(text, frame):
        p85[0].response_calls += 1
        return {"opening": "understood", "fact_order": list(frame.facts)}
    monkeypatch.setattr(p85[0], "p85_respond", expression)
    session = ok(start(client, ids)); request_id = uuid4().hex
    result = ok(send(client, ids, session, "牛奶多少放哪", request_id=request_id))
    with Session() as db:
        row = row_for(db, request_id); saved = deepcopy(row.binding_json)
        state = saved[dialogue.P85_KEY]
        assert state["memory_delta"] == state["resolved"]["memory_delta"]
        assert state["final_reply"] == result["reply"]
        assert state["memory_delta"]["episode"]["reply"] != result["reply"]
        assert state["completed_at"] == saved["memory_v1"]["completed_at"]
        assert gateway.datetime.fromisoformat(state["completed_at"]) == gateway.datetime.fromisoformat(saved["episode_v1"]["created_at"])
        assert row.task_id is not None and row.phase == "completed"
    assert ok(send(client, ids, session, "牛奶多少放哪", request_id=request_id)) == result
    with Session() as db: assert row_for(db, request_id).binding_json == saved


def seed(db, ids, session, suffix, *, days=0, phase="completed", **info):
    row = ConversationTurn(user_id=ids["user"], household_id=ids["home"], request_id="archive-"+suffix,
        request_hash="0"*64, original_text="之前讨论收纳"+suffix, phase=phase,
        created_at=gateway.now()-timedelta(days=days, minutes=5, seconds=int(suffix) if suffix.isdigit() else 0),
        binding_json={"memory_v1": {"protocol_version": "conversation-memory-1", "kind": "message",
            "conversation_id": session["conversation_id"], "revision": 0, **info}}, response_json={"reply": "历史回复"})
    db.add(row)
    return row


def test_archive_bound_filters_original_time_reset_scope_and_incomplete_rows(execution_state, p85):
    client, Session, ids = execution_state
    session = ok(start(client, ids))
    with Session.begin() as db:
        for index in range(105): seed(db, ids, session, str(index))
        seed(db, ids, session, "old", days=31)
        seed(db, ids, session, "other", conversation_id=str(uuid4()))
        seed(db, ids, session, "unfinished", phase="understanding")
        foreign = seed(db, ids, session, "foreign"); foreign.household_id = ids["foreign_home"]
    result = ok(send(client, ids, session, "你好"))
    with Session() as db:
        archive = row_for(db, result["request_id"]).binding_json["payload"]["archive"]
        assert len(archive["episodes"]) == 100 and archive["has_more"]
        assert not {"archive-old", "archive-other", "archive-unfinished", "archive-foreign"} & {e["request_id"] for e in archive["episodes"]}
        assert archive["revision"] == row_for(db, result["request_id"]).binding_json["payload"]["context"]["revision"]
    reset = ok(start(client, ids, result))
    next_result = ok(send(client, ids, reset, "你好"))
    with Session() as db:
        assert row_for(db, next_result["request_id"]).binding_json["payload"]["archive"]["episodes"] == []


@pytest.mark.parametrize("field", ["memory_id", "reply", "created_at", "reference"])
def test_delta_cannot_inject_episode_identity_text_time_or_reference(execution_state, p85, monkeypatch, field):
    client, Session, ids = execution_state
    original = dialogue.call
    async def forged(identity, home, stage, payload, seconds):
        result = await original(identity, home, stage, payload, seconds)
        if stage == "p85/resolve":
            ep = result["memory_delta"]["episode"]
            ep[field] = {"batch_id": str(ids["batch"])} if field == "reference" else gateway.now().isoformat() if field == "created_at" else "forged"
        return result
    monkeypatch.setattr(dialogue, "call", forged)
    assert send(client, ids, ok(start(client, ids)), "你好").status_code == 503


def test_restart_style_recovery_saved_plan_uses_archive_without_understanding(execution_state, p85, monkeypatch):
    client, Session, ids = execution_state
    session = ok(send(client, ids, ok(start(client, ids)), "牛奶多少放哪"))
    original = dialogue.call
    async def crash(identity, home, stage, *args):
        if stage == "p85/resolve": raise TimeoutError()
        return await original(identity, home, stage, *args)
    monkeypatch.setattr(dialogue, "call", crash)
    request_id = uuid4().hex
    assert send(client, ids, session, "你好", request_id=request_id).status_code == 504
    count = p85[0].understanding_calls
    monkeypatch.setattr(dialogue, "call", original)
    result = ok(send(client, ids, session, "你好", request_id=request_id))
    assert result["dialogue"]["recovery_model_calls"] == 0 and p85[0].understanding_calls == count
    with Session() as db:
        state = row_for(db, request_id).binding_json[dialogue.P85_KEY]
        assert state["understand_payload"]["archive"]["episodes"]
        assert state["final_reply"] == result["reply"]
