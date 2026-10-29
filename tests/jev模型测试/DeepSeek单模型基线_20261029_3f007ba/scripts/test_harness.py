import asyncio, json, os, socket, sys
from datetime import datetime
from pathlib import Path
from decimal import Decimal
import httpx,pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from run import Recorder,network_guard,checks,oracle,rows,make_budget
from p0.deepseek import DeepSeekEngine
from p0.budget import Budget
from p0.engines import EngineError
from summarize import cost,distribution,ci
from audit_existing import audit
from scoring import classify

@pytest.mark.parametrize('mode', ['success','http_error','timeout','bad_json','empty','missing_usage'])
def test_wire_record_and_ledger(tmp_path,monkeypatch,mode):
    # Stub HTTP transport: zero external connections, native engine/parser/budget remain active.
    monkeypatch.setenv('DEEPSEEK_API_KEY','synthetic-test-key-never-a-credential')
    async def fake(transport,request):
        if mode=='timeout': raise httpx.ReadTimeout('synthetic timeout')
        data={'id':'synthetic-id','model':'synthetic-test-model','usage':{'prompt_tokens':100,'completion_tokens':10,'prompt_cache_hit_tokens':20,'prompt_cache_miss_tokens':80},
            'choices':[{'message':{'content':'{"intent":"ADD"}'}}]}
        if mode=='bad_json': data['choices'][0]['message']['content']='this is not JSON'
        if mode=='empty': data['choices'][0]['message']['content']=''
        if mode=='missing_usage': data.pop('usage')
        return httpx.Response(429 if mode=='http_error' else 200,json=data,request=request)
    monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',fake)
    pricing=tmp_path/'pricing.json'; pricing.write_text(json.dumps({'model':'deepseek-flash','input_cny_per_million':2,'output_cny_per_million':8}),encoding='utf-8')
    budget=Budget(tmp_path/'ledger.sqlite',pricing)
    recorder=Recorder(tmp_path/'evidence','mock')
    engine=DeepSeekEngine(budget,output_parser=json.loads)
    async def go():
        with network_guard(False),recorder.install(),recorder.case(batch='mock-test',turn_id='mock-1'),recorder.stage('understanding'):
            if mode in {'success','missing_usage'}: assert (await engine.extract('synthetic'))['intent']=='ADD'
            else:
                with pytest.raises(EngineError): await engine.extract('synthetic')
    asyncio.run(go())
    assert len(recorder.requests)==1 and len(recorder.extractions)==1
    event=recorder.requests[0]
    assert event['engine_call_id']==recorder.extractions[0]['engine_call_id']
    assert event['stage']=='understanding' and event['turn_id']=='mock-1'
    assert 'authorization' not in json.dumps(event).lower()
    assert 'synthetic-test-key-never-a-credential' not in (tmp_path/'evidence/requests.jsonl').read_text(encoding='utf-8')
    assert budget.summary()['calls']==1
    if mode in {'timeout','http_error','missing_usage'}: assert budget.summary()['unknown_usage_calls']==1
    else: assert budget.summary()['unknown_usage_calls']==0

def test_no_key_no_wire(tmp_path,monkeypatch):
    monkeypatch.delenv('DEEPSEEK_API_KEY',raising=False)
    price=tmp_path/'pricing.json'; price.write_text('{}',encoding='utf-8')
    budget=Budget(tmp_path/'budget.sqlite',price); rec=Recorder(tmp_path/'events')
    async def go():
        with rec.install():
            with pytest.raises(EngineError,match='MODEL_NOT_CONFIGURED'): await DeepSeekEngine(budget).extract('hello')
    asyncio.run(go()); assert len(rec.requests)==0 and budget.summary()['calls']==0

def test_network_blocked():
    async def go():
        with network_guard(False):
            with pytest.raises(RuntimeError,match='NETWORK_DNS_BLOCKED'): socket.getaddrinfo('api.deepseek.com',443)
            with pytest.raises(RuntimeError,match='NETWORK_CONNECTION_BLOCKED'):
                with socket.socket() as s: s.connect(('127.0.0.1',18080))
    asyncio.run(go())

def test_live_guard_allows_only_deepseek(monkeypatch):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('192.0.2.1',443))])
    with network_guard(True):
        assert socket.getaddrinfo('api.deepseek.com',443)[0][4][0]=='192.0.2.1'
        with pytest.raises(RuntimeError): socket.getaddrinfo('example.com',443)
        with pytest.raises(RuntimeError): socket.socket().connect(('127.0.0.1',5432))

def test_no_loosened_field_scoring():
    expected={'draft':{'action':'CONSUME','quantity':'2','unit':'盒','batch_id':'b1'}}
    frame={'result':{'draft':{'action':'CONSUME','quantity':'1','unit':'盒','batch_id':'b1'}}}
    result=checks(expected,frame)
    assert result['draft.quantity'] is False and result['draft.action'] is True

def test_cost_cache_and_unknown():
    event={'started_at':'2026-10-29T02:00:00+00:00','finished_at':'2026-10-29T02:00:01+00:00',
        'usage':{'prompt_tokens':100,'completion_tokens':10,'prompt_cache_hit_tokens':20,'prompt_cache_miss_tokens':80}}
    assert Decimal(cost(event)['cny'])==Decimal('0.0002408')
    assert cost({'usage':None})['cny'] is None
    event['usage'].pop('prompt_cache_hit_tokens'); assert cost(event)['cny'] is None

def test_metrics_denominators():
    assert distribution([])['p95'] is None
    assert distribution([1,2,3,4,5])['p95']==5
    assert ci([{'group_id':'g','status':'PASS'}]*100) is None

def test_frozen_sample_counts():
    assert len(rows('new-single'))==120
    assert len(rows('new-multi'))==20
    assert all(len(r['turns'])==6 for r in rows('new-multi'))
    assert all(r['human_review_status']=='pending' for r in rows('new-single'))

def test_cap_survives_reopen(tmp_path,monkeypatch):
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    first=make_budget(); assert first.limit==Decimal('5')
    call,_,prices=first.reserve('deepseek-flash',100,10); first.settle(call,{'prompt_tokens':100,'completion_tokens':10},prices)
    reopened=make_budget(); assert reopened.limit==Decimal('5') and reopened.summary()['calls']==1
    with pytest.raises(EngineError,match='BUDGET_EXCEEDED'): reopened.reserve('deepseek-flash',3_000_000,100)

def test_supplemental_audit_preserves_original_but_catches_wrong_quantity():
    row={'id':'p84-08-2','status':'PASS','inventory_unchanged_by_ai':True,
        'frame':{'result':{'status':'needs_confirmation','draft':{'action':'CONSUME','batch_id':'b1','quantity':'1','unit':'盒','expected_version':4}}}}
    extra=audit(row)
    assert row['status']=='PASS' and not extra['passed'] and 'draft.quantity' in extra['failed_checks']

def test_preflight_budget_failure_is_blocked():
    assert classify({}, {}, {'no_exception':False}, 'BUDGET_EXCEEDED')[0]=='BLOCKED'

def test_unknown_usage_not_free():
    from summarize import summarize
    value=summarize([], [{'usage':None,'http_status':None,'transport_error':'ReadTimeout','latency_ms':100,'response':None}], [])
    assert value['known_calculated_cost_cny'] is None and value['cost_unknown_or_inexact_requests']==1

def test_snapshot_restore_checks_exact_windows_newlines():
    import hashlib
    from restore_snapshot import frozen_bytes
    desired=b'a\r\nb\r\n'
    assert frozen_bytes(b'a\nb\n',hashlib.sha256(desired).hexdigest())==desired
    with pytest.raises(RuntimeError):frozen_bytes(b'changed',hashlib.sha256(desired).hexdigest())
