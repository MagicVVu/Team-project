"""Read-only batch selectors. Never infer a product identity from its name."""
import re
from datetime import timedelta

from p0.domain import DomainError, new_id
from p0.engines import EngineError
from p2.manager import Manager as RiskManager
from p2.schemas import RiskQuery, RiskSelectionContext, RiskSelectionParsed
from p3.manager import Manager as PlanningManager

READ_INTENTS = {"QUERY_RISK", "QUERY_CONSUMPTION", "QUERY_FORECAST", "SUGGEST_PURCHASE"}
FINISH = re.compile(r"(?:它|这一批|这批|这个)(?:已经|已)?(?:全部用完|全用完|都用完|用完|耗尽)(?:了)?[。！!]?$")


def literal_query(text):
    """Exact UI expressions only; other language keeps the one-call extractor."""
    from p3.schemas import Parsed
    if re.fullmatch(r"(?:它|这一批|这批|这个)还能用多久[？?。]?", text):
        return Parsed(intent="QUERY_FORECAST")
    match = re.fullmatch(r"查看(?:它|这一批|这批|这个)最近(\d+)天的消费统计[？?。]?", text)
    if match and 1 <= int(match[1]) <= 28:
        return Parsed(intent="QUERY_CONSUMPTION", window_days=int(match[1]))
    if re.fullmatch(r"评估(?:它|这一批|这批|这个)的风险和缺少的标签储存资料[？?。]?", text):
        return Parsed(intent="QUERY_RISK")
    if re.fullmatch(r"根据记录计算(?:它|这一批|这批|这个)的补货建议，只展示建议，不提交采购[。]?", text):
        return Parsed(intent="SUGGEST_PURCHASE")
    return None


class BatchPlanningReader:
    def __init__(self, reader, batch):
        self.reader, self.batch = reader, batch

    async def planning_context(self, scope, **unused):
        snapshot = await self.reader.planning_context(scope, item_key=self.batch.id)
        items = [i for i in snapshot.items if any(b.id == self.batch.id for b in i.batches)]
        # Group-wide history/coverage cannot be relabelled as one batch's facts.
        if len(items) != 1 or len(items[0].batches) != 1:
            raise DomainError("BATCH_PLANNING_SCOPE_UNAVAILABLE", "后端尚未提供该批次独立的规划依据；请明确查询范围。", 409)
        current = items[0].batches[0]
        if any(getattr(current, k) != getattr(self.batch, k) for k in
               ("id", "household_id", "name", "quantity", "unit", "version", "status")):
            raise DomainError("VERSION_CONFLICT", "库存与规划快照已变化，请重新核对。", 409)
        return snapshot.model_copy(deep=True, update={"items": items})


async def read_query(operation, raw, message, scope, batch):
    from interaction.manager import Manager as InputManager
    from p3.schemas import AgentResult
    if raw.multiple_items or raw.multiple_actions or re.search(r"然后|并且|顺便|同时", message.text):
        return AgentResult(status="unsupported", intent="UNSUPPORTED", original_text=message.text,
                           trace_id=new_id("trace"), reply="请分次提交单物品、单动作请求。")
    if raw.intent == "QUERY_RISK":
        manager = RiskManager(operation.engine, operation.reader, operation.owner.catalog, now=operation.owner.now)
        now = operation.owner.now()
        context = RiskSelectionContext(protocol_version="p2-risk-selection-1", id=new_id("clarify"), revision=1, scope=scope,
            original_text=message.text, request_id=message.request_id, trace_id=new_id("trace"),
            household_timezone=message.household_timezone, created_at=now,
            expires_at=now+timedelta(minutes=15), parsed=RiskSelectionParsed(), reminder_days=message.reminder_days)
        operation.context = context
        if operation.bound_reference:
            context.expires_at = min(context.expires_at, operation.bound_reference.expires_at)
        if batch is None:
            result = AgentResult(status="needs_clarification", intent=raw.intent, reply="请重新选择批次或明确物品名称。",
                original_text=message.text, trace_id=context.trace_id, clarification=context,
                missing_fields=["name"], manual_entry=True)
        else:
            result = await manager._risk_answer(RiskQuery(batch_ids=[batch.id],
                household_timezone=message.household_timezone, reminder_days=message.reminder_days),
                scope, new_id("trace"), message.text, [], operation.start)
    else:
        explicit = re.search(r"(?:过去|最近)(\d+)天", message.text)
        expected = int(explicit[1]) if explicit else 14 if re.search(r"过去两周|最近两周", message.text) else 28
        if raw.window_days != expected or (raw.draft_mode and "草稿" not in message.text):
            raise EngineError("INVALID_MODEL_OUTPUT")
        manager = PlanningManager(operation.engine, operation.reader, operation.owner.catalog, now=operation.owner.now)
        context = manager.context(message, scope, raw, new_id("trace"))
        operation.context = context
        if operation.bound_reference:
            context.expires_at = min(context.expires_at, operation.bound_reference.expires_at)
        if batch is None:
            result = manager.selection(context, [], None)
        else:
            reader = BatchPlanningReader(operation.reader, batch)
            snapshot = await reader.planning_context(scope)
            manager.reader = reader
            # Use the original-text context and the existing deterministic evaluator.
            # The outer operation owns the model+reads total deadline.
            result = await manager._run(context, scope, item_key=snapshot.items[0].item_key)
    return InputManager.wrap(result, operation.input_receipt, message.text)
