"""uvicorn p1.app:create_app --factory. No demo, inventory writer or task store."""
import os
import secrets

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from p0.domain import DomainError, new_id
from p0.schemas import Scope
from .engines import DeepSeekEngine, RuleEngine
from .manager import Manager
from .schemas import AgentResult, ClarificationRequest, Message
from .tools import RemoteInventoryReader


def create_app(*, engine=None, reader=None, now=None, timeout_seconds=10) -> FastAPI:
    token = os.getenv("AI_SERVICE_TOKEN", "")
    if not token.strip():
        raise RuntimeError("P1 requires AI_SERVICE_TOKEN")
    if reader is None:
        if not all(os.getenv(key) for key in ("BACKEND_BASE_URL", "BACKEND_TOOL_TOKEN")):
            raise RuntimeError("P1 requires BACKEND_BASE_URL and BACKEND_TOOL_TOKEN")
        reader = RemoteInventoryReader(os.environ["BACKEND_BASE_URL"], os.environ["BACKEND_TOOL_TOKEN"])
    engine_name = os.getenv("P1_ENGINE", "deepseek")
    if engine_name not in {"rules", "deepseek"}:
        raise RuntimeError("P1_ENGINE must be rules or deepseek")
    engine = engine or (RuleEngine() if engine_name == "rules" else DeepSeekEngine())
    manager = Manager(engine, reader, now=now, timeout_seconds=timeout_seconds)
    app = FastAPI(title="Household V1-P1 read-only AI", version="0.2.0",
        description="Authenticated internal AI: generates drafts only. No inventory writes, task storage or Mock routes.")

    def scope(authorization: str = Header(default=""), x_user_id: str = Header(default=""),
              x_household_id: str = Header(default="")) -> Scope:
        if not secrets.compare_digest(authorization.encode(), f"Bearer {token}".encode()) or not x_user_id.strip() or not x_household_id.strip():
            raise DomainError("UNAUTHENTICATED", "需要已认证业务后端的服务身份和用户上下文。", 401)
        return Scope(user_id=x_user_id, household_id=x_household_id)

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, error: DomainError):
        return JSONResponse(status_code=error.status, content={"success": False, "data": None,
            "error": {"code": error.code, "message": error.message}, "trace_id": new_id("trace")})

    @app.exception_handler(RequestValidationError)
    async def invalid_fields(request: Request, error: RequestValidationError):
        return JSONResponse(status_code=422, content={"success": False, "data": None,
            "error": {"code": "VALIDATION_ERROR", "message": "请核对请求字段。", "fields": [
                {"location": list(item["loc"]), "type": item["type"]} for item in error.errors()]},
            "trace_id": new_id("trace")})

    @app.get("/health")
    def health():
        return {"status": "ok", "release_version": "V1-P1", "engine": engine_name,
                "inventory_writes": False, "production_chain_verified": False}

    @app.post("/agent/message", response_model=AgentResult)
    async def message(body: Message, identity: Scope = Depends(scope)):
        return await manager.handle(body, identity)

    @app.post("/agent/clarification", response_model=AgentResult)
    async def clarify(body: ClarificationRequest, identity: Scope = Depends(scope)):
        return await manager.clarify(body, identity)

    return app
