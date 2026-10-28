"""Pure reducer for trusted caller-owned input state; no server session store.

Android must implement the equivalent transitions in its own lifecycle owner.
These functions are executable contract/reference code, not device integration.
"""
import hashlib
import json
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, model_validator
from p0.domain import DomainError
from p0.schemas import Model, Scope
from p1.schemas import Message as BaseMessage
from .schemas import InputProvenance, Message


class Session(Model):
    scope: Scope
    source: Literal["text","voice","manual_fallback"]
    id: str = Field(min_length=1,max_length=100)
    phase: Literal["idle","recognizing","editing","reviewed","submitted","cancelled"] = "idle"
    recognition_id: str | None = None
    raw_transcript: str = ""
    final_text: str = ""
    transcript_revision: int = Field(default=1,ge=1)
    user_edited: bool = False
    request_id: str | None = None
    submitted_fingerprint: str | None = None
    submitted_message: Message | None = None
    task_id: str | None = None


def new_session(scope, source="voice"):
    return Session(scope=scope,source=source,id="input-"+uuid4().hex)


def begin_recognition(state):
    if state.phase in {"submitted","cancelled"}:
        raise DomainError("NEW_SESSION_REQUIRED","已提交或取消的输入请创建新会话。",409)
    result = state.model_copy(deep=True)
    result.source = "voice"
    result.phase, result.recognition_id = "recognizing", "recognition-"+uuid4().hex
    result.transcript_revision += 1
    return result


def recognition_result(state, recognition_id, text):
    if state.phase != "recognizing" or state.recognition_id != recognition_id:
        return state.model_copy(deep=True)  # Late/duplicate result is inert.
    if not isinstance(text,str):
        raise DomainError("INVALID_RECOGNITION","识别结果必须是文字。")
    if len(text)>1000:
        raise DomainError("INPUT_TOO_LONG","识别文字超过长度，请缩短后提交。")
    result = state.model_copy(deep=True)
    result.raw_transcript = text
    result.final_text = text
    result.phase, result.recognition_id = "editing", None
    result.user_edited = False
    return result


def recognition_failed(state, recognition_id):
    if state.phase != "recognizing" or state.recognition_id != recognition_id:
        return state.model_copy(deep=True)
    result = state.model_copy(deep=True)
    result.phase, result.recognition_id, result.source = "editing", None, "manual_fallback"
    return result


def edit(state, text):
    if state.phase in {"submitted","cancelled"}:
        raise DomainError("NEW_SESSION_REQUIRED","修改已提交文字须新建请求，旧草稿不能继续使用。",409)
    if len(text)>1000:
        raise DomainError("INPUT_TOO_LONG","文字超过长度，请缩短后提交。")
    result = state.model_copy(deep=True)
    result.final_text, result.phase, result.recognition_id = text, "editing", None
    result.transcript_revision += 1
    result.user_edited = text != result.raw_transcript
    return result


def cancel(state):
    result = state.model_copy(deep=True)
    result.phase, result.recognition_id = "cancelled", None
    return result


def confirm_text(state):
    if state.phase != "editing" or not state.final_text.strip():
        raise DomainError("INPUT_NOT_REVIEWED","请先核对非空识别文字。")
    result = state.model_copy(deep=True)
    result.phase = "reviewed"
    return result


def submission(state, *, household_timezone="Asia/Shanghai", reminder_days=3):
    # No UUID on transport retries: same reviewed content => same body/key.
    if state.phase == "submitted":
        _check_submission(state)
        body = state.submitted_message
        if body is None or household_timezone != body.household_timezone or reminder_days != body.reminder_days:
            raise DomainError("SUBMISSION_CONFLICT","恢复请求不能修改已提交字段。",409)
        if state.final_text != body.text:
            raise DomainError("SUBMISSION_CONFLICT","已提交文字已改变，请新建请求。",409)
        return state.model_copy(deep=True), body.model_copy(deep=True)
    if state.phase != "reviewed":
        raise DomainError("INPUT_NOT_REVIEWED","请先核对识别文字。")
    result = state.model_copy(deep=True)
    body = Message(text=result.final_text,request_id="message-"+uuid4().hex,
        household_timezone=household_timezone,reminder_days=reminder_days,
        input=InputProvenance(source=result.source,input_session_id=result.id,
            transcript_revision=result.transcript_revision,user_confirmed=True,user_edited=result.user_edited))
    result.phase, result.request_id, result.submitted_message = "submitted", body.request_id, body
    result.submitted_fingerprint = _fingerprint(result)
    return result, body


def recovery(state):
    if state.phase != "submitted" or state.submitted_message is None:
        return "no_task"
    _check_submission(state)
    return "get_task" if state.task_id else "explicit_same_key_replay"


def public_message(state):
    if state.phase != "submitted" or state.submitted_message is None:
        raise DomainError("INPUT_NOT_REVIEWED","尚无已确认提交。")
    _check_submission(state)
    # v0.6 body: provenance stays caller-owned until backend opts into it.
    try:
        household = str(UUID(state.scope.household_id))
    except ValueError:
        raise DomainError("INVALID_HOUSEHOLD","正式家庭身份必须为有效UUID。") from None
    body = state.submitted_message
    return {"household_id":household,"text":body.text,"request_id":body.request_id,
            "household_timezone":body.household_timezone}


def _fingerprint(state):
    value={"scope":state.scope.model_dump(),"message":state.submitted_message.model_dump(mode="json")}
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()


def _check_submission(state):
    body=state.submitted_message
    if (body is None or state.request_id!=body.request_id or state.final_text!=body.text
        or state.submitted_fingerprint!=_fingerprint(state)
        or body.input.input_session_id!=state.id or body.input.transcript_revision!=state.transcript_revision
        or body.input.source!=state.source or body.input.user_edited!=state.user_edited):
        raise DomainError("SUBMISSION_CONFLICT","恢复状态与已确认请求不一致，请重新核对。",409)


def bind_task(state, task):
    _check_submission(state)
    if str(task.household_id)!=state.scope.household_id or (task.result and task.result.original_text!=state.final_text):
        raise DomainError("TASK_CONFLICT","任务不属于这份已提交文字或家庭。",409)
    if state.task_id and state.task_id!=str(task.task_id):
        raise DomainError("TASK_CONFLICT","恢复时不能替换已有任务。",409)
    result=state.model_copy(deep=True)
    result.task_id=str(task.task_id)
    return result
