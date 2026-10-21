import os
import secrets
from copy import deepcopy
from pathlib import Path

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError

from .deepseek import DeepSeekEngine
from .domain import DomainError, new_id
from .engines import FailureEngine, RuleEngine
from .manager import Manager
from .mock import MockBackend
from .schemas import (AgentResult, Command, Confirm, DraftEdit, DraftRecord, EngineSetting,
    Envelope, EventData, InventoryCommit, InventoryData, Message, PlanCommit, PlanRecord,
    PlanUpdate, Scope, Undo)
from .tools import RemoteInventoryReader

ROOT = Path(__file__).resolve().parents[1]


def create_app(mode: str | None = None) -> FastAPI:
    mode = mode or os.getenv("P0_MODE", "mock")
    if mode not in {"mock", "service"}:
        raise RuntimeError("P0_MODE must be mock or service")
    app = FastAPI(title=f"Household V1-P0 AI ({mode})", version="0.1.0")
    app.state.mode = mode
    app.state.store = MockBackend() if mode == "mock" else None
    if mode == "service":
        if not all(os.getenv(x) for x in ["AI_SERVICE_TOKEN", "BACKEND_TOOL_TOKEN", "BACKEND_BASE_URL"]):
            raise RuntimeError("service mode requires AI_SERVICE_TOKEN, BACKEND_TOOL_TOKEN, BACKEND_BASE_URL")
        reader = RemoteInventoryReader(os.environ["BACKEND_BASE_URL"], os.environ["BACKEND_TOOL_TOKEN"])
    else:
        reader = app.state.store
    app.state.deepseek = DeepSeekEngine()
    engine_name = os.getenv("P0_ENGINE", "deepseek" if mode == "service" else "rules")
    if engine_name not in {"rules", "deepseek"}:
        raise RuntimeError("P0_ENGINE must be rules or deepseek")
    app.state.manager = Manager(app.state.deepseek if engine_name == "deepseek" else RuleEngine(), reader)
    app.state.engine_name = engine_name

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, error: DomainError):
        return JSONResponse(status_code=error.status, content={"success": False, "data": None,
            "error": {"code": error.code, "message": error.message}, "trace_id": new_id("trace"), "mode": mode})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        return JSONResponse(status_code=422, content={"success": False, "data": None,
            "error": {"code": "VALIDATION_ERROR", "message": "请核对请求字段。", "fields": [
                {"location": list(e["loc"]), "message": e["msg"], "type": e["type"]} for e in error.errors()]},
            "trace_id": new_id("trace"), "mode": mode})

    def mock_scope(authorization: str = Header(default="")) -> Scope:
        tokens = {f"Bearer {os.getenv('DEMO_TOKEN', 'demo-local')}": Scope(user_id="u1", household_id="h1"),
                  "Bearer demo-other-household": Scope(user_id="u2", household_id="h2")}
        if authorization not in tokens:
            raise DomainError("UNAUTHENTICATED", "请使用开发 token。", 401)
        return tokens[authorization]

    def service_scope(authorization: str = Header(default=""), x_user_id: str = Header(default=""), x_household_id: str = Header(default="")) -> Scope:
        expected = f"Bearer {os.getenv('AI_SERVICE_TOKEN', '')}"
        if mode != "service" or not secrets.compare_digest(authorization, expected) or not x_user_id or not x_household_id:
            raise DomainError("UNAUTHENTICATED", "需要已认证后端的服务身份和用户上下文。", 401)
        return Scope(user_id=x_user_id, household_id=x_household_id)

    def envelope(data):
        return {"success": True, "data": data, "error": None, "mode": mode}

    @app.get("/health")
    def health():
        return {"status": "ok", "mode": mode, "engine": app.state.engine_name, "release_version": "V1-P0", "production_chain_verified": False}

    @app.post("/agent/message", response_model=AgentResult)
    async def agent_message(message: Message, scope: Scope = Depends(service_scope if mode == "service" else mock_scope)):
        return await app.state.manager.handle(message, scope)

    if mode == "mock":
        store = app.state.store

        @app.get("/", include_in_schema=False)
        def demo():
            return FileResponse(ROOT / "demo/index.html", headers={"Cache-Control": "no-store", "Content-Security-Policy": "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'"})

        @app.post("/api/v1/agent/messages", response_model=Envelope[AgentResult])
        async def gateway(message: Message, scope: Scope = Depends(mock_scope)):
            result = await app.state.manager.handle(message, scope)
            if result.draft:
                try:
                    draft = store.create_draft(scope, result.draft, result.trace_id)
                    result.draft_id = draft["id"]
                except DomainError as error:
                    result.status, result.draft = "error", None
                    result.error_code, result.reply, result.manual_entry = error.code, error.message, True
            return envelope(result)

        @app.post("/api/v1/drafts", response_model=Envelope[DraftRecord])
        def manual(command: Command, scope: Scope = Depends(mock_scope)):
            return envelope(store.create_draft(scope, command, new_id("trace")))

        @app.get("/api/v1/drafts/{draft_id}", response_model=Envelope[DraftRecord])
        def draft(draft_id: str, scope: Scope = Depends(mock_scope)):
            with store.lock:
                return envelope(deepcopy(store.draft(scope, draft_id)))

        @app.patch("/api/v1/drafts/{draft_id}", response_model=Envelope[DraftRecord])
        def edit(draft_id: str, update: DraftEdit, scope: Scope = Depends(mock_scope)):
            return envelope(store.edit_draft(scope, draft_id, update.revision, update.command))

        @app.delete("/api/v1/drafts/{draft_id}", response_model=Envelope[DraftRecord])
        def cancel(draft_id: str, scope: Scope = Depends(mock_scope)):
            return envelope(store.cancel_draft(scope, draft_id))

        @app.post("/api/v1/drafts/{draft_id}/confirm", response_model=Envelope[InventoryCommit | PlanCommit])
        def confirm(draft_id: str, body: Confirm, scope: Scope = Depends(mock_scope), idempotency_key: str = Header(default="")):
            return envelope(store.confirm(scope, draft_id, body.revision, idempotency_key))

        @app.get("/api/v1/inventory", response_model=Envelope[InventoryData])
        async def inventory(scope: Scope = Depends(mock_scope)):
            return envelope({"batches": await store.search(scope, None)})

        @app.get("/internal/v1/inventory/search", response_model=Envelope[InventoryData])
        async def search(name: str | None = None, scope: Scope = Depends(mock_scope)):
            return envelope({"batches": await store.search(scope, name)})

        @app.get("/api/v1/inventory/events", response_model=Envelope[EventData])
        def events(scope: Scope = Depends(mock_scope)):
            return envelope({"events": store.events(scope)})

        @app.post("/api/v1/inventory/events/{event_id}/undo", response_model=Envelope[InventoryCommit])
        def undo(event_id: str, body: Undo, scope: Scope = Depends(mock_scope), idempotency_key: str = Header(default="")):
            return envelope(store.undo(scope, event_id, body.expected_version, idempotency_key))

        @app.get("/api/v1/shopping-plans/current", response_model=Envelope[PlanRecord])
        def plan(scope: Scope = Depends(mock_scope)):
            with store.lock:
                return envelope(deepcopy(store.current_plan(scope)))

        @app.put("/api/v1/shopping-plans/current", response_model=Envelope[PlanRecord])
        def update_plan(body: PlanUpdate, scope: Scope = Depends(mock_scope)):
            return envelope(store.update_plan(scope, body))

        @app.post("/api/v1/shopping-plans/current/confirm", response_model=Envelope[PlanRecord])
        def confirm_plan(body: Confirm, scope: Scope = Depends(mock_scope), idempotency_key: str = Header(default="")):
            return envelope(store.confirm_plan(scope, body.revision, idempotency_key))

        @app.post("/api/mock/reset")
        def reset(scope: Scope = Depends(mock_scope)):
            if scope.household_id != "h1":
                raise DomainError("HOUSEHOLD_FORBIDDEN", "仅演示主用户可重置。", 403)
            store.reset()
            return envelope({"reset": True, "budget_reset": False})

        @app.put("/api/mock/engine")
        def engine(body: EngineSetting, scope: Scope = Depends(mock_scope)):
            if scope.household_id != "h1":
                raise DomainError("HOUSEHOLD_FORBIDDEN", "仅演示主用户可切换。", 403)
            app.state.manager.engine = {"rules": RuleEngine(), "deepseek": app.state.deepseek, "failure": FailureEngine()}[body.engine]
            app.state.engine_name = body.engine
            return envelope({"engine": body.engine})

        @app.get("/api/mock/budget")
        def budget(scope: Scope = Depends(mock_scope)):
            return envelope(app.state.deepseek.budget.summary())

    return app


app = create_app()
