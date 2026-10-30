"""Request-local memory orchestration; history supplies identity, never live stock."""
import asyncio
import json
import re

from p0.domain import DomainError
from p0.engines import EngineError
from p0.text import number
from p1.domain import guard, ground
from interaction.policy import review_reason
from p3.schemas import Parsed
from .chat_text import quick_response
from .manager import Manager, Operation, LOCATION_REFERENCE, PRONOUN
from .replies import resolve_reply
from .schemas import Message
from .memory_schemas import MAX_CONTEXT_BYTES, TurnRequest, TurnResult, Understanding
from v1.render import REASONS
from .engines import MEMORY_PROMPT_VERSION

STATUS = re.compile(r"(?:执行了吗|完成了吗|做完了吗|成功了吗|现在什么状态|任务状态|为什么(?:还)?没(?:有)?(?:移动|执行|完成)|(?:刚才|之前|那|这|它).*(?:执行|完成|成功|状态).*(?:吗|了|怎样|如何|什么)|还需要我做什么)[？?。]?")
BASIS = re.compile(r"(?:为什么(?:这样|这么)?建议.*|(?:这个|刚才的|之前的|这次)?建议(?:的)?依据.*|依据是什么)[？?。]?")
RECALL = re.compile(r"(?:刚才|之前|我们刚才).*(?:聊了|说了|讨论|提到).*[？?。]?")
ORDINAL = re.compile(r"(?:选|选择|就)?第([一二两三四五六七八九十0-9]+)(?:个|批|件|份)(?:(?:的)?(?:在哪里|在哪儿|在哪|在什么地方|还有多少))?[？?。]?")
START_TASK = {"开始新任务", "新任务", "重新开始"}

STATE_TEXT = {
    "needs_clarification": "还需要补充信息，尚未执行。",
    "needs_confirmation": "已生成待确认草稿，尚未执行，需要你核对并确认。",
    "processing": "任务仍在处理中，请先核实原请求，不要重复提交。",
    "pending": "草稿待确认，尚未执行。",
    "cancelled": "这份草稿已取消，没有因取消而改变库存。",
    "expired": "草稿已过期，尚无可核实的成功执行回执，请重新核对。",
    "superseded": "原草稿已失效或被替代，请核对最新任务。",
    "conflict": "库存或草稿版本发生冲突，需要重新核对。",
    "unavailable": "当前业务能力暂不可执行这项草稿。",
    "answered": "这项查询已经回答；查询本身不会修改库存。",
    "error": "任务处理失败，请核实原任务或手动处理。",
    "unsupported": "这项请求暂不支持，尚未执行。",
    "unknown": "结果待核实，暂时不能确认操作已经成功。",
}


def basis_text(items):
    labels = {**REASONS, "HUMAN_RULE_REVIEW_REQUIRED":"平台缺少适用的人工审核规则，建议仍需核对",
              "EXISTING_STOCK_AND_PENDING_COVER_TARGET":"登记库存和已确认待购已覆盖目标",
              "BATCH_PLANNING_SCOPE_UNAVAILABLE":"暂时缺少该批次对应的统计资料"}
    return "；".join(labels.get(item, "部分计算资料需要核对" if re.fullmatch(r"[A-Z][A-Z0-9_]+", item) else item)
                    for item in items)


def bounded_context(context):
    context = context.model_copy(deep=True)
    while len(context.model_dump_json().encode()) > MAX_CONTEXT_BYTES and context.history:
        context.history.pop(0)
        context.truncated = True
    if len(context.model_dump_json().encode()) > MAX_CONTEXT_BYTES:
        raise DomainError("MEMORY_CONTEXT_TOO_LARGE", "必要任务信息过大，请进入原任务选择批次或手动处理。", 422)
    return context


class ReplayEngine:
    """Only returns the one already-understood request, never invokes a provider."""
    def __init__(self, parsed): self.parsed = parsed
    async def extract(self, text): return self.parsed.model_copy(deep=True)


class MemoryOperation(Operation):
    allow_implicit_reference = True


class MemoryManager(Manager):
    def operation(self): return MemoryOperation(self)


def explain_state(evidence):
    state = evidence.execution_status or evidence.status
    if state == "committed":
        if not evidence.receipt_verified or evidence.operation_id is None:
            return STATE_TEXT["unknown"]
        if evidence.action == "PLAN_ADD":
            return "已加入待购清单；尚未购买或入库。"
        return "已由正式业务接口执行成功，执行回执已核实。当前库存请重新查询。"
    return STATE_TEXT.get(state, STATE_TEXT["unknown"])


async def handle_turn(owner, body: TurnRequest, scope, metrics=None):
    metrics = metrics if metrics is not None else {"calls": 0}
    if body.context.scope != scope:
        raise DomainError("HOUSEHOLD_FORBIDDEN", "会话不属于当前用户或家庭。", 403)
    context = bounded_context(body.context)
    now = owner.now()
    if abs((now-context.trusted_now).total_seconds()) > 30:
        raise DomainError("MEMORY_SNAPSHOT_EXPIRED", "请重新读取会话与任务状态。", 409)
    calls = 0

    def response(kind, reply, **kwargs):
        return TurnResult(kind=kind, original_text=body.text, reply=reply, model_calls=calls,
                          truncated=context.truncated, filled_fields=metrics.get("filled_fields", {}), **kwargs)

    text = body.text.strip().rstrip("。！？?! ")
    if guard(body.text) or (review_reason(body.text) and not STATUS.fullmatch(text)):
        return response("needs_input", "请直接描述家庭库存任务，不能通过聊天绕过权限或确认。", preserve_active=True,
                        error_code="INVALID_CONVERSATION_INPUT")
    if text in START_TASK:
        return response("clear_reference", "已开始新任务，之前的草稿没有被取消或执行。")
    if quick := quick_response(text):
        return response("explain", quick[1], preserve_active=True)
    if body.replay:
        understood = body.replay.model_copy(deep=True)
    elif STATUS.fullmatch(text):
        understood = Understanding(kind="status")
    elif BASIS.fullmatch(text):
        understood = Understanding(kind="basis")
    elif RECALL.fullmatch(text):
        understood = Understanding(kind="recall")
    else:
        if context.active and context.active.task.status == "needs_clarification":
            routing = resolve_reply(context.active, body.text, scope, context.trusted_now,
                                    selected_batch_id=context.reference.batch_id if context.reference else None)
            if routing.kind == "clarify":
                return response("clarify", "继续原任务，尚未执行。", answers=routing.answers,
                                task_revision=routing.revision, reference=context.reference)
            if routing.kind == "needs_input":
                return response("needs_input", "请补充当前允许的字段或重新选择批次。", preserve_active=True,
                                error_code=routing.error_code)
        ordinal = ORDINAL.fullmatch(text)
        if ordinal:
            value = number(ordinal[1])
            if value is None or value != int(value) or not 1 <= value <= len(context.choices):
                return response("needs_input", "请从当前显示的候选中明确选择一个批次。", preserve_active=True,
                                error_code="INVALID_CANDIDATE")
            understood = Understanding(parsed=Parsed(intent="QUERY_INVENTORY" if "多少" in text else "QUERY_LOCATION"),
                                       reference_index=int(value)-1)
        elif LOCATION_REFERENCE.fullmatch(text):
            understood = Understanding(parsed=Parsed(intent="QUERY_LOCATION"))
        elif re.fullmatch(r"(?:它|这一批|这批|这个)(?:还有多少|剩多少|的数量)", text):
            understood = Understanding(parsed=Parsed(intent="QUERY_INVENTORY"))
        else:
            # The provider sees separate original text/history. No name substitution.
            calls = 1
            metrics["calls"] = 1
            understood = await owner.engine.understand_turn(body.text, context)

    if understood.kind in {"status", "basis"}:
        evidence = next((t for t in context.tasks if t.task_id == understood.task_id), None) if understood.task_id else next(
            (t for t in context.tasks if context.active and t.task_id == context.active.task.task_id), None)
        if understood.kind == "status" and understood.task_id is None:
            mentions = [action for action, pattern in {"MOVE":"移动|移到", "OPEN":"开封", "DISCARD":"丢弃",
                        "CONSUME":"消耗", "PLAN_ADD":"待购|采购", "ADD":"新增|入库"}.items() if re.search(pattern, text)]
            if len(mentions) == 1:
                evidence = next((t for t in context.tasks if t.action == mentions[0]), None)
        if understood.kind == "basis" and understood.task_id is None:
            evidence = next((t for t in context.tasks if t.basis), evidence)
        if evidence is None:
            return response("needs_input", "无法可靠定位要核实的任务，请选择原任务。", preserve_active=True,
                            error_code="TASK_REFERENCE_REQUIRED")
        reply = explain_state(evidence) if understood.kind == "status" else (
            "这项建议的已记录依据：" + basis_text(evidence.basis) if evidence.basis else "原任务没有保存足够的建议依据，无法可靠解释。")
        return response("explain", reply, preserve_active=True,
                        evidence=[{"task_id": str(evidence.task_id), "revision": evidence.revision,
                                   "checked_at": evidence.checked_at.isoformat(),
                                   "kind": "execution_read" if understood.kind == "status" else "recorded_basis"}])
    if understood.kind == "recall":
        if not context.history:
            return response("needs_input", "当前没有可可靠回顾的对话，请提供物品名称或选择原任务。", preserve_active=True)
        return response("explain", "最近的库存对话：" + "；".join(t.text for t in context.history[-3:]) +
                        "。以上是历史讨论，不能代表当前库存或执行结果。", preserve_active=True,
                        evidence=[{"request_id": t.request_id, "kind": "historical_message"} for t in context.history[-3:]])
    if understood.kind == "needs_input" or understood.parsed is None:
        return response("needs_input", "请明确要查询的物品或原任务，我暂时无法可靠承接。", preserve_active=True)

    parsed = understood.parsed
    grounded = ground(parsed, body.text)
    metrics["filled_fields"] = {field: str(getattr(grounded, field)) for field in (
        "name", "quantity", "unit", "location", "to_location", "opened_at", "purchased_at", "label_expiry")
        if getattr(grounded, field, None) is not None and getattr(grounded, field) not in {"它", "这批", "这一批", "这个"}}
    reference = context.reference
    if understood.reference_index is not None:
        if understood.reference_index >= len(context.choices):
            return response("needs_input", "请选择当前候选中的真实批次。", preserve_active=True, error_code="INVALID_CANDIDATE")
        reference = context.choices[understood.reference_index]
    # A historical name never becomes literal evidence for a new operation.
    if parsed.name and parsed.name.casefold() not in body.text.casefold():
        parsed = parsed.model_copy(update={"name": None})
    if parsed.name and parsed.name not in {"它", "这批", "这一批", "这个"}:
        reference = None
    elif context.reference_error:
        return response("needs_input", "之前选择的对象已失效、变化或过期，请重新查询或选择批次。",
                        preserve_active=True, error_code=context.reference_error)
    if reference and not reference.issued_at <= context.trusted_now < reference.expires_at:
        return response("needs_input", "之前的对象引用已过期，请重新查询或选择批次。", preserve_active=True,
                        error_code="REFERENCE_EXPIRED")
    local = MemoryManager(ReplayEngine(parsed), owner.reader, owner.catalog, now=owner.now,
                          timeout_seconds=owner.timeout_seconds, max_stock_age_hours=owner.max_stock_age_hours)
    result = await local.handle(Message(text=body.text, request_id=body.request_id,
                                       household_timezone=body.household_timezone, reference=reference), scope)
    if result.error_code in {"REFERENCE_EXPIRED", "REFERENCE_NOT_FOUND", "REFERENCE_TERMINAL"}:
        return response("needs_input", result.reply, preserve_active=True, error_code=result.error_code)
    if result.runtime:
        result.runtime.model_calls = calls
        result.runtime.prompt_version = MEMORY_PROMPT_VERSION
        result.runtime.model = getattr(owner.engine, "last_model", None) if calls else None
    if result.decisions and calls and hasattr(owner.engine, "budget"):
        result.decisions[0].source = "llm"
    return response("task", result.reply, result=result, reference=reference, understanding=understood)


async def safe_turn(owner, body, scope):
    metrics = {"calls": 0}
    try:
        async with asyncio.timeout(owner.timeout_seconds):
            return await handle_turn(owner, body, scope, metrics)
    except (TimeoutError, EngineError) as error:
        code = getattr(error, "code", "AGENT_TIMEOUT")
        return TurnResult(kind="needs_input", original_text=body.text,
                          reply="本次理解未完成，原文和已填字段已保留。请核实原请求，系统不会自动重试模型。",
                          model_calls=metrics["calls"], filled_fields=metrics.get("filled_fields", {}), preserve_active=True, error_code=code)
    except DomainError as error:
        if error.status == 403:
            raise
        return TurnResult(kind="needs_input", original_text=body.text, reply=error.message,
                          model_calls=metrics["calls"], filled_fields=metrics.get("filled_fields", {}), preserve_active=True, error_code=error.code)


def install(app, manager, scope):
    from fastapi import Depends
    from p0.schemas import Scope
    @app.post("/agent/conversation-turn", response_model=TurnResult)
    async def conversation_turn(body: TurnRequest, identity: Scope = Depends(scope)):
        return await safe_turn(manager, body, identity)
