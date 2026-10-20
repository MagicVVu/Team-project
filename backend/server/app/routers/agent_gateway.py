"""v0.6 authenticated, read-only AI gateway.

Existing P1 agent is authoritative for parsing and clarification. Only PostgreSQL
controls identity, household, current context, idempotent request IDs and drafts.
This module contains NO write path for inventory, shopping lists, or events.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.dependencies import Identity, get_db, get_identity
from app.models import AIDraft, AITask, HouseholdMember

logger = logging.getLogger(__name__)
router = APIRouter(tags=["AI Gateway — read-only v0.6"])
AI_STATES = frozenset({"needs_clarification", "needs_confirmation", "answered", "unsupported", "error"})
AI_LEASE_SECONDS = 30


def now() -> datetime:
    return datetime.now(timezone.utc)


def as_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)  # SQLite test compatibility


class NewMessage(BaseModel):
    household_id: UUID
    text: str = Field(min_length=1, max_length=1000, pattern=r"\S")
    request_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")
    household_timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)

    @field_validator("household_timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Invalid IANA timezone") from None
        return value


class ContinueMessage(BaseModel):
    revision: int = Field(ge=1)
    answers: dict[str, Any] = Field(min_length=1, max_length=9)


ALLOWED_ANSWERS = frozenset({
    "name", "quantity", "unit", "location", "purchased_at", "label_expiry",
    "opened_at", "to_location", "batch_id",
})


def check_membership(db: Session, identity: Identity, household_id: UUID) -> None:
    member = db.get(HouseholdMember, (household_id, identity.user.id))
    if member is None:
        raise HTTPException(404, "Household not found")


def check_config() -> tuple[str, str]:
    url = os.getenv("AI_SERVICE_URL", "").rstrip("/")
    token = os.getenv("AI_SERVICE_TOKEN", "")
    if not token or len(token) < 32 or not url.startswith("http://agent:8767") or url != "http://agent:8767":
        # Fixed Docker service network destination; do not allow App-controlled SSRF.
        raise HTTPException(503, "AI service is not configured")
    return url, token


async def _call_ai(path: Literal["/agent/message", "/agent/clarification"], user_id: UUID,
                   household_id: UUID, payload: dict[str, Any]) -> dict:
    url, token = check_config()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(13.0, connect=3.0),
                                     trust_env=False, follow_redirects=False) as client:
            res = await client.post(url + path, json=payload, headers={
                "Authorization": f"Bearer {token}",
                "X-User-Id": str(user_id),
                "X-Household-Id": str(household_id),
            })
        if res.status_code != 200:
            logger.warning("P1 returned HTTP %s", res.status_code)
            raise HTTPException(503, "AI service unavailable")
        data = res.json()
        if not isinstance(data, dict) or data.get("status") not in AI_STATES:
            raise ValueError("Invalid AI result")
        if not isinstance(data.get("trace_id"), str) or not isinstance(data.get("original_text"), str):
            raise ValueError("Invalid AI result metadata")
        if data["status"] == "needs_clarification" and not isinstance(data.get("clarification"), dict):
            raise ValueError("AI clarification missing")
        if data["status"] == "needs_confirmation" and not isinstance(data.get("draft"), dict):
            raise ValueError("AI draft missing")
        return data
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        logger.warning("P1 call unavailable / invalid response")
        raise HTTPException(503, "AI service unavailable") from None


def fingerprint(payload: NewMessage) -> str:
    canonical = json.dumps({"text": payload.text, "household_timezone": payload.household_timezone},
                           ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def owned_task(db: Session, task_id: UUID, identity: Identity) -> AITask:
    task = db.scalar(select(AITask).where(AITask.id == task_id, AITask.user_id == identity.user.id))
    if task is None:
        raise HTTPException(404, "AI task not found")
    check_membership(db, identity, task.household_id)
    return task


def response_for(db: Session, task: AITask) -> dict:
    draft = db.scalar(select(AIDraft).where(AIDraft.task_id == task.id))
    # Never describe a prospective preview as a successfully executed mutation.
    public_result = dict(task.result_json) if task.result_json else None
    if public_result and isinstance(public_result.get("clarification"), dict):
        # Never expose internal continuation context; only server reads it back.
        public_result["clarification"] = {
            "revision": task.revision,
            "allowed_fields": list(task.context_json.get("allowed_fields", [])) if task.context_json else [],
            "expires_at": as_aware(task.expires_at).isoformat() if task.expires_at else None,
        }
    return {
        "task_id": str(task.id), "household_id": str(task.household_id),
        "status": task.status, "revision": task.revision,
        "expires_at": as_aware(task.expires_at).isoformat() if task.expires_at else None,
        "draft_id": str(draft.id) if draft and draft.status == "pending" else None,
        "result": public_result,
        "inventory_written": False,
    }


<<<<<<< HEAD
<<<<<<< HEAD
def reference_expiry(task: AITask) -> datetime:
    # GET/reopening a window never extends a reference's lifetime.
    limit = as_aware(task.updated_at) + timedelta(minutes=15)
    return min(limit, as_aware(task.expires_at)) if task.expires_at else limit


async def reference_message(body, identity, db):
    from app.services.draft_execution import fail
    check_membership(db, identity, body.household_id)
    # Idempotency lookup precedes expiry validation so completed requests recover.
    canonical = body.model_dump(mode="json")
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    task = db.scalar(select(AITask).where(AITask.user_id == identity.user.id,
        AITask.household_id == body.household_id, AITask.request_id == body.request_id).with_for_update())
    if task is not None:
        if task.request_hash != digest:
            fail("REQUEST_ID_CONFLICT")
        if task.status != "processing":
            return response_for(db, task)
        if task.lease_until and as_aware(task.lease_until) > now():
            fail("TASK_PROCESSING")
    source = owned_task(db, body.source_task_id, identity)
    if source.household_id != body.household_id:
        fail("REFERENCE_NOT_FOUND", 404)
    if source.revision != body.source_revision:
        fail("REFERENCE_REVISION_CONFLICT")
    if source.status not in {"answered", "needs_clarification", "needs_confirmation"}:
        fail("REFERENCE_REQUIRED")
    until = reference_expiry(source)
    if until <= now():
        fail("REFERENCE_EXPIRED")
    result = source.result_json or {}
    rows = [*(result.get("facts") or []), *(result.get("candidates") or [])]
    before = (result.get("preview") or {}).get("before")
    if isinstance(before, dict):
        rows.append(before)
    if not any(isinstance(row, dict) and str(row.get("id")) == str(body.batch_id) for row in rows):
        fail("INVALID_REFERENCE_CANDIDATE", 422)
    from app.models import InventoryItem
    batch = db.scalar(select(InventoryItem).where(InventoryItem.id == body.batch_id,
                                               InventoryItem.household_id == body.household_id))
    if batch is None:
        fail("REFERENCE_NOT_FOUND", 404)
<<<<<<< Updated upstream
    if batch.status != 'ACTIVE' or batch.quantity <= 0: fail('REFERENCE_TERMINAL')
=======
    if batch.status != 'ACTIVE' or batch.quantity <= 0:
        fail('REFERENCE_TERMINAL')
>>>>>>> Stashed changes
    # Validate timezone with the same rules as ordinary four-field messages.
    NewMessage.model_validate({k: canonical[k] for k in NewMessage.model_fields})
    check_config()
    reference = {"protocol_version": "p7-object-reference-1",
        "scope": {"user_id": str(identity.user.id), "household_id": str(body.household_id)},
        "source_task_id": str(source.id), "source_revision": source.revision,
        "batch_id": str(body.batch_id), "issued_at": as_aware(source.updated_at).isoformat(),
        "expires_at": until.isoformat()}
    user_id, household_id = identity.user.id, body.household_id
    if task is None:
        task = AITask(user_id=user_id, household_id=household_id, request_id=body.request_id,
            request_hash=digest, original_text=body.text, household_timezone=body.household_timezone,
            status="processing", expires_at=until)
        db.add(task)
    nonce = reserve(task)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        fail("CONCURRENT_DUPLICATE_REQUEST")
    try:
        data = await _call_ai("/agent/message", user_id, household_id,
            {"text": body.text, "request_id": body.request_id,
             "household_timezone": body.household_timezone, "reference": reference})
        if data["original_text"] != body.text:
            raise HTTPException(503, "AI returned inconsistent original text")
        save_result(db, task, nonce, data)
    except Exception:
        db.rollback()
        restore_after_failure(db, task, nonce, "error")
        raise
    return response_for(db, task)


=======
>>>>>>> parent of 3aa98be (feat: integrate P72 clarification references and open discard execution)
=======
>>>>>>> parent of 3aa98be (feat: integrate P72 clarification references and open discard execution)
def reserve(task: AITask) -> str:
    nonce = str(uuid4())
    task.status = "processing"
    task.processing_nonce = nonce
    task.lease_until = now() + timedelta(seconds=AI_LEASE_SECONDS)
    task.updated_at = now()
    return nonce


def save_result(db: Session, task: AITask, nonce: str, data: dict) -> None:
    db.refresh(task)
    if task.processing_nonce != nonce or task.status != "processing":
        raise HTTPException(409, "Task already superseded; fetch latest")
    task.status = data["status"]
    task.result_json = data
    task.processing_nonce = None
    task.lease_until = None
    task.updated_at = now()
    context = data.get("clarification")
    if isinstance(context, dict):
        if context.get("scope") != {"user_id": str(task.user_id), "household_id": str(task.household_id)}:
            raise HTTPException(503, "AI returned inconsistent identity")
        if not isinstance(context.get("revision"), int) or context["revision"] < task.revision:
            raise HTTPException(503, "AI returned inconsistent revision")
        task.context_json = context
        task.revision = context["revision"]
        try:
            expiry = datetime.fromisoformat(context["expires_at"].replace("Z", "+00:00"))
        except (ValueError, TypeError, KeyError, AttributeError):
            raise HTTPException(503, "Invalid AI clarification expiry") from None
        task.expires_at = expiry
    if data["status"] == "needs_confirmation":
        preview = data.get("preview")
        if preview is not None and not isinstance(preview, dict):
            raise HTTPException(503, "Invalid AI preview")
        old_draft = db.scalar(select(AIDraft).where(AIDraft.task_id == task.id))
        if old_draft is not None:
            old_draft.command_json = data["draft"]
            old_draft.preview_json = preview
            old_draft.revision += 1
            old_draft.updated_at = now()
            old_draft.status = "pending"
        else:
            db.add(AIDraft(task_id=task.id, user_id=task.user_id, household_id=task.household_id,
                           command_json=data["draft"], preview_json=preview, status="pending", revision=1))
    elif data["status"] != "needs_clarification":
        # A completion/error that invalidates an old draft must never leave it executable.
        previous = db.scalar(select(AIDraft).where(AIDraft.task_id == task.id))
        if previous is not None:
            previous.status = "superseded"
    db.commit()


def restore_after_failure(db: Session, task: AITask, nonce: str, previous: str) -> None:
    db.refresh(task)
    if task.processing_nonce == nonce:
        task.status = previous
        task.processing_nonce = None
        task.lease_until = None
        task.updated_at = now()
        db.commit()


@router.post("/api/v1/agent/messages")
async def new_message(body: NewMessage, identity: Identity = Depends(get_identity),
                      db: Session = Depends(get_db)) -> dict:
    check_membership(db, identity, body.household_id)
    user_id = identity.user.id  # Snapshot before commit expires ORM attributes.
    check_config()  # fail closed: do not create a stuck task if AI isn't configured
    digest = fingerprint(body)
    task = db.scalar(select(AITask).where(AITask.user_id == identity.user.id,
                    AITask.household_id == body.household_id, AITask.request_id == body.request_id).with_for_update())
    if task is not None:
        if task.request_hash != digest:
            raise HTTPException(409, "request_id was already used with different content")
        if task.status != "processing":
            return response_for(db, task)
        if task.lease_until and as_aware(task.lease_until) > now():
            raise HTTPException(409, "Task is currently processing; retry later")
        nonce = reserve(task)  # recover an abandoned request after lease expiry
    else:
        task = AITask(user_id=identity.user.id, household_id=body.household_id,
                      request_id=body.request_id, request_hash=digest,
                      original_text=body.text, household_timezone=body.household_timezone,
                      status="processing")
        db.add(task)
        nonce = reserve(task)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # A concurrent duplicate is still at most one paid AI call.
        raise HTTPException(409, "Concurrent duplicate request; retry same request_id") from None
    try:
        result = await _call_ai("/agent/message", user_id, body.household_id,
                                {"text": body.text, "request_id": body.request_id,
                                 "household_timezone": body.household_timezone})
        if result["original_text"] != body.text:
            raise HTTPException(503, "AI returned inconsistent original text")
        save_result(db, task, nonce, result)
    except Exception:
        db.rollback()
        restore_after_failure(db, task, nonce, "error")
        raise
    return response_for(db, task)


@router.post("/api/v1/agent/clarifications/{task_id}")
async def clarification(task_id: UUID, body: ContinueMessage,
                        identity: Identity = Depends(get_identity), db: Session = Depends(get_db)) -> dict:
    task = db.scalar(select(AITask).where(AITask.id == task_id, AITask.user_id == identity.user.id).with_for_update())
    if task is None:
        raise HTTPException(404, "AI task not found")
    check_membership(db, identity, task.household_id)
    if task.status == "processing":
        if task.lease_until and as_aware(task.lease_until) > now():
            raise HTTPException(409, "Task is currently processing")
        if task.context_json is None:
            raise HTTPException(409, "Task has no persisted clarification")
        task.status = "needs_clarification"  # recover after worker exit
    if task.status != "needs_clarification" or task.context_json is None:
        raise HTTPException(409, "Task does not require clarification")
    if body.revision != task.revision:
        raise HTTPException(409, "Clarification revision mismatch")
    if task.expires_at is None or as_aware(task.expires_at) <= now():
        raise HTTPException(409, "Clarification expired")
    allowed = set(task.context_json.get("allowed_fields") or [])
    if not set(body.answers).issubset(ALLOWED_ANSWERS & allowed):
        raise HTTPException(422, "Only currently requested clarification fields are allowed")
    # P1 owns detailed schema validation. Disallow arbitrary complex injected JSON.
    if any(not isinstance(v, (str, int, float)) or isinstance(v, bool) for v in body.answers.values()):
        raise HTTPException(422, "Invalid clarification value")
    if len(json.dumps(body.answers, ensure_ascii=False)) > 1500:
        raise HTTPException(422, "Clarification fields too large")
    check_config()
    prior = "needs_clarification"
    context = task.context_json
    user_id, household_id, original_text = identity.user.id, task.household_id, task.original_text
    nonce = reserve(task)
    db.commit()
    try:
        result = await _call_ai("/agent/clarification", user_id, household_id,
                                {"context": context, "revision": body.revision, "answers": body.answers})
        if result["original_text"] != original_text:
            raise HTTPException(503, "AI returned inconsistent original text")
        save_result(db, task, nonce, result)
    except Exception:
        db.rollback()
        restore_after_failure(db, task, nonce, prior)
        raise
    return response_for(db, task)


@router.get("/api/v1/agent/tasks/{task_id}")
def get_task(task_id: UUID, identity: Identity = Depends(get_identity),
             db: Session = Depends(get_db)) -> dict:
    return response_for(db, owned_task(db, task_id, identity))


@router.get("/api/v1/drafts/{draft_id}")
def get_draft(draft_id: UUID, identity: Identity = Depends(get_identity),
              db: Session = Depends(get_db)) -> dict:
    draft = db.scalar(select(AIDraft).where(AIDraft.id == draft_id, AIDraft.user_id == identity.user.id))
    if draft is None:
        raise HTTPException(404, "Draft not found")
    check_membership(db, identity, draft.household_id)
    return {"id": str(draft.id), "task_id": str(draft.task_id), "revision": draft.revision,
            "status": draft.status, "draft": draft.command_json, "preview": draft.preview_json,
            "prospective": True, "inventory_written": False}
