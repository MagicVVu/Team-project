"""Check synchronized source in an ephemeral, offline container. Never deploy."""
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
CHECK=r'''
import asyncio,json,os
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path
import httpx
from integration.source_manifest import manifest
from conversation.app import create_app
from p2.schemas import Batch

paths=manifest()['files']
for rel in paths:
    if rel.endswith('.py'):compile(Path(rel).read_bytes(),rel,'exec')
at=datetime.now(timezone.utc)
scope={'user_id':'synthetic-user','household_id':'synthetic-home'}
batch=Batch(id='synthetic-b1',household_id=scope['household_id'],name='合成校验物品',quantity=Decimal(4),unit='盒',
    location='合成校验位置',version=7,status='ACTIVE')
class ReadOnlyFixture:
    calls=0
    async def get_batch(self,identity,ident):
        assert identity.model_dump()==scope and ident==batch.id
        self.calls+=1
        return batch.model_copy(deep=True)
    async def search(self,identity,name):
        assert identity.model_dump()==scope
        self.calls+=1
        return [batch.model_copy(deep=True)]
reader=ReadOnlyFixture()
app=create_app(reader=reader)
api=app.openapi()
stages=['/agent/dialogue/'+s for s in ['understand','resolve','respond']]
assert all(p in api['paths'] for p in stages)
assert '/agent/message' in api['paths'] and '/agent/clarification' in api['paths'] and '/agent/conversation-turn' in api['paths']
context={'scope':scope,'conversation_id':'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','revision':0,'trusted_now':at.isoformat(),
    'reference':{'scope':scope,'source_task_id':'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb','source_revision':1,'batch_id':batch.id,
        'issued_at':at.isoformat(),'expires_at':(at+timedelta(minutes=15)).isoformat()}}
headers={'Authorization':'Bearer source-check-synthetic-token','X-User-Id':scope['user_id'],'X-Household-Id':scope['household_id']}
async def check():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://offline-source-check') as client:
        body={'text':'它在哪里','request_id':'source-check','context':context}
        denied=await client.post(stages[0],json=body)
        assert denied.status_code==401
        first=await client.post(stages[0],json=body,headers=headers)
        assert first.status_code==200,first.text
        first=first.json();assert first['understanding_calls']==0
        resolved=await client.post(stages[1],json={**body,'plan':first['plan']},headers=headers)
        assert resolved.status_code==200,resolved.text
        resolved=resolved.json()
        assert resolved.get('result') is not None,resolved
        assert resolved['model_calls']==0 and resolved['result']['facts'][0]['location']=='合成校验位置'
        assert resolved['result']['inventory_writes'] is False and resolved['result']['shopping_writes'] is False
        half=await client.post(stages[1],headers=headers,json={**body,'text':'喝了一半，登记消耗','plan':{
            'speech_act':'request','action':'CONSUME','write_count':1,'selector':{'use_reference':True},'amount_mode':'half'}})
        assert half.status_code==200,half.text
        half=half.json();draft=half['result']['draft']
        assert half['result']['status']=='needs_confirmation' and Decimal(draft['quantity'])==2
        assert draft['batch_id']==batch.id and draft['expected_version']==7
        assert batch.quantity==4 and half['model_calls']==0
        assert half['result']['inventory_writes'] is False
        health=(await client.get('/health')).json()
        assert health['conversation_dialogue_protocol']=='p84-dialogue-1'
    return {'source_files_verified':len(paths),'python_compilation':True,'old_routes_preserved':True,'new_stage_routes':stages,
        'authentication_verified':True,'deterministic_reference_verified':True,'fresh_half_draft_verified':True,
        'model_calls':0,'inventory_writes':0,'shopping_writes':0,'production_backend_contacted':False}
print(json.dumps(asyncio.run(check())))
'''

REMOTE=r'''
import json,os,pathlib,subprocess
root=pathlib.Path.home()/'workspace'/'agent'
if root.is_symlink() or not root.is_dir():raise RuntimeError('Invalid AI workspace')
names=['magicvvu-starter-agent-1','magicvvu-starter-backend-1','magicvvu-starter-db-1']
def state():
    rows=json.loads(subprocess.check_output(['docker','inspect',*names]))
    return {r['Name'].lstrip('/'):{'id':r['Id'],'image':r['Config']['Image'],'started_at':r['State']['StartedAt'],
        'running':r['State']['Running'],'health':r['State'].get('Health',{}).get('Status')} for r in rows}
before=state()
command=['docker','run','--rm','--pull','never','--network','none','--read-only','--cap-drop','ALL',
    '--security-opt','no-new-privileges','--tmpfs','/tmp:rw,noexec,nosuid,size=16m',
    '--user',str(os.getuid())+':'+str(os.getgid()),'-e','PYTHONDONTWRITEBYTECODE=1','-e','P3_ENGINE=rules',
    '-e','AI_SERVICE_TOKEN=source-check-synthetic-token','-v',str(root)+':/app/agent:ro',
    '-w','/app/agent','--entrypoint','python',before[names[0]]['image'],'-c',CHECK]
process=subprocess.run(command,capture_output=True,text=True,timeout=60)
if process.returncode:raise RuntimeError('Offline source check failed: '+process.stderr[-2200:]+process.stdout[-800:])
after=state()
assert before==after,'Running service identity or health changed'
print(json.dumps({'checks':json.loads(process.stdout),'services_before':before,'services_after':after,
    'production_services_unchanged':True,'server_version_replaced':False,'ephemeral_container_removed':True}))
'''
script=REMOTE.replace('CHECK',repr(CHECK))
command=['ssh','-i',str(Path.home()/'.ssh/magicvvu_ai_ed25519'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes',
    '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','magicvvu_ai@8.134.172.165','python3 -']
result=subprocess.run(command,input=script.encode(),capture_output=True,timeout=90)
if result.returncode:
    print(result.stderr.decode(errors='replace')[-2400:])
    raise SystemExit(result.returncode)
value=json.loads(result.stdout)
path=ROOT/'reports/p84-dialogue/server-source-verification.json'
path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(value,ensure_ascii=False))
