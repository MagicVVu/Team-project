"""Real loopback Backend -> Agent -> Backend verification in an ephemeral PG run.

Called only by p72_local_postgres_tests.py --stage p4 with guarded environment.
No production credentials, model calls, or pre-existing database are used.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend/server'))
sys.path.insert(0, str(ROOT / 'agent'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('base')
    args = parser.parse_args()
    assert os.environ.get('P72_LOCAL_EPHEMERAL') == 'yes'
    assert os.environ.get('DB_NAME') == 'magicvvu_p7_execution_test'
    assert args.base.startswith('http://127.0.0.1:')
    from sqlalchemy import text
    from app.database import engine, SessionLocal
    from app.models import User, Household, HouseholdMember, ShoppingList, InventoryItem, AuthSession, AITask, AIDraft
    from app.security import digest_token
    import httpx
    with engine.connect() as db:
        assert Path(db.scalar(text('SHOW data_directory'))).resolve() == Path(os.environ['P72_PG_DATA_DIR']).resolve()
    ids = {key:uuid4() for key in ('user','home','list','batch','task','draft')}
    login = 'p4-synthetic-login-' + uuid4().hex
    command = {'action':'CONSUME','name':'牛奶','batch_id':str(ids['batch']),
               'expected_version':1,'quantity':'1','unit':'盒'}
    with SessionLocal.begin() as db:
        db.add(User(id=ids['user'],email=uuid4().hex+'@example.invalid',display_name='P4 synthetic',password_hash='fixture'))
        db.flush()
        db.add(Household(id=ids['home'],name='P4 isolated HTTP',created_by_user_id=ids['user']))
        db.flush()
        db.add(HouseholdMember(household_id=ids['home'],user_id=ids['user'],role='owner'))
        db.add(ShoppingList(id=ids['list'],household_id=ids['home'],name='Shared'))
        db.add(InventoryItem(id=ids['batch'],household_id=ids['home'],name='牛奶',quantity=5,unit='盒',storage_location='冰箱'))
        db.add(AuthSession(user_id=ids['user'],token_hash=digest_token(login),expires_at=datetime.now(timezone.utc)+timedelta(hours=1)))
        db.add(AITask(id=ids['task'],user_id=ids['user'],household_id=ids['home'],request_id=uuid4().hex,
            request_hash='fixture',original_text='HTTP fixture',household_timezone='Asia/Shanghai',status='needs_confirmation',
            revision=1,result_json={'status':'needs_confirmation','draft':command}))
        db.flush()
        db.add(AIDraft(id=ids['draft'],task_id=ids['task'],user_id=ids['user'],household_id=ids['home'],
            revision=1,status='pending',command_json=command))
    agent_port = os.environ['P4_AGENT_LOOPBACK_PORT']
    agent_base = 'http://127.0.0.1:' + agent_port
    env = dict(os.environ, BACKEND_BASE_URL=args.base, P3_ENGINE='rules', PYTHONPATH=str(ROOT/'agent'))
    agent_python = ROOT / '.cache/p2-agent-venv/Scripts/python.exe'
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen([str(agent_python), '-m','uvicorn','conversation.app:create_app','--factory',
            '--host','127.0.0.1','--port',agent_port], cwd=ROOT, env=env, stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        result = {'production_accessed':False, 'model':'project RuleEngine, no provider calls', 'real_loopback_http':True}
        try:
            with httpx.Client(timeout=10,trust_env=False) as client:
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError('Isolated Agent startup failed')
                    try:
                        health = client.get(agent_base+'/health')
                        if health.status_code==200: break
                    except httpx.HTTPError: pass
                    time.sleep(.1)
                else: raise RuntimeError('Isolated Agent startup timed out')
                result['agent_health']=health.json()
                h = {'Authorization':'Bearer '+login}
                request = {'operation_id':str(uuid4()),'draft_revision':1,'task_revision':1,'edits':{}}
                receipt = client.post(args.base+f"/api/v1/drafts/{ids['draft']}/commit",headers=h,json=request)
                assert receipt.status_code==200, receipt.status_code
                tool_headers = {'Authorization':'Bearer '+os.environ['BACKEND_TOOL_TOKEN'],
                    'X-User-Id':str(ids['user']),'X-Household-Id':str(ids['home'])}
                raw = client.get(args.base+'/internal/v1/planning/context', headers=tool_headers)
                assert raw.status_code==200
                payload=raw.json()
                from v1.tools import RemoteReader, Reader
                from p0.schemas import Scope
                from p3.history import consumption
                scope=Scope(user_id=str(ids['user']),household_id=str(ids['home']))
                snapshot=asyncio.run(Reader(RemoteReader(args.base,os.environ['BACKEND_TOOL_TOKEN']),
                    lambda:datetime.now(timezone.utc)).planning_context(scope))
                summary=consumption(snapshot.items[0],snapshot,'Asia/Shanghai')
                assert summary.status=='insufficient_data'
                assert snapshot.items[0].batches[0].quantity==4 and len(snapshot.items[0].events)==1
                result['snapshot']=payload
                result['agent_summary']=json.loads(summary.model_dump_json())
                message=client.post(args.base+'/api/v1/agent/messages',headers=h,json={
                    'household_id':str(ids['home']),'text':'牛奶消耗统计','request_id':uuid4().hex})
                assert message.status_code==200, (message.status_code, message.text)
                task=message.json()
                assert task['status']=='answered', task['status']
                assert task['result']['consumption_summary'][0]['status']=='insufficient_data'
                assert 'RECORDING_COMPLETENESS_UNKNOWN' in task['result']['consumption_summary'][0]['reason_codes']
                assert task['result']['inventory_writes'] is False and task['result']['shopping_writes'] is False
                result['backend_agent_roundtrip']=task
                for endpoint, field in [('/forecast/evaluate','forecast'),('/procurement/suggest','recommendations')]:
                    answer=client.post(agent_base+endpoint,headers={**tool_headers,
                        'Authorization':'Bearer '+os.environ['AI_SERVICE_TOKEN']},json={'name':'牛奶'})
                    assert answer.status_code==200, answer.status_code
                    data=answer.json()
                    assert data[field] and data['inventory_writes'] is False and data['shopping_writes'] is False
                    result[field]=data[field]
                assert client.get(args.base+'/internal/v1/planning/context').status_code==401
                assert client.post(args.base+'/internal/v1/planning/context',headers=tool_headers,json={}).status_code==405
                caps=client.get(args.base+'/api/v1/agent/execution-capabilities',headers=h).json()
                assert caps['automatic_planning_commit'] is False
                result['capabilities']=caps
        finally:
            process.terminate()
            process.wait(timeout=10)
            result['agent_stopped']=process.poll() is not None
        (ROOT/'reports/backend-p4-http-evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Real loopback Backend -> Agent -> Backend contract passed; no model calls')


if __name__=='__main__': main()
