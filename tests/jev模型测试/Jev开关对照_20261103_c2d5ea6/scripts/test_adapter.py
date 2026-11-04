"""Meaningful pre-paid checks: effective switches, real route, faults, logging, cap."""
import asyncio,json
from decimal import Decimal
from pathlib import Path
import pytest,httpx
import ab
from jev.providers import MockProvider
from jev.runtime import Router
from jev.schemas import JevError
from p0.engines import EngineError
from telemetry import Recorder,network_guard
import budget_pair

def run(coro):return asyncio.run(coro)

def test_actual_factory_switches_and_same_preconditions():
    snapshots=[]
    for mode in ['off','assist']:
        owner,ctx,reader,clock,archive=ab.state('none',ab.old.Oracle())
        snapshots.append({'context':ctx.model_dump(mode='json'),'inventory':reader.data.model_dump(mode='json')})
        app,value=ab.application((owner,ctx,reader,clock,archive),mode,Router(MockProvider()))
        assert (value[0].jev_router is not None)==(mode=='assist')
        async def health():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://local') as c:return (await c.get('/health')).json()
        info=run(health());assert info['jev_mode']==mode and info['maintenance_release']=='V1-P8.7'
    assert snapshots[0]==snapshots[1]

def test_simple_read_really_routes_without_deepseek(tmp_path):
    semantic=ab.old.Oracle();semantic.decision=ab.old.Decision(action='ask',clarification='object')
    app,value=ab.application(ab.state('none',semantic),'assist',Router(MockProvider()))
    row={'id':'route','group_id':'Jev','category':'route','text':'牛奶在哪里','expected':{'no_draft':True,'facts':['冰箱']}}
    rec=Recorder(tmp_path,'mock')
    with network_guard(False),rec.install():out=run(ab.question(row,value,app,rec))
    assert out['status']=='PASS',out['checks']
    assert any(a['status']=='routed_read' for a in out['jev_audit'])
    assert out['output']['model_calls']==0 and not rec.requests

@pytest.mark.parametrize('failure',['MODEL_NOT_CONFIGURED','BUDGET_EXCEEDED','INVALID_MODEL_OUTPUT','timeout'])
def test_jev_failure_falls_back_without_write(tmp_path,failure):
    class Fails:
        source='mock'
        async def ask(self,payload,trace):
            if failure=='timeout':raise TimeoutError()
            raise JevError(failure)
    semantic=ab.old.Oracle();semantic.decision=ab.old.Decision(action='ask',clarification='object')
    app,value=ab.application(ab.state('none',semantic),'assist',Router(Fails()))
    row={'id':'fallback','group_id':'Jev','category':'fault','text':'牛奶在哪里','expected':{'no_draft':True}}
    with network_guard(False):out=run(ab.question(row,value,app,Recorder(tmp_path)))
    assert out['local_http_status']==200 and out['inventory_unchanged']
    assert out['jev_audit'][0]['status']=='fallback'
    assert out['output']['status']=='needs_input'

def test_corrected_archive_and_empty_fixture():
    ab.state('archive',ab.old.Oracle())
    _,ctx,reader,_,_=ab.state('empty_absent',ab.old.Oracle())
    assert not reader.data.items and not reader.data.pending

@pytest.mark.parametrize('response_kind',['success','http_error','format_error','timeout'])
def test_wire_recorder_counts_and_redacts_both_providers(tmp_path,monkeypatch,response_kind):
    monkeypatch.setenv('DEEPSEEK_API_KEY','synthetic-deep-key');monkeypatch.setenv('TYPESAFE_API_KEY','synthetic-jev-key')
    async def fake(transport,request):
        if response_kind=='timeout':raise httpx.ReadTimeout('synthetic',request=request)
        if response_kind=='format_error':return httpx.Response(200,content=b'not json',request=request)
        return httpx.Response(500 if response_kind=='http_error' else 200,json={'model':'synthetic','usage':{'input_tokens':1},'echo':'synthetic-deep-key synthetic-jev-key'},request=request)
    monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',fake)
    rec=Recorder(tmp_path,'synthetic')
    async def calls():
        async with httpx.AsyncClient() as c:
            for url in ['https://api.deepseek.com/chat/completions','https://api.typesafe.ai/v1/systemone']:
                try:await c.post(url,json={'text':'synthetic-deep-key synthetic-jev-key'})
                except httpx.ReadTimeout:pass
    with rec.install():run(calls())
    assert len(rec.requests)==2 and {r['provider'] for r in rec.requests}=={'deepseek','jev'}
    text=(tmp_path/'requests.jsonl').read_text(encoding='utf-8')
    assert 'synthetic-deep-key' not in text and 'synthetic-jev-key' not in text

def test_combined_cap_includes_unsettled_both_currencies(tmp_path,monkeypatch):
    monkeypatch.setattr(budget_pair,'PRIVATE',tmp_path)
    book=budget_pair.Combined();first=book.reserve('deepseek',Decimal('9'))
    with pytest.raises(EngineError):book.reserve('jev',Decimal('1.000001'))
    assert book.summary()['charged_or_reserved_cny']=='9'
    book.update(first,actual=Decimal('1'))
    book.reserve('jev',Decimal('9'))
    with pytest.raises(EngineError):book.reserve('deepseek',Decimal('.000001'))
    assert book.summary()['charged_or_reserved_cny']=='10'

def test_fixture_failures_are_not_silently_scored_as_model_failures():
    for kind,row in ab.units():
        value=ab.state(row['profile'],ab.old.Oracle())
        # Validate all non-cross-scope requests before any paid run.
        if row['profile']=='foreign':continue
        _,ctx,_,_,archive=value
        turns=row['turns'] if kind=='multi' else [row]
        for t in turns:
            ab.old.RunRequest(text=t['text'],request_id=row['id'],context=ctx,archive=ab.P85Archive(scope=ab.old.SCOPE,conversation_id=ctx.conversation_id,revision=ctx.revision,episodes=archive))
