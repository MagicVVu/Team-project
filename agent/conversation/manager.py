import re
import time
from datetime import timedelta
from decimal import Decimal
from p0.domain import DomainError, new_id
from p1.domain import guard, ground
from p1.manager import Manager as BaseLifecycleManager
from p1.schemas import Parsed, Intent, TraceStep, ClarificationContext
from p1.tools import check_scope
from p2.tools import P1ReaderAdapter
from interaction.policy import extraction_text, review_reason
from interaction.schemas import receipt
from v1.manager import Manager as BaseManager, Operation as BaseOperation
from v1.schemas import ClarificationRequest as OldRequest, Guidance
from .schemas import (AgentResult, ReferenceContext, ReferenceUse, RuntimeInfo,
                      ProcurementSource, POLICY_VERSION)
from .engines import PROMPT_VERSION, QUALIFIED_MOVE
from .chat_text import present, quick_response
from .supplements import RESET
from .scoped_queries import READ_INTENTS, FINISH, read_query, literal_query
from .planning import Reader as PlanningReader, attach_review

PRONOUN = re.compile(r"它|这一批|这批|这一个|这个|这件")
PRONOUN_NAMES = {"它", "这一批", "这批", "这一个", "这个", "这件", "这"}
LOCATION_REFERENCE = re.compile(
    r"(?:它|这一批|这批|这一个|这个|这件)\s*"
    r"(?:在哪里|在哪儿|在哪|在什么地方|放在哪里|放在哪儿|放在哪|放在什么地方|的位置)"
    r"[。！？?!]?"
)


def business_fields(parsed):
    """P7 draft admission only; legacy P0-P6 schemas and behavior stay intact."""
    fields = []
    if parsed.intent == "ADD" and (not parsed.location or not parsed.location.strip() or len(parsed.location) > 100):
        fields.append("location")
    if parsed.intent == "MOVE" and parsed.to_location and len(parsed.to_location) > 100:
        fields.append("to_location")
    if parsed.intent == "PLAN_ADD" and parsed.quantity is not None:
        amount = parsed.quantity
        if amount.normalize().as_tuple().exponent < -3 or amount > Decimal("999999999.999"):
            fields.append("quantity")
    return fields


class LifecycleManager(BaseLifecycleManager):
    async def _resolve(self, context, scope, trace):
        if context.parsed.intent == "PLAN_ADD" and context.selected_batch_id:
            batch = await self.reader.get_batch(scope, context.selected_batch_id)
            check_scope(scope, [batch])
            if batch.status != "ACTIVE" or batch.quantity <= 0:
                return self._result(context, "answered", "原采购来源已结束，请重新选择对象并新建采购任务。",
                                    facts=[batch], error_code="BATCH_TERMINAL")
            previous = next((b for b in context.candidates if b.id == context.selected_batch_id), None)
            if previous != batch:
                context.candidates, context.selected_batch_id = [batch], None
                return self._clarify(context, ["batch_id"], "采购来源已变化，请重新核对。", "VERSION_CONFLICT")
            context.parsed.name = batch.name
        fields = business_fields(context.parsed)
        context.parsed.uncertainties = list(dict.fromkeys([*context.parsed.uncertainties, *fields]))
        result = await super()._resolve(context, scope, trace)
        if result.status == "needs_clarification" and fields:
            result.reply = "请核对业务字段：新增位置必填、位置最多100字；采购数量最多三位小数且不超过999999999.999。尚未写入。"
        result.reply = present(result)
        return result


def check_reference(reference, scope, now):
    if reference.scope != scope:
        raise DomainError("HOUSEHOLD_FORBIDDEN", "对象引用不属于当前用户或家庭。", 403)
    if not reference.issued_at <= now < reference.expires_at:
        raise DomainError("REFERENCE_EXPIRED", "对象引用已过期，请重新选择物品。", 409)


class Manager(BaseManager):
    planning_reader_type = PlanningReader

    async def query(self, query, scope, intent):
        if query.item_key and query.item_key.startswith("product:"):
            operation = self.operation()
            operation.product_intent = intent
            return await operation.execute("product_query", query, scope)
        return await super().query(query, scope, intent)

    async def review_planning(self, request, scope):
        operation = self.operation()
        operation.review_request = request
        operation.product_intent = "SUGGEST_PURCHASE"
        return await operation.execute("review_planning", request.query, scope)
    def operation(self):
        return Operation(self)


class Operation(BaseOperation):
    bound_reference = None

    async def execute(self, method, body, scope, intent=None):
        self.planning_timezone = getattr(body, "household_timezone", getattr(getattr(body, "context", None), "household_timezone", "Asia/Shanghai"))
        text = getattr(body, "text", "") or getattr(getattr(body, "context", None), "original_text", "")
        window = re.search(r"(?:过去|最近)(\d+)天", text)
        self.planning_window = getattr(body, "window_days", int(window[1]) if window else 14 if re.search(r"过去两周|最近两周", text) else 28)
        self.product_selector = getattr(body, "item_key", None)
        return await super().execute(method, body, scope, intent)

    async def product_query(self, body, scope):
        if body.mode != "suggest":
            raise DomainError("PROCUREMENT_SOURCE_REQUIRED", "商品整体建议不能默认选取某一批次生成采购草稿，请明确来源批次。", 409)
        snapshot = await self.reader.planning_context(scope, name=body.name, item_key=body.item_key)
        sources = list(self.reader.backend_snapshots.values())
        if not sources or not any(p.item_key == body.item_key for p in sources[-1].provenance.product_aggregates_v1):
            raise DomainError("ITEM_NOT_FOUND", "没有可核验的商品映射，请重新选择。", 409)
        from v1.schemas import AgentResult as BaseResult
        return BaseResult(status="answered", intent=self.product_intent, original_text="结构化只读商品规划请求",
            trace_id=new_id("trace"), reply="已重新读取真实商品与批次资料。",
            facts=[b for i in snapshot.items for b in i.batches], snapshot_id=snapshot.snapshot_id,
            evaluated_at=snapshot.as_of)

    async def review_planning(self, body, scope):
        query = body.model_copy(update={"mode":"suggest"})
        if query.item_key and query.item_key.startswith("product:"):
            return await self.product_query(query, scope)
        return await self.delegate.query(query, scope, "SUGGEST_PURCHASE")

    def restrict_move_source(self, text):
        match = QUALIFIED_MOVE.fullmatch(extraction_text(text))
        if match:
            original_search = self.reader.search
            async def search(scope, name):
                rows = await original_search(scope, name)  # Scope checks happen before filtering.
                return [b for b in rows if b.location == match[1]]
            self.reader.search = search

    def __init__(self, owner):
        self.planning_timezone, self.planning_window, self.product_selector = "Asia/Shanghai", 28, None
        super().__init__(owner)
        operation = self
        class ObservedEngine:
            def __init__(self, engine): self.engine = engine
            async def extract(self, text):
                parsed = await self.engine.extract(text)
                parsed.uncertainties = list(dict.fromkeys([*parsed.uncertainties, *business_fields(parsed)]))
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
        value["runtime"] = {**value["runtime"], "release": "V1-P7", "prompt_version": PROMPT_VERSION,
                            "maintenance_release":"V1-P8.3"}
        value["policy_version"] = POLICY_VERSION
        result = AgentResult.model_validate(value)
        if result.draft and result.draft.action == "CONSUME" and result.quantity_source == "current_batch":
            result.consume_mode = "all"
        if result.draft and result.draft.action == "PLAN_ADD" and not result.planning_basis and self.bound_reference:
            candidates = getattr(self.context, "candidates", [])
            batch = next((b for b in candidates if b.id == self.bound_reference.batch_id), None)
            if batch:
                result.procurement_source = ProcurementSource(batch_id=batch.id, expected_version=batch.version)
        items = {i.item_key: i for snapshot in self.reader.snapshots.values() for i in snapshot.items}
        for recommendation in result.recommendations:
            item = items.get(recommendation.item_key)
            if item:
                recommendation.inventory_unit = item.unit
                recommendation.order_unit = recommendation.unit
                recommendation.pack_size = item.preferences.pack_size if recommendation.status == "suggested" else None
                recommendation.pack_size_source = "saved_preferences" if recommendation.pack_size else None
        platform_fields = {"applicable_reviewed_rule", "label_date_rule", "storage_rule", "after_open_rule", "rule_resolution"}
        guidance_items = []
        for guidance in result.guidance:
            missing_rules = [f for f in guidance.missing_fields if f in platform_fields]
            facts = [f for f in guidance.missing_fields if f not in platform_fields]
            if facts:
                from v1.policy import FACT_LABELS
                guidance_items.append(Guidance(batch_id=guidance.batch_id, missing_fields=facts,
                    instructions=["请在物品资料中核对"+FACT_LABELS.get(f,f)+"，保存后重新查询。" for f in facts]))
            if missing_rules:
                guidance_items.append(Guidance(batch_id=guidance.batch_id, missing_fields=missing_rules,
                    instructions=["平台尚缺适用的人工审核规则或审核结论，需由规则负责人核实发布；补录库存资料不能替代规则审核。"],
                    fact_write_required=False))
        result.guidance = guidance_items
        if any("applicable_reviewed_rule" in r.missing_information for r in result.risks):
            result.data_gaps = sorted(set([*result.data_gaps, "HUMAN_RULE_REVIEW_REQUIRED"]))
            for recommendation in result.recommendations:
                if recommendation.status == "needs_review":
                    recommendation.reason_codes = list(dict.fromkeys([*recommendation.reason_codes, "HUMAN_RULE_REVIEW_REQUIRED"]))
            result.reply += "\n平台缺少适用的人工审核规则；补录库存资料不能替代规则负责人审核发布。"
        result.clear_reference = getattr(self, "reset_requested", False)
        if result.error_code != "HOUSEHOLD_FORBIDDEN":
            if self.bound_reference:
                result.object_source = "trusted_reference"
                result.reference_used = ReferenceUse(**{k:getattr(self.bound_reference,k)
                    for k in ("source_task_id", "source_revision", "batch_id")})
                if type(result.clarification) is ClarificationContext:
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
        result.reply = present(result)
        result = self.reader.enrich(result, timezone=self.planning_timezone, window_days=self.planning_window,
            product_selector=self.product_selector, collapse=not bool(self.bound_reference))
        if hasattr(self, "review_request"):
            result = attach_review(result, self.review_request)
        return result

    async def handle(self, message, scope):
        self.current_message, self.scope = message, scope
        text = extraction_text(message.text)
        self.restrict_move_source(message.text)
        quick = quick_response(text)
        if quick and message.reference and message.reference.scope != scope:
            raise DomainError("HOUSEHOLD_FORBIDDEN", "对象引用不属于当前用户或家庭。", 403)
        if quick and not guard(message.text) and not review_reason(message.text) and not (message.input and not message.input.user_confirmed):
            return AgentResult(status="answered", reply=quick[1], original_text=message.text,
                               trace_id=new_id("trace"))
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
        if RESET.fullmatch(text.strip()):
            from v1.schemas import AgentResult as BaseResult
            result = BaseResult(status="answered", reply="已清除当前对象引用，请输入新的库存任务。",
                trace_id=new_id("trace"), original_text=message.text)
            self.reset_requested = True
            return result
        if ((message.input and not message.input.user_confirmed) or guard(message.text)
                or review_reason(message.text) or (not PRONOUN.search(text) and not getattr(self, "allow_implicit_reference", False))):
            return await super().handle(message, scope)
        self.input_receipt = receipt(message, scope)
        if message.reference and message.reference.scope != scope:
            raise DomainError("HOUSEHOLD_FORBIDDEN", "对象引用不属于当前用户或家庭。", 403)
        finish = FINISH.fullmatch(text)
        literal_read = literal_query(text)
        if finish:
            from p3.schemas import Parsed as Extracted
            raw = Extracted(intent="CONSUME")
        elif literal_read:
            raw = literal_read
        elif LOCATION_REFERENCE.fullmatch(text):
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
        if raw.intent in READ_INTENTS:
            raw.name = None
            reference = message.reference
            batch = None
            if reference:
                check_reference(reference, scope, self.owner.now())
                try:
                    batch = await self.reader.get_batch(scope, reference.batch_id)
                except DomainError as error:
                    if error.code != "BATCH_NOT_FOUND":
                        raise
                    result = await read_query(self, raw, message, scope, None)
                    result.error_code = "REFERENCE_NOT_FOUND"
                    return result
                if batch.status != "ACTIVE" or batch.quantity <= 0:
                    result = await read_query(self, raw, message, scope, None)
                    result.error_code = "REFERENCE_TERMINAL"
                    return result
                self.bound_reference = reference
            return await read_query(self, raw, message, scope, batch)
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
            if finish:
                return await self.prepare_finish(message, scope)
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
        if finish:
            return await self.prepare_finish(message, scope, batch, reference)
        self.context.expires_at = min(self.context.expires_at, reference.expires_at)
        # Bind only identity after grounding user fields. No text substitution.
        self.context.parsed.name = batch.name
        self.context.parsed.uncertainties = [f for f in parsed.uncertainties if f != "name"]
        base = lifecycle.reader.base(batch)
        self.context.candidates, self.context.selected_batch_id = [base], batch.id
        trace = [TraceStep(step="reference_binding", outcome="trusted_identity_current_read", elapsed_ms=0)]
        return await lifecycle._resolve(self.context, scope, trace)

    async def prepare_finish(self, message, scope, batch=None, reference=None):
        from v1.schemas import LocalContext
        now = self.owner.now()
        self.context = LocalContext(id=new_id("clarify"), revision=1, scope=scope,
            original_text=message.text, request_id=message.request_id, trace_id=new_id("trace"),
            household_timezone=message.household_timezone, created_at=now,
            expires_at=min(now+timedelta(minutes=15), reference.expires_at) if reference else now+timedelta(minutes=15),
            kind="finish", name=batch.name if batch else None, candidates=[batch] if batch else [],
            selected_batch_id=batch.id if batch else None, allowed_fields=[], input_receipt=self.input_receipt)
        return await self.resolve_local(self.context, scope)

    async def delegate_extracted(self, raw, message, scope):
        from interaction.policy import ExtractionAdapter
        class Extracted:
            async def extract(_, unused): return raw.model_copy(deep=True)
        self.delegate.delegate.engine = ExtractionAdapter(Extracted())
        return await self.delegate.handle(message, scope)

    async def clarify(self, request, scope):
        if request.context.scope != scope:
            raise DomainError("HOUSEHOLD_FORBIDDEN", "澄清任务不属于当前用户或家庭。", 403)
        self.restrict_move_source(request.context.original_text)
        if not isinstance(request.context, ReferenceContext):
            from interaction.schemas import ContinuationContext
            context = request.context
            inner = context.delegate if isinstance(context, ContinuationContext) else context
            if type(inner) is ClarificationContext:
                if inner.scope == scope:
                    self.context = inner
                    self.input_receipt = getattr(context, "input_receipt", None)
                if any(isinstance(v, str) and (guard(v) or review_reason(v))
                       for v in request.answers.model_dump(exclude_none=True).values()):
                    raise DomainError("INVALID_CLARIFICATION_INPUT", "请仅补充缺失字段。")
                result = await self.resume_lifecycle(inner, request, scope)
                if result.error_code == "HOUSEHOLD_FORBIDDEN":
                    return result
                from interaction.manager import Manager as InputManager
                return InputManager.wrap(result, self.input_receipt, context.original_text)
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
        return await self.resume_lifecycle(wrapped.delegate, request, scope)

    async def resume_lifecycle(self, context, request, scope):
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
        return await lifecycle.clarify(ClarificationRequest(context=context,
            revision=request.revision, answers=request.answers), scope)

    def public_result(self, response):
        # Only old-domain fields reach the frozen P6 conversion.
        if isinstance(response, AgentResult):
            from v1.schemas import AgentResult as BaseResult
            value = response.model_dump(exclude={"clear_reference", "object_source", "reference_used", "consume_mode", "procurement_source",
                "planning_calculation", "product_planning", "planning_context", "planning_review"})
            value["policy_version"] = "v1-completion-1"
            response = BaseResult.model_validate(value)
        result = super().public_result(response)
        if result.planning_basis and result.draft and business_fields(
                Parsed(intent=Intent.PLAN_ADD, quantity=result.draft.quantity)):
            # Do not turn an unexecutable computed amount into a manual supplement:
            # that would discard the protected planning/revalidation evidence.
            key = result.planning_basis.item_key
            code = "BUSINESS_PURCHASE_QUANTITY_INVALID"
            result.draft = result.preview = result.planning_basis = None
            result.status = "answered"
            result.error_code = code
            result.data_gaps.append(code)
            for recommendation in result.recommendations:
                if recommendation.item_key == key:
                    recommendation.status = "needs_review"
                    recommendation.suggested_quantity = None
                    recommendation.reason_codes.append(code)
        if self.input_receipt:
            result.input_receipt = self.input_receipt
        return result
