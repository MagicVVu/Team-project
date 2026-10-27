"""Opt-in P8.4 adapter over ConversationTurn JSON and existing task gateway.

No schema migrations, inventory writes, confirmation or receipt fabrication.
"""
import asyncio
import os
import time
from decimal import Decimal
from datetime import timedelta
from uuid import UUID

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from pydantic import BaseModel, ConfigDict, Field
from app.conversation_models import ConversationTurn
from app.models import AIDraft
from app.execution_models import DraftDecision
from app.routers import agent_gateway as gateway
from app.services import conversation as routing, draft_execution as execution

PROTOCOL = "p84-dialogue-1"
KEY = "dialogue_v1"


def enabled():
    return os.getenv("AI_CONVERSATION_DIALOGUE_PROTOCOL", "") == PROTOCOL


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


async def call(identity, home, stage, payload, seconds):
    url, token = gateway.check_config()
    async with httpx.AsyncClient(timeout=seconds, trust_env=False, follow_redirects=False) as client:
        response = await client.post(url+"/agent/dialogue/"+stage, json=payload, headers={
            "Authorization":"Bearer "+token, "X-User-Id":str(identity.user.id), "X-Household-Id":str(home)})
    if response.status_code != 200: execution.fail("DIALOGUE_AI_UNAVAILABLE", 503)
    try: data = response.json()
    except ValueError: execution.fail("DIALOGUE_AI_INVALID", 503)
    if not isinstance(data,dict) or data.get("protocol_version") != PROTOCOL:
        execution.fail("DIALOGUE_AI_INVALID",503)
    return data


def persist(db, identity, turn_id, nonce, saved, state, phase):
    _, turn = routing.locked_turn(db, identity, turn_id, nonce)
    saved = {**saved, KEY:state}
    turn.binding_json, turn.phase = saved, phase
    db.commit()
    return saved


async def run(db, identity, body, turn_id, nonce, saved, *, recovering=False):
    from app.services import session_memory as memory
    start = time.monotonic()
    state = dict(saved.get(KEY) or {})
    original = dict(saved["payload"])
    def remaining():
        value = 18-(time.monotonic()-start)
        if value <= 0: raise TimeoutError()
        return value
    payload = {**original, "context":memory.context_for(db,identity,body.household_id,db.get(ConversationTurn,turn_id))}
    active = payload["context"].get("active")
    if active:
        previous = db.scalar(memory.query(identity.user.id,body.household_id).where(
            ConversationTurn.task_id==UUID(active["task"]["task_id"]),ConversationTurn.phase=="completed").order_by(
            ConversationTurn.created_at.desc(),ConversationTurn.id.desc()).limit(1))
        pending_plan=((previous.binding_json or {}).get(KEY) or {}).get("plan") if previous else None
        if pending_plan: payload["current_task_plan"]=pending_plan
    if not state.get("plan"):
        if recovering: execution.fail("AI_OUTCOME_UNKNOWN")
        state.update(protocol_version=PROTOCOL, understanding_started=True)
        saved = persist(db,identity,turn_id,nonce,saved,state,"understanding")
        understood = Understanding.model_validate(await call(identity,body.household_id,"understand",
            {**payload,"remaining_seconds":remaining()},remaining()))
        if understood.original_text != body.text: execution.fail("DIALOGUE_AI_INVALID",503)
        state.update(plan=understood.plan, understanding_calls=understood.understanding_calls, truncated=understood.truncated)
        saved = persist(db,identity,turn_id,nonce,saved,state,"understood")
    # Understanding may take seconds: task/receipt facts must be loaded again
    # for resolve, not merely carried from the model's initial snapshot.
    payload["context"]=memory.context_for(db,identity,body.household_id,db.get(ConversationTurn,turn_id,populate_existing=True))
    frame = Resolution.model_validate(await call(identity,body.household_id,"resolve",
        {**payload,"plan":state["plan"],"remaining_seconds":remaining()},remaining())).model_dump(mode="json")
    if frame["original_text"] != body.text or frame["kind"] not in {"task","clarify","edit","explain","needs_input","clear_reference"}:
        execution.fail("DIALOGUE_AI_INVALID",503)
    if frame.get("result"):
        data = frame["result"]
        if data.get("inventory_writes") is not False or data.get("shopping_writes") is not False or data.get("original_text") != body.text:
            execution.fail("DIALOGUE_AI_INVALID",503)
    state.update(resolved=frame)
    saved = persist(db,identity,turn_id,nonce,saved,state,"resolved")
    response_calls, fallback = 0, True
    # Structured continuation/status and recovery are deliberately zero-model.
    paid_understanding = state.get("understanding_calls",0)
    if not recovering and paid_understanding and frame["kind"] != "clarify":
        state.update(response_started=True)
        saved = persist(db,identity,turn_id,nonce,saved,state,"responding")
        response_calls = 1
        try:
            response = await call(identity,body.household_id,"respond",{"text":body.text,"resolved":frame,
                "remaining_seconds":remaining()},remaining())
            if type(response.get("response_calls")) is not int or response["response_calls"]!=1 or not isinstance(response.get("reply"),str):
                execution.fail("DIALOGUE_AI_INVALID",503)
            frame["reply"] = response["reply"]
            fallback = bool(response.get("fallback_used"))
        except (TimeoutError,httpx.HTTPError,HTTPException):
            pass  # Verified frame is already durable. No paid retry.
    state.update(response_calls=response_calls if not recovering else state.get("response_calls", int(state.get("response_started",False))),
                 fallback_used=fallback)
    counts = {"understanding":paid_understanding,"response":state["response_calls"]}
    counts["total"] = sum(counts.values())
    frame.update(model_calls=counts["total"], dialogue={"protocol_version":PROTOCOL,"calls":counts,
        "recovery_model_calls":0 if recovering else None,"fallback_used":fallback,"field_sources":frame["field_sources"]})
    saved = persist(db,identity,turn_id,nonce,saved,state,"prepared")
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
