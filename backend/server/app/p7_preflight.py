"""Read-only deployment checks; never submit a valid AI message or a mutation.

Run inside the backend container: python -m app.p7_preflight.
Only fixed check names and booleans are printed, including on network/DB errors.
This is an integration preflight, not model or business acceptance.
"""
import asyncio
import json
import os
from uuid import uuid4

import httpx


async def check_http(client, env):
    checks = {
        "ai_service_url": env.get("AI_SERVICE_URL", "").rstrip("/") == "http://agent:8767",
        "ai_service_token": len(env.get("AI_SERVICE_TOKEN", "")) >= 32,
        "backend_tool_token": len(env.get("BACKEND_TOOL_TOKEN", "")) >= 32,
    }

    async def get_json(url):
        response = await client.get(url)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("Invalid response")
        return body

    async def record(name, operation):
        try:
            checks[name] = bool(await operation())
        except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
            checks[name] = False

    async def backend():
        health = await get_json("http://127.0.0.1:8000/api/v1/health")
        return health.get("status") == "ok" and health.get("version") == "0.9.0"

    async def ready():
        return (await get_json("http://127.0.0.1:8000/api/v1/ready")).get("database") == "ok"

    async def routes():
        # Docs are disabled in hardened deployments. Probe only unauthenticated
        # GETs using a nonexistent identifier; never submit a write or a token.
        placeholder = "00000000-0000-0000-0000-000000000000"
        required = [
            ("/api/v1/agent/execution-capabilities", 401),
            (f"/api/v1/drafts/{placeholder}/execution", 401),
            (f"/api/v1/drafts/{placeholder}/commit", 405),
            (f"/api/v1/drafts/{placeholder}/cancel", 405),
            (f"/api/v1/operations/{placeholder}", 401),
        ]
        for path, expected in required:
            if (await client.get("http://127.0.0.1:8000" + path)).status_code != expected:
                return False
        return True

    await record("backend_p7_version", backend)
    await record("database_ready", ready)
    await record("execution_routes", routes)
    if not checks["ai_service_url"]:
        # Never connect to an unapproved address, even when configuration is invalid.
        return checks

    async def ai():
        health = await get_json("http://agent:8767/health")
        return (health.get("status") == "ok" and health.get("release_version") == "V1-P7"
                and health.get("engine") in {"rules", "deepseek"}
                and health.get("input_policy_version") == "p7-limited-context-1"
                and health.get("inventory_writes") is False
                and health.get("shopping_writes") is False
                and health.get("execution_capabilities_owner") == "business_backend")

    async def ai_schema():
        spec = await get_json("http://agent:8767/openapi.json")
        return (spec["info"]["version"] == "0.7.0"
                and "post" in spec["paths"]["/agent/message"]
                and "post" in spec["paths"]["/agent/clarification"])

    async def authorization():
        headers = {"X-User-Id": str(uuid4()), "X-Household-Id": str(uuid4())}
        # Missing required body fields cannot enter the handler, even in DeepSeek mode.
        denied = await client.post("http://agent:8767/agent/message", json={}, headers=headers)
        headers["Authorization"] = "Bearer " + env["AI_SERVICE_TOKEN"]
        accepted = await client.post("http://agent:8767/agent/message", json={}, headers=headers)
        return denied.status_code == 401 and accepted.status_code == 422

    await record("ai_p7_health", ai)
    await record("ai_p7_schema", ai_schema)
    if checks["ai_service_token"]:
        await record("backend_to_ai_auth", authorization)
    else:
        checks["backend_to_ai_auth"] = False
    return checks


def check_database():
    from sqlalchemy import inspect, text
    from app.database import engine

    try:
        with engine.connect() as connection:
            versions = set(connection.execute(text("SELECT version_num FROM alembic_version")).scalars())
            tables = set(inspect(connection).get_table_names())
        return {"execution_migration": versions == {"20261017_0007"},
                "execution_tables": {"draft_operations", "draft_decisions", "business_events"} <= tables}
    finally:
        engine.dispose()


async def run():
    async with httpx.AsyncClient(timeout=httpx.Timeout(5, connect=3),
                                 trust_env=False, follow_redirects=False) as client:
        checks = await check_http(client, os.environ)
    try:
        checks.update(check_database())
    except Exception:
        # Do not expose connection strings or driver exception messages.
        checks.update(execution_migration=False, execution_tables=False)
    passed = all(checks.values())
    print(json.dumps({"checks": checks, "preflight_passed": passed,
                      "model_called": False, "business_data_written": False,
                      "live_acceptance_verified": False}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
