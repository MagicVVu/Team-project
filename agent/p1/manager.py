import asyncio
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from p0.domain import DomainError, new_id
from p0.engines import EngineError
from p0.schemas import Scope
from .domain import TARGET_ACTIONS, guard, ground, make_draft, missing_fields
from .schemas import (AgentResult, ClarificationContext, ClarificationRequest, Intent,
                      Message, Parsed, TraceStep)
from .tools import check_scope


class Manager:
    def __init__(self, engine, reader, *, now=None, timeout_seconds=10):
        self.engine, self.reader = engine, reader
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.timeout_seconds = timeout_seconds

    def _context(self, message: Message, scope: Scope, trace_id: str, parsed: Parsed):
        now = self.now()
        return ClarificationContext(id=new_id("clarify"), revision=1, scope=scope,
            original_text=message.text, request_id=message.request_id, trace_id=trace_id,
            household_timezone=message.household_timezone, created_at=now,
            expires_at=now + timedelta(minutes=15), parsed=parsed)

    def _result(self, context, status, reply, **kwargs):
        return AgentResult(status=status, reply=reply, trace_id=context.trace_id,
                           original_text=context.original_text, intent=context.parsed.intent, **kwargs)

    def _clarify(self, context, fields, reply, code=None):
        fields = list(dict.fromkeys(fields))
        context = context.model_copy(deep=True, update={"allowed_fields": fields})
        return self._result(context, "needs_clarification", reply, candidates=context.candidates,
            missing_fields=fields, clarification=context, error_code=code, manual_entry=True)

    async def _resolve(self, context, scope, trace):
        parsed = context.parsed
        today = self.now().astimezone(ZoneInfo(context.household_timezone)).date()
        missing, dates = missing_fields(parsed, context.created_at, context.household_timezone, today)
        batch = None
        if parsed.intent in {Intent.QUERY_INVENTORY, Intent.QUERY_LOCATION} and "name" in missing:
            return self._clarify(context, ["name"], "请明确要查询的物品名称；尚未写入。")
        if parsed.name and (parsed.intent in TARGET_ACTIONS or parsed.intent in {Intent.QUERY_INVENTORY, Intent.QUERY_LOCATION}):
            start = time.perf_counter()
            if context.selected_batch_id:
                previous = next((b for b in context.candidates if b.id == context.selected_batch_id), None)
                if previous is None:
                    raise DomainError("INVALID_CANDIDATE", "只能选择当前候选中的批次。")
                batch = await self.reader.get_batch(scope, context.selected_batch_id)
                check_scope(scope, [batch])
                if batch.id != previous.id:
                    raise DomainError("TOOL_UNAVAILABLE", "库存工具返回错误批次。", 503)
                if batch != previous:
                    context.candidates = [batch]
                    context.selected_batch_id = None
                    return self._clarify(context, missing + ["batch_id"], "库存已变化，请核对当前批次后重新选择；尚未写入。", "VERSION_CONFLICT")
                candidates = [batch]
            else:
                candidates = await self.reader.search(scope, parsed.name)
                check_scope(scope, candidates)
                candidates = [b for b in candidates if parsed.name.casefold() in b.name.casefold()]
                exact = [b for b in candidates if b.name.casefold() == parsed.name.casefold()]
                if exact:
                    candidates = exact
            trace.append(TraceStep(step="inventory_read", outcome="ok", elapsed_ms=(time.perf_counter()-start)*1000))
            context.candidates = candidates
            if parsed.intent in {Intent.QUERY_INVENTORY, Intent.QUERY_LOCATION}:
                summary = "；".join(f"{b.name}：{b.quantity} {b.unit}，位置 {b.location or '待定位'}，开封 {b.opened_at or '未知'}，状态 {b.status}（批次 {b.id}）" for b in candidates)
                return self._result(context, "answered", summary or "没有找到匹配的库存记录。", facts=candidates)
            if len(candidates) != 1:
                if candidates:
                    return self._clarify(context, missing + ["batch_id"], "请选择目标批次并补充缺失字段；尚未写入。")
                context.selected_batch_id = None
                return self._clarify(context, missing + ["name"], "没有找到匹配批次，请核对物品名称。", "BATCH_NOT_FOUND")
            batch = candidates[0]
            if batch.status != "ACTIVE" or batch.quantity <= 0:
                return self._result(context, "answered", "该批次已结束或无库存，不产生新变更。", facts=[batch], error_code="BATCH_TERMINAL")
            # No-op checks need only a uniquely identified current batch.
            if parsed.intent == Intent.OPEN and batch.opened_at:
                return self._result(context, "answered", f"该批次已于 {batch.opened_at} 开封，无需重复记录。", facts=[batch])
            if parsed.intent == Intent.MOVE and parsed.to_location and batch.location == parsed.to_location.strip():
                return self._result(context, "answered", "该批次已在目标位置，无需移动。", facts=[batch])
            if "batch_id" in context.allowed_fields and not context.selected_batch_id:
                return self._clarify(context, missing + ["batch_id"], "请明确选择已重新展示的批次；尚未写入。")
            context.selected_batch_id = batch.id
        elif parsed.intent == Intent.QUERY_INVENTORY and not parsed.name:
            start = time.perf_counter()
            facts = check_scope(scope, await self.reader.search(scope, None))
            trace.append(TraceStep(step="inventory_read", outcome="ok", elapsed_ms=(time.perf_counter()-start)*1000))
            summary = "；".join(f"{b.name}：{b.quantity} {b.unit}，{b.location or '待定位'}，开封 {b.opened_at or '未知'}，状态 {b.status}" for b in facts)
            return self._result(context, "answered", summary or "当前没有库存记录。", facts=facts)
        if missing:
            return self._clarify(context, missing, "请补充或核对：" + "、".join(missing) + "。尚未写入。")
        try:
            draft, preview = make_draft(parsed, batch, dates)
        except DomainError as error:
            fields = ["unit"] if error.code == "INVALID_UNIT" else ["quantity"]
            return self._clarify(context, fields, error.message, error.code)
        except (ValidationError, ValueError):
            return self._clarify(context, ["quantity"], "数量或换算精度无效，请核对。", "VALIDATION_ERROR")
        trace.append(TraceStep(step="validation", outcome="needs_confirmation", elapsed_ms=0))
        return self._result(context, "needs_confirmation", "草稿已生成，尚未写入。请核对目标批次与变更内容后确认。", draft=draft, preview=preview)

    def _failure(self, text, trace_id, error, context=None):
        code = error.code if isinstance(error, (DomainError, EngineError)) else "AGENT_TIMEOUT"
        reply = error.message if isinstance(error, DomainError) else "AI 暂时无法处理，输入和已补字段已保留。请重试或手动填写。"
        if code == "HOUSEHOLD_FORBIDDEN":
            return AgentResult(status="error", reply=reply, trace_id=trace_id, original_text=text,
                               error_code=code, manual_entry=True)
        return AgentResult(status="error", reply=reply, trace_id=trace_id, original_text=text,
            intent=context.parsed.intent if context else None, clarification=context,
            candidates=context.candidates if context else [], error_code=code, manual_entry=True,
            retryable=code in {"AGENT_TIMEOUT", "MODEL_TIMEOUT", "MODEL_UNAVAILABLE", "TOOL_UNAVAILABLE"})

    async def handle(self, message: Message, scope: Scope):
        trace_id, trace = new_id("trace"), []
        context = None
        start = time.perf_counter()
        try:
            async with asyncio.timeout(self.timeout_seconds):
                reason = guard(message.text)
                if reason:
                    result = AgentResult(status="unsupported", intent=Intent.UNSUPPORTED, reply=reason,
                                         trace_id=trace_id, original_text=message.text)
                    trace.append(TraceStep(step="guard", outcome="rejected", elapsed_ms=0))
                else:
                    parsed = await self.engine.extract(message.text)
                    trace.append(TraceStep(step="extraction", outcome=parsed.intent.value, elapsed_ms=(time.perf_counter()-start)*1000))
                    context = self._context(message, scope, trace_id, parsed)
                    reason = guard(message.text, parsed)
                    if reason:
                        result = self._result(context, "unsupported", reason)
                        result.intent = Intent.UNSUPPORTED
                    else:
                        context.parsed = ground(parsed, message.text)
                        result = await self._resolve(context, scope, trace)
        except (DomainError, EngineError, TimeoutError) as error:
            result = self._failure(message.text, trace_id, error, context)
        trace.append(TraceStep(step="total", outcome=result.status, elapsed_ms=(time.perf_counter()-start)*1000))
        result.trace = trace
        return result

    async def clarify(self, request: ClarificationRequest, scope: Scope):
        context = request.context.model_copy(deep=True)
        trace, start = [], time.perf_counter()
        try:
            async with asyncio.timeout(self.timeout_seconds):
                if context.scope != scope:
                    # Never return another identity's original text/context/candidates.
                    return AgentResult(status="error", reply="澄清任务不属于当前用户或家庭。", trace_id=new_id("trace"),
                                       original_text="", error_code="HOUSEHOLD_FORBIDDEN")
                if request.revision != context.revision:
                    raise DomainError("CLARIFICATION_CONFLICT", "澄清修订号已变化，请读取最新任务。", 409)
                if context.expires_at <= self.now() or context.created_at > self.now() or context.expires_at <= context.created_at:
                    raise DomainError("CLARIFICATION_EXPIRED", "澄清任务已过期，请重新提交原文。", 409)
                check_scope(scope, context.candidates)
                # Validate a stored timezone too; do not rely on arbitrary JSON.
                ZoneInfo(context.household_timezone)
                values = request.answers.model_dump(exclude_unset=True, exclude_none=True)
                if not values or any(field not in context.allowed_fields for field in values):
                    raise DomainError("INVALID_CLARIFICATION", "只能补充当前缺失字段或选择候选批次。")
                if "batch_id" in values:
                    if values["batch_id"] not in {b.id for b in context.candidates}:
                        raise DomainError("INVALID_CANDIDATE", "只能选择当前候选中的批次。")
                    context.selected_batch_id = values.pop("batch_id")
                for field, value in values.items():
                    setattr(context.parsed, field, value.strip() if isinstance(value, str) else value)
                context.parsed.uncertainties = [field for field in context.parsed.uncertainties if field not in values]
                context.revision += 1
                trace.append(TraceStep(step="clarification", outcome="structured_no_model_call", elapsed_ms=(time.perf_counter()-start)*1000))
                result = await self._resolve(context, scope, trace)
        except (DomainError, EngineError, TimeoutError) as error:
            result = self._failure(context.original_text, context.trace_id, error, context)
        trace.append(TraceStep(step="total", outcome=result.status, elapsed_ms=(time.perf_counter()-start)*1000))
        result.trace = trace
        return result
