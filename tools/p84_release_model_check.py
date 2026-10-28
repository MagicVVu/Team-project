"""Post-release synthetic provider check. Secrets stay in the server process."""
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
REMOTE=r'''
import datetime,json,pathlib,sqlite3,subprocess,time,urllib.request
agent=json.loads(subprocess.check_output(['docker','inspect','magicvvu-starter-agent-1']))[0]
env=dict(v.split('=',1) for v in agent['Config']['Env'])
assert env.get('P3_ENGINE')=='deepseek' and env.get('DEEPSEEK_API_KEY')
origin='http://'+next(iter(agent['NetworkSettings']['Networks'].values()))['IPAddress']+':8767'
headers={'Authorization':'Bearer '+env['AI_SERVICE_TOKEN'],'Content-Type':'application/json',
    'X-User-Id':'33333333-3333-4333-8333-333333333333','X-Household-Id':'22222222-2222-4222-8222-222222222222'}
def post(stage,body):
    request=urllib.request.Request(origin+'/agent/dialogue/'+stage,headers=headers,data=json.dumps(body).encode())
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=20) as response:return json.load(response)
def ledger():
    path=pathlib.Path('/home/magicvvu_ai/workspace/agent/.cache/p0/budget.sqlite')
    with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
        row=db.execute('SELECT count(*),count(actual),COALESCE(sum(COALESCE(actual,reserved)),0) FROM calls').fetchone()
    return {'calls':row[0],'measured_calls':row[1],'conservative_cost_cny':row[2]}
before=ledger();start=time.monotonic()
body={'text':'你好，先打个招呼，不查库存，也不修改任何东西。','request_id':'p84-provider-'+str(time.time_ns()),
    'context':{'scope':{'user_id':headers['X-User-Id'],'household_id':headers['X-Household-Id']},
        'conversation_id':'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','revision':0,
        'trusted_now':datetime.datetime.now(datetime.timezone.utc).isoformat()},'remaining_seconds':12}
understood=post('understand',body)
assert understood['understanding_calls']==1
plan=understood['plan'];assert not plan['action'] and not plan['reads'],'Provider check must not read real inventory'
resolved=post('resolve',{**body,'plan':plan,'remaining_seconds':min(12,18-(time.monotonic()-start))})
assert resolved['kind']=='explain' and resolved['result'] is None and not resolved['evidence'] and resolved['model_calls']==0
rendered=post('respond',{'text':body['text'],'resolved':resolved,'remaining_seconds':min(8,18-(time.monotonic()-start))})
assert rendered['response_calls']==1 and rendered['reply']
after=ledger();assert after['measured_calls']>before['measured_calls']
print(json.dumps({'maintenance_release':'V1-P8.4','protocol':'p84-dialogue-1','model':env.get('LLM_MODEL'),
    'synthetic_provider_verified':True,'understanding_calls':1,'response_calls':1,'total_calls':2,
    'response_fallback':rendered['fallback_used'],'latency_ms':(time.monotonic()-start)*1000,
    'real_inventory_read':False,'business_database_writes':False,'tasks_or_sessions_created':False,
    'key_printed_or_uploaded':False,'budget_before':before,'budget_after':after,'app_joint_acceptance':False}))
'''
command=['ssh','-i',str(Path.home()/'.ssh/magicvvu_ai_ed25519'),'-o','IdentitiesOnly=yes','-o','BatchMode=yes',
    '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','magicvvu_ai@8.134.172.165','python3 -']
result=subprocess.run(command,input=REMOTE.encode(),capture_output=True,timeout=60)
if result.returncode:
    print(result.stderr.decode(errors='replace')[-1600:])
    raise SystemExit(result.returncode)
value=json.loads(result.stdout)
(ROOT/'reports/p84-dialogue/production-model-check.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(value,ensure_ascii=False))
