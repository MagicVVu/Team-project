"""Synthetic HTTP acceptance. No service credentials; only a verified loopback tunnel."""
import argparse, concurrent.futures, hashlib, json, subprocess, time, urllib.request, urllib.error
from pathlib import Path
from uuid import uuid4

p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True); p.add_argument('--fixture', type=Path, required=True); a = p.parse_args()
a.output.mkdir(exist_ok=True, parents=True)
base = 'http://127.0.0.1:18083'
records=[]; checks={}
def call(method, path, body=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token: headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers, method=method)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=25) as response: code, raw = response.status, response.read()
    except urllib.error.HTTPError as e: code, raw = e.code, e.read()
    data=json.loads(raw); ms=(time.perf_counter() - start) * 1000
    # Authentication payloads and Bearer headers must never enter public evidence.
    if not path.startswith('/api/v1/auth/'):
        records.append({'method':method,'path':path,'request':body,'status_code':code,'response':data,'duration_ms':ms})
        (a.output/'http-acceptance-progress.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    return code,data,ms
assert call('GET','/api/v1/health')[1] == {'service':'magicvvu-backend','status':'ok','version':'0.9.0','isolated_test':True}
f = json.loads(a.fixture.read_text(encoding='utf-8-sig'))
def login(phone):
    code,data,_ = call('POST','/api/v1/auth/login',{'phone':phone,'password':f['password']}); assert code==200
    return data['access_token']
token,other,member = [login(f[k]) for k in ('phone','other_phone','member_phone')]
code,caps,_=call('GET','/api/v1/agent/execution-capabilities',token=token)
assert code==200 and caps['protocol_version']=='draft-execution-1' and caps['owner']=='business_backend'
home=f['household']
def api(method,path,body=None,who=token,expect=200,label=None):
    code,data,ms=call(method,path,body,who)
    assert code==expect, (label,path,code,data)
    return data
def inventory(): return api('GET',f'/api/v1/households/{home}/inventory-items')['items']
def paper(): return next(x for x in inventory() if x['name']=='纸巾')
def message(text,who=token):
    return api('POST','/api/v1/agent/messages',{'household_id':home,'text':text,'request_id':str(uuid4()),'household_timezone':'Asia/Shanghai'},who,label='message: '+text)
def state(t,who=token): return api('GET',f"/api/v1/drafts/{t['draft_id']}/execution",who=who,label='execution')
def body(t,edits=None,who=token):
    s=state(t,who);return {'operation_id':str(uuid4()),'task_revision':s['task_revision'],'draft_revision':s['draft_revision'],'edits':edits or {}}
def commit(t,b,who=token,expect=200): return api('POST',f"/api/v1/drafts/{t['draft_id']}/commit",b,who,expect,label='commit')
before=inventory(); q=message('冰箱里还有多少牛奶？')
assert q['status']=='answered' and not q['draft_id']
assert len(q['result']['facts'])==1 and float(q['result']['facts'][0]['quantity'])==2
assert q['result']['facts'][0]['location']=='冰箱'
assert inventory()==before; checks['query_no_business_write']=True
t=message('添加两盒牛奶。'); assert inventory()==before
b=body(t,{'name':'P5 HTTP 牛奶','location':'冰箱'}); r=commit(t,b); assert r['status']=='committed'
assert commit(t,b)==r; assert api('GET','/api/v1/operations/'+b['operation_id'])==r
checks['add_replay_recovery']=True
before=paper();t=message('把书房的纸巾移动到储藏室。'); r=commit(t,body(t))
after=paper(); assert after['quantity']==before['quantity'] and after['storage_location']=='储藏室' and after['version']==before['version']+1
checks['move_only_location_version']=True
before=paper();t=message('纸巾消耗一包。');b=body(t);r=commit(t,b)
after=paper();assert float(after['quantity'])==float(before['quantity'])-1
events=api('GET',f'/api/v1/households/{home}/consumption-events')['items']
assert sum(x['operation_id']==b['operation_id'] and x['event_type']=='Consumed' for x in events)==1
checks['consume_real_event']=True
t=message('采购清单加两包纸巾。'); before=inventory();r=commit(t,body(t))
assert r['shopping_written'] and not r['inventory_written'] and inventory()==before
assert r['result']['shopping_item']['is_checked'] is False
checks['manual_plan_only_no_stock_write']=True
t=message('纸巾消耗一包。');b=body(t);before=inventory()
api('POST',f"/api/v1/drafts/{t['draft_id']}/cancel",{k:v for k,v in b.items() if k.endswith('_revision')},label='cancel')
commit(t,b,expect=409);assert inventory()==before;checks['cancel_no_write']=True
t=message('牛奶消耗一盒。');assert t['status']=='needs_clarification'
candidates=t['result']['candidates']; assert len(candidates)==2
batch=candidates[1].get('batch_id') or candidates[1]['id']
c=api('POST',f"/api/v1/agent/clarifications/{t['task_id']}",{'revision':t['revision'],'answers':{'batch_id':batch}},label='select_second')
assert c['task_id']==t['task_id'] and c['result']['draft']['batch_id']==batch
checks['same_task_second_candidate']=True
b=body(c)
for method,path,payload in [('GET',f'/api/v1/households/{home}/inventory-items',None),('GET',f"/api/v1/agent/tasks/{c['task_id']}",None),('GET',f"/api/v1/drafts/{c['draft_id']}",None),('GET',f"/api/v1/drafts/{c['draft_id']}/execution",None),('POST',f"/api/v1/drafts/{c['draft_id']}/commit",b),('GET','/api/v1/operations/'+r['operation_id'],None)]:
    api(method,path,payload,other,404,label='foreign_denied')
api('POST',f"/api/v1/agent/clarifications/{t['task_id']}",{'revision':t['revision'],'answers':{'batch_id':batch}},other,404,label='foreign_candidate_denied')
checks['family_and_owner_isolation']=True
api('POST','/api/v1/agent/reference-messages',{'household_id':home,'text':'把它移动到厨房','request_id':str(uuid4()),'source_task_id':t['task_id'],'source_revision':t['revision'],'batch_id':batch},expect=503,label='public_reference_closed')
for text in ('纸巾昨天开封','把纸巾全部丢弃'):
    before=inventory();t=message(text)
    # The compatible AI gateway may preserve an OPEN/DISCARD preview. The
    # independent business executor, rather than AI wording, owns capability.
    if t.get('draft_id'):
        s=state(t);assert s['status']=='unavailable'
        denied=commit(t,body(t),expect=409)
        assert denied['detail']['code']=='ACTION_NOT_EXECUTABLE'
    else:
        assert t['status']=='unsupported'
    assert inventory()==before
t=message('买两包纸巾');assert t['status']=='unsupported'
checks['unsupported_no_fake_success']=True
first,second=message('纸巾消耗一包。'),message('纸巾消耗一包。',member)
b1,b2=body(first),body(second,who=member);before=paper()
with concurrent.futures.ThreadPoolExecutor(2) as pool:
    results=list(pool.map(lambda v:call('POST',f"/api/v1/drafts/{v[0]['draft_id']}/commit",v[1],v[2]),[(first,b1,token),(second,b2,member)]))
assert sorted(x[0] for x in results)==[200,409]; assert float(paper()['quantity'])==float(before['quantity'])-1
records.append({'label':'two_member_concurrent_version','results':[{'status_code':x[0],'response':x[1],'duration_ms':x[2]} for x in results]})
checks['two_member_version_conflict']=True
with concurrent.futures.ThreadPoolExecutor(2) as pool:
    messages=list(pool.map(lambda who:call('POST','/api/v1/agent/messages',{'household_id':home,'text':'纸巾还有多少','request_id':str(uuid4())},who),(token,member)))
assert all(x[0]==200 and x[1]['status']=='answered' for x in messages)
records.append({'label':'two_concurrent_messages_internal_tool_pool','results':[{'status_code':x[0],'response':x[1],'duration_ms':x[2]} for x in messages]})
checks['concurrent_ai_tool_reads_no_pool_deadlock']=True
t=message('纸巾消耗一包。'); stable=body(t); before=paper()
with concurrent.futures.ThreadPoolExecutor(2) as pool:
    same=list(pool.map(lambda _:call('POST',f"/api/v1/drafts/{t['draft_id']}/commit",stable,token),range(2)))
assert all(x[0]==200 for x in same) and same[0][1]==same[1][1]
assert float(paper()['quantity'])==float(before['quantity'])-1
assert api('GET','/api/v1/operations/'+stable['operation_id'])==same[0][1]
checks['same_draft_same_operation_concurrent_exactly_once']=True
summary={'health':call('GET','/api/v1/health')[1],'capabilities':caps,'checks':checks,'household_id':home,'records':records}
(a.output/'http-acceptance.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'checks':checks,'requests_recorded':len(records)}))
