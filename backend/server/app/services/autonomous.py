"""Single-call adapter. The model/tool loop lives only in the AI service."""
import copy
import os
import time
from typing import Literal
from uuid import UUID
import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.conversation_models import ConversationTurn
from app.services import conversation as routing, draft_execution as execution, dialogue
from app.routers import agent_gateway as gateway

PROTOCOL = "inventory-autonomous-1"
KEY = "autonomous_v1"


def enabled(): return os.getenv("AI_CONVERSATION_DIALOGUE_PROTOCOL", "") == PROTOCOL


def saved_state(saved):
    if KEY not in saved: return None
    value=saved[KEY]
    if not isinstance(value,dict) or value.get("protocol_version")!=PROTOCOL or dialogue.saved_protocol(saved) is not None:
        execution.fail("DIALOGUE_STATE_INVALID",503)
    return value


def previous_plan(saved):
    state=saved_state(saved)
    if state: return (state.get("result") or {}).get("plan")
    protocol=dialogue.saved_protocol(saved)
    return (saved.get(dialogue.PROTOCOL_KEYS[protocol]) or {}).get("plan") if protocol else None


class Resolution(dialogue.Resolution):
    protocol_version: Literal["p85-dialogue-1"]
    kind: Literal["task","clarify","edit","explain","needs_input","clear_reference"]
    memory: dict = Field(default_factory=dict)
    memory_delta: dict | None = None
    expression_required: bool = True


class Result(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_version: str
    request_id: str
    context_revision: int = Field(ge=0, strict=True)
    original_text: str
    reply: str
    status: str
    stop_reason: str
    resolved: Resolution | None = None
    plan: dict | None = None
    verified_plans: list[dict] = Field(default_factory=list)
    filled_fields: dict[str,str] = Field(default_factory=dict)
    model_calls: int = Field(ge=0, strict=True)
    tool_reads: int = Field(ge=0, strict=True)
    elapsed_ms: float = Field(ge=0)
    fallback_used: bool = False
    error_code: str | None = None
    trace: list[dict] = Field(default_factory=list)
    inventory_writes: Literal[False]
    shopping_writes: Literal[False]

    @model_validator(mode="after")
    def invariants(self):
        if self.protocol_version != PROTOCOL or self.inventory_writes or self.shopping_writes:
            raise ValueError("Invalid autonomous protocol or write boundary")
        if self.model_calls != sum(s.get("model_call") is True for s in self.trace):
            raise ValueError("Invalid attempt count")
        if self.resolved and (self.resolved.original_text != self.original_text or self.resolved.protocol_version != "p85-dialogue-1"):
            raise ValueError("Invalid resolved original or protocol")
        if self.status not in {"completed","needs_input","needs_confirmation","stopped"}:
            raise ValueError("Invalid stop status")
        domain=(self.resolved.result or {}) if self.resolved else {}
        if domain and (domain.get("original_text") != self.original_text
            or domain.get("inventory_writes") is not False or domain.get("shopping_writes") is not False):
            raise ValueError("Invalid domain original or write boundary")
        if (domain.get("status")=="needs_confirmation") != (self.status=="needs_confirmation"):
            raise ValueError("Draft status mismatch")
        return self


async def call(identity, home, path, payload, seconds):
    url, token = gateway.check_config()
    async with httpx.AsyncClient(timeout=seconds, trust_env=False, follow_redirects=False) as client:
        response = await client.post(url+path, json=payload, headers={"Authorization":"Bearer "+token,
            "X-User-Id":str(identity.user.id), "X-Household-Id":str(home)})
    if response.status_code != 200: execution.fail("AUTONOMOUS_AI_UNAVAILABLE",503)
    try: return response.json()
    except ValueError: execution.fail("AUTONOMOUS_AI_INVALID",503)


def persist(db, identity, turn_id, nonce, saved, state, phase):
    _, turn = routing.locked_turn(db, identity, turn_id, nonce)
    saved = {**saved, KEY:state}
    turn.binding_json, turn.phase = saved, phase
    db.commit()
    return saved


def checked_context(db, identity, body, turn_id, nonce, original=None, plan=None):
    from app.services import session_memory as memory
    _, turn = routing.locked_turn(db,identity,turn_id,nonce)
    latest = memory.head(db,identity,body.household_id)
    if latest is None or latest.id != turn.id:
        execution.fail("CONVERSATION_REVISION_CONFLICT")
    ctx = memory.context_for(db,identity,body.household_id,turn)
    if original:
        if (ctx["conversation_id"],ctx["revision"]) != (original["conversation_id"],original["revision"]):
            execution.fail("CONVERSATION_REVISION_CONFLICT")
        # Original candidate order and issue/expiry times remain authoritative.
        selector=(plan or {}).get("selector") or {}
        choices=original.get("choices",[])
        index=selector.get("choice_index")
        if plan and (plan.get("memory_id") or plan.get("speech_act") in {"status","basis","recall","social","discuss","negation","new_task"}):
            used=[]
        elif type(index) is int and 0<=index<len(choices): used=[choices[index]]
        elif selector.get("location") and choices: used=choices
        elif selector.get("use_reference") or (plan and not selector.get("name") and not (plan.get("fields") or {}).get("name")):
            used=[original["reference"]] if original.get("reference") else []
        else: used=[]
        for ref in used:
            routing.validate_reference(db,identity,body.household_id,ref)
        ctx["choices"], ctx["reference"] = original.get("choices",[]), original.get("reference")
    return ctx


def frame_for(result):
    frame = result.resolved.model_dump(mode="json") if result.resolved else dict(
        kind="needs_input", reply=result.reply, evidence=[], filled_fields=result.filled_fields, field_sources={}, preserve_active=True)
    frame.update(reply=result.reply, original_text=result.original_text, filled_fields=result.filled_fields,
                 model_calls=result.model_calls, error_code=result.error_code)
    return frame


def project_intake(frame):
    """Use the business owner's pure intake projection on zero-model replay."""
    domain=frame.get("result") or {}
    command=domain.get("draft") or {}
    if command.get("action")!="ADD":return
    from app.services.physical_inventory import intake_shape
    count,unit,specification=intake_shape(command["quantity"],command["unit"])
    if specification and (domain.get("preview") or {}).get("after"):
        domain["preview"]["after"].update(quantity="1",unit=unit)
        domain["preview"]["quantity_delta"]="1"
    note=f"确认后将新增{count}件独立物品，单位为{unit}"+(f"，规格为{specification}" if specification else "")+"；尚未写入。"
    facts=frame.setdefault("facts",{})
    if note not in facts.values():facts[f"f{len(facts)}"]=note
    frame["reply"]="\n".join(facts.values())
    frame.setdefault("evidence",[]).append({"kind":"physical_intake_projection","created_count":count,
        "per_object_quantity":1,"inventory_unit":unit,"specification":specification,
        "input_quantity":str(command["quantity"]),"input_unit":command["unit"]})
    if frame.get("memory_delta"):
        frame["memory_delta"]=copy.deepcopy(frame["memory_delta"])
        frame["memory_delta"]["episode"]["reply"]=frame["reply"][:8000]


async def run(db, identity, body, turn_id, nonce, saved, *, recovering=False):
    from app.services import session_memory as memory
    from app.services import memory_archive as archive
    start = time.monotonic()
    state = copy.deepcopy(saved_state(saved) or {})
    original = dict(saved["payload"])
    if not state.get("result"):
        if recovering or state.get("started"): execution.fail("AI_OUTCOME_UNKNOWN")
        original["context"] = checked_context(db,identity,body,turn_id,nonce)
        original["archive"] = archive.build(db,identity,body.household_id,db.get(ConversationTurn,turn_id),original["context"])
        active = original["context"].get("active")
        if active:
            from sqlalchemy import select
            previous = db.scalar(memory.query(identity.user.id,body.household_id).where(
                ConversationTurn.task_id==UUID(active["task"]["task_id"]),ConversationTurn.phase=="completed").order_by(
                ConversationTurn.created_at.desc(),ConversationTurn.id.desc()).limit(1))
            binding = previous.binding_json or {} if previous else {}
            old_plan = previous_plan(binding)
            if old_plan: original["current_task_plan"] = {k:v for k,v in old_plan.items() if k != "memory_id"}
        state.update(started=True, protocol_version=PROTOCOL)
        saved = {**saved,"payload":original}
        saved = persist(db,identity,turn_id,nonce,saved,state,"autonomous_running")
        db.rollback()  # Never hold DB row locks across model or tool HTTP waits.
        try:
            raw = await call(identity,body.household_id,"/agent/dialogue/run",
                {**original,"remaining_seconds":58},60)
            result = Result.model_validate(raw)
        except (ValueError,TypeError): execution.fail("AUTONOMOUS_AI_INVALID",503)
        if (result.request_id != body.request_id or result.original_text != body.text
                or result.context_revision != original["context"]["revision"]):
            execution.fail("AUTONOMOUS_AI_INVALID",503)
        if result.resolved:
            resolved=result.resolved.model_dump(mode="json")
            archive.validate_use(resolved["memory"],original)
            archive.validate_delta(resolved["memory_delta"],original,resolved["reply"])
        state["result"] = result.model_dump(mode="json")
        saved = persist(db,identity,turn_id,nonce,saved,state,"autonomous_resolved")
    result = Result.model_validate(state["result"])
    frame = frame_for(result)
    frame_attestation=original
    ctx=original["context"]
    revalidation_calls = 0
    try:
        plan = result.plan
        ctx = checked_context(db,identity,body,turn_id,nonce,original["context"],plan)
        can_revalidate=not (frame.get("error_code") and not result.verified_plans)
        needs_check = can_revalidate and plan and (recovering or frame.get("kind") in {"clarify","edit"}
            or (frame.get("result") or {}).get("status") in {"needs_confirmation","needs_clarification"}
            or plan.get("speech_act") in {"status","basis","correction","supplement"}
            or result.stop_reason == "context_refresh_required")
        if needs_check:
            # Revalidate all successful read plans on recovery, and the final
            # draft/task plan on a normal turn. No understanding/respond calls.
            candidates = result.verified_plans if recovering and result.verified_plans else [plan]
            checked = None
            fresh_archive=archive.build(db,identity,body.household_id,db.get(ConversationTurn,turn_id),ctx)
            revalidation_payload={**original,"context":ctx,"archive":fresh_archive}
            db.rollback()
            stop = time.monotonic()+min(10,max(.001,72-(time.monotonic()-start)))
            for planned in candidates:
                seconds = min(10,max(.001,stop-time.monotonic()))
                revalidation_calls += 1
                fresh = Resolution.model_validate(await call(identity,body.household_id,"/agent/dialogue/p85/resolve",
                    {**revalidation_payload,"plan":planned,"plan_context_revision":ctx["revision"],
                     "remaining_seconds":seconds},seconds)).model_dump(mode="json")
                if fresh["model_calls"] != 0 or fresh["original_text"] != body.text:
                    execution.fail("AUTONOMOUS_REVALIDATION_INVALID",503)
                archive.validate_use(fresh["memory"],revalidation_payload)
                archive.validate_delta(fresh["memory_delta"],revalidation_payload,fresh["reply"])
                project_intake(fresh)
                if fresh.get("error_code") or fresh["kind"] == "needs_input":
                    checked = fresh; break
                # Recovery is deterministic; old computed facts aren't replayed.
                if checked is None: checked = fresh
                else:
                    values=list(checked["facts"].values())+list(fresh["facts"].values())
                    checked={**fresh,"facts":{f"f{i}":v for i,v in enumerate(dict.fromkeys(values))},
                             "reply":"\n".join(dict.fromkeys(values)),"evidence":checked["evidence"]+fresh["evidence"]}
            if checked:
                before, after = frame.get("result") or {}, checked.get("result") or {}
                if before.get("draft") and routing.digest(before.get("draft")) != routing.digest(after.get("draft")):
                    checked = dict(kind="needs_input",reply="库存或原草稿已变化，请重新核对；尚未执行。",
                        error_code="INVENTORY_VERSION_CONFLICT",facts={},evidence=[],field_sources={},filled_fields=frame.get("filled_fields",{}))
                if frame.get("answers") and (frame.get("answers"),frame.get("task_revision")) != (checked.get("answers"),checked.get("task_revision")):
                    checked = dict(kind="needs_input",reply="原任务已更新，请重新核对。",error_code="TASK_REVISION_CONFLICT",
                        facts={},evidence=[],field_sources={},filled_fields=frame.get("filled_fields",{}))
                if recovering or checked.get("error_code") or plan.get("speech_act") in {"status","basis"} or result.stop_reason=="context_refresh_required":
                    frame = {**checked,"model_calls":result.model_calls}
                    frame_attestation=revalidation_payload
                    if frame.get("memory_delta"):
                        frame["memory_delta"]=copy.deepcopy(frame["memory_delta"])
                        frame["memory_delta"]["episode"]["reply"]=frame["reply"][:8000]
                else:
                    for key in ("result","answers","edit","task_revision","reference"):
                        if key in checked: frame[key]=checked[key]
        # Reacquire and recheck permissions/session after all network waits.
        routing.locked_turn(db,identity,turn_id,nonce)
    except (TimeoutError,httpx.HTTPError):
        execution.fail("AUTONOMOUS_REVALIDATION_UNAVAILABLE",503)
    except HTTPException as error:
        code=error.detail.get("code") if isinstance(error.detail,dict) else None
        if code not in {"REFERENCE_EXPIRED","REFERENCE_SOURCE_CHANGED","REFERENCE_TERMINAL","REFERENCE_NOT_FOUND",
            "CANDIDATES_CHANGED","TASK_REVISION_CONFLICT","TASK_SNAPSHOT_CHANGED","DRAFT_ALREADY_DECIDED",
            "DRAFT_EXPIRED","INVENTORY_VERSION_CONFLICT"}: raise
        db.rollback()
        routing.locked_turn(db,identity,turn_id,nonce)
        frame=dict(kind="needs_input",reply="原对象或任务已变化，请重新选择并核对；尚未执行。",
            error_code=code,model_calls=result.model_calls,field_sources={},filled_fields=result.filled_fields,
            evidence=[],preserve_active=True)
    frame["dialogue"] = dict(protocol_version=PROTOCOL,
        calls={"decision":result.model_calls,"response":0,"total":result.model_calls},
        recovery_model_calls=0 if recovering else None, fallback_used=result.fallback_used or recovering,
        field_sources=frame.get("field_sources",{}),stop_reason=result.stop_reason,status=result.status,
        tool_reads=result.tool_reads,elapsed_ms=(time.monotonic()-start)*1000,
        ai_elapsed_ms=result.elapsed_ms,revalidation_calls=revalidation_calls)
    if result.stop_reason=="context_refresh_required" and not frame.get("error_code"):
        pending=(frame.get("result") or {}).get("status")
        frame["dialogue"].update(status="needs_confirmation" if pending=="needs_confirmation" else
            "needs_input" if pending=="needs_clarification" or frame["kind"] in {"clarify","needs_input"} else "completed",
            stop_reason="confirmation_required" if pending=="needs_confirmation" else
            "user_input_required" if pending=="needs_clarification" or frame["kind"] in {"clarify","needs_input"} else "completed")
    if frame.get("error_code"):
        frame["dialogue"]["fallback_used"]=True
        if frame["error_code"]!=result.error_code:
            frame["dialogue"].update(status="needs_input",stop_reason="boundary")
    frame["dialogue"]["loop_stop_reason"]=frame["dialogue"]["stop_reason"]
    if frame["dialogue"]["status"]=="stopped":
        # Preserve the exact diagnostic separately; use already-supported UI
        # reasons so the current client need not change to display a safe stop.
        frame["dialogue"]["stop_reason"]={"deadline":"time_budget_exceeded","model_error":"ai_unavailable",
            "context_limit":"insufficient_information","no_progress":"insufficient_information",
            "repeated_plan":"insufficient_information"}.get(frame["dialogue"]["stop_reason"],frame["dialogue"]["stop_reason"])
    state["completed_at"] = gateway.now().isoformat()
    # The final frame can differ after a fresh task/status check. Keep its delta
    # and original attestation together for the shared atomic episode finalizer.
    state["resolved"] = copy.deepcopy(frame)
    state["resolution_payload"] = copy.deepcopy(frame_attestation)
    saved = persist(db,identity,turn_id,nonce,saved,state,"prepared")
    _, turn = routing.locked_turn(db,identity,turn_id,nonce)
    turn.resolution_json = frame
    db.commit()
    return frame, saved
