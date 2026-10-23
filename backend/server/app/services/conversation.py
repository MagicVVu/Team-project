"""Authenticated cursor + input receipts around the existing database gateway.

No extraction rules live here. P7.3 owns reply resolution over a server-built
snapshot. The request receipt and cursor are finalized in the same transaction
as the task/draft. Neither table executes business mutations.
"""
import hashlib
import json
import os
from datetime import timedelta
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.conversation_models import ConversationBinding, ConversationTurn
from app.conversation_schemas import Resolution
from app.models import AITask, InventoryItem, AuthSession, User
from app.routers import agent_gateway as gateway
from app.services.draft_execution import fail, membership


def reference_enabled():
    return os.getenv("MAGICVVU_TRUSTED_REFERENCE_MESSAGES", "false").lower() == "true"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def cursor(db, user_id):
    return db.scalar(select(ConversationBinding).where(ConversationBinding.user_id == user_id)
                     .with_for_update().execution_options(populate_existing=True))


def source_task(db, identity, task_id, home, revision=None):
    task = gateway.owned_task(db, task_id, identity)
    if task.household_id != home:
        fail("REFERENCE_SCOPE_MISMATCH", 404)
    if revision is not None and task.revision != revision:
        fail("TASK_REVISION_CONFLICT")
    return task


def rows(task):
    result = task.result_json or {}
    values = [*(result.get("facts") or []), *(result.get("candidates") or [])]
    before = (result.get("preview") or {}).get("before")
    if isinstance(before, dict):
        values.append(before)
    return [row for row in values if isinstance(row, dict)]


def batch(db, home, batch_id):
    try:
        row = db.scalar(select(InventoryItem).where(InventoryItem.id == UUID(str(batch_id)),
            InventoryItem.household_id == home).execution_options(populate_existing=True))
    except ValueError:
        fail("REFERENCE_NOT_FOUND", 404)
    if row is None:
        fail("REFERENCE_NOT_FOUND", 404)
    if row.status != "ACTIVE" or row.quantity <= 0:
        fail("REFERENCE_TERMINAL")
    return row


def issue(db, identity, task, selected=None):
    result = task.result_json or {}
    if task.status not in {"answered", "needs_clarification", "needs_confirmation"} or result.get("status") != task.status:
        fail("REFERENCE_REQUIRED")
    if selected is None:
        facts = result.get("facts") or []
        if task.status != "answered" or len(facts) != 1:
            return None
        selected = facts[0].get("id")
    if str(selected) not in {str(row.get("id")) for row in rows(task)}:
        fail("INVALID_REFERENCE_CANDIDATE", 422)
    batch(db, task.household_id, selected)
    issued = gateway.as_aware(task.updated_at)
    until = issued + timedelta(minutes=15)
    if task.expires_at:
        until = min(until, gateway.as_aware(task.expires_at))
    if gateway.now() >= until:
        fail("REFERENCE_EXPIRED")
    return {"protocol_version": "p7-object-reference-1",
        "scope": {"user_id": str(identity.user.id), "household_id": str(task.household_id)},
        "source_task_id": str(task.id), "source_revision": task.revision,
        "batch_id": str(selected), "issued_at": issued.isoformat(), "expires_at": until.isoformat()}


def validate_reference(db, identity, home, reference):
    if not reference:
        fail("REFERENCE_REQUIRED")
    if reference["scope"] != {"user_id": str(identity.user.id), "household_id": str(home)}:
        fail("REFERENCE_SCOPE_MISMATCH", 404)
    until = gateway.datetime.fromisoformat(reference["expires_at"])
    if gateway.now() >= until:
        fail("REFERENCE_EXPIRED")
    source = source_task(db, identity, UUID(reference["source_task_id"]), home, reference["source_revision"])
    if reference["batch_id"] not in {str(row.get("id")) for row in rows(source)}:
        fail("REFERENCE_SOURCE_CHANGED")
    batch(db, home, reference["batch_id"])
    return reference


def candidates_unchanged(db, task):
    candidates = (task.result_json or {}).get("candidates") or []
    for candidate in candidates:
        row = batch(db, task.household_id, candidate["id"])
        if row.version != candidate["version"]:
            fail("CANDIDATES_CHANGED")


async def resolve(binding, text, user_id, home, trusted_now, selected=None):
    url, token = gateway.check_config()
    try:
        async with httpx.AsyncClient(timeout=5, trust_env=False, follow_redirects=False) as client:
            response = await client.post(url + "/agent/reply-resolution", json={
                "binding": binding, "text": text, "trusted_now": trusted_now,
                "selected_batch_id": selected}, headers={"Authorization": "Bearer " + token,
                "X-User-Id": str(user_id), "X-Household-Id": str(home)})
        if response.status_code != 200:
            fail("REPLY_ADAPTER_UNAVAILABLE", 503)
        result = Resolution.model_validate(response.json()).model_dump(mode="json")
        if result["kind"] == "clarify":
            allowed = set(binding["task"]["result"]["clarification"]["allowed_fields"])
            if (result["revision"] != binding["task"]["revision"] or not result["answers"]
                    or not set(result["answers"]) <= allowed & gateway.ALLOWED_ANSWERS):
                fail("REPLY_ADAPTER_INVALID", 503)
        elif result["answers"] or result["revision"] is not None:
            fail("REPLY_ADAPTER_INVALID", 503)
        return result
    except (httpx.HTTPError, ValueError, TypeError, KeyError, ValidationError):
        fail("REPLY_ADAPTER_UNAVAILABLE", 503)


def locked_turn(db, identity, turn_id, nonce):
    # Gateway already holds its task lock before this callback acquires the cursor.
    current = cursor(db, identity.user.id)
    turn = db.get(ConversationTurn, turn_id, populate_existing=True)
    if (current is None or turn is None or current.processing_nonce != nonce
            or turn.processing_nonce != nonce or current.household_id != turn.household_id
            or current.session_id != identity.session_id):
        fail("CONVERSATION_SUPERSEDED")
    membership(db, identity.user.id, turn.household_id, lock=True)
    session = db.get(AuthSession, identity.session_id, populate_existing=True)
    user = db.get(User, identity.user.id, populate_existing=True)
    if (session is None or session.revoked_at is not None or gateway.as_aware(session.expires_at) <= gateway.now()
            or user is None or not user.is_active):
        fail("CONVERSATION_SESSION_EXPIRED", 401)
    return current, turn


def complete(db, identity, turn_id, nonce, resolution, task=None, reference=None):
    current, turn = locked_turn(db, identity, turn_id, nonce)
    if task is not None:
        current.task_id = task.id
        turn.task_id = task.id
        if task.status in {"error", "unsupported"}:
            reference = None
        if reference is not None and reference["source_task_id"] == str(task.id):
            # Same task accepted another supplement. Preserve issue time/TTL;
            # carry its selected identity into the newly committed revision.
            reference = {**reference, "source_revision": task.revision}
        if reference is not None:
            validate_reference(db, identity, turn.household_id, reference)
        if reference is None and reference_enabled() and task.status in {"answered", "needs_clarification", "needs_confirmation"}:
            selected = resolution["answers"].get("batch_id") if resolution["kind"] == "clarify" else None
            reference = issue(db, identity, task, selected)
    elif resolution["kind"] == "clear_reference":
        current.task_id = None
    current.reference_json = reference
    current.processing_nonce = None
    current.lease_until = None
    turn.phase = "completed"
    turn.processing_nonce = None
    turn.response_json = {"protocol_version": "backend-conversation-1", "request_id": turn.request_id,
        "original_text": turn.original_text, "resolution": resolution,
        "task": gateway.response_for(db, task) if task else (
            gateway.response_for(db, db.get(AITask, current.task_id)) if current.task_id else None),
        "reference": reference, "inventory_written": False}
    db.flush()
    return turn.response_json


async def handle(body, identity, db, *, explicit_reference=False):
    if explicit_reference and not reference_enabled():
        fail("TRUSTED_REFERENCE_ADAPTER_UNAVAILABLE", 503)
    user_id, home = identity.user.id, body.household_id
    membership(db, user_id, home, lock=True)
    payload = body.model_dump(mode="json")
    request_hash = digest({"input": payload, "reference_endpoint": explicit_reference})
    current = cursor(db, user_id)
    fresh_cursor = current is None
    turn = db.scalar(select(ConversationTurn).where(ConversationTurn.user_id == user_id,
        ConversationTurn.household_id == home, ConversationTurn.request_id == body.request_id))
    if turn is not None:
        if turn.request_hash != request_hash:
            fail("REQUEST_ID_CONFLICT")
        if current is None or current.household_id != home or current.session_id != identity.session_id:
            fail("CONVERSATION_BINDING_CHANGED")
        if turn.phase == "completed":
            return turn.response_json
        if turn.phase == "messaging":
            # The provider may already have charged this extraction. Never retry it blindly.
            raise HTTPException(409, detail={"code": "AI_OUTCOME_UNKNOWN",
                "task_id": str(turn.task_id) if turn.task_id else None,
                "recovery": "GET /api/v1/agent/tasks/{task_id}"})
    if current is None:
        current = ConversationBinding(user_id=user_id, household_id=home, session_id=identity.session_id)
        db.add(current)
    elif current.processing_nonce and current.lease_until and gateway.as_aware(current.lease_until) > gateway.now():
        fail("CONVERSATION_PROCESSING")
    if current.household_id != home or current.session_id != identity.session_id:
        if explicit_reference or body.task_id is not None:
            fail("CONVERSATION_BINDING_CHANGED")
        current.household_id, current.session_id = home, identity.session_id
        current.task_id = current.reference_json = None
    if turn is None:
        task = None
        reference = current.reference_json
        if explicit_reference:
            task = source_task(db, identity, body.source_task_id, home, body.source_revision)
            if not fresh_cursor and current.task_id is None:
                fail("CONVERSATION_BINDING_CHANGED")
            if current.task_id is not None and current.task_id != task.id:
                if not reference or reference["source_task_id"] != str(task.id):
                    fail("CONVERSATION_BINDING_CHANGED")
            if reference and reference["source_task_id"] == str(task.id) and reference["batch_id"] == str(body.batch_id):
                reference = validate_reference(db, identity, home, reference)
            else:
                reference = issue(db, identity, task, str(body.batch_id))
        else:
            if body.task_id is not None:
                task = source_task(db, identity, body.task_id, home, body.revision)
                if current.task_id is not None and current.task_id != task.id:
                    fail("CONVERSATION_BINDING_CHANGED")
            elif current.task_id is not None:
                # An existing active task requires an explicit revision selector.
                fail("TASK_SELECTOR_REQUIRED")
        snapshot = None
        if task is not None:
            if task.status == "processing":
                fail("TASK_PROCESSING")
            current.task_id = task.id
            snapshot = {"scope": {"user_id": str(user_id), "household_id": str(home)},
                "task": gateway.response_for(db, task), "household_timezone": task.household_timezone}
        turn = ConversationTurn(user_id=user_id, household_id=home, request_id=body.request_id,
            request_hash=request_hash, original_text=body.text, task_id=task.id if task else None,
            source_revision=task.revision if task else None, binding_json={"binding": snapshot,
                "reference": reference, "trusted_now": gateway.now().isoformat(),
                "timezone": task.household_timezone if task else os.getenv("MAGICVVU_HOUSEHOLD_TIMEZONE", "Asia/Shanghai")},
            phase="resolving")
        db.add(turn)
    nonce = str(uuid4())
    current.processing_nonce = turn.processing_nonce = nonce
    current.lease_until = gateway.now() + timedelta(seconds=30)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail("CONCURRENT_DUPLICATE_REQUEST")
    turn_id = turn.id
    saved = turn.binding_json
    resolution = turn.resolution_json
    # Release every DB connection before crossing the container boundary.
    db.rollback()
    try:
        if resolution is None:
            if explicit_reference or saved["binding"] is None:
                resolution = Resolution(kind="new_task", clear_reference=not explicit_reference).model_dump(mode="json")
            else:
                resolution = await resolve(saved["binding"], body.text, user_id, home,
                    saved["trusted_now"], (saved["reference"] or {}).get("batch_id"))
            _, turn = locked_turn(db, identity, turn_id, nonce)
            turn.resolution_json = resolution
            db.commit()
        reference = saved["reference"]
        if resolution["kind"] in {"needs_input", "clear_reference"}:
            result = complete(db, identity, turn_id, nonce, resolution,
                reference=reference if resolution["kind"] == "needs_input" else None)
            db.commit()
            return result
        current, turn = locked_turn(db, identity, turn_id, nonce)
        if resolution["kind"] == "clarify":
            task = source_task(db, identity, turn.task_id, home, resolution["revision"])
            if reference is not None:
                validate_reference(db, identity, home, reference)
            if task.status == "processing" and task.context_json is not None:
                if task.lease_until and gateway.as_aware(task.lease_until) > gateway.now():
                    fail("TASK_PROCESSING")
                task.status = "needs_clarification"
            if digest(gateway.response_for(db, task)) != digest(saved["binding"]["task"]):
                fail("TASK_SNAPSHOT_CHANGED")
            candidates_unchanged(db, task)
            turn.phase = "clarifying"
        else:
            gateway.check_config()
            if resolution["clear_reference"]:
                reference = None
            if reference is not None:
                if not reference_enabled():
                    fail("TRUSTED_REFERENCE_ADAPTER_UNAVAILABLE", 503)
                reference = validate_reference(db, identity, home, reference)
            current.reference_json = None  # A new topic invalidates the active reference immediately.
            current.task_id = None
            turn.phase = "messaging"
        db.commit()

        def on_saved(database, task):
            complete(database, identity, turn_id, nonce, resolution, task, reference)

        if resolution["kind"] == "clarify":
            await gateway.run_clarification(turn.task_id,
                gateway.ContinueMessage(revision=resolution["revision"], answers=resolution["answers"]),
                identity, db, on_saved=on_saved)
        else:
            await gateway.run_message(gateway.NewMessage(household_id=home, text=body.text,
                request_id=body.request_id, household_timezone=saved["timezone"]), identity, db,
                reference=reference, on_saved=on_saved)
        return db.get(ConversationTurn, turn_id, populate_existing=True).response_json
    except Exception:
        db.rollback()
        current = cursor(db, user_id)
        if current is not None and current.processing_nonce == nonce:
            current.processing_nonce = None
            current.lease_until = None
            turn = db.get(ConversationTurn, turn_id, populate_existing=True)
            if turn is not None and turn.phase == "messaging":
                original = db.scalar(select(AITask).where(AITask.user_id == user_id,
                    AITask.household_id == home, AITask.request_id == body.request_id))
                if original is not None:
                    turn.task_id = original.id
            db.commit()
        raise
