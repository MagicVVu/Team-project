"""Two real HTTP services + ephemeral PostgreSQL, with shipped RuleEngine.

No provider calls or production addresses. Tokens exist only in process memory.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'backend/server'), str(ROOT/'agent')]


def main():
    base = sys.argv[1]
    assert base.startswith('http://127.0.0.1:')
    assert os.environ.get('P72_LOCAL_EPHEMERAL') == os.environ.get('ISOLATED_APP_TEST') == 'yes'
    assert os.environ['DB_NAME'] == 'magicvvu_p7_execution_test'
    from sqlalchemy import text
    from app.database import engine, SessionLocal
    from app.models import User, Household, HouseholdMember, ShoppingList, InventoryItem, AuthSession
    from app.security import digest_token
    import httpx
    with engine.connect() as db:
        assert Path(db.scalar(text('SHOW data_directory'))).resolve() == Path(os.environ['P72_PG_DATA_DIR']).resolve()
    user, home, batch, shopping_list = [uuid4() for _ in range(4)]
    login = uuid4().hex+uuid4().hex
    with SessionLocal.begin() as db:
        db.add(User(id=user, email=uuid4().hex+'@example.invalid', display_name='P9 synthetic', password_hash='fixture'))
        db.flush()
        db.add(Household(id=home, name='P9 disposable HTTP', created_by_user_id=user));db.flush()
        db.add(HouseholdMember(household_id=home, user_id=user, role='owner'))
        db.add(ShoppingList(id=shopping_list, household_id=home, name='Shared'))
        db.add(InventoryItem(id=batch, household_id=home, name='牛奶', quantity=10, unit='盒', storage_location='冰箱'))
        db.add(AuthSession(user_id=user, token_hash=digest_token(login), expires_at=datetime.now(timezone.utc)+timedelta(hours=1)))
    port = os.environ['P4_AGENT_LOOPBACK_PORT']
    env = dict(os.environ, BACKEND_BASE_URL=base, P3_ENGINE='rules', PYTHONPATH=str(ROOT/'agent'))
    result = {'real_socket_http': True, 'production_accessed': False, 'provider_calls': 0,
              'engine': 'shipped RuleEngine', 'chains': {}}
    path = ROOT/'reports/backend-ai-p9/http-e2e.json'
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'conversation.app:create_app', '--factory',
            '--host', '127.0.0.1', '--port', port], cwd=ROOT, env=env, stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            with httpx.Client(timeout=20, trust_env=False) as client:
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError('Isolated Agent startup failed')
                    try:
                        if client.get('http://127.0.0.1:'+port+'/health').status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(.1)
                else:
                    raise RuntimeError('Isolated Agent startup timed out')
                h = {'Authorization':'Bearer '+login}

                def call(method, route, payload=None):
                    r = client.request(method, base+route, headers=h, json=payload)
                    assert r.status_code in (200,201), (route, r.status_code, r.text[:300])
                    return r.json()

                routes = [
                    ('ADD', '买了2包纸巾', {'location':'储物柜'}, None),
                    ('MOVE', '把牛奶移动', {'to_location':'书房'}, None),
                    ('CONSUME', '喝了牛奶', {'quantity':'1','unit':'盒'}, None),
                    ('PLAN_ADD', '计划买牛奶', {'quantity':'2','unit':'盒'}, None),
                    ('OPEN', '牛奶开封了', {'opened_at':(datetime.now(timezone.utc).date()-timedelta(days=1)).isoformat()}, None),
                    ('DISCARD', '扔掉牛奶', {'quantity':'2','unit':'盒'}, None)]
                receipts = []
                for action, message, answers, reply in routes:
                    request = {'household_id':str(home), 'request_id':uuid4().hex,
                               'text':message, 'household_timezone':'Asia/Shanghai'}
                    task = call('POST', '/api/v1/agent/messages', request)
                    if task['status'] == 'needs_clarification':
                        if reply:
                            continuation = call('POST', '/api/v1/agent/conversation-messages', {
                                'household_id':str(home),'request_id':uuid4().hex,'text':reply,
                                'task_id':task['task_id'],'revision':task['revision']})
                            task = continuation['task']
                        else:
                            allowed = task['result']['clarification']['allowed_fields']
                            task = call('POST', '/api/v1/agent/clarifications/'+task['task_id'], {
                                'revision':task['revision'], 'answers':{k:v for k,v in answers.items() if k in allowed}})
                    assert task['status'] == 'needs_confirmation', (action, task['status'])
                    draft = call('GET', '/api/v1/drafts/'+task['draft_id'])
                    commit = {'operation_id':str(uuid4()),'task_revision':task['revision'],
                              'draft_revision':draft['revision'],'edits':{}}
                    route = '/api/v1/drafts/'+task['draft_id']+'/commit'
                    receipt = call('POST', route, commit)
                    assert receipt['action'] == action
                    assert call('POST', route, commit) == receipt
                    assert call('GET', '/api/v1/operations/'+commit['operation_id']) == receipt
                    feedback = call('POST', '/api/v1/operations/'+commit['operation_id']+'/feedback')
                    if action == 'PLAN_ADD':
                        assert feedback['feedback_status'] == 'not_applicable'
                    else:
                        assert feedback['feedback_status'] in {'available','partial'}
                    result['chains'][action] = {'status':'PASS','receipt':receipt,'feedback':feedback}
                    receipts.append(receipt)
                # Current session API, immutable recovery and re-opening history.
                session = call('POST', '/api/v1/agent/conversation/reset', {'household_id':str(home),'request_id':uuid4().hex})
                request = {'household_id':str(home),'request_id':uuid4().hex,'text':'牛奶还有多少',
                    'conversation_id':session['conversation_id'],'conversation_revision':session['conversation_revision']}
                turn = call('POST', '/api/v1/agent/conversation-turns', request)
                assert call('POST', '/api/v1/agent/conversation-turns', request) == turn
                recovered = call('GET', '/api/v1/agent/conversation-turns/'+request['request_id']+'?household_id='+str(home))
                assert recovered['response'] == turn
                history = call('GET', '/api/v1/agent/conversation?household_id='+str(home))
                assert history['conversation_id'] == session['conversation_id']
                result['session'] = {'status':'PASS','turn':turn,'recovery':recovered,'history':history}
                tool = {'Authorization':'Bearer '+os.environ['BACKEND_TOOL_TOKEN'],
                        'X-User-Id':str(user),'X-Household-Id':str(home)}
                snap = client.get(base+'/internal/v1/planning/context', headers=tool)
                assert snap.status_code == 200
                result['planning_snapshot'] = snap.json()
                caps = call('GET', '/api/v1/agent/execution-capabilities')
                assert caps['automatic_planning_commit'] is False and caps['manual_plan_only'] is True
                result['capabilities'] = caps
                # Real connection failure after committed business work.
                process.terminate();process.wait(timeout=10)
                first = receipts[0]
                feedback = call('POST', '/api/v1/operations/'+first['operation_id']+'/feedback')
                assert feedback['feedback_status'] == 'unavailable'
                retried = call('POST', '/api/v1/drafts/'+first['draft_id']+'/commit', {
                    'operation_id':first['operation_id'], 'task_revision':first['task_revision'],
                    'draft_revision':first['draft_revision'], 'edits':{}})
                assert retried == first
                result['ai_unavailable_after_commit'] = {'status':'PASS', 'feedback':feedback,
                    'original_receipt_recovered':True}
                result['status'] = 'PASS'
        except Exception as error:
            result.update(status='FAIL', error_type=type(error).__name__, error=str(error)[:800])
            raise
        finally:
            if process.poll() is None:
                process.terminate();process.wait(timeout=10)
            result['agent_stopped'] = process.poll() is not None
            path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('P9 six actions, feedback, session recovery and planning passed through real HTTP services')


if __name__ == '__main__':
    main()
