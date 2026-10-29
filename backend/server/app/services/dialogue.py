"""Opt-in P8.4/P8.5 adapter over ConversationTurn JSON and existing task gateway.

No schema migrations, inventory writes, confirmation or receipt fabrication.
"""
import asyncio
import os
import time
from copy import deepcopy
from decimal import Decimal
from datetime import timedelta
from uuid import UUID

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from typing import Literal
from app import dialogue_schemas as p85
from app.conversation_models import ConversationTurn
from app.models import AIDraft
from app.execution_models import DraftDecision
from app.routers import agent_gateway as gateway
from app.services import conversation as routing, draft_execution as execution

PROTOCOL = "p84-dialogue-1"
KEY = "dialogue_v1"
P85_PROTOCOL = "p85-dialogue-1"
P85_KEY = "dialogue_v2"
PROTOCOL_KEYS = {PROTOCOL: KEY, P85_PROTOCOL: P85_KEY}


def configured_protocol():
    value = os.getenv("AI_CONVERSATION_DIALOGUE_PROTOCOL", "")
    return value if value in PROTOCOL_KEYS else None


def saved_protocol(saved):
    found = [p for p, key in PROTOCOL_KEYS.items() if key in saved]
    if len(found) > 1:
        execution.fail("DIALOGUE_STATE_INVALID", 503)
    if found:
        state = saved[PROTOCOL_KEYS[found[0]]]
        if not isinstance(state, dict) or state.get("protocol_version") != found[0]:
            execution.fail("DIALOGUE_STATE_INVALID", 503)
        return found[0]
    return None


def has_plan(saved):
    protocol = saved_protocol(saved)
    return bool(protocol and saved[PROTOCOL_KEYS[protocol]].get("plan"))


def enabled():
    return configured_protocol() is not None


class Understanding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_version: str
    original_text: str
    plan: dict
    understanding_calls: int = Field(ge=0, le=1, strict=True)
    truncated: bool = False


class Resolution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_version: str
    original_text: str
    kind: str
    reply: str
    result: dict | None = None
    answers: dict[str,str] = Field(default_factory=dict)
    task_revision: int | None = None
    reference: dict | None = None
    preserve_active: bool = True
    evidence: list[dict] = Field(default_factory=list)
    field_sources: dict = Field(default_factory=dict)
    filled_fields: dict[str,str] = Field(default_factory=dict)
    facts: dict[str,str] = Field(default_factory=dict)
    edit: dict | None = None
    error_code: str | None = None
    truncated: bool = False
    model_calls: int = Field(ge=0, le=0, strict=True)


class P85Resolution(Resolution):
    protocol_version: Literal["p85-dialogue-1"]
    memory: p85.MemoryUse = Field(default_factory=p85.MemoryUse)
    memory_delta: p85.MemoryDelta | None = None
    expression_required: bool = True


class P85Request(p85.Wire):
    text: str = Field(min_length=1, max_length=1000)
    request_id: str = Field(min_length=1, max_length=100)
    household_timezone: str = "Asia/Shanghai"
    context: dict
    archive: p85.Archive | None = None
    current_task_plan: dict | None = None
    remaining_seconds: float = Field(gt=0, le=18)


class P85ResolveRequest(P85Request):
    plan: p85.Plan
    plan_context_revision: int = Field(ge=0, strict=True)


class P85RespondRequest(p85.Wire):
    text: str = Field(min_length=1, max_length=1000)
    resolved: P85Resolution
    remaining_seconds: float = Field(gt=0, le=18)


def validated(model, value):
    try:
        return model.model_validate(value)
    except (ValidationError, TypeError, ValueError):
        execution.fail("DIALOGUE_AI_INVALID", 503)


async def call(identity, home, stage, payload, seconds):
    url, token = gateway.check_config()
    async with httpx.AsyncClient(timeout=seconds, trust_env=False, follow_redirects=False) as client:
        response = await client.post(url+"/agent/dialogue/"+stage, json=payload, headers={
            "Authorization":"Bearer "+token, "X-User-Id":str(identity.user.id), "X-Household-Id":str(home)})
    if response.status_code != 200: execution.fail("DIALOGUE_AI_UNAVAILABLE", 503)
    try: data = response.json()
    except ValueError: execution.fail("DIALOGUE_AI_INVALID", 503)
    expected = P85_PROTOCOL if stage.startswith("p85/") else PROTOCOL
    if not isinstance(data,dict) or data.get("protocol_version") != expected:
        execution.fail("DIALOGUE_AI_INVALID",503)
    return data


def persist(db, identity, turn_id, nonce, saved, state, phase, key=KEY):
    _, turn = routing.locked_turn(db, identity, turn_id, nonce)
    saved = {**saved, key:dict(state)}
    turn.binding_json, turn.phase = saved, phase
    db.commit()
    return saved


async def run(db, identity, body, turn_id, nonce, saved, *, recovering=False):
    from app.services import session_memory as memory
    from app.services import memory_archive as archive
    start = time.monotonic()
    protocol = saved_protocol(saved) or configured_protocol()
    if protocol is None: execution.fail("DIALOGUE_STATE_INVALID", 503)
    key = PROTOCOL_KEYS[protocol]
    is_p85 = protocol == P85_PROTOCOL
    state = dict(saved.get(key) or {})
    def save(phase):
        return persist(db, identity, turn_id, nonce, saved, state, phase, key)
    async def invoke(stage, value):
        if is_p85:
            validated({"understand": P85Request, "resolve": P85ResolveRequest,
                       "respond": P85RespondRequest}[stage], value)
        return await call(identity, body.household_id, ("p85/" if is_p85 else "")+stage,
                          value, remaining())
    original = dict(saved["payload"])
    def remaining():
        value = 18-(time.monotonic()-start)
        if value <= 0: raise TimeoutError()
        return value
    payload = {**original, "context":memory.context_for(db,identity,body.household_id,db.get(ConversationTurn,turn_id))}
    if is_p85:
        payload["archive"] = archive.build(db, identity, body.household_id, db.get(ConversationTurn, turn_id), payload["context"])
    active = payload["context"].get("active")
    if active:
        previous = db.scalar(memory.query(identity.user.id,body.household_id).where(
            ConversationTurn.task_id==UUID(active["task"]["task_id"]),ConversationTurn.phase=="completed").order_by(
            ConversationTurn.created_at.desc(),ConversationTurn.id.desc()).limit(1))
        previous_protocol = saved_protocol(previous.binding_json or {}) if previous else None
        pending_plan=((previous.binding_json or {}).get(PROTOCOL_KEYS[previous_protocol]) or {}).get("plan") if previous_protocol else None
        if pending_plan:
            # P8.5 memory_id is not part of the shared current_task_plan type.
            payload["current_task_plan"]={k:v for k,v in pending_plan.items() if k != "memory_id"}
    if not state.get("plan"):
        if recovering: execution.fail("AI_OUTCOME_UNKNOWN")
        state.update(protocol_version=protocol, understanding_started=True)
        state["understand_payload"] = deepcopy(payload)
        saved = {**saved, "payload": payload}
        saved = save("understanding")
        understood = validated(p85.Understanding if is_p85 else Understanding,
            await invoke("understand", {**payload,"remaining_seconds":remaining()}))
        if understood.original_text != body.text: execution.fail("DIALOGUE_AI_INVALID",503)
        value = understood.model_dump(mode="json")
        if is_p85 and understood.context_revision != payload["context"]["revision"]:
            execution.fail("DIALOGUE_AI_INVALID", 503)
        if is_p85:
            archive.validate_use(value["memory"], payload)
            if understood.plan.memory_id and understood.plan.memory_id not in understood.memory.selected_ids:
                execution.fail("DIALOGUE_AI_INVALID", 503)
        state.update(value)
        saved = save("understood")
    # Understanding may take seconds: task/receipt facts must be loaded again
    # for resolve, not merely carried from the model's initial snapshot.
    payload["context"]=memory.context_for(db,identity,body.household_id,db.get(ConversationTurn,turn_id,populate_existing=True))
    if is_p85:
        payload["archive"] = archive.build(db, identity, body.household_id, db.get(ConversationTurn, turn_id), payload["context"])
    # Persist the exact refreshed attestation used for downstream validation.
    saved = {**saved, "payload": payload}
    saved = save("resolving")
    resolution_payload = {**payload,"plan":state["plan"],"remaining_seconds":remaining()}
    if is_p85:
        resolution_payload["plan_context_revision"] = state["context_revision"]
    frame = validated(P85Resolution if is_p85 else Resolution,
        await invoke("resolve", resolution_payload)).model_dump(mode="json")
    if frame["original_text"] != body.text or frame["kind"] not in {"task","clarify","edit","explain","needs_input","clear_reference"}:
        execution.fail("DIALOGUE_AI_INVALID",503)
    if frame.get("result"):
        data = frame["result"]
        if data.get("inventory_writes") is not False or data.get("shopping_writes") is not False or data.get("original_text") != body.text:
            execution.fail("DIALOGUE_AI_INVALID",503)
    if is_p85:
        archive.validate_use(frame["memory"], payload)
        archive.validate_delta(frame.get("memory_delta"), payload, frame["reply"])
        frame["truncated"] = frame["truncated"] or frame["memory"]["truncated"]
    state.update(resolved=deepcopy(frame))
    saved = save("resolved")
    response_calls, fallback = 0, recovering or frame.get("expression_required", True)
    # Structured continuation/status and recovery are deliberately zero-model.
    paid_understanding = state.get("understanding_calls",0)
    if not recovering and paid_understanding and frame["kind"] != "clarify" and frame.get("expression_required", True):
        state.update(response_started=True)
        saved = save("responding")
        response_calls = 1
        try:
            # Public truncation is projected separately from the strict AI DTO.
            wire_frame = dict(frame)
            if is_p85:
                wire_frame["truncated"] = state["resolved"]["truncated"]
            response = validated(p85.Expression, await invoke("respond",{"text":body.text,"resolved":wire_frame,
                "remaining_seconds":remaining()}))
            if response.protocol_version != protocol:
                execution.fail("DIALOGUE_AI_INVALID", 503)
            response_calls = response.response_calls
            frame["reply"] = response.reply
            fallback = response.fallback_used
        except (TimeoutError,httpx.HTTPError,HTTPException):
            pass  # Verified frame is already durable. No paid retry.
    state.update(response_calls=response_calls if not recovering else state.get("response_calls", int(state.get("response_started",False))),
                 fallback_used=fallback)
    counts = {"understanding":paid_understanding,"response":state["response_calls"]}
    counts["total"] = sum(counts.values())
    frame.update(model_calls=counts["total"], dialogue={"protocol_version":protocol,"calls":counts,
        "recovery_model_calls":0 if recovering else None,"fallback_used":fallback,"field_sources":frame["field_sources"]})
    saved = save("prepared")
    _, turn = routing.locked_turn(db,identity,turn_id,nonce)
    turn.resolution_json = frame
    db.commit()
    return frame, saved


def save_edit(db, identity, body, frame, callback):
    """Persist a new draft revision atomically; use business validators, no stock write."""
    edit = frame.get("edit") or {}
    task = gateway.owned_task(db, UUID(edit["task_id"]), identity)
    if task.household_id != body.household_id: execution.fail("TASK_NOT_FOUND",404)
    draft = db.scalar(select(AIDraft).where(AIDraft.task_id==task.id))
    if draft is None: execution.fail("DRAFT_NOT_FOUND",404)
    task,draft = execution.owned(db,identity,draft.id,lock=True)
    if task.revision != edit.get("task_revision") or str(draft.id)!=edit.get("draft_id"):
        execution.fail("TASK_REVISION_CONFLICT")
    if db.get(DraftDecision,draft.id) is not None: execution.fail("DRAFT_ALREADY_DECIDED")
    execution.pending(task,draft)
    deadline = execution.expiry(task,draft)
    if deadline <= execution.now(): execution.fail("DRAFT_EXPIRED")
    edits=dict(edit.get("edits") or {})
    for field in ("opened_at","purchased_at","label_expiry"):
        if edits.get(field) in {"今天","昨天"}:
            edits[field]=(execution.business_day(task)-timedelta(days=edits[field]=="昨天")).isoformat()
    action,target,fields,command = execution.command(task,draft,edits)
    if target is not None:
        item = execution.target_item(db,body.household_id,target)
        execution.stock_changes(action,fields,item,command)
    data = frame["result"]
    expected=dict(command)
    proposed=dict(data.get("draft") or {})
    if target is not None and hasattr(fields,"quantity"):
        expected["quantity"]=str(execution.converted(fields.quantity,fields.unit,item.unit))
        expected["unit"]=item.unit
    def canonical(value):
        value=dict(value)
        if "quantity" in value: value["quantity"]=Decimal(value["quantity"])
        return value
    if canonical(proposed) != canonical(expected): execution.fail("DIALOGUE_EDIT_MISMATCH",503)
    data = {**data,"original_text":task.original_text}
    nonce = gateway.reserve(task)
    db.flush()
    gateway.save_result(db,task,nonce,data,on_saved=callback,next_revision=task.revision+1,deadline=deadline)
