"""Probe real protected routes without invoking model or inventory reads."""
import asyncio
import sys
from pathlib import Path

import httpx
import pytest

from test_v09_execution import app, execution_state
from test_p7_preflight import Forbidden, TOKEN
from app.p8_preflight import check_http

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'agent'))
from conversation.app import create_app


@pytest.mark.parametrize('case', ['ready', 'old_ai', 'missing_backend_route'])
def test_p8_preflight_checks_actual_routes(execution_state, monkeypatch, case):
    monkeypatch.setenv('AI_SERVICE_TOKEN', TOKEN)
    monkeypatch.setenv('P3_ENGINE', 'rules')
    ai = create_app(engine=Forbidden(), reader=Forbidden())
    env = {'AI_SERVICE_URL':'http://agent:8767', 'AI_SERVICE_TOKEN':TOKEN,
           'BACKEND_TOOL_TOKEN':'synthetic-tool-token-at-least-32-characters'}

    async def run():
        backend = httpx.ASGITransport(app=app)
        agent = httpx.ASGITransport(app=ai)
        async def respond(request):
            if request.url.host == 'agent':
                if case == 'old_ai' and request.url.path == '/health':
                    return httpx.Response(200, json={'status':'ok','release_version':'V1-P7'})
                return await agent.handle_async_request(request)
            assert request.method == 'GET' and request.url.host == '127.0.0.1'
            if request.url.path == '/api/v1/ready':
                return httpx.Response(200, json={'database':'ok'})
            if case == 'missing_backend_route' and request.url.path.endswith('/planning-facts'):
                return httpx.Response(404)
            return await backend.handle_async_request(request)
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await check_http(client, env)

    result = asyncio.run(run())
    assert all(result.values()) is (case == 'ready')
