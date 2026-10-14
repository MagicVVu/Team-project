import asyncio
import re
import time
from datetime import datetime, timezone

from p0.domain import DomainError, new_id
from p0.engines import EngineError
from p1.domain import guard
from p1.manager import Manager as P1Manager
from p1.schemas import Parsed as P1Parsed, TraceStep
from p1.tools import check_scope
from .risk import PRIORITY, RiskTool
from .schemas import AgentResult, RiskQuery, RiskResponse
from .tools import P1ReaderAdapter


class Manager:
    def __init__(self, engine, reader, catalog, *, now=None, timeout_seconds=10):
        self.engine, self.reader = engine, reader
        self.catalog, self.risk_tool = catalog, RiskTool(catalog)
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.timeout_seconds = timeout_seconds

    async def _evaluate(self, query, scope, trace_id):
        if query.batch_ids:
            batches = []
            for batch_id in query.batch_ids:
                batch = await self.reader.get_batch(scope, batch_id)
                if batch.id != batch_id:
                    raise DomainError("TOOL_UNAVAILABLE", "库存工具返回错误批次。", 503)
                batches.append(batch)
        else:
            batches = await self.reader.search(scope, query.name)
        check_scope(scope, batches)
        if len(batches) > 1000:
            raise DomainError("TOOL_UNAVAILABLE", "库存结果超出本阶段上限，请缩小查询范围。", 503)
        if query.name:
            batches = [b for b in batches if query.name.casefold() in b.name.casefold()]
            exact = [b for b in batches if b.name.casefold() == query.name.casefold()]
            batches = exact or batches
        now, results = self.now(), []
        for batch in batches:
            await asyncio.sleep(0)  # Cancellation point for the shared total deadline.
            results.append(self.risk_tool.evaluate(batch, now, query.household_timezone, query.reminder_days))
        evaluated_count = len(results)
        results = [r for r in results if not query.attention_only or r.attention]
        results.sort(key=lambda r: (-PRIORITY[r.level], r.name, r.batch_id))
        return RiskResponse(trace_id=trace_id, evaluated_count=evaluated_count, returned_count=len(results),
                            risks=results, facts=batches)

    async def evaluate(self, query, scope):
        async with asyncio.timeout(self.timeout_seconds):
            return await self._evaluate(query, scope, new_id("trace"))

    @staticmethod
    def explain(results):
        if not results:
            return "当前读取的记录没有符合本次筛选的关注项；这不代表已验证所有物品安全。"
        labels = {"red": "需优先处理", "orange": "需核对条件", "yellow": "日期关注", "unknown": "待核对", "green": "已知规则未触发"}
        field_labels = {"category":"物品类别", "label_expiry":"包装日期", "label_date_type":"日期含义",
            "label_context_valid":"标签是否仍适用", "storage_condition":"实际保存条件",
            "label_storage_condition":"包装保存要求", "is_opened":"开封状态", "opened_at":"开封日期",
            "after_open_rule":"该商品的开封规则", "rule_resolution":"冲突规则的审核结论",
            "applicable_reviewed_rule":"适用的已核对规则", "label_date_rule":"日期规则",
            "storage_rule":"保存规则", "purchased_at_or_label_expiry":"购入日期与包装日期的一致性"}
        lines = []
        for result in results:
            reasons = "；".join(e.explanation for e in result.evidence if e.reason_code not in {"LABEL_DATE_CURRENT", "STORAGE_RECORDED_MATCH", "INFORMATION_INCOMPLETE"})
            line = f"{result.name}（批次 {result.batch_id}）：{labels[result.level]}。{reasons or '当前登记事实未触发关注条件。'}"
            if result.missing_information:
                line += " 缺少：" + "、".join(field_labels.get(field, "待补充资料") for field in result.missing_information) + "。"
            line += " " + result.recommended_action
            lines.append(line)
        return "\n\n".join(lines) + "\n\n以上依据已登记事实与本地规则，不代表实物已检测安全；本次没有修改库存。"

    async def handle(self, message, scope):
        start, trace_id = time.perf_counter(), new_id("trace")
        trace, parsed = [], None
        try:
            async with asyncio.timeout(self.timeout_seconds):
                reason = guard(message.text)
                if reason:
                    result = AgentResult(status="unsupported", intent="UNSUPPORTED", reply=reason,
                                         original_text=message.text, trace_id=trace_id)
                else:
                    parsed = await self.engine.extract(message.text)
                    trace.append(TraceStep(step="routing", outcome=parsed.intent.value, elapsed_ms=(time.perf_counter()-start)*1000))
                    if parsed.intent != "QUERY_RISK":
                        original = P1Parsed.model_validate(parsed.model_dump())
                        class Extracted:
                            async def extract(self, text):
                                return original
                        adapter = P1ReaderAdapter(self.reader)
                        response = await P1Manager(Extracted(), adapter, now=self.now,
                                                   timeout_seconds=self.timeout_seconds).handle(message, scope)
                        result = AgentResult.model_validate(response.model_dump())
                        result.facts = [adapter.observed[b.id] for b in response.facts]
                    elif parsed.multiple_items or parsed.multiple_actions or re.search(r"然后|并且|顺便|同时", message.text):
                        result = AgentResult(status="unsupported", intent="UNSUPPORTED", reply="请分别提交风险查询与库存变更；本次不执行操作。", original_text=message.text, trace_id=trace_id)
                    elif parsed.name and parsed.name.strip().casefold() not in message.text.casefold():
                        raise EngineError("INVALID_MODEL_OUTPUT")
                    else:
                        name = parsed.name.strip() if parsed.name else None
                        # Deictic requests cannot silently expand to all inventory.
                        if not name and re.search(r"这批|这盒|这个", message.text):
                            result = AgentResult(status="needs_clarification", intent="QUERY_RISK", reply="请说明物品名称，或在详情中选择批次后评估。", original_text=message.text, trace_id=trace_id, missing_fields=["name"], manual_entry=True)
                        else:
                            query = RiskQuery(name=name, household_timezone=message.household_timezone,
                                              reminder_days=message.reminder_days, attention_only=name is None)
                            evaluated = await self._evaluate(query, scope, trace_id)
                            trace.append(TraceStep(step="risk_evaluation", outcome="read_only", elapsed_ms=(time.perf_counter()-start)*1000))
                            result = AgentResult(status="answered", intent="QUERY_RISK", reply=self.explain(evaluated.risks), original_text=message.text,
                                trace_id=trace_id, facts=evaluated.facts, risks=evaluated.risks, evaluated_count=evaluated.evaluated_count)
                            if name and not evaluated.facts:
                                result.reply = "没有找到匹配的库存记录，请核对名称；不能据此推断物品风险。"
        except (DomainError, EngineError, TimeoutError) as error:
            code = error.code if isinstance(error, (DomainError, EngineError)) else "AGENT_TIMEOUT"
            result = AgentResult(status="error", intent=parsed.intent if parsed else None, original_text=message.text,
                trace_id=trace_id, reply=error.message if isinstance(error, DomainError) else "AI 暂时无法处理，原文已保留，请重试或手动核对。",
                error_code=code, manual_entry=True, retryable=code in {"AGENT_TIMEOUT", "MODEL_TIMEOUT", "MODEL_UNAVAILABLE", "TOOL_UNAVAILABLE"})
        trace.extend(result.trace)
        trace.append(TraceStep(step="p2_total", outcome=result.status, elapsed_ms=(time.perf_counter()-start)*1000))
        result.trace = trace
        return result

    async def clarify(self, request, scope):
        # P1 clarification schema and state ownership remain unchanged.
        adapter = P1ReaderAdapter(self.reader)
        response = await P1Manager(self.engine, adapter, now=self.now,
                                   timeout_seconds=self.timeout_seconds).clarify(request, scope)
        result = AgentResult.model_validate(response.model_dump())
        result.facts = [adapter.observed[b.id] for b in response.facts if b.id in adapter.observed]
        return result
