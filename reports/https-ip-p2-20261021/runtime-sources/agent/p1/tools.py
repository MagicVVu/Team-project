from typing import Protocol
from urllib.parse import quote

import httpx

from p0.domain import DomainError
from p0.schemas import Scope
from .schemas import Batch


class InventoryReader(Protocol):
    async def search(self, scope: Scope, name: str | None) -> list[Batch]: ...
    async def get_batch(self, scope: Scope, batch_id: str) -> Batch: ...


def check_scope(scope: Scope, batches: list[Batch]) -> list[Batch]:
    if any(batch.household_id != scope.household_id for batch in batches):
        raise DomainError("HOUSEHOLD_FORBIDDEN", "库存工具返回了其他家庭的数据。", 403)
    if len({batch.id for batch in batches}) != len(batches):
        raise DomainError("TOOL_UNAVAILABLE", "库存工具返回重复批次，请重试。", 503)
    return batches


class RemoteInventoryReader:
    """Two explicit read capabilities; never accepts a caller-supplied URL."""
    def __init__(self, base_url: str, token: str):
        self.base_url, self.token = base_url.rstrip("/"), token

    async def _read(self, scope: Scope, path: str, params=None):
        try:
            async with httpx.AsyncClient(timeout=5, trust_env=False, follow_redirects=False) as client:
                response = await client.get(self.base_url + path, params=params,
                    headers={"Authorization": f"Bearer {self.token}", "X-User-Id": scope.user_id,
                             "X-Household-Id": scope.household_id})
                if response.status_code == 404:
                    raise DomainError("BATCH_NOT_FOUND", "批次已不存在，请重新核对。", 404)
                response.raise_for_status()
                return response.json()["data"]
        except DomainError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise DomainError("TOOL_UNAVAILABLE", "库存服务暂不可用，请重试。", 503) from None

    async def search(self, scope: Scope, name: str | None) -> list[Batch]:
        data = await self._read(scope, "/internal/v1/inventory/search", {"name": name} if name else {})
        try:
            batches = [Batch.model_validate(item) for item in data["batches"]]
            if len(batches) > 1000:
                raise ValueError("too many batches")
        except (ValueError, KeyError, TypeError):
            raise DomainError("TOOL_UNAVAILABLE", "库存数据格式错误，请重试。", 503) from None
        return check_scope(scope, batches)

    async def get_batch(self, scope: Scope, batch_id: str) -> Batch:
        data = await self._read(scope, "/internal/v1/inventory/batches/" + quote(batch_id, safe=""))
        try:
            batch = Batch.model_validate(data["batch"])
        except (ValueError, KeyError, TypeError):
            raise DomainError("TOOL_UNAVAILABLE", "批次数据格式错误，请重试。", 503) from None
        check_scope(scope, [batch])
        if batch.id != batch_id:
            raise DomainError("TOOL_UNAVAILABLE", "库存工具返回了错误批次。", 503)
        return batch
