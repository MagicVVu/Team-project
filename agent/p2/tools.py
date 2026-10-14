from p0.domain import DomainError
from p1.schemas import Batch as P1Batch
from p1.tools import RemoteInventoryReader as P1RemoteReader, check_scope
from .schemas import Batch


class RemoteInventoryReader(P1RemoteReader):
    async def search(self, scope, name):
        data = await self._read(scope, "/internal/v1/inventory/search", {"name": name} if name else {})
        try:
            batches = [Batch.model_validate(row) for row in data["batches"]]
            if len(batches) > 1000:
                raise ValueError("too many batches")
        except (ValueError, KeyError, TypeError):
            raise DomainError("TOOL_UNAVAILABLE", "风险所需库存字段格式错误，请重试。", 503) from None
        return check_scope(scope, batches)

    async def get_batch(self, scope, batch_id):
        from urllib.parse import quote
        data = await self._read(scope, "/internal/v1/inventory/batches/" + quote(batch_id, safe=""))
        try:
            batch = Batch.model_validate(data["batch"])
        except (ValueError, KeyError, TypeError):
            raise DomainError("TOOL_UNAVAILABLE", "批次字段格式错误，请重试。", 503) from None
        check_scope(scope, [batch])
        if batch.id != batch_id:
            raise DomainError("TOOL_UNAVAILABLE", "库存工具返回了错误批次。", 503)
        return batch


class P1ReaderAdapter:
    """Project extended facts to the unchanged P1 contract before delegation."""
    def __init__(self, reader):
        self.reader = reader
        self.observed = {}

    def base(self, batch):
        self.observed[batch.id] = batch.model_copy(deep=True)
        return P1Batch.model_validate({key: getattr(batch, key) for key in P1Batch.model_fields})

    async def search(self, scope, name):
        return [self.base(batch) for batch in await self.reader.search(scope, name)]

    async def get_batch(self, scope, batch_id):
        return self.base(await self.reader.get_batch(scope, batch_id))
