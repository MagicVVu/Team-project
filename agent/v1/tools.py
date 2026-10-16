"""Authenticated reads for future business modules; no running fake services."""
from urllib.parse import quote
from p0.domain import DomainError
from p1.tools import check_scope
from p3.schemas import PlanningSnapshot as P3Snapshot, PlanningItem
from p3.tools import RemotePlanningReader, validate_scope
from .schemas import PlanningSnapshot, CommitReceipt

class RemoteReader(RemotePlanningReader):
    async def planning_context(self, scope, *, name=None, item_key=None):
        params = {k:v for k,v in {"name":name, "item_key":item_key}.items() if v is not None}
        try:
            data = await self._read(scope, "/internal/v1/planning/context", params)
        except DomainError as error:
            if error.code == "BATCH_NOT_FOUND":
                raise DomainError("PLANNING_CONTEXT_UNAVAILABLE", "后端规划读取模块尚未就绪；请手动核对，不提供虚构预测。", 503) from None
            raise
        try: result = PlanningSnapshot.model_validate(data)
        except (ValueError, TypeError):
            raise DomainError("PLANNING_CONTRACT_INVALID", "规划数据不符合已保留的V1接口契约。", 503) from None
        validate_scope(result, scope)
        return result

    async def operation_receipt(self, scope, operation_id):
        try:
            data = await self._read(scope, "/internal/v1/operations/"+quote(operation_id, safe=""))
        except DomainError as error:
            if error.code == "BATCH_NOT_FOUND":
                raise DomainError("OPERATION_CONTEXT_UNAVAILABLE", "后端提交凭证读取模块尚未就绪；请在业务端查询结果。", 503) from None
            raise
        try: result = CommitReceipt.model_validate(data)
        except (ValueError, TypeError):
            raise DomainError("OPERATION_CONTRACT_INVALID", "业务提交凭证不符合接口契约。", 503) from None
        if result.scope != scope:
            raise DomainError("HOUSEHOLD_FORBIDDEN", "提交凭证不属于当前用户或家庭。", 403)
        if result.operation_id != operation_id:
            raise DomainError("OPERATION_CONTRACT_INVALID", "返回了其他操作的提交凭证。", 503)
        return result

class Reader:
    """Per-request adapter/cache, so facts and diagnostics cannot cross requests."""
    def __init__(self, delegate, now, max_stock_age_hours=168):
        self.delegate, self.now = delegate, now
        self.max_stock_age_hours = max_stock_age_hours
        self.gaps = []
        self.snapshots = {}
        self.inventory_cache = {}

    async def search(self, scope, name):
        key = (scope.user_id, scope.household_id, name)
        if key not in self.inventory_cache:
            rows = check_scope(scope, await self.delegate.search(scope, name))
            if len(rows) > 1000:
                raise DomainError("INVENTORY_INCOMPLETE", "库存超过完整读取范围，请缩小查询。", 503)
            self.inventory_cache[key] = rows
        return [b.model_copy(deep=True) for b in self.inventory_cache[key]]

    async def get_batch(self, scope, batch_id):
        result = await self.delegate.get_batch(scope, batch_id)
        check_scope(scope, [result])
        if result.id != batch_id:
            raise DomainError("TOOL_UNAVAILABLE", "工具返回了其他批次。", 503)
        return result

    async def planning_context(self, scope, *, name=None, item_key=None):
        key = (scope.user_id, scope.household_id, name, item_key)
        if key not in self.snapshots:
            try: raw = await self.delegate.planning_context(scope, name=name, item_key=item_key)
            except AttributeError:
                raise DomainError("PLANNING_CONTEXT_UNAVAILABLE", "后端尚未提供规划读取接口。", 503) from None
            try: snapshot = PlanningSnapshot.model_validate(raw.model_dump() if hasattr(raw,"model_dump") else raw)
            except (ValueError, TypeError):
                raise DomainError("PLANNING_CONTRACT_INVALID", "规划数据不符合V1契约。", 503) from None
            validate_scope(snapshot, scope)
            age = (self.now()-snapshot.as_of).total_seconds()
            if age < -1 or age > 300:
                raise DomainError("STALE_PLANNING_SNAPSHOT", "规划快照已过期或时间不可信。", 409)
            if not snapshot.items_complete or snapshot.next_cursor:
                raise DomainError("PLANNING_INCOMPLETE", "规划快照不完整，请后端提供完整资料。", 503)
            values = {field:getattr(snapshot, field) for field in P3Snapshot.model_fields}
            values["protocol_version"] = "p3-planning-context-1"
            values["items"] = []
            for item in snapshot.items:
                verification = item.stock_verification
                reason = None
                if verification is None: reason = "STOCK_VERIFICATION_REQUIRED"
                elif (verification.checked_at-snapshot.as_of).total_seconds() > 1:
                    reason = "STOCK_VERIFICATION_FUTURE"
                elif (snapshot.as_of-verification.checked_at).total_seconds() > self.max_stock_age_hours*3600:
                    reason = "STOCK_VERIFICATION_STALE"
                copied = PlanningItem.model_validate({f:getattr(item,f) for f in PlanningItem.model_fields})
                if reason:
                    self.gaps.append(item.item_key+":"+reason)
                    copied.usable_quantity_verified = False
                    # Keep event statistics independent of stock verification.
                    # The completion result removes unverified forecast dates.
                values["items"].append(copied)
            self.snapshots[key] = P3Snapshot.model_validate(values)
        return self.snapshots[key].model_copy(deep=True)

    async def operation_receipt(self, scope, operation_id):
        if not hasattr(self.delegate, "operation_receipt"):
            raise DomainError("OPERATION_CONTEXT_UNAVAILABLE", "后端尚未提供提交凭证读取接口。", 503)
        value = await self.delegate.operation_receipt(scope, operation_id)
        try: result = CommitReceipt.model_validate(value.model_dump() if hasattr(value,"model_dump") else value)
        except (ValueError,TypeError):
            raise DomainError("OPERATION_CONTRACT_INVALID", "业务提交凭证格式无效。", 503) from None
        if result.scope != scope:
            raise DomainError("HOUSEHOLD_FORBIDDEN", "提交凭证不属于当前用户或家庭。", 403)
        if result.operation_id != operation_id:
            raise DomainError("OPERATION_CONTRACT_INVALID", "提交凭证引用不一致。", 503)
        return result
