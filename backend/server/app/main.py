"""MagicVVu v0.7: shared shopping with atomic purchase-to-stock."""

import logging
import os

from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database import engine
from app.login_guard import LoginGuard
from app.routers.auth import router as auth_router
from app.routers.households import router as household_router
from app.routers.ai_inventory import router as ai_inventory_router
from app.routers.agent_gateway import router as agent_gateway_router
from app.routers.shopping import router as shopping_router
from app.routers.inventory import router as inventory_router
from app.routers.draft_execution import router as draft_execution_router
from app.routers.conversation import router as conversation_router

logger = logging.getLogger(__name__)

app = FastAPI(
    title="MagicVVu API",
    description="Shared shopping and atomic purchase-to-stock; household-scoped read-only P1 gateway",
    version="0.9.0",
    docs_url="/docs" if os.getenv("MAGICVVU_ENABLE_DOCS", "false").lower() == "true" else None,
    redoc_url="/redoc" if os.getenv("MAGICVVU_ENABLE_DOCS", "false").lower() == "true" else None,
    openapi_url="/openapi.json" if os.getenv("MAGICVVU_ENABLE_DOCS", "false").lower() == "true" else None,
)
app.state.login_guard = LoginGuard()
app.include_router(auth_router)
app.include_router(household_router)
app.include_router(ai_inventory_router)
app.include_router(agent_gateway_router)
app.include_router(shopping_router)
app.include_router(inventory_router)
app.include_router(draft_execution_router)
app.include_router(conversation_router)


@app.get("/api/v1/health", tags=["System"])
def health_check() -> dict:
    return {"status": "ok", "service": "magicvvu-backend", "version": app.version,
            "isolated_test": os.getenv("ISOLATED_APP_TEST") == "yes"}


@app.get("/api/v1/ready", tags=["System"])
def readiness_check() -> dict[str, str]:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("Database readiness query failed")
        raise HTTPException(status_code=503, detail="Database unavailable") from None
    return {"status": "ready", "database": "ok"}
