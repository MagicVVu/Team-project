from typing import Protocol

import httpx

from .domain import DomainError
from .schemas import Batch, Scope


class InventoryReader(Protocol):
    async def search(self, scope: Scope, name: str | None) -> list[Batch]: ...


class RemoteInventoryReader:
    """Only read capabilities are exposed to the AI. No generic HTTP/SQL tool."""

    def __init__(self, base_url: str, token: str):
        self.base_url, self.token = base_url.rstrip("/"), token

    async def search(self, scope: Scope, name: str | None) -> list[Batch]:
        try:
            async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
                response = await client.get(
                    f"{self.base_url}/internal/v1/inventory/search",
                    params={"name": name} if name else {},
                    headers={"Authorization": f"Bearer {self.token}",
                             "X-User-Id": scope.user_id, "X-Household-Id": scope.household_id},
                )
                response.raise_for_status()
                batches = [Batch.model_validate(x) for x in response.json()["data"]["batches"]]
                if any(b.household_id != scope.household_id for b in batches):
                    raise DomainError("HOUSEHOLD_FORBIDDEN", "库存工具返回了其他家庭的数据。", 403)
                return batches
        except DomainError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise DomainError("TOOL_UNAVAILABLE", "库存服务暂不可用，请重试。", 503) from None
