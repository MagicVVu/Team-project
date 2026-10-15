"""Read-only AI gateway for the app's existing on-device inventory.

There is deliberately no cloud inventory replica: every request uses a device
snapshot, and confirmed writes remain in the Android store.
"""
import asyncio
import os
import secrets
from datetime import date
from decimal import Decimal

from fastapi import Depends, FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import Field, model_validator

from agent.p0.deepseek import DeepSeekEngine
from agent.p0.domain import DomainError, convert, new_id, normalize_command
from agent.p0.engines import DecisionEngine, RuleEngine
from agent.p0.manager import Manager
from agent.p0.schemas import AgentResult, Batch, Command, Message, Model, Scope

SCOPE = Scope(user_id="local-app", household_id="device-snapshot")


class Item(Model):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=80)
    quantity: Decimal = Field(ge=0, le=1_000_000_000)
    unit: str = Field(min_length=1, max_length=20)
    location: str | None = Field(default=None, max_length=120)
    expiry: date | None = None


class Snapshot(Model):
    inventory_revision: int = Field(ge=0, le=2_000_000_000)
    items: list[Item] = Field(max_length=1000)

    @model_validator(mode="after")
    def unique_ids(self):
        if len({item.id for item in self.items}) != len(self.items):
            raise ValueError("duplicate inventory ids")
        return self


class AppMessage(Snapshot):
    text: str = Field(min_length=1, max_length=1000)
    request_id: str = Field(min_length=1, max_length=100)


class ValidateDraft(Snapshot):
    command: Command


class SnapshotReader:
    def __init__(self, snapshot: Snapshot):
        self.batches = [Batch(id=item.id, household_id=SCOPE.household_id,
            name=item.name, quantity=item.quantity, unit=item.unit,
            location=item.location, label_expiry=item.expiry,
            status="ACTIVE" if item.quantity > 0 else "FINISHED",
            version=snapshot.inventory_revision + 1) for item in snapshot.items]

    async def search(self, scope: Scope, name: str | None) -> list[Batch]:
        return [batch.model_copy(deep=True) for batch in self.batches
                if name is None or name.casefold() in batch.name.casefold()]


def validate_command(command: Command, snapshot: Snapshot) -> Command:
    command = normalize_command(command)
    if command.action == "ADD":
        return command
    if command.action == "PLAN_ADD":
        candidates = [item for item in snapshot.items if item.name == command.name]
        if len(candidates) != 1:
            raise DomainError("PLAN_ITEM_REQUIRED", "采购清单请选择一个已经登记的物品；新物品请先通过添加入口登记。")
        item = candidates[0]
        return command.model_copy(update={"quantity": convert(command.quantity, command.unit, item.unit), "unit": item.unit})
    item = next((item for item in snapshot.items if item.id == command.batch_id), None)
    if item is None:
        raise DomainError("BATCH_NOT_FOUND", "物品已不存在，请重新查看库存。", 409)
    if command.expected_version != snapshot.inventory_revision + 1:
        raise DomainError("VERSION_CONFLICT", "库存已变化，请重新核对后生成草稿。", 409)
    if item.name != command.name:
        raise DomainError("VALIDATION_ERROR", "消耗草稿名称必须与选中批次一致。")
    quantity = convert(command.quantity, command.unit, item.unit)
    if quantity > item.quantity or item.quantity <= 0:
        raise DomainError("INSUFFICIENT_STOCK", "消耗量超过库存，请核对数量。")
    return normalize_command(command.model_copy(update={"quantity": quantity, "unit": item.unit}))


def create_app(engine: DecisionEngine | None = None) -> FastAPI:
    app = FastAPI(title="MagicVVu Android AI gateway", version="0.1.0")
    token = os.getenv("APP_API_TOKEN", "local-development")
    if not token.strip():
        raise RuntimeError("APP_API_TOKEN cannot be empty")
    engine_name = os.getenv("APP_AI_ENGINE", "deepseek" if os.getenv("DEEPSEEK_API_KEY") else "rules")
    if engine_name not in {"deepseek", "rules"}:
        raise RuntimeError("APP_AI_ENGINE must be rules or deepseek")
    remote = engine or (DeepSeekEngine() if engine_name == "deepseek" else None)

    def authorized(authorization: str = Header(default="")):
        if not secrets.compare_digest(authorization, f"Bearer {token}"):
            raise DomainError("UNAUTHENTICATED", "连接口令不正确，请核对服务设置。", 401)

    @app.exception_handler(DomainError)
    async def domain_error(request, error: DomainError):
        return JSONResponse(status_code=error.status, content={"success": False,
            "error": {"code": error.code, "message": error.message}})

    @app.get("/health")
    def health():
        return {"status": "ok", "engine": engine_name, "storage": "android-device",
                "inventory_writes": False}

    @app.post("/api/v1/agent/messages", dependencies=[Depends(authorized)])
    async def message(body: AppMessage):
        reader = SnapshotReader(body)
        try:
            async with asyncio.timeout(10):
                result = await Manager(remote or RuleEngine(), reader).handle(
                    Message(text=body.text, request_id=body.request_id), SCOPE)
            if result.draft:
                result.draft = validate_command(result.draft, body)
        except TimeoutError:
            result = AgentResult(status="error", original_text=body.text, trace_id=new_id("trace"),
                reply="AI 响应超时，原文已保留。请重试或手动填写。", error_code="MODEL_TIMEOUT", retryable=True, manual_entry=True)
        except DomainError as error:
            # Keep the original intent, trace and safe context so the phone can
            # explain which proposal failed validation. Never return its draft.
            result.status = "needs_clarification"
            result.draft = None
            result.reply = error.message
            result.error_code = error.code
            result.manual_entry = True
            result.missing_fields = {
                "INVALID_UNIT": ["unit"], "PLAN_ITEM_REQUIRED": ["name"],
                "INSUFFICIENT_STOCK": ["quantity"], "VERSION_CONFLICT": ["batch_id"],
            }.get(error.code, [])
        return {"success": True, "engine": engine_name, "expected_revision": body.inventory_revision,
                "data": result.model_dump(mode="json")}

    @app.post("/api/v1/agent/drafts/validate", dependencies=[Depends(authorized)])
    def validate(body: ValidateDraft):
        command = validate_command(body.command, body)
        return {"success": True, "expected_revision": body.inventory_revision,
                "command": command.model_dump(mode="json")}

    return app


app = create_app()
