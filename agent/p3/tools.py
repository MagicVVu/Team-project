"""Proposed authenticated, single-snapshot backend contract. GET only."""
from p0.domain import DomainError
from p1.tools import check_scope
from p2.tools import RemoteInventoryReader as P2Reader
from .schemas import PlanningSnapshot


class RemotePlanningReader(P2Reader):
    async def planning_context(self, scope, *, name=None, item_key=None):
        params = {k: v for k, v in {"name": name, "item_key": item_key}.items() if v is not None}
        try:
            data = await self._read(scope, "/internal/v1/planning/context", params)
        except DomainError as error:
            if error.code == "BATCH_NOT_FOUND":
                raise DomainError("PLANNING_CONTEXT_UNAVAILABLE", "后端尚未提供可访问的消耗与补货上下文，请手动核对。", 503) from None
            raise
        try:
            snapshot = PlanningSnapshot.model_validate(data)
        except (ValueError, TypeError):
            raise DomainError("PLANNING_CONTRACT_INVALID", "消耗与补货上下文字段不符合协议，请联系后端核对。", 503) from None
        validate_scope(snapshot, scope)
        return snapshot


def validate_scope(snapshot, scope):
    if snapshot.scope != scope:
        raise DomainError("HOUSEHOLD_FORBIDDEN", "规划数据不属于当前用户或家庭。", 403)
    keys, batches = set(), set()
    for item in snapshot.items:
        if item.item_key in keys:
            raise DomainError("PLANNING_CONTRACT_INVALID", "商品标识重复。", 503)
        keys.add(item.item_key)
        check_scope(scope, item.batches)
        for batch in item.batches:
            if batch.category != item.category:
                raise DomainError("PLANNING_CONTRACT_INVALID", "商品与批次类别不一致。", 503)
            if batch.id in batches:
                raise DomainError("PLANNING_CONTRACT_INVALID", "库存批次跨商品重复。", 503)
            batches.add(batch.id)
    if any(p.item_key not in keys for p in snapshot.pending):
        raise DomainError("PLANNING_CONTRACT_INVALID", "待购记录缺少明确商品对应。", 503)
