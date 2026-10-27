"""Additive session projection over existing receipts. No schema or business writes.

memory_v1 in binding_json is private metadata; response_json stores the immutable
accepted response. Business tasks/decisions/receipts remain their original owners.
"""
import asyncio
import json
from datetime import timedelta
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError

from app.conversation_models import ConversationTurn, ConversationBinding
from app.models import AITask, AIDraft, InventoryItem
from app.routers import agent_gateway as gateway
from app.services import conversation as routing
from app.services import draft_execution as execution
from app.memory_schemas import AIResolution

PROTOCOL = "conversation-memory-1"
KEY = "memory_v1"


def meta(turn):
    return (turn.binding_json or {}).get(KEY, {}) if turn else {}


def query(user_id, home):
    return select(ConversationTurn).where(ConversationTurn.user_id == user_id,
        ConversationTurn.household_id == home,
        ConversationTurn.binding_json[KEY]["protocol_version"].as_string() == PROTOCOL)


def head(db, identity, home):
    return db.scalar(query(identity.user.id, home).order_by(ConversationTurn.created_at.desc(), ConversationTurn.id.desc()).limit(1))


def checked_head(db, identity, body):
    execution.membership(db, identity.user.id, body.household_id, lock=True)
    value = head(db, identity, body.household_id)
    current = meta(value)
    if current.get("conversation_id") != str(body.conversation_id) or current.get("revision", 0) != body.conversation_revision:
        execution.fail("CONVERSATION_REVISION_CONFLICT")
    return value


def live_task(db, identity, home, task_id):
    if not task_id:
        return None
    task = routing.source_task(db, identity, UUID(str(task_id)), home)
    draft = db.scalar(select(AIDraft).where(AIDraft.task_id == task.id))
    state = execution.execution_status(db, identity, draft.id) if draft else None
    if state and state["status"] == "pending":
        command = draft.command_json or {}
        if command.get("batch_id"):
            item = db.get(InventoryItem, UUID(command["batch_id"]), populate_existing=True)
            if item is None or item.household_id != home or item.status != "ACTIVE" or item.version != command.get("expected_version"):
                state = {**state, "status": "conflict", "reason_code": "INVENTORY_VERSION_CONFLICT"}
    return {"task": gateway.response_for(db, task), "execution": state}


def cursor_for_write(db, identity, home):
    current = routing.cursor(db, identity.user.id)
    if current is not None and current.processing_nonce and current.lease_until and gateway.as_aware(current.lease_until) > gateway.now():
        execution.fail("CONVERSATION_PROCESSING")
    if current is None:
        current = ConversationBinding(user_id=identity.user.id, household_id=home, session_id=identity.session_id)
        db.add(current)
    if current.household_id != home or current.session_id != identity.session_id:
        current.household_id, current.session_id = home, identity.session_id
        current.task_id = current.reference_json = None
    return current


def in_window(turn):
    return gateway.as_aware(turn.created_at) > gateway.now()-timedelta(days=30)


def session_rows(db, identity, home, session_id, *, completed=False, limit=None):
    statement = query(identity.user.id, home).where(
        ConversationTurn.binding_json[KEY]["conversation_id"].as_string() == str(session_id),
        ConversationTurn.created_at > gateway.now()-timedelta(days=30))
    if completed:
        statement = statement.where(ConversationTurn.phase == "completed")
    statement = statement.order_by(ConversationTurn.created_at.desc(), ConversationTurn.id.desc())
    if limit:
        statement = statement.limit(limit)
    return list(db.scalars(statement))


def page(db, identity, home, cursor=None, limit=20):
    execution.membership(db, identity.user.id, home)
    latest = head(db, identity, home)
    info = meta(latest)
    if not latest:
        return dict(conversation_id=None, conversation_revision=0, household_id=home,
                    messages=[], requires_reset=True)
    statement = query(identity.user.id, home).where(
        ConversationTurn.binding_json[KEY]["conversation_id"].as_string() == info["conversation_id"],
        ConversationTurn.binding_json[KEY]["kind"].as_string() == "message",
        ConversationTurn.created_at > gateway.now()-timedelta(days=30))
    if cursor:
        anchor = db.get(ConversationTurn, cursor)
        if (anchor is None or anchor.user_id != identity.user.id or anchor.household_id != home
                or meta(anchor).get("conversation_id") != info["conversation_id"] or not in_window(anchor)):
            execution.fail("INVALID_HISTORY_CURSOR", 404)
        from sqlalchemy import or_, and_
        statement = statement.where(or_(ConversationTurn.created_at < anchor.created_at,
            and_(ConversationTurn.created_at == anchor.created_at, ConversationTurn.id < anchor.id)))
    rows = list(db.scalars(statement.order_by(ConversationTurn.created_at.desc(), ConversationTurn.id.desc()).limit(limit+1)))
    more = len(rows) > limit
    rows = rows[:limit]
    messages = []
    for row in reversed(rows):
        saved = row.response_json or {}
        messages.append(dict(request_id=row.request_id, original_text=row.original_text, created_at=row.created_at,
            phase=row.phase, reply=saved.get("reply", ""), task_id=str(row.task_id) if row.task_id else None,
            historical_status=(saved.get("task") or {}).get("status"), evidence=saved.get("evidence", [])))
    active = live_task(db, identity, home, info.get("active_task_id")) if in_window(latest) else None
    return dict(conversation_id=info["conversation_id"], conversation_revision=info["revision"],
                household_id=home, messages=messages, next_cursor=rows[-1].id if more else None, active_task=active)


def reset(db, identity, body, original_text=""):
    execution.membership(db, identity.user.id, body.household_id, lock=True)
    payload_hash = routing.digest({"reset": body.model_dump(mode="json"), "original_text": original_text})
    prior = db.scalar(select(ConversationTurn).where(ConversationTurn.user_id == identity.user.id,
        ConversationTurn.household_id == body.household_id, ConversationTurn.request_id == body.request_id))
    if prior:
        if prior.request_hash != payload_hash:
            execution.fail("REQUEST_ID_CONFLICT")
        if meta(head(db, identity, body.household_id)).get("conversation_id") != meta(prior).get("conversation_id"):
            execution.fail("CONVERSATION_SUPERSEDED")
        return final_response(db, identity, prior, prior.response_json)
    latest = head(db, identity, body.household_id)
    if latest:
        checked_head(db, identity, body)
    elif body.conversation_id is not None or body.conversation_revision != 0:
        execution.fail("CONVERSATION_REVISION_CONFLICT")
    current = cursor_for_write(db, identity, body.household_id)
    current.task_id = current.reference_json = current.processing_nonce = current.lease_until = None
    session_id = str(uuid4())
    response = dict(protocol_version=PROTOCOL, conversation_id=session_id, conversation_revision=0, current_conversation_revision=0,
        request_id=body.request_id, original_text=original_text, reply="已开始新会话。旧草稿没有被取消或执行。",
        kind="reset", model_calls=0, inventory_written=False)
    db.add(ConversationTurn(user_id=identity.user.id, household_id=body.household_id,
        request_id=body.request_id, request_hash=payload_hash, original_text=original_text,
        binding_json={KEY: {"protocol_version": PROTOCOL, "kind": "reset", "conversation_id": session_id,
                           "revision": 0, "active_task_id": None, "reference": None, "focus_task_id": None}},
        response_json=response, phase="completed", created_at=gateway.now()))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        execution.fail("CONCURRENT_DUPLICATE_REQUEST")
    return response


def task_evidence(db, identity, home, task_id, at):
    latest = live_task(db, identity, home, task_id)
    task, state = latest["task"], latest["execution"]
    result = task.get("result") or {}
    command = result.get("draft") or {}
    basis = []
    for row in result.get("recommendations") or []:
        basis += [str(reason) for reason in row.get("reason_codes", [])]
        unit = row.get("inventory_unit")
        if unit and all(row.get(key) is not None for key in ("current_stock", "pending_quantity", "target_stock")):
            basis.append(f"原建议计算时：登记库存{row['current_stock']} {unit}，已确认待购{row['pending_quantity']} {unit}，目标{row['target_stock']} {unit}；这些历史数值不是当前库存")
    basis += [str(reason) for reason in result.get("data_gaps") or []]
    if result.get("planning_basis"):
        basis.append("原任务保存了计算依据快照；数量和待购情况需重新读取后才能再次建议。")
    receipt = (state or {}).get("receipt") or {}
    return dict(task_id=task["task_id"], revision=task["revision"], status=task["status"],
        action=command.get("action"), missing_fields=result.get("missing_fields") or [], draft_id=task.get("draft_id"),
        operation_id=receipt.get("operation_id"), execution_status=(state or {}).get("status"),
        receipt_verified=bool(receipt.get("status") == "committed" and receipt.get("operation_id")
                              and receipt.get("draft_id") == task.get("draft_id")),
        basis=list(dict.fromkeys(basis))[:30], checked_at=at)


def context_for(db, identity, home, latest):
    info = meta(latest)
    at = gateway.now().isoformat()
    rows = session_rows(db, identity, home, info["conversation_id"], completed=True, limit=31)
    messages = [r for r in rows if meta(r).get("kind") == "message"]
    active_id = info.get("active_task_id") if in_window(latest) else None
    active = live_task(db, identity, home, active_id)
    history = [dict(request_id=r.request_id, text=r.original_text,
                    reply=(r.response_json or {}).get("reply", "")[:8000], created_at=gateway.as_aware(r.created_at).isoformat(),
                    task_id=str(r.task_id) if r.task_id else None) for r in reversed(messages[:10])]
    task_ids = list(dict.fromkeys([*([active_id] if active_id else []),
                                  *(str(r.task_id) for r in messages if r.task_id)]))[:20]
    tasks = [task_evidence(db, identity, home, item, at) for item in task_ids]
    reference = info.get("reference") if in_window(latest) else None
    reference_error = None
    # Validate scope/source/version now; expired refs are kept only for a clear expiry answer.
    if reference:
        try:
            routing.validate_reference(db, identity, home, reference)
        except HTTPException as error:
            reference_error = error.detail.get("code", "REFERENCE_REQUIRED") if isinstance(error.detail, dict) else "REFERENCE_REQUIRED"
            reference = None
    choices = []
    focus_id = info.get("focus_task_id") if in_window(latest) else None
    if focus_id:
        focus = routing.source_task(db, identity, UUID(focus_id), home)
        for item in routing.rows(focus):
            if any(r["batch_id"] == str(item["id"]) for r in choices):
                continue
            try:
                # Preserve the last displayed list order AND the old attestation
                # expiry when a follow-up query returned only its selected batch.
                choices.append(reference if reference and reference["batch_id"] == str(item["id"])
                               else routing.issue(db, identity, focus, str(item["id"])))
            except HTTPException:
                # Never shift a surviving ordinal into a deleted/expired row's slot.
                choices = []
                break
    return dict(protocol_version=PROTOCOL, scope={"user_id": str(identity.user.id), "household_id": str(home)},
        conversation_id=info["conversation_id"], revision=info["revision"], trusted_now=at, history=history,
        active={"scope": {"user_id": str(identity.user.id), "household_id": str(home)},
                "task": active["task"], "household_timezone": routing.source_task(db, identity, UUID(active_id), home).household_timezone} if active else None,
        reference=reference, reference_error=reference_error, choices=choices, tasks=tasks,
        truncated=len(messages)>10 or any(len((r.response_json or {}).get("reply", "")) > 8000 for r in messages[:10]))


async def understand(identity, home, payload):
    url, token = gateway.check_config()
    async with httpx.AsyncClient(timeout=9, trust_env=False, follow_redirects=False) as client:
        result = await client.post(url+"/agent/conversation-turn", json=payload, headers={
            "Authorization": "Bearer "+token, "X-User-Id": str(identity.user.id), "X-Household-Id": str(home)})
    if result.status_code != 200:
        execution.fail("MEMORY_AI_UNAVAILABLE", 503)
    try:
        data = AIResolution.model_validate(result.json()).model_dump(mode="json")
    except (ValueError, TypeError, ValidationError):
        execution.fail("MEMORY_AI_INVALID", 503)
    # Full AI schema is exported for teammates; backend independently validates the wire boundary.
    if (not isinstance(data, dict) or data.get("protocol_version") != PROTOCOL
            or data.get("kind") not in {"task", "clarify", "explain", "needs_input", "clear_reference"}
            or type(data.get("model_calls")) is not int or not 0 <= data["model_calls"] <= 1
            or data.get("original_text") != payload["text"] or not isinstance(data.get("reply"), str)):
        execution.fail("MEMORY_AI_INVALID", 503)
    known_tasks = {t["task_id"]: t["revision"] for t in payload["context"]["tasks"]}
    known_requests = {t["request_id"] for t in payload["context"]["history"]}
    for evidence in data["evidence"]:
        if "task_id" in evidence and known_tasks.get(evidence["task_id"]) != evidence.get("revision"):
            execution.fail("MEMORY_AI_INVALID", 503)
        if "request_id" in evidence and evidence["request_id"] not in known_requests:
            execution.fail("MEMORY_AI_INVALID", 503)
    return data


def final_response(db, identity, turn, response):
    value = dict(response)
    latest = head(db, identity, turn.household_id)
    value["current_conversation_revision"] = meta(latest)["revision"]
    value["active_task"] = live_task(db, identity, turn.household_id, meta(latest).get("active_task_id")) if in_window(latest) else None
    return value


def recover(db, identity, home, request_id):
    execution.membership(db, identity.user.id, home)
    turn = db.scalar(select(ConversationTurn).where(ConversationTurn.user_id == identity.user.id,
        ConversationTurn.household_id == home, ConversationTurn.request_id == request_id))
    if turn is None or not meta(turn) or not in_window(turn):
        execution.fail("CONVERSATION_TURN_NOT_FOUND", 404)
    if meta(head(db, identity, home)).get("conversation_id") != meta(turn).get("conversation_id"):
        execution.fail("CONVERSATION_SUPERSEDED")
    if turn.phase == "completed":
        return dict(phase="completed", request_id=request_id, original_text=turn.original_text,
                    response=final_response(db, identity, turn, turn.response_json))
    task = db.scalar(select(AITask).where(AITask.user_id == identity.user.id,
        AITask.household_id == home, AITask.request_id == request_id))
    active = live_task(db, identity, home, str(task.id) if task else meta(turn).get("active_task_id"))
    current = routing.cursor(db, identity.user.id)
    processing = bool(current and current.processing_nonce == turn.processing_nonce and current.processing_nonce
                      and current.lease_until and gateway.as_aware(current.lease_until) > gateway.now())
    return dict(phase="processing" if processing else "prepared" if turn.resolution_json else "result_unknown", request_id=request_id,
                original_text=turn.original_text, active_task=active,
                recovery_hint="以原请求ID和原请求体恢复；理解结果未知时不会再次调用模型。")


async def send(db, identity, body):
    from app.services import dialogue
    execution.membership(db, identity.user.id, body.household_id, lock=True)
    digest = routing.digest({"memory_message": body.model_dump(mode="json")})
    turn = db.scalar(select(ConversationTurn).where(ConversationTurn.user_id == identity.user.id,
        ConversationTurn.household_id == body.household_id, ConversationTurn.request_id == body.request_id))
    if turn:
        if turn.request_hash != digest:
            execution.fail("REQUEST_ID_CONFLICT")
        if meta(head(db, identity, body.household_id)).get("conversation_id") != str(body.conversation_id):
            execution.fail("CONVERSATION_SUPERSEDED")
        if turn.phase == "completed":
            if not in_window(turn): execution.fail("CONVERSATION_TURN_EXPIRED", 410)
            return final_response(db, identity, turn, turn.response_json)
        if not turn.resolution_json and not (turn.binding_json or {}).get(dialogue.KEY, {}).get("plan"):
            execution.fail("AI_OUTCOME_UNKNOWN")
        current = cursor_for_write(db, identity, body.household_id)
    else:
        latest = checked_head(db, identity, body)
        if latest.phase != "completed": execution.fail("CONVERSATION_OUTCOME_UNRESOLVED")
        current = cursor_for_write(db, identity, body.household_id)
        context = context_for(db, identity, body.household_id, latest)
        if body.task_id is not None:
            active = context.get("active")
            if not active or str(body.task_id) != active["task"]["task_id"] or body.revision != active["task"]["revision"]:
                execution.fail("TASK_REVISION_CONFLICT")
        from app.services.planning_facts import business_zone
        payload = dict(text=body.text, request_id=body.request_id, household_timezone=business_zone().key, context=context)
        info = {**meta(latest), "kind": "message", "revision": body.conversation_revision+1}
        turn = ConversationTurn(user_id=identity.user.id, household_id=body.household_id,
            request_id=body.request_id, request_hash=digest, original_text=body.text, created_at=gateway.now(),
            binding_json={KEY: info, "payload": payload}, phase="understanding")
        db.add(turn)
    recovering_dialogue = bool((turn.binding_json or {}).get(dialogue.KEY))
    use_dialogue = dialogue.enabled() or recovering_dialogue
    nonce = str(uuid4())
    current.processing_nonce = turn.processing_nonce = nonce
    current.lease_until = gateway.now()+timedelta(seconds=30)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        execution.fail("CONCURRENT_DUPLICATE_REQUEST")
    turn_id, saved = turn.id, turn.binding_json
    understood = turn.resolution_json
    db.rollback()
    try:
        if use_dialogue:
            understood, saved = await dialogue.run(db, identity, body, turn_id, nonce, saved, recovering=recovering_dialogue)
        if not use_dialogue and understood is not None and understood.get("kind") == "task" and understood.get("understanding"):
            # Recovery reuses semantic parsing, not stale computed inventory.
            # Replay is internal-only and cannot call a model.
            _, turn = routing.locked_turn(db, identity, turn_id, nonce)
            refreshed = {**saved["payload"], "context": context_for(db, identity, body.household_id, turn),
                         "replay": understood["understanding"]}
            paid_calls = understood["model_calls"]
            db.rollback()
            understood = await understand(identity, body.household_id, refreshed)
            if understood["model_calls"] != 0:
                execution.fail("MEMORY_REPLAY_CALLED_MODEL", 503)
            understood["model_calls"] = paid_calls
            _, turn = routing.locked_turn(db, identity, turn_id, nonce)
            saved = {**saved, "payload": refreshed}
            turn.binding_json = saved
            turn.resolution_json = understood
            db.commit()
        if understood is None:
            understood = await understand(identity, body.household_id, saved["payload"])
            _, turn = routing.locked_turn(db, identity, turn_id, nonce)
            turn.resolution_json = understood
            turn.phase = "prepared"
            db.commit()
        task = None
        kind = understood["kind"]
        if kind == "edit":
            dialogue.save_edit(db, identity, body, understood,
                lambda database, task: complete(database, identity, turn_id, nonce, understood, saved, task))
            turn = db.get(ConversationTurn, turn_id, populate_existing=True)
            return final_response(db, identity, turn, turn.response_json)
        if kind == "task":
            result = understood.get("result")
            if not isinstance(result, dict) or result.get("status") not in gateway.AI_STATES or result.get("original_text") != body.text:
                execution.fail("MEMORY_AI_INVALID", 503)
            reference = understood.get("reference")
            if reference:
                permitted = [*saved["payload"]["context"].get("choices", []), saved["payload"]["context"].get("reference")]
                def same(left, right):
                    if not right:
                        return False
                    if any(left.get(k) != right.get(k) for k in ("protocol_version", "scope", "source_task_id", "source_revision", "batch_id")):
                        return False
                    try:
                        return all(gateway.datetime.fromisoformat(left[k]) == gateway.datetime.fromisoformat(right[k])
                                   for k in ("issued_at", "expires_at"))
                    except (KeyError, TypeError, ValueError):
                        return False
                original_reference = next((r for r in permitted if same(reference, r)), None)
                if original_reference is None:
                    execution.fail("MEMORY_AI_INVALID_REFERENCE", 503)
                reference = original_reference
                understood = {**understood, "reference": reference}
                routing.validate_reference(db, identity, body.household_id, reference)
            # The existing gateway still reserves/saves task + draft. No second extraction.
            async def provided(): return result
            task_value = await gateway.run_message(gateway.NewMessage(household_id=body.household_id,
                text=body.text, request_id=body.request_id, household_timezone=saved["payload"]["household_timezone"]),
                identity, db, reference=reference, result_provider=provided,
                on_saved=lambda database, task: complete(database, identity, turn_id, nonce, understood, saved, task))
            turn = db.get(ConversationTurn, turn_id, populate_existing=True)
            return final_response(db, identity, turn, turn.response_json)
        elif kind == "clarify":
            active = saved["payload"]["context"].get("active")
            if not active: execution.fail("TASK_REFERENCE_REQUIRED")
            task = routing.source_task(db, identity, UUID(active["task"]["task_id"]), body.household_id,
                                       understood.get("task_revision"))
            answers = understood.get("answers") or {}
            allowed = set(((task.result_json or {}).get("clarification") or {}).get("allowed_fields") or [])
            if not answers or not set(answers) <= allowed & gateway.ALLOWED_ANSWERS:
                execution.fail("MEMORY_AI_INVALID", 503)
            routing.candidates_unchanged(db, task)
            if routing.digest(gateway.response_for(db, task)) != routing.digest(active["task"]):
                execution.fail("TASK_SNAPSHOT_CHANGED")
            task_value = await gateway.run_clarification(task.id,
                gateway.ContinueMessage(revision=understood["task_revision"], answers=answers), identity, db,
                on_saved=lambda database, task: complete(database, identity, turn_id, nonce, understood, saved, task))
            turn = db.get(ConversationTurn, turn_id, populate_existing=True)
            return final_response(db, identity, turn, turn.response_json)
        response = complete(db, identity, turn_id, nonce, understood, saved)
        db.commit()
        turn = db.get(ConversationTurn, turn_id, populate_existing=True)
        return final_response(db, identity, turn, response)
    except HTTPException as error:
        code = error.detail.get("code") if isinstance(error.detail, dict) else None
        if understood is None or code not in {"CANDIDATES_CHANGED", "TASK_REVISION_CONFLICT", "TASK_SNAPSHOT_CHANGED",
                "REFERENCE_EXPIRED", "REFERENCE_SOURCE_CHANGED", "REFERENCE_TERMINAL", "REFERENCE_NOT_FOUND",
                "DRAFT_ALREADY_DECIDED", "DRAFT_EXPIRED", "INVENTORY_VERSION_CONFLICT", "PROTECTED_OR_UNKNOWN_FIELD", "INVALID_DRAFT_FIELDS"}:
            raise
        db.rollback()
        # A known stale-read conflict is a completed clarification outcome, not an
        # unknown paid extraction that would permanently block the conversation.
        conflict = dict(kind="needs_input", reply="库存或原任务已经变化，请重新查询并核对；尚未执行。",
                        model_calls=understood["model_calls"], error_code=code, dialogue=understood.get("dialogue"))
        response = complete(db, identity, turn_id, nonce, conflict, saved)
        db.commit()
        turn = db.get(ConversationTurn, turn_id, populate_existing=True)
        return final_response(db, identity, turn, response)
    finally:
        db.rollback()
        current = routing.cursor(db, identity.user.id)
        if current and current.processing_nonce == nonce:
            current.processing_nonce = current.lease_until = None
            db.commit()


def complete(db, identity, turn_id, nonce, understood, saved, task=None):
    """Used as gateway on_saved: turn, task and draft finalize atomically."""
    current, turn = routing.locked_turn(db, identity, turn_id, nonce)
    info, kind = dict(meta(turn)), understood["kind"]
    if kind == "clear_reference":
        info.update(active_task_id=None, reference=None, focus_task_id=None)
    elif task is not None:
        if not understood.get("preserve_active") or not info.get("active_task_id"):
            info["active_task_id"] = str(task.id)
        reference = understood.get("reference")
        if kind == "clarify":
            selected = understood["answers"].get("batch_id")
            reference = routing.issue(db, identity, task, selected) if selected else saved["payload"]["context"].get("reference")
            if reference and reference["source_task_id"] == str(task.id):
                reference = {**reference, "source_revision": task.revision}
        elif reference is None:
            reference = routing.issue(db, identity, task) if task.status == "answered" else None
        info["reference"] = reference
        info["focus_task_id"] = str(task.id)
        turn.task_id = task.id
    current.task_id = UUID(info["active_task_id"]) if info.get("active_task_id") else None
    current.reference_json = info.get("reference")
    current.processing_nonce = current.lease_until = turn.processing_nonce = None
    turn.binding_json = {**saved, KEY: info}
    turn.phase = "completed"
    response = dict(protocol_version=PROTOCOL, conversation_id=info["conversation_id"],
        conversation_revision=info["revision"], request_id=turn.request_id, original_text=turn.original_text,
        reply=understood["reply"] if understood.get("dialogue") else (task.result_json or {}).get("reply", understood["reply"]) if task else understood["reply"],
        kind=kind, task=gateway.response_for(db, task) if task else None,
        filled_fields=understood.get("filled_fields", {}),
        evidence=understood.get("evidence", []), model_calls=understood["model_calls"],
        truncated=understood.get("truncated", False), error_code=understood.get("error_code"), inventory_written=False)
    turn.response_json = response
    if understood.get("dialogue"):
        response["dialogue"] = understood["dialogue"]
    db.flush()
    return response
