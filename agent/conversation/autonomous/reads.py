"""Only explicit scoped reads. No delegation of write/confirmation methods."""
import asyncio
import time
from p0.domain import DomainError
from p1.tools import check_scope


class ReadOnly:
    def __init__(self, delegate, scope, deadline):
        self.delegate, self.scope, self.deadline = delegate, scope, deadline
        self.rows, self.searches, self.planning = {}, {}, {}
        self.calls = 0

    def authorize(self, scope):
        if scope != self.scope:
            raise DomainError("HOUSEHOLD_FORBIDDEN", "不能跨用户或家庭读取。", 403)

    async def read(self, method, *args, **kwargs):
        self.calls += 1
        async with asyncio.timeout(min(5, max(.001, self.deadline-time.monotonic()))):
            return await method(*args, **kwargs)

    def remember(self, row):
        check_scope(self.scope, [row])
        old = self.rows.get(row.id)
        if old is not None and old.model_dump() != row.model_dump():
            raise DomainError("INVENTORY_VERSION_CONFLICT", "本轮库存已变化，请重新核对。", 409)
        for snapshot in self.planning.values():
            for item in snapshot.items:
                for batch in item.batches:
                    if batch.id == row.id: self.same_stock(row, batch)
        self.rows[row.id] = row.model_copy(deep=True)

    @staticmethod
    def same_stock(left, right):
        if any(getattr(left, k) != getattr(right, k) for k in
               ("version", "quantity", "unit", "location", "status", "opened_at", "label_expiry")):
            raise DomainError("INVENTORY_VERSION_CONFLICT", "规划与库存不一致，请重新核对。", 409)

    async def search(self, scope, name):
        self.authorize(scope)
        if name not in self.searches:
            rows = check_scope(scope, await self.read(self.delegate.search, scope, name))
            if len(rows) > 1000:
                raise DomainError("INVENTORY_INCOMPLETE", "请缩小查询范围。", 503)
            for row in rows: self.remember(row)
            self.searches[name] = [row.id for row in rows]
        return [self.rows[key].model_copy(deep=True) for key in self.searches[name]]

    async def get_batch(self, scope, ident):
        self.authorize(scope)
        if ident not in self.rows:
            row = await self.read(self.delegate.get_batch, scope, ident)
            check_scope(scope, [row])
            if row.id != ident:
                raise DomainError("TOOL_UNAVAILABLE", "工具返回了其他批次。", 503)
            self.remember(row)
        return self.rows[ident].model_copy(deep=True)

    async def planning_context(self, scope, *, name=None, item_key=None):
        self.authorize(scope)
        key = (name, item_key)
        if key not in self.planning:
            method = getattr(self.delegate, "planning_context", None)
            if method is None:
                raise DomainError("PLANNING_CONTEXT_UNAVAILABLE", "规划资料暂不可用。", 503)
            value = await self.read(method, scope, name=name, item_key=item_key)
            if value.scope != scope:
                raise DomainError("HOUSEHOLD_FORBIDDEN", "规划数据不属于当前用户或家庭。", 403)
            for item in value.items:
                for batch in item.batches:
                    if batch.id in self.rows: self.same_stock(self.rows[batch.id], batch)
            self.planning[key] = value.model_copy(deep=True)
        return self.planning[key].model_copy(deep=True)
