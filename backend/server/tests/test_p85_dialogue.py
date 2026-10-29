"""Authenticated backend -> P8.5 ASGI stages, with durable SQLite records."""
from uuid import UUID, uuid4
import pytest
import httpx
from sqlalchemy import select
from test_p84_dialogue import p84
from test_backend_p2_conversation import p7
from test_v09_execution import execution_state, headers
from test_session_memory import start, send, ok, BASE
from app.services import dialogue
from app.conversation_models import ConversationTurn
from app.models import InventoryItem
from app.execution_models import DraftOperation


@pytest.fixture
def p85(p84, p7, monkeypatch):
    from conversation.p85.app import create_app
    from conversation.p85.schemas import P85Plan
    from v1.tools import RemoteReader
    from httpx._client import AsyncClient
    engine = p84
    async def understand(text, context, episodes, memory):
        return P85Plan(**(await engine.dialogue_understand(text, context)).model_dump())
    async def respond(text, frame):
        engine.response_calls += 1
        return {"fact_order": list(frame.facts)}
    monkeypatch.setattr(engine, "p85_understand", understand, raising=False)
    monkeypatch.setattr(engine, "p85_respond", respond, raising=False)
    ai = create_app(engine=engine, reader=RemoteReader("http://backend:8000", "synthetic-p2-tool-token-at-least-32"))
    transport = httpx.ASGITransport(app=ai)
    async def dispatch(request):
        if request.url.host == "agent":
            p7[1].append(("agent", request.url.path))
            return await transport.handle_async_request(request)
        return await p7[3](request)
    def client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(dispatch)
        return AsyncClient(*args, **kwargs)
    monkeypatch.setattr(httpx, "AsyncClient", client)
    monkeypatch.setenv("AI_CONVERSATION_DIALOGUE_PROTOCOL", dialogue.P85_PROTOCOL)
    return engine, p7[1]


def test_p85_query_draft_edit_and_internal_delta(execution_state, p85):
    client, Session, ids = execution_state
    first = ok(send(client, ids, ok(start(client, ids)), "牛奶多少放哪"))
    draft = ok(send(client, ids, first, "我喝了一半"))
    edit = ok(send(client, ids, draft, "还是两盒吧"))
    assert edit["task"]["task_id"] == draft["task"]["task_id"]
    assert edit["task"]["revision"] == draft["task"]["revision"]+1
    assert edit["model_calls"] == 0
    assert first["dialogue"]["protocol_version"] == dialogue.P85_PROTOCOL
    assert first["dialogue"]["calls"] == {"understanding": 1, "response": 1, "total": 2}
    assert "memory_delta" not in edit and "memory" not in edit
    with Session() as db:
        turn = db.scalar(select(ConversationTurn).where(ConversationTurn.request_id == edit["request_id"]))
        state = turn.binding_json[dialogue.P85_KEY]
        assert state["plan"]["memory_id"] is None
        assert state["context_revision"] >= 0
        assert state["resolved"]["memory_delta"]["episode"]["text"] == "还是两盒吧"
        assert dialogue.KEY not in turn.binding_json
        assert db.get(InventoryItem, ids["batch"]).quantity == 5
        assert db.query(DraftOperation).count() == 0
    assert any(path == "/agent/dialogue/p85/respond" for _, path in p85[1])


def test_discussion_skips_expression_and_recovers_without_calls(execution_state, p85):
    client, Session, ids = execution_state
    session = ok(start(client, ids)); request_id = uuid4().hex
    value = ok(send(client, ids, session, "你好", request_id=request_id))
    assert value["dialogue"]["calls"] == {"understanding": 1, "response": 0, "total": 1}
    assert value["dialogue"]["fallback_used"] is False
    assert p85[0].response_calls == 0
    assert ok(send(client, ids, session, "你好", request_id=request_id)) == value
    recovered = ok(client.get(BASE+"conversation-turns/"+request_id, headers=headers(), params={"household_id": str(ids["home"])}))
    assert recovered["response"]["dialogue"]["protocol_version"] == dialogue.P85_PROTOCOL
    assert p85[0].understanding_calls == 1
    caps = ok(client.get(BASE+"execution-capabilities", headers=headers()))
    assert caps["conversation_dialogue_protocol"] == dialogue.P85_PROTOCOL


@pytest.mark.parametrize("count", [0, 1, 2, True])
def test_expression_counter_validation_and_fallback(execution_state, p85, monkeypatch, count):
    client, Session, ids = execution_state
    original = dialogue.call
    async def changed(identity, home, stage, payload, seconds):
        if stage == "p85/respond":
            return {"protocol_version": dialogue.P85_PROTOCOL, "reply": "validated expression", "response_calls": count}
        return await original(identity, home, stage, payload, seconds)
    monkeypatch.setattr(dialogue, "call", changed)
    value = ok(send(client, ids, ok(start(client, ids)), "把牛奶移到书房"))
    if type(count) is int and count in (0, 1):
        assert value["reply"] == "validated expression"
        assert value["model_calls"] == 1+count
    else:
        assert value["reply"] != "validated expression"
        assert value["model_calls"] == 2 and value["dialogue"]["fallback_used"]
    assert value["task"]["status"] == "needs_confirmation"


@pytest.mark.parametrize("field", ["scope", "conversation_id", "expected_revision", "request_id", "text", "source_text_sha256"])
def test_delta_must_match_attested_request(execution_state, p85, monkeypatch, field):
    client, Session, ids = execution_state
    original = dialogue.call
    async def changed(identity, home, stage, payload, seconds):
        data = await original(identity, home, stage, payload, seconds)
        if stage == "p85/resolve":
            delta = data["memory_delta"]
            if field in {"request_id", "text"}: delta["episode"][field] = "forged"
            elif field == "scope": delta["scope"]["user_id"] = str(uuid4())
            elif field == "conversation_id": delta[field] = str(uuid4())
            elif field == "expected_revision": delta[field] += 1
            else: delta[field] = "0"*64
        return data
    monkeypatch.setattr(dialogue, "call", changed)
    assert send(client, ids, ok(start(client, ids)), "你好").status_code == 503
    with Session() as db:
        assert db.query(DraftOperation).count() == 0


@pytest.mark.parametrize("protocol", [dialogue.PROTOCOL, dialogue.P85_PROTOCOL])
@pytest.mark.parametrize("disabled", [False, True])
def test_prepared_recovery_pins_original_protocol_after_config_change(execution_state, p85, monkeypatch, protocol, disabled):
    client, Session, ids = execution_state
    monkeypatch.setenv("AI_CONVERSATION_DIALOGUE_PROTOCOL", protocol)
    original = dialogue.call
    async def crash(identity, home, stage, *args):
        if stage.endswith("resolve"): raise TimeoutError()
        return await original(identity, home, stage, *args)
    session = ok(start(client, ids)); request_id = uuid4().hex
    monkeypatch.setattr(dialogue, "call", crash)
    assert send(client, ids, session, "把牛奶移到书房", request_id=request_id).status_code == 504
    recovery = ok(client.get(BASE+"conversation-turns/"+request_id, headers=headers(), params={"household_id": str(ids["home"])}))
    assert recovery["phase"] == "prepared"
    calls = p85[0].understanding_calls
    monkeypatch.setattr(dialogue, "call", original)
    switched = dialogue.PROTOCOL if protocol == dialogue.P85_PROTOCOL else dialogue.P85_PROTOCOL
    monkeypatch.setenv("AI_CONVERSATION_DIALOGUE_PROTOCOL", "" if disabled else switched)
    value = ok(send(client, ids, session, "把牛奶移到书房", request_id=request_id))
    assert value["dialogue"]["protocol_version"] == protocol
    assert value["dialogue"]["recovery_model_calls"] == 0
    assert p85[0].understanding_calls == calls and p85[0].response_calls == 0


def test_revision_forwarded_without_rewriting_and_memory_truncation(execution_state, p85, monkeypatch):
    client, Session, ids = execution_state
    original = dialogue.call; revision = []
    async def changed(identity, home, stage, payload, seconds):
        if stage == "p85/resolve": assert payload["plan_context_revision"] == revision[0]
        data = await original(identity, home, stage, payload, seconds)
        if stage == "p85/understand": revision.append(data["context_revision"])
        if stage == "p85/resolve": data["memory"]["truncated"] = True
        return data
    monkeypatch.setattr(dialogue, "call", changed)
    value = ok(send(client, ids, ok(start(client, ids)), "你好"))
    assert value["truncated"]


def test_invalid_understanding_revision_and_unknown_model_outcome(execution_state, p85, monkeypatch):
    client, Session, ids = execution_state
    original = dialogue.call; stages = []
    async def changed(identity, home, stage, payload, seconds):
        stages.append(stage)
        data = await original(identity, home, stage, payload, seconds)
        if stage == "p85/understand": data["context_revision"] += 1
        return data
    monkeypatch.setattr(dialogue, "call", changed)
    session = ok(start(client, ids)); request_id = uuid4().hex
    assert send(client, ids, session, "你好", request_id=request_id).status_code == 503
    assert send(client, ids, session, "你好", request_id=request_id).status_code == 409
    assert stages == ["p85/understand"]


@pytest.mark.parametrize("change", ["missing_delta", "memory_selection", "new_field", "expression_lost"])
def test_optional_delta_and_untrusted_response_boundaries(execution_state, p85, monkeypatch, change):
    client, Session, ids = execution_state
    original = dialogue.call
    async def changed(identity, home, stage, payload, seconds):
        if change == "expression_lost" and stage == "p85/respond":
            raise httpx.ReadTimeout("synthetic timeout")
        data = await original(identity, home, stage, payload, seconds)
        if stage == "p85/resolve":
            if change == "missing_delta": data.pop("memory_delta")
            elif change == "memory_selection": data["memory"]["selected_ids"] = ["invented"]
            elif change == "new_field": data["untrusted_extra"] = True
        return data
    monkeypatch.setattr(dialogue, "call", changed)
    result = send(client, ids, ok(start(client, ids)), "把牛奶移到书房")
    if change in {"memory_selection", "new_field"}:
        assert result.status_code == 503
    else:
        value = ok(result)
        assert value["task"]["status"] == "needs_confirmation"
        if change == "expression_lost":
            assert value["dialogue"]["fallback_used"] and value["model_calls"] == 2
    with Session() as db:
        assert db.query(DraftOperation).count() == 0
