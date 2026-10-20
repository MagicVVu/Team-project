"""Synthetic scoped fixtures only; the upstream spy verifies unchanged text."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from test_v09_execution import execution_state, headers, seed_draft
from app.models import AITask


def source(Session, ids):
    _, task_id = seed_draft(Session, ids)
    with Session.begin() as db:
        task = db.get(AITask, task_id)
        task.status = 'answered'
        task.result_json = {'status': 'answered', 'facts': [{'id': str(ids['batch'])}]}
    return task_id


def payload(ids, task_id):
    return dict(household_id=str(ids['home']), text='它在什么地方', request_id=uuid4().hex,
                household_timezone='Asia/Shanghai', source_task_id=str(task_id),
                source_revision=1, batch_id=str(ids['batch']))


def test_reference_attestation_replay_and_exact_original(execution_state, monkeypatch):
    client, Session, ids = execution_state
    task_id = source(Session, ids)
    body = payload(ids, task_id)
    body['text'] = ' 它在什么地方？ '
    monkeypatch.setenv('AI_SERVICE_URL', 'http://agent:8767')
    monkeypatch.setenv('AI_SERVICE_TOKEN', 'x' * 32)
    upstream = AsyncMock(return_value=dict(status='answered', trace_id='synthetic', original_text=body['text'], facts=[]))
    with patch('app.routers.agent_gateway._call_ai', upstream):
        result = client.post('/api/v1/agent/reference-messages', headers=headers(), json=body)
        assert result.status_code == 200, result.text
        assert client.post('/api/v1/agent/reference-messages', headers=headers(), json=body).json() == result.json()
        assert upstream.await_count == 1
        sent = upstream.call_args.args[3]
        assert sent['text'] == body['text']
        ref = sent['reference']
        assert ref['scope'] == {'user_id': str(ids['user']), 'household_id': str(ids['home'])}
        assert ref['batch_id'] == body['batch_id']
        assert datetime.fromisoformat(ref['expires_at']) - datetime.fromisoformat(ref['issued_at']) <= timedelta(minutes=15)
        # A completed idempotent result remains recoverable after the source expires.
        with Session.begin() as db:
            db.get(AITask, task_id).updated_at = datetime.now(timezone.utc) - timedelta(hours=1)
        assert client.post('/api/v1/agent/reference-messages', headers=headers(), json=body).json() == result.json()


@pytest.mark.parametrize('change,code', [('revision', 409), ('batch', 422), ('household', 404), ('expiry', 409), ('owner', 404)])
def test_reference_rejects_untrusted_bindings(execution_state, change, code):
    client, Session, ids = execution_state
    task_id = source(Session, ids)
    body = payload(ids, task_id)
    if change == 'revision': body['source_revision'] = 2
    if change == 'batch': body['batch_id'] = str(uuid4())
    if change == 'household': body['household_id'] = str(ids['foreign_home'])
    if change == 'expiry':
        with Session.begin() as db:
            db.get(AITask, task_id).updated_at = datetime.now(timezone.utc) - timedelta(hours=1)
    with patch('app.routers.agent_gateway._call_ai', AsyncMock()) as upstream:
        result = client.post('/api/v1/agent/reference-messages', headers=headers('outsider' if change == 'owner' else 'user'), json=body)
        assert result.status_code == code, result.text
        upstream.assert_not_called()


def test_real_p7_reference_rereads_moved_location_without_model(execution_state, monkeypatch):
    import sys
    from pathlib import Path
    import httpx
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'agent'))
    from test_v09_execution import app, post, body as commit_body
    from conversation.app import create_app
    from conversation.engines import RuleEngine
    from v1.tools import RemoteReader

    client, Session, ids = execution_state
    token, tool = 'p72-service-token-with-at-least-32-characters', 'p72-tool-token-with-at-least-32-characters'
    for key, value in {'AI_SERVICE_URL': 'http://agent:8767', 'AI_SERVICE_TOKEN': token,
                       'BACKEND_TOOL_TOKEN': tool, 'P3_ENGINE': 'rules'}.items(): monkeypatch.setenv(key, value)
    class Counted(RuleEngine):
        calls = 0
        async def extract(self, text):
            self.calls += 1
            return await super().extract(text)
    engine = Counted()
    ai = create_app(engine=engine, reader=RemoteReader('http://backend:8000', tool))
    transports = {'agent': httpx.ASGITransport(app=ai), 'backend': httpx.ASGITransport(app=app)}
    async def dispatch(request): return await transports[request.url.host].handle_async_request(request)
    real_client = httpx.AsyncClient
    def local_client(*args, **kwargs):
        kwargs['transport'] = httpx.MockTransport(dispatch)
        return real_client(*args, **kwargs)
    monkeypatch.setattr(httpx, 'AsyncClient', local_client)
    original = client.post('/api/v1/agent/messages', headers=headers(), json={
        'household_id': str(ids['home']), 'text': '库存有什么', 'request_id': uuid4().hex,
        'household_timezone': 'Asia/Shanghai'})
    assert original.status_code == 200 and original.json()['status'] == 'answered', original.text
    task = original.json()
    move, _ = seed_draft(Session, ids, 'MOVE')
    assert post(client, move, commit_body()).status_code == 200
    response = client.post('/api/v1/agent/reference-messages', headers=headers(), json=payload(ids, task['task_id']))
    assert response.status_code == 200, response.text
    result = response.json()['result']
    assert result['original_text'] == '它在什么地方' and result['status'] == 'answered'
    assert result['facts'][0]['location'] == '书房' and result['facts'][0]['version'] == 2
    assert result['reference_used']['batch_id'] == str(ids['batch'])
    assert result['runtime']['model_calls'] == engine.calls == 0
