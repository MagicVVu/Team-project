"""P3 entry point; P0/P1/P2 factories and Command schemas stay unchanged."""
import os
import secrets

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from p0.domain import DomainError, new_id
from p0.schemas import Scope
from p2.knowledge import RuleCatalog
from p2.schemas import Category, RiskQuery, RiskResponse
from p2.manager import Manager as P2Manager
from .engines import DeepSeekEngine, RuleEngine
from .manager import Manager
from .schemas import AgentResult, ClarificationRequest, PlanningMessage, Query, POLICY_VERSION
from .tools import RemotePlanningReader


def create_app(*, engine=None, reader=None, catalog=None, now=None, timeout_seconds=10):
    token = os.getenv("AI_SERVICE_TOKEN", "")
    if not token.strip():
        raise RuntimeError("P3 requires AI_SERVICE_TOKEN")
    if reader is None:
        if not all(os.getenv(k) for k in ("BACKEND_BASE_URL", "BACKEND_TOOL_TOKEN")):
            raise RuntimeError("P3 requires BACKEND_BASE_URL and BACKEND_TOOL_TOKEN")
        reader = RemotePlanningReader(os.environ["BACKEND_BASE_URL"], os.environ["BACKEND_TOOL_TOKEN"])
    engine_name = os.getenv("P3_ENGINE", "rules")
    if engine_name not in {"rules", "deepseek"}:
        raise RuntimeError("P3_ENGINE must be rules or deepseek")
    engine = engine or (RuleEngine() if engine_name == "rules" else DeepSeekEngine())
    catalog = catalog or RuleCatalog.load(os.getenv("P2_RULES_PATH"))
    manager = Manager(engine, reader, catalog, now=now, timeout_seconds=timeout_seconds)
    app = FastAPI(title="Household V1-P3 read-only planning AI", version="0.4.0")

    def scope(authorization: str = Header(default=""), x_user_id: str = Header(default=""), x_household_id: str = Header(default="")):
        if not secrets.compare_digest(authorization.encode(), f"Bearer {token}".encode()) or not x_user_id.strip() or not x_household_id.strip():
            raise DomainError("UNAUTHENTICATED", "需要后端服务认证及可信用户、家庭上下文。", 401)
        return Scope(user_id=x_user_id, household_id=x_household_id)

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, error: DomainError):
        return JSONResponse(status_code=error.status, content={"success": False, "data": None,
            "error": {"code": error.code, "message": error.message}, "trace_id": new_id("trace")})

    @app.exception_handler(RequestValidationError)
    async def validation(request: Request, error: RequestValidationError):
        return JSONResponse(status_code=422, content={"success": False, "data": None,
            "error": {"code": "VALIDATION_ERROR", "message": "请核对请求字段。", "fields": [
                {"location": list(e["loc"]), "type": e["type"]} for e in error.errors()]}, "trace_id": new_id("trace")})

    @app.exception_handler(TimeoutError)
    async def timeout(request: Request, error: TimeoutError):
        return JSONResponse(status_code=503, content={"success": False, "data": None,
            "error": {"code": "AGENT_TIMEOUT", "message": "读取或计算超时，请手动核对。"}, "trace_id": new_id("trace")})

    @app.get("/health")
    def health():
        return {"status": "ok", "release_version": "V1-P3", "engine": engine_name,
            "policy_version": POLICY_VERSION, "ruleset_version": catalog.data.version, "ruleset_sha256": catalog.sha256,
            "clarification_protocols": ["p1", "p2-risk-selection-1", "p3-item-selection-1"],
            "planning_contract": "p3-planning-context-1", "inventory_writes": False,
            "shopping_writes": False, "production_chain_verified": False}

    @app.post("/agent/message", response_model=AgentResult)
    async def message(body: PlanningMessage, identity: Scope = Depends(scope)):
        return await manager.handle(body, identity)

    @app.post("/agent/clarification", response_model=AgentResult)
    async def clarification(body: ClarificationRequest, identity: Scope = Depends(scope)):
        return await manager.clarify(body, identity)

    @app.post("/consumption/query", response_model=AgentResult)
    async def consumption(body: Query, identity: Scope = Depends(scope)):
        return await manager.query(body, identity, "QUERY_CONSUMPTION")

    @app.post("/forecast/evaluate", response_model=AgentResult)
    async def forecast(body: Query, identity: Scope = Depends(scope)):
        return await manager.query(body, identity, "QUERY_FORECAST")

    @app.post("/procurement/suggest", response_model=AgentResult)
    async def procurement(body: Query, identity: Scope = Depends(scope)):
        return await manager.query(body, identity, "SUGGEST_PURCHASE")

    @app.post("/risk/evaluate", response_model=RiskResponse)
    async def risk(body: RiskQuery, identity: Scope = Depends(scope)):
        return await P2Manager(engine, reader, catalog, now=now, timeout_seconds=timeout_seconds).evaluate(body, identity)

    @app.get("/knowledge/rules")
    def rules(category: Category | None = None, identity: Scope = Depends(scope)):
        return {"ruleset_version": catalog.data.version, "ruleset_sha256": catalog.sha256,
                "rules": [r.model_dump(mode="json") for r in catalog.list_rules(category)]}

    return app
