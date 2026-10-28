import asyncio
import re
import time
from datetime import datetime, timedelta, timezone

from p0.domain import DomainError, new_id
from p0.engines import EngineError
from p1.domain import guard
from p1.schemas import ChangePreview, TraceStep
from p2.manager import Manager as P2Manager
from p2.schemas import Parsed as P2Parsed, ClarificationRequest as P2ClarificationRequest
from p2.risk import RiskTool
from . import forecast, procurement
from .schemas import (AgentResult, Candidate, Query, SelectionContext, SelectionParsed)
from .tools import validate_scope

P3_INTENTS = {"QUERY_CONSUMPTION", "QUERY_FORECAST", "SUGGEST_PURCHASE"}


class Manager:
    def __init__(self, engine, reader, catalog, *, now=None, timeout_seconds=10):
        self.engine, self.reader, self.catalog = engine, reader, catalog
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.timeout_seconds = timeout_seconds
        self.risk_tool = RiskTool(catalog)

    def context(self, message, scope, parsed, trace_id):
        now = self.now()
        return SelectionContext(id=new_id("clarify"), revision=1, scope=scope,
            original_text=message.text, request_id=message.request_id, trace_id=trace_id,
            household_timezone=message.household_timezone, created_at=now,
            expires_at=now+timedelta(minutes=15), parsed=SelectionParsed(
                intent=parsed.intent, name=parsed.name, window_days=parsed.window_days, draft_mode=parsed.draft_mode),
            allowed_fields=[] if parsed.name else ["name"])

    @staticmethod
    def result(context, **kwargs):
        return AgentResult(intent=context.parsed.intent, original_text=context.original_text,
                           trace_id=context.trace_id, **kwargs)

    def selection(self, context, items, snapshot_id, *, changed=False):
        context.candidates = [Candidate(item_key=i.item_key, name=i.name, unit=i.unit,
            version=i.version, batches=i.batches) for i in items]
        context.snapshot_id = snapshot_id
        context.selected_item_key = None
        context.allowed_fields = ["item_key"] if items else ["name"]
        return self.result(context, status="needs_clarification", clarification=context,
            item_candidates=context.candidates, missing_fields=context.allowed_fields, manual_entry=True,
            reply="库存或规划快照已变化，请重新选择核对。尚未写入。" if changed else "请明确选择商品；同名商品不会自动合并。尚未写入。")

    async def _run(self, context, scope, *, item_key=None, previous=None):
        parsed = context.parsed
        item_key = item_key or context.selected_item_key
        if item_key:
            context.selected_item_key = item_key
            context.allowed_fields = []
        if parsed.draft_mode and not (parsed.name or item_key):
            return self.selection(context, [], None)
        snapshot = await self.reader.planning_context(scope, name=parsed.name if not item_key else None, item_key=item_key)
        validate_scope(snapshot, scope)
        age = (self.now()-snapshot.as_of).total_seconds()
        if age < -1 or age > 300:
            raise DomainError("STALE_PLANNING_SNAPSHOT", "规划快照已过期或时间不可信，请后端刷新。", 409)
        if not snapshot.items_complete or snapshot.next_cursor:
            raise DomainError("PLANNING_INCOMPLETE", "规划结果未读取完整，请缩小范围或由后端提供完整快照。", 503)
        items = snapshot.items
        if item_key:
            items = [i for i in items if i.item_key == item_key]
            if len(items) != 1:
                raise DomainError("ITEM_NOT_FOUND", "所选商品已不可用，请重新查询。", 409)
        elif parsed.name:
            matching = [i for i in items if parsed.name.casefold() in i.name.casefold()]
            exact = [i for i in matching if i.name.casefold() == parsed.name.casefold()]
            items = exact or matching
            if len(items) != 1:
                return self.selection(context, items, snapshot.snapshot_id)
        if previous is not None:
            fresh = [Candidate(item_key=i.item_key, name=i.name, unit=i.unit, version=i.version, batches=i.batches) for i in items]
            selected_old = [c for c in previous.candidates if c.item_key == item_key]
            if previous.snapshot_id != snapshot.snapshot_id or selected_old != fresh:
                return self.selection(context, items, snapshot.snapshot_id, changed=True)
        if parsed.draft_mode and len(items) != 1:
            return self.selection(context, items, snapshot.snapshot_id)
        result = self.result(context, status="answered", reply="按已登记事实计算；本次没有修改库存或购物清单。",
                             snapshot_id=snapshot.snapshot_id, evaluated_at=snapshot.as_of)
        for item in items:
            await asyncio.sleep(0)
            evaluated = forecast.evaluate(item, snapshot, context.household_timezone, parsed.window_days)
            result.facts.extend(item.batches)
            if parsed.intent == "QUERY_CONSUMPTION":
                result.consumption_summary.append(evaluated.summary)
            else:
                result.forecast.append(evaluated)
            if parsed.intent in {"QUERY_FORECAST", "SUGGEST_PURCHASE"}:
                risks = [self.risk_tool.evaluate(b, snapshot.as_of, context.household_timezone, 3) for b in item.batches]
                result.risks.extend(risks)
            if parsed.intent == "SUGGEST_PURCHASE":
                rec = procurement.suggest(item, snapshot, evaluated, risks)
                result.recommendations.append(rec)
                if parsed.draft_mode and rec.status == "suggested":
                    result.draft, result.planning_basis = procurement.draft(item, snapshot, rec)
                    result.preview = ChangePreview(inventory_changes=False)
                    result.status = "needs_confirmation"
                    result.reply = "已生成可编辑的单项补货草稿，尚未写入。确认时须由后端重新核对库存和待购版本。"
        if not items:
            result.reply = "没有匹配商品的可核验规划数据，请核对名称或由后端补充资料。"
        elif parsed.intent == "QUERY_CONSUMPTION":
            result.reply = "\n".join(f"{s.name}：完整覆盖 {s.observed_days} 天，记录有效消耗 {s.effective_quantity} {s.unit}；状态 {s.status}。" for s in result.consumption_summary) + "\n只统计已确认消费，排除丢弃等事件；没有记录不代表没有实际消耗。尚未写入。"
        elif parsed.intent == "QUERY_FORECAST":
            result.reply = "\n".join(f"{f.name}：" + (f"参考剩余 {f.remaining_days} 天，参考日期 {f.reference_date}。{f.conditions}" if f.status == "estimated" else f"状态 {f.status}；暂不提供未来耗尽日期。") for f in result.forecast) + "\n依据已登记库存和消费记录，尚未写入。"
        elif result.status == "answered":
            result.reply = "\n".join(f"{r.name}：" + (f"建议新增待购 {r.suggested_quantity} {r.unit}，依据 {r.source}。" if r.status == "suggested" else f"状态 {r.status}，原因 {'、'.join(r.reason_codes)}。") for r in result.recommendations) + "\n尚未写入库存或购物清单。"
        return result

    async def handle(self, message, scope):
        start, trace_id, parsed, context = time.perf_counter(), new_id("trace"), None, None
        try:
            async with asyncio.timeout(self.timeout_seconds):
                reason = guard(message.text)
                if reason:
                    return AgentResult(status="unsupported", intent="UNSUPPORTED", reply=reason,
                        original_text=message.text, trace_id=trace_id)
                parsed = await self.engine.extract(message.text)
                if parsed.intent not in P3_INTENTS:
                    old = P2Parsed.model_validate({k: getattr(parsed, k) for k in P2Parsed.model_fields})
                    class Extracted:
                        async def extract(self, text):
                            return old
                    response = await P2Manager(Extracted(), self.reader, self.catalog, now=self.now,
                                               timeout_seconds=self.timeout_seconds).handle(message, scope)
                    return AgentResult.model_validate(response.model_dump())
                if parsed.multiple_actions or parsed.multiple_items or re.search(r"然后|并且|顺便|同时", message.text):
                    return AgentResult(status="unsupported", intent="UNSUPPORTED", reply="请分次提交单物品、单动作请求。",
                                       original_text=message.text, trace_id=trace_id)
                if parsed.name and parsed.name.strip().casefold() not in message.text.casefold():
                    raise EngineError("INVALID_MODEL_OUTPUT")
                # Model output cannot invent a window or a draft request.
                explicit = re.search(r"(?:过去|最近)(\d+)天", message.text)
                expected_days = int(explicit[1]) if explicit else 14 if re.search(r"过去两周|最近两周", message.text) else 28
                if parsed.window_days != expected_days or (parsed.draft_mode and "草稿" not in message.text):
                    raise EngineError("INVALID_MODEL_OUTPUT")
                context = self.context(message, scope, parsed, trace_id)
                if not parsed.name and re.search(r"这批|这盒|这个", message.text):
                    result = self.selection(context, [], None)
                else:
                    result = await self._run(context, scope)
        except (DomainError, EngineError, TimeoutError) as error:
            result = self.failure(error, message.text, trace_id, context)
        result.trace.append(TraceStep(step="p3_total", outcome=result.status, elapsed_ms=(time.perf_counter()-start)*1000))
        return result

    @staticmethod
    def failure(error, text, trace_id, context=None):
        code = error.code if isinstance(error, (DomainError, EngineError)) else "AGENT_TIMEOUT"
        return AgentResult(status="error", intent=context.parsed.intent if context else None,
            original_text=text, trace_id=trace_id, clarification=context,
            reply=error.message if isinstance(error, DomainError) else "处理暂不可用，已保留原文与已填字段，请手动核对。",
            error_code=code, manual_entry=True, retryable=code in {"AGENT_TIMEOUT", "TOOL_UNAVAILABLE", "MODEL_UNAVAILABLE"})

    async def clarify(self, request, scope):
        if not isinstance(request.context, SelectionContext):
            if request.answers.item_key is not None:
                return AgentResult(status="error", reply="此上下文不接受商品标识字段。", original_text="",
                                   trace_id=new_id("trace"), error_code="INVALID_CLARIFICATION")
            old = P2ClarificationRequest.model_validate(request.model_dump(exclude_none=True))
            response = await P2Manager(self.engine, self.reader, self.catalog, now=self.now,
                                       timeout_seconds=self.timeout_seconds).clarify(old, scope)
            return AgentResult.model_validate(response.model_dump())
        context = request.context.model_copy(deep=True)
        if context.scope != scope:
            return AgentResult(status="error", reply="任务不属于当前用户或家庭。", original_text="",
                               trace_id=new_id("trace"), error_code="HOUSEHOLD_FORBIDDEN")
        start = time.perf_counter()
        try:
            async with asyncio.timeout(self.timeout_seconds):
                if context.revision != request.revision:
                    raise DomainError("CLARIFICATION_CONFLICT", "修订号已变化，请读取最新任务。", 409)
                if self.now() >= context.expires_at or self.now() < context.created_at:
                    raise DomainError("CLARIFICATION_EXPIRED", "澄清上下文已过期，请重新提交。", 409)
                answers = request.answers.model_dump(exclude_none=True)
                if (not answers and context.allowed_fields) or not set(answers) <= set(context.allowed_fields) or len(answers) > 1:
                    raise DomainError("INVALID_CLARIFICATION", "仅接受当前缺失字段或候选商品选择。")
                previous = context.model_copy(deep=True)
                item_key = answers.get("item_key", context.selected_item_key)
                if item_key and context.candidates and item_key not in {c.item_key for c in context.candidates}:
                    raise DomainError("INVALID_CLARIFICATION", "请选择当前候选商品。")
                if "name" in answers:
                    if guard(answers["name"]):
                        raise DomainError("INVALID_CLARIFICATION", "请仅填写物品名称。")
                    context.parsed.name = answers["name"].strip()
                context.revision += 1
                result = await self._run(context, scope, item_key=item_key, previous=previous if item_key else None)
        except (DomainError, TimeoutError) as error:
            result = self.failure(error, context.original_text, context.trace_id, context)
        result.trace.append(TraceStep(step="p3_clarification_total", outcome=result.status, elapsed_ms=(time.perf_counter()-start)*1000))
        return result

    async def query(self, query: Query, scope, intent):
        from .schemas import PlanningMessage, Parsed
        message = PlanningMessage(text="结构化只读规划请求", request_id=new_id("query"), household_timezone=query.household_timezone)
        context = self.context(message, scope, Parsed(intent=intent, name=query.name,
            window_days=query.window_days, draft_mode=query.mode == "draft"), new_id("trace"))
        try:
            async with asyncio.timeout(self.timeout_seconds):
                if intent != "SUGGEST_PURCHASE" and query.mode == "draft":
                    raise DomainError("INVALID_QUERY_MODE", "只有补货建议接口支持草稿模式。")
                return await self._run(context, scope, item_key=query.item_key)
        except (DomainError, TimeoutError) as error:
            return self.failure(error, message.text, context.trace_id, context)
