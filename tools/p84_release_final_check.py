"""Verify legacy live routes, rollback image availability and final source hashes."""
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
audit=json.loads((ROOT/'reports/p84-dialogue/production-audit.json').read_text(encoding='utf-8'))
released=json.loads((ROOT/'reports/p84-dialogue/production-switch.json').read_text(encoding='utf-8'))
payload={'old':audit['services'],'new':released['services'],'db':audit['protected_services']}
REMOTE=r'''
import datetime,hashlib,json,pathlib,subprocess,urllib.request
data=PAYLOAD
def inspect(name):return json.loads(subprocess.check_output(['docker','inspect',name]))[0]
rollback={}
for service,value in data['old'].items():
    old=value
    image=json.loads(subprocess.check_output(['docker','image','inspect',old['image']]))[0]
    assert image['Id']==old['image_id']
    rollback[service]={'image':old['image'],'image_id':image['Id'],'available':True}
for service,value in data['new'].items():
    obj=inspect('magicvvu-starter-'+service+'-1')
    assert obj['Id']==value['id'] and obj['State']['Health']['Status']=='healthy'
for name,value in data['db'].items():
    obj=inspect(name)
    assert obj['Id']==value['id'] and obj['State']['StartedAt']==value['started_at']
agent=inspect('magicvvu-starter-agent-1')
env=dict(v.split('=',1) for v in agent['Config']['Env'])
origin='http://'+next(iter(agent['NetworkSettings']['Networks'].values()))['IPAddress']+':8767'
home='22222222-2222-4222-8222-222222222222';user='33333333-3333-4333-8333-333333333333'
headers={'Authorization':'Bearer '+env['AI_SERVICE_TOKEN'],'X-User-Id':user,'X-Household-Id':home,'Content-Type':'application/json'}
def post(path,body):
    request=urllib.request.Request(origin+path,headers=headers,data=json.dumps(body).encode())
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=8) as response:return json.load(response)
message=post('/agent/message',{'text':'帮助','request_id':'p84-legacy-help'})
assert message['status']=='answered' and message['runtime']['model_calls']==0 and message['runtime']['maintenance_release']=='V1-P8.4'
assert message['inventory_writes'] is False and message['shopping_writes'] is False
memory=post('/agent/conversation-turn',{'text':'你好','request_id':'p84-legacy-memory','context':{
    'scope':{'user_id':user,'household_id':home},'conversation_id':'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    'revision':0,'trusted_now':datetime.datetime.now(datetime.timezone.utc).isoformat()}})
assert memory['kind']=='explain' and memory['model_calls']==0
script="from integration.source_manifest import manifest\nimport json\nprint(json.dumps(manifest()))"
runtime=json.loads(subprocess.check_output(['docker','exec','magicvvu-starter-agent-1','python','-B','-c',script]))
root=pathlib.Path('/home/magicvvu_ai/workspace/agent')
assert all(hashlib.sha256((root/p).read_bytes()).hexdigest()==digest for p,digest in runtime['files'].items())
print(json.dumps({'rollback_images':rollback,'legacy_message_verified':True,'legacy_memory_verified':True,
    'legacy_model_calls':0,'production_business_writes':False,'production_tasks_or_sessions_created':False,
    'ai_runtime_and_workspace_match':True,'ai_file_count':len(runtime['files']),
    'database_container_unchanged':True,'services_healthy':True}))
'''
script=REMOTE.replace('data=PAYLOAD','data='+repr(payload))
command=['ssh','-i',str(Path.home()/'.ssh/magicvvu_ai_ed25519'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes',
    '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','magicvvu_ai@8.134.172.165','python3 -']
result=subprocess.run(command,input=script.encode(),capture_output=True,timeout=60)
if result.returncode:
    print(result.stderr.decode(errors='replace')[-1800:]);raise SystemExit(result.returncode)
value=json.loads(result.stdout)
(ROOT/'reports/p84-dialogue/production-final-check.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(value,ensure_ascii=False))
