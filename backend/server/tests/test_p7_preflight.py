"""Exercise auth preflight against the actual P7 factory without model calls."""
import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "agent"))
from app.p7_preflight import check_http
from conversation.app import create_app


TOKEN = "synthetic-internal-service-token-32-characters"


class Forbidden:
    def __getattr__(self, name):
        raise AssertionError("Preflight must not access engine or inventory")


@pytest.mark.parametrize("case", ["valid", "wrong_token", "missing_token", "wrong_url", "old_ai", "network_error"])
def test_preflight_real_p7_auth_without_model_or_inventory(monkeypatch, case):
    monkeypatch.setenv("AI_SERVICE_TOKEN", TOKEN)
    monkeypatch.setenv("P3_ENGINE", "deepseek")
    ai = create_app(engine=Forbidden(), reader=Forbidden())
    env = {"AI_SERVICE_URL": "http://agent:8767", "AI_SERVICE_TOKEN": TOKEN,
           "BACKEND_TOOL_TOKEN": "synthetic-tool-token-32-characters"}
    if case == "wrong_token":
        env["AI_SERVICE_TOKEN"] = "different-synthetic-service-token-32-characters"
    elif case == "missing_token":
        env.pop("AI_SERVICE_TOKEN")
    elif case == "wrong_url":
        env["AI_SERVICE_URL"] = "http://unapproved.invalid/private-address"

    requests = []

    async def run():
        asgi = httpx.ASGITransport(app=ai)

        async def respond(request):
            requests.append((request.method, request.url.host, request.url.path))
            if request.url.host == "agent":
                if case == "network_error":
                    raise httpx.ConnectError("sensitive-address-must-not-escape", request=request)
                if case == "old_ai" and request.url.path == "/health":
                    return httpx.Response(200, json={"release_version": "V1-P1"})
                assert request.method == "GET" or json.loads(request.content) == {}
                return await asgi.handle_async_request(request)
            assert request.url.host == "127.0.0.1" and request.method == "GET"
            if request.url.path.endswith("/health"):
                return httpx.Response(200, json={"status": "ok", "version": "0.9.0"})
            if request.url.path.endswith("/ready"):
                return httpx.Response(200, json={"database": "ok"})
            assert request.url.path != "/openapi.json"
            status = 405 if request.url.path.endswith(("/commit", "/cancel")) else 401
            return httpx.Response(status, json={"detail": "synthetic denial"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await check_http(client, env)

    checks = asyncio.run(run())
    assert all(checks.values()) is (case == "valid")
    output = json.dumps(checks)
    assert TOKEN not in output and env["BACKEND_TOOL_TOKEN"] not in output
    assert "private-address" not in output and "sensitive-address" not in output
    if case == "wrong_url":
        assert all(host == "127.0.0.1" for _, host, _ in requests)
    if case in {"wrong_token", "missing_token"}:
        assert checks["backend_to_ai_auth"] is False
