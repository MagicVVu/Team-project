"""Authorized, bounded episodes over completed ConversationTurn JSON records."""
import json
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
from uuid import UUID

from pydantic import ValidationError
from app import dialogue_schemas as wire
from app.conversation_models import ConversationTurn
from app.services import conversation as routing, draft_execution as execution
from app.routers import agent_gateway as gateway

EPISODE_KEY = "episode_v1"


def memory_id(scope, conversation_id, request_id):
    key = json.dumps([scope, str(conversation_id), request_id], sort_keys=True)
    return "mem_" + sha256(key.encode()).hexdigest()[:32]


def checked_reference(reference, scope, completed_at):
    """Preserve original attestations, including expired ones for historical recall."""
    if not reference:
        return None
    try:
        if set(reference) != {"protocol_version", "scope", "source_task_id", "source_revision", "batch_id", "issued_at", "expires_at"}:
            raise ValueError()
        issued = gateway.datetime.fromisoformat(reference["issued_at"])
        expires = gateway.datetime.fromisoformat(reference["expires_at"])
        UUID(reference["source_task_id"])
        if (reference["protocol_version"] != "p7-object-reference-1" or reference["scope"] != scope
                or type(reference["source_revision"]) is not int or reference["source_revision"] < 1
                or not isinstance(reference["batch_id"], str) or not reference["batch_id"]
                or issued > completed_at or not timedelta(0) < expires-issued <= timedelta(minutes=15)):
            raise ValueError()
    except (KeyError, ValueError, TypeError):
        execution.fail("MEMORY_ARCHIVE_INVALID", 503)
    return deepcopy(reference)


def subjects_for(turn):
    from app.services import dialogue
    saved = turn.binding_json or {}
    protocol = dialogue.saved_protocol(saved)
    plan = (saved.get(dialogue.PROTOCOL_KEYS[protocol]) or {}).get("plan", {}) if protocol else {}
    candidates = [(plan.get("selector") or {}).get("name")]
    field = (plan.get("fields") or {}).get("name") or {}
    if field.get("source", "current_text") == "current_text":
        candidates.append(field.get("value"))
    return [{"name": name, "quote": name} for name in dict.fromkeys(candidates)
            if isinstance(name, str) and name and name in turn.original_text][:4]


def build(db, identity, home, latest, context):
    from app.services import session_memory as memory
    execution.membership(db, identity.user.id, home)
    scope = {"user_id": str(identity.user.id), "household_id": str(home)}
    if context["scope"] != scope or context["conversation_id"] != memory.meta(latest)["conversation_id"]:
        execution.fail("MEMORY_SCOPE_MISMATCH", 403)
    at = gateway.datetime.fromisoformat(context["trusted_now"])
    statement = memory.query(identity.user.id, home).where(
        ConversationTurn.binding_json[memory.KEY]["conversation_id"].as_string() == context["conversation_id"],
        ConversationTurn.binding_json[memory.KEY]["kind"].as_string() == "message",
        ConversationTurn.created_at > at-timedelta(days=30), ConversationTurn.created_at <= at,
        ConversationTurn.phase == "completed").order_by(
            ConversationTurn.created_at.desc(), ConversationTurn.id.desc()).limit(101)
    rows = list(db.scalars(statement))
    episodes = []
    for row in reversed(rows[:100]):
        info = memory.meta(row)
        if info["revision"] > context["revision"]:
            execution.fail("MEMORY_REVISION_CONFLICT")
        # Old rows have no trusted completion timestamp: retain their original
        # text/time, but do not invent a completion time or attach later refs.
        completed = gateway.datetime.fromisoformat(info["completed_at"]) if info.get("completed_at") else gateway.as_aware(row.created_at)
        if not at-timedelta(days=30) < completed <= at:
            execution.fail("MEMORY_ARCHIVE_INVALID", 503)
        saved_episode = (row.binding_json or {}).get(EPISODE_KEY)
        subjects = saved_episode.get("subjects", []) if saved_episode else subjects_for(row)
        reference = saved_episode.get("reference") if saved_episode else info.get("reference") if info.get("completed_at") else None
        episode = wire.Episode(memory_id=memory_id(scope, context["conversation_id"], row.request_id),
            request_id=row.request_id, text=row.original_text,
            reply=(row.response_json or {}).get("reply", "")[:8000], created_at=completed,
            subjects=subjects, reference=checked_reference(reference, scope, completed))
        episodes.append(episode)
    return wire.Archive(scope=scope, conversation_id=context["conversation_id"], revision=context["revision"],
        episodes=episodes, has_more=len(rows)>100).model_dump(mode="json")


def validate_use(value, payload):
    archive = payload.get("archive")
    allowed = {e["memory_id"] for e in (archive or {}).get("episodes", [])}
    selected = value["selected_ids"]
    if (len(set(selected)) != len(selected) or not set(selected) <= allowed
            or value["archive_available"] != (archive is not None)):
        execution.fail("DIALOGUE_AI_INVALID", 503)


def validate_delta(delta, payload, reply):
    if delta is None:
        return
    try:
        value = wire.MemoryDelta.model_validate(delta).model_dump(mode="json")
        ctx, episode = payload["context"], value["episode"]
        if (value["scope"] != ctx["scope"] or value["conversation_id"] != ctx["conversation_id"]
                or value["expected_revision"] != ctx["revision"]
                or episode["request_id"] != payload["request_id"] or episode["text"] != payload["text"]
                or value["source_text_sha256"] != sha256(payload["text"].encode()).hexdigest()
                or episode["memory_id"] != memory_id(ctx["scope"], ctx["conversation_id"], payload["request_id"])
                or gateway.datetime.fromisoformat(episode["created_at"]) != gateway.datetime.fromisoformat(ctx["trusted_now"])
                or episode["reply"] != reply[:8000] or episode.get("reference") is not None):
            raise ValueError()
    except (ValidationError, ValueError, TypeError, KeyError):
        execution.fail("DIALOGUE_AI_INVALID", 503)


def finalize(turn, saved, info, understood, response, *, has_task):
    """Called in the task/draft/turn completion transaction, never commits itself."""
    from app.services import dialogue
    protocol = dialogue.saved_protocol(saved)
    completed = gateway.now()
    info["completed_at"] = completed.isoformat()
    if protocol != dialogue.P85_PROTOCOL:
        return {**saved, "memory_v1": info}
    state = deepcopy(saved[dialogue.P85_KEY])
    # Revalidate the durable resolved delta, not a mobile-supplied or edited copy.
    resolved = state.get("resolved") or {}
    delta = resolved.get("memory_delta")
    validate_delta(delta, saved["payload"], resolved.get("reply", ""))
    scope = saved["payload"]["context"]["scope"]
    episode = wire.Episode(memory_id=memory_id(scope, info["conversation_id"], turn.request_id),
        request_id=turn.request_id, text=turn.original_text, reply=response["reply"][:8000],
        created_at=completed, subjects=delta["episode"]["subjects"] if delta else subjects_for(turn),
        reference=checked_reference(info.get("reference"), scope, completed) if has_task else None)
    state.update(memory_delta=delta, final_reply=response["reply"], completed_at=completed.isoformat())
    return {**saved, "memory_v1": info, dialogue.P85_KEY: state,
            EPISODE_KEY: episode.model_dump(mode="json")}
