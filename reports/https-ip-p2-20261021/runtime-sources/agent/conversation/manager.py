import re
import time
from p0.domain import DomainError, new_id
from p1.domain import guard, ground
from p1.manager import Manager as LifecycleManager
from p1.schemas import Parsed, Intent, TraceStep, ClarificationContext
from p1.tools import check_scope
from p2.tools import P1ReaderAdapter
from interaction.policy import extraction_text, review_reason
from interaction.schemas import receipt
from v1.manager import Manager as BaseManager, Operation as BaseOperation
from v1.schemas import ClarificationRequest as OldRequest
from .schemas import (AgentResult, ReferenceContext, ReferenceUse, RuntimeInfo,
                      POLICY_VERSION)
from .engines import PROMPT_VERSION, QUALIFIED_MOVE

PRONOUN = re.compile(r"它|这一批|这批|这一个|这个|这件")
PRONOUN_NAMES = {"它", "这一批", "这批", "这一个", "这个", "这件", "这"}


def check_reference(reference, scope, now):
    if reference.scope != scope:
        raise DomainError("HOUSEHOLD_FORBIDDEN", "对象引用不属于当前用户或家庭。", 403)
    if not reference.issued_at <= now < reference.expires_at:
        raise DomainError("REFERENCE_EXPIRED", "对象引用已过期，请重新选择物品。", 409)


class Manager(BaseManager):
    def operation(self):
        return Operation(self)


class Operation(BaseOperation):
    bound_reference = None

    def restrict_move_source(self, text):
        match = QUALIFIED_MOVE.fullmatch(extraction_text(text))
        if match:
            original_search = self.reader.search
            async def search(scope, name):
                rows = await original_search(scope, name)  # Scope checks happen before filtering.
                return [b for b in rows if b.location == match[1]]
            self.reader.search = search

    def __init__(self, owner):
        super().__init__(owner)
        operation = self
        class ObservedEngine:
            def __init__(self, engine): self.engine = engine
            async def extract(self, text):
                parsed = await self.engine.extract(text)
                # Preserve grounded fields if the outer deadline cancels a tool read.
                message = getattr(operation, "current_message", None)
                if message and parsed.intent in set(Intent) and operation.context is None:
                    lifecycle = LifecycleManager(operation.engine, operation.reader, now=owner.now)
                    base = Parsed.model_validate({k:getattr(parsed,k) for k in Parsed.model_fields})
                    operation.context = lifecycle._context(message, operation.scope, new_id("trace"), ground(base, text))
                return parsed
        self.engine.engine = ObservedEngine(self.engine.engine)

    def decorate(self, result):
        result = super().decorate(result)
        value = result.model_dump()
        value["runtime"] = {**value["runtime"], "release": "V1-P7", "prompt_version": PROMPT_VERSION}
        value["policy_version"] = POLICY_VERSION
        result = AgentResult.model_validate(value)
        result.clear_reference = getattr(self, "reset_requested", False)
        if result.error_code != "HOUSEHOLD_FORBIDDEN":
            if self.bound_reference:
                result.object_source = "trusted_reference"
                result.reference_used = ReferenceUse(**{k:getattr(self.bound_reference,k)
                    for k in ("source_task_id", "source_revision", "batch_id")})
                if isinstance(result.clarification, ClarificationContext):
                    inner = result.clarification
                    values = {k:getattr(inner,k) for k in ReferenceContext.model_fields
                              if k not in {"protocol_version", "reference", "delegate", "input_receipt"}}
                    result.clarification = ReferenceContext(**values, reference=self.bound_reference, delegate=inner,
                        input_receipt=self.input_receipt)
            elif result.intent:
                result.object_source = "user_input"
        else:
            result.clarification = None
            result.candidates = result.facts = []
        return result

    async def handle(self, message, scope):
        self.current_message, self.scope = message, scope
        text = extraction_text(message.text)
        self.restrict_move_source(message.text)
        if message.input and not message.input.user_confirmed:
            return await super().handle(message, scope)
        if re.fullmatch(r"库存(?:有什么|有哪些)[？?。]?", text) and not guard(message.text) and not review_reason(message.text):
            rows = await self.reader.search(scope, None)
            matched = [b for b in rows if b.status == "ACTIVE" and b.quantity > 0]
            summary = "；".join(f"{b.name} {format(b.quantity, 'f')} {b.unit}（{b.location or '未定位'}）" for b in matched)
            return AgentResult(status="answered", intent="QUERY_INVENTORY", original_text=message.text,
                trace_id=new_id("trace"), facts=matched, reply=summary or "当前家庭没有有效库存记录。")
        # Literal location/name query: do not rewrite the user's text or invent a name.
        located = re.fullmatch(r"([^\s，,；;？?。]{1,100})里还有多少([^\s，,；;？?。]{1,80})[？?。]?", text)
        if located and not PRONOUN.search(text) and not guard(message.text) and not review_reason(message.text):
            location, name = located.groups()
            rows = await self.reader.search(scope, name)
            matched = [b for b in rows if b.name.casefold() == name.casefold() and
                       b.location == location and b.status == "ACTIVE" and b.quantity > 0]
            totals = {}
            for batch in matched:
                totals[batch.unit] = totals.get(batch.unit, 0) + batch.quantity
            summary = "、".join(f"{format(q, 'f')} {u}" for u, q in sorted(totals.items()))
            return AgentResult(status="answered", intent="QUERY_INVENTORY", original_text=message.text,
                trace_id=new_id("trace"), facts=matched,
                reply=f"{location}里的{name}：{summary}。" if matched else f"未找到{location}中名称为{name}的有效库存记录。")
        if text.strip().rstrip("。！! ") == "开始新任务":
            from v1.schemas import AgentResult as BaseResult
            result = BaseResult(status="answered", reply="已清除当前对象引用，请输入新的库存任务。",
                trace_id=new_id("trace"), original_text=message.text)
            self.reset_requested = True
            return result
        if ((message.input and not message.input.user_confirmed) or guard(message.text)
                or review_reason(message.text) or not PRONOUN.search(text)):
            return await super().handle(message, scope)
        self.input_receipt = receipt(message, scope)
        if message.reference and message.reference.scope != scope:
            raise DomainError("HOUSEHOLD_FORBIDDEN", "对象引用不属于当前用户或家庭。", 403)
        if re.fullmatch(r"(?:它|这一批|这批|这个)(?:在哪里|在哪|在哪儿|的位置|放在哪里)[？?]?", text):
            from p3.schemas import Parsed as Extracted
            raw = Extracted(intent="QUERY_LOCATION")
        elif re.fullmatch(r"(?:它|这一批|这批|这个)(?:还有多少|剩多少|的数量)[？?]?", text):
            from p3.schemas import Parsed as Extracted
            raw = Extracted(intent="QUERY_INVENTORY")
        elif re.fullmatch(r"(?:它|这一批|这批|这个)(?:消耗|用了|吃了|喝了)", text):
            from p3.schemas import Parsed as Extracted
            raw = Extracted(intent="CONSUME")
        else:
            raw = await self.engine.extract(text)
        # Explicit new names always start a new task; never bind the old object.
        if raw.name and raw.name.strip() not in PRONOUN_NAMES:
            return await self.delegate_extracted(raw, message, scope)
        if raw.intent not in set(Intent):
            raw.name = None
            return await self.delegate_extracted(raw, message, scope)
        parsed = Parsed.model_validate({k:getattr(raw,k) for k in Parsed.model_fields})
        reason = guard(message.text, parsed)
        if reason:
            return AgentResult(status="unsupported", intent="UNSUPPORTED", reply=reason,
                original_text=message.text, trace_id=new_id("trace"))
        parsed = ground(parsed, text)
        parsed.name = None  # A pronoun is not literal name evidence.
        lifecycle = LifecycleManager(self.engine, P1ReaderAdapter(self.reader), now=self.owner.now)
        self.context = lifecycle._context(message, scope, new_id("trace"), parsed)
        reference = message.reference
        if not reference:
            return lifecycle._clarify(self.context, ["name"], "请明确或重新选择要处理的物品。尚未写入。", "REFERENCE_REQUIRED")
        check_reference(reference, scope, self.owner.now())
        if parsed.intent in {Intent.ADD, Intent.UNSUPPORTED}:
            return lifecycle._clarify(self.context, ["name"], "新增物品请明确名称，不能从旧批次推断。", "REFERENCE_ACTION_UNSUPPORTED")
        try:
            batch = await self.reader.get_batch(scope, reference.batch_id)
        except DomainError as error:
            if error.code != "BATCH_NOT_FOUND": raise
            return lifecycle._clarify(self.context, ["name"], "原批次不可访问，请重新选择物品。", "REFERENCE_NOT_FOUND")
        check_scope(scope, [batch])
        if batch.id != reference.batch_id:
            raise DomainError("TOOL_UNAVAILABLE", "库存工具返回错误批次。", 503)
        if batch.status != "ACTIVE" or batch.quantity <= 0:
            return lifecycle._clarify(self.context, ["name"], "原批次已结束，请重新选择物品。", "REFERENCE_TERMINAL")
        self.bound_reference = reference
        self.context.expires_at = min(self.context.expires_at, reference.expires_at)
        # Bind only identity after grounding user fields. No text substitution.
        self.context.parsed.name = batch.name
        self.context.parsed.uncertainties = [f for f in parsed.uncertainties if f != "name"]
        base = lifecycle.reader.base(batch)
        self.context.candidates, self.context.selected_batch_id = [base], batch.id
        trace = [TraceStep(step="reference_binding", outcome="trusted_identity_current_read", elapsed_ms=0)]
        return await lifecycle._resolve(self.context, scope, trace)

    async def delegate_extracted(self, raw, message, scope):
        from interaction.policy import ExtractionAdapter
        class Extracted:
            async def extract(_, unused): return raw.model_copy(deep=True)
        self.delegate.delegate.engine = ExtractionAdapter(Extracted())
        return await self.delegate.handle(message, scope)

    async def clarify(self, request, scope):
        self.restrict_move_source(request.context.original_text)
        if not isinstance(request.context, ReferenceContext):
            return await super().clarify(OldRequest.model_validate(request.model_dump()), scope)
        wrapped = request.context
        if wrapped.scope == scope:
            self.bound_reference = wrapped.reference
            self.context = wrapped.delegate
            self.input_receipt = wrapped.input_receipt
        check_reference(wrapped.reference, scope, self.owner.now())
        if any(isinstance(v, str) and (guard(v) or review_reason(v))
               for v in request.answers.model_dump(exclude_none=True).values()):
            raise DomainError("INVALID_CLARIFICATION_INPUT", "请只补充当前字段，不要加入改变规则或执行指令。")
        from p1.schemas import ClarificationRequest
        # Track the validated, updated copy before awaiting reads. Cancellation
        # at either deadline must retain fields just entered by the user.
        remaining = self.owner.timeout_seconds-(time.perf_counter()-self.start)
        if remaining <= 0: raise TimeoutError
        operation = self
        class TrackedLifecycle(LifecycleManager):
            async def _resolve(inner, context, identity, trace):
                operation.context = context
                return await super()._resolve(context, identity, trace)
        lifecycle = TrackedLifecycle(self.engine, P1ReaderAdapter(self.reader), now=self.owner.now,
            timeout_seconds=remaining)
        return await lifecycle.clarify(ClarificationRequest(context=wrapped.delegate,
            revision=request.revision, answers=request.answers), scope)

    def public_result(self, response):
        # Only old-domain fields reach the frozen P6 conversion.
        if isinstance(response, AgentResult):
            from v1.schemas import AgentResult as BaseResult
            value = response.model_dump(exclude={"clear_reference", "object_source", "reference_used"})
            value["policy_version"] = "v1-completion-1"
            response = BaseResult.model_validate(value)
        result = super().public_result(response)
        if self.input_receipt:
            result.input_receipt = self.input_receipt
        return result
