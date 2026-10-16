"""SQLite-isolated v0.6 regression: authentication, household boundaries, retry,
clarification binding, unconfirmed draft, and 0005 migration."""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

os.environ.setdefault('DB_PASSWORD', 'sqlite-test-only')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Main engine is connected only during real deployment; patch during import.
with patch('sqlalchemy.create_engine', return_value=create_engine('sqlite://')):
    from app.database import Base
    from app.dependencies import get_db
    from app.main import app
    from app.models import User, AuthSession, Household, HouseholdMember, AITask, AIDraft, InventoryItem
    from app.routers import agent_gateway
from app.security import digest_token


@pytest.fixture
def env(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path/'v06.sqlite'}", connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    a, b, home = uuid4(), uuid4(), uuid4()
    token = 'test-user-secret'
    with Session.begin() as db:
        db.add_all([
            User(id=a, email='a@example.invalid', password_hash='dummy', display_name='A'),
            User(id=b, email='b@example.invalid', password_hash='dummy', display_name='B'),
        ])
        db.flush()
        db.add(Household(id=home, name='home', created_by_user_id=a))
        db.flush()
        db.add(HouseholdMember(user_id=a, household_id=home, role='owner'))
        db.add(AuthSession(user_id=a, token_hash=digest_token(token),
                           expires_at=datetime.now(timezone.utc) + timedelta(hours=2)))
    monkeypatch.setenv('AI_SERVICE_URL', 'http://agent:8767')
    monkeypatch.setenv('AI_SERVICE_TOKEN', 'test-only-internal-ai-token-long-enough')

    def db_override():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = db_override
    with TestClient(app) as client:
        yield client, Session, {'a': a, 'b': b, 'home': home, 'token': token}
    app.dependency_overrides.clear()
    engine.dispose()


def auth(state):
    return {'Authorization': 'Bearer ' + state['token']}


def test_no_bearer_or_household_cross_access(env, monkeypatch):
    client, _, state = env
    payload = {'household_id': str(state['home']), 'text': '还有牛奶吗', 'request_id': 'x1'}
    assert client.post('/api/v1/agent/messages', json=payload).status_code == 401
    payload['household_id'] = str(uuid4())
    assert client.post('/api/v1/agent/messages', json=payload, headers=auth(state)).status_code == 404
    assert client.get('/api/v1/agent/tasks/'+str(uuid4()), headers=auth(state)).status_code == 404
    assert client.get('/api/v1/drafts/'+str(uuid4()), headers=auth(state)).status_code == 404


def test_idempotent_read_only_message(env, monkeypatch):
    client, Session, state = env
    inv_before = None
    calls = []
    async def agent(path, user, home, payload):
        calls.append(path)
        return {'status': 'answered', 'trace_id': 'trace_1', 'original_text': payload['text'],
                'reply': '没有找到匹配库存', 'facts': [], 'intent': 'QUERY_INVENTORY'}
    monkeypatch.setattr(agent_gateway, '_call_ai', agent)
    payload = {'household_id': str(state['home']), 'text': '还有牛奶吗', 'request_id': 'query-1'}
    res = client.post('/api/v1/agent/messages', json=payload, headers=auth(state))
    assert res.status_code == 200, res.text
    d = res.json()
    assert d['status'] == 'answered' and d['draft_id'] is None and not d['inventory_written']
    duplicate = client.post('/api/v1/agent/messages', json=payload, headers=auth(state))
    assert duplicate.status_code == 200 and duplicate.json()['task_id'] == d['task_id']
    assert calls == ['/agent/message']
    payload['text'] = '牛奶昨天开封了'
    assert client.post('/api/v1/agent/messages', json=payload, headers=auth(state)).status_code == 409
    assert client.get('/api/v1/agent/tasks/'+d['task_id'], headers=auth(state)).status_code == 200
    with Session() as db:
        assert db.scalar(select(InventoryItem)) is None
        assert db.query(AITask).count() == 1


def test_clarification_and_draft_are_persisted_and_never_confirmed(env, monkeypatch):
    client, Session, state = env
    scope = {'user_id': str(state['a']), 'household_id': str(state['home'])}
    expiry = (datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat()
    captured = []
    async def agent(path, user, home, payload):
        captured.append(payload)
        if path == '/agent/message':
            return {'status': 'needs_clarification', 'trace_id': 'trace_2',
                    'original_text': payload['text'], 'reply': '缺少日期',
                    'clarification': {'id': 'clarify-1', 'revision': 1, 'scope': scope,
                                      'allowed_fields': ['opened_at'], 'expires_at': expiry,
                                      'original_text': payload['text']}}
        return {'status': 'needs_confirmation', 'trace_id': 'trace_2',
                'original_text': payload['context']['original_text'], 'reply': '待确认',
                'draft': {'action': 'OPEN', 'name': '牛奶', 'batch_id': 'milk1',
                          'expected_version': 1, 'opened_at': '2026-10-14'},
                'preview': {'prospective': True, 'inventory_changes': True}}
    monkeypatch.setattr(agent_gateway, '_call_ai', agent)
    payload = {'household_id': str(state['home']), 'text': '牛奶开封了', 'request_id': 'clarify-1'}
    d = client.post('/api/v1/agent/messages', json=payload, headers=auth(state)).json()
    task_id = d['task_id']
    assert d['status'] == 'needs_clarification' and d['revision'] == 1
    assert 'scope' not in d['result']['clarification']
    assert d['result']['clarification']['allowed_fields'] == ['opened_at']
    url = '/api/v1/agent/clarifications/' + task_id
    # App cannot inject full context or change action or household.
    assert client.post(url, json={'revision': 1, 'answers': {'evil': 'abc'}}, headers=auth(state)).status_code == 422
    assert client.post(url, json={'revision': 2, 'answers': {'opened_at': '昨天'}}, headers=auth(state)).status_code == 409
    response = client.post(url, json={'revision': 1, 'answers': {'opened_at': '昨天'}}, headers=auth(state))
    assert response.status_code == 200, response.text
    out = response.json()
    assert out['status'] == 'needs_confirmation' and out['draft_id'] and not out['inventory_written']
    assert captured[1]['context']['scope'] == scope
    draft = client.get('/api/v1/drafts/' + out['draft_id'], headers=auth(state))
    assert draft.status_code == 200 and draft.json()['preview']['prospective'] is True
    assert client.post('/api/v1/drafts/' + out['draft_id'] + '/confirm', headers=auth(state)).status_code == 404
    assert client.post(url, json={'revision': 1, 'answers': {'opened_at': '昨天'}}, headers=auth(state)).status_code == 409
    with Session() as db:
        assert db.query(AIDraft).count() == 1
        assert db.query(InventoryItem).count() == 0


def test_wrong_ai_token_fails_closed(env, monkeypatch):
    client, Session, state = env
    monkeypatch.delenv('AI_SERVICE_TOKEN')
    payload = {'household_id': str(state['home']), 'text': '还有牛奶吗', 'request_id': 'x1'}
    r = client.post('/api/v1/agent/messages', json=payload, headers=auth(state))
    assert r.status_code == 503
    with Session() as db:
        assert db.query(AITask).count() == 0


def test_migration_from_0004_to_0005(tmp_path):
    from alembic import command
    from alembic.config import Config
    path = Path(__file__).resolve().parents[1]
    engine = create_engine(f"sqlite:///{tmp_path/'migrate.sqlite'}")
    cfg = Config(str(path/'alembic.ini'))
    cfg.set_main_option('script_location', str(path/'alembic'))
    with patch('sqlalchemy.create_engine', return_value=engine):
        command.upgrade(cfg, '20261014_0004')
        command.upgrade(cfg, '20261014_0005')
    with engine.connect() as c:
        assert c.execute(text('SELECT version_num FROM alembic_version')).scalar() == '20261014_0005'
        assert c.execute(text('SELECT count(*) FROM ai_tasks')).scalar() == 0
        assert c.execute(text('SELECT count(*) FROM ai_drafts')).scalar() == 0
        assert c.execute(text('SELECT count(*) FROM inventory_items')).scalar() == 0
    engine.dispose()
