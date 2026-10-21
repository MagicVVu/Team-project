import asyncio
import time
from datetime import timedelta

from p0.domain import new_id
from p1.domain import guard
from p1.schemas import TraceStep
from p3.manager import Manager as PlanningManager
from p3.schemas import ClarificationRequest as P3Request, PlanningMessage
from .policy import ExtractionAdapter, extraction_text, review_reason
from .schemas import (AgentResult, ContinuationContext, Receipt, ReviewAdvice,
                      ReviewContext, receipt)


class Manager:
    """Input adapter only. Business tasks and latest revisions remain external."""
    def __init__(self, engine, reader, catalog, *, now=None, timeout_seconds=10):
        self.delegate = PlanningManager(ExtractionAdapter(engine), reader, catalog, now=now, timeout_seconds=timeout_seconds)
        self.now, self.timeout_seconds = self.delegate.now, timeout_seconds

    @staticmethod
    def wrap(response, input_receipt=None, original_text=None):
        result = AgentResult.model_validate(response.model_dump())
        result.input_receipt = input_receipt
        if original_text is not None:
            result.original_text = original_text
        if response.clarification is not None:
            context = response.clarification
            values = {key:getattr(context,key) for key in (
                "id","revision","scope","original_text","request_id","trace_id","household_timezone",
                "created_at","expires_at","allowed_fields")}
            if original_text is not None:
                values["original_text"] = original_text
            result.clarification = ContinuationContext(**values, delegate=context, input_receipt=input_receipt)
        return result

    async def handle(self, message, scope):
        # Preflight is synchronous; the existing Manager receives the remaining
        # total budget and retains its parsed fields on timeout.
        start = time.perf_counter()
        try:
            return await self._handle(message, scope, start)
        except TimeoutError:
            return AgentResult(status="error", reply="处理超时，原文已保留，请手动核对。", original_text=message.text,
                trace_id=new_id("trace"), error_code="AGENT_TIMEOUT", manual_entry=True, input_receipt=receipt(message,scope))

    async def _handle(self, message, scope, start):
        trace_id = new_id("trace")
        accepted = receipt(message, scope)
        if message.input is not None and not message.input.user_confirmed:
            result = AgentResult(status="error", reply="请先核对识别文字，再提交AI；尚未写入。",
                trace_id=trace_id, original_text=message.text, error_code="INPUT_NOT_REVIEWED", manual_entry=True)
        elif guard(message.text):
            result = AgentResult(status="unsupported", intent="UNSUPPORTED", reply=guard(message.text),
                trace_id=trace_id, original_text=message.text)
        elif reason := review_reason(message.text) or ("EMPTY_REVIEWED_TEXT" if not extraction_text(message.text) else None):
            if reason == "CANCELLED_INPUT":
                result = AgentResult(status="answered", reply="本条输入未生成新草稿。已有任务或已确认操作需在业务端取消或撤销。",
                    trace_id=trace_id, original_text=message.text, error_code=reason)
            else:
                now = self.now()
                context = ReviewContext(id=new_id("review"), scope=scope, original_text=message.text,
                    request_id=message.request_id, trace_id=trace_id, household_timezone=message.household_timezone,
                    created_at=now, expires_at=now+timedelta(minutes=15), input_receipt=accepted)
                result = AgentResult(status="needs_clarification", reply="请核对并重新提交一条明确请求；否定、引用和不确定表达不会自动执行。尚未写入。",
                    trace_id=trace_id, original_text=message.text, clarification=context,
                    missing_fields=["text"], error_code=reason, manual_entry=True,
                    input_review=ReviewAdvice(reason_code=reason))
        else:
            values = {key:getattr(message,key) for key in PlanningMessage.model_fields}
            values["text"] = extraction_text(message.text)
            body = PlanningMessage.model_validate(values)
            remaining = self.timeout_seconds-(time.perf_counter()-start)
            if remaining <= 0:
                raise TimeoutError
            delegate = PlanningManager(self.delegate.engine,self.delegate.reader,self.delegate.catalog,
                now=self.now,timeout_seconds=remaining)
            response = await delegate.handle(body, scope)
            result = self.wrap(response, accepted, message.text)
        result.input_receipt = accepted
        result.trace.append(TraceStep(step="p5_input_total",outcome=result.status,elapsed_ms=(time.perf_counter()-start)*1000))
        return result

    async def clarify(self, request, scope):
        context = request.context
        if context.scope != scope:
            return AgentResult(status="error", reply="澄清任务不属于当前用户或家庭。", original_text="",
                trace_id=new_id("trace"), error_code="HOUSEHOLD_FORBIDDEN")
        if isinstance(context, ReviewContext):
            code = "CLARIFICATION_CONFLICT" if request.revision != context.revision else "CLARIFICATION_EXPIRED" if self.now() >= context.expires_at else "REVIEW_RESUBMIT_REQUIRED"
            return AgentResult(status="error",reply="请核对最终文字并用新的request_id重新提交，不能通过旧任务改写动作。",
                original_text=context.original_text, trace_id=context.trace_id, error_code=code,
                manual_entry=True, input_receipt=context.input_receipt)
        accepted = context.input_receipt if isinstance(context, ContinuationContext) else None
        if any(isinstance(value,str) and (guard(value) or review_reason(value))
               for value in request.answers.model_dump(exclude_none=True).values()):
            return AgentResult(status="error",reply="请仅补充当前缺失字段，不要在答案中改变动作或添加不确定指令。",
                original_text=context.original_text,trace_id=context.trace_id,error_code="INVALID_CLARIFICATION_INPUT",
                clarification=context,manual_entry=True,input_receipt=accepted)
        delegate_context = context.delegate if isinstance(context, ContinuationContext) else context
        response = await self.delegate.clarify(P3Request(context=delegate_context, revision=request.revision, answers=request.answers), scope)
        return self.wrap(response, accepted, context.original_text)

    async def query(self, query, scope, intent):
        return self.wrap(await self.delegate.query(query, scope, intent))
