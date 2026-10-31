import asyncio,json,sys
from pathlib import Path
import pytest,httpx
sys.path.insert(0,str(Path(__file__).resolve().parent))
from runner import Recorder,network_guard,score
from p0.budget import Budget
from p0.deepseek import DeepSeekEngine
from p0.engines import EngineError

@pytest.mark.parametrize('kind',['ok','timeout','http','bad_json','no_usage'])
def test_each_actual_request_counted_once(tmp_path,monkeypatch,kind):
    monkeypatch.setenv('DEEPSEEK_API_KEY','synthetic-test-key')
    async def fake(*args):
        if kind=='timeout':raise httpx.ReadTimeout('synthetic')
        body={'model':'synthetic-model','choices':[{'message':{'content':'wrong' if kind=='bad_json' else '{}'}}]}
        if kind!='no_usage':body['usage']={'prompt_tokens':100,'completion_tokens':10}
        return httpx.Response(429 if kind=='http' else 200,json=body)
    monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',fake)
    pricing=tmp_path/'price.json';pricing.write_text(json.dumps({'model':'deepseek-flash','input_cny_per_million':2,'output_cny_per_million':8}))
    b=Budget(tmp_path/'ledger.sqlite',pricing);b.limit=__import__('decimal').Decimal('5')
    rec=Recorder(tmp_path/'evidence','mock');e=DeepSeekEngine(b,output_parser=json.loads)
    async def go():
        with network_guard(False),rec.install(),rec.case(question_id='test'):
            if kind in {'ok','no_usage'}:await e.extract('synthetic')
            else:
                with pytest.raises(EngineError):await e.extract('synthetic')
    asyncio.run(go());assert len(rec.requests)==1 and b.summary()['calls']==1
    assert 'synthetic-test-key' not in (tmp_path/'evidence/requests.jsonl').read_text(encoding='utf-8')
    assert b.summary()['unknown_usage_calls']==(1 if kind in {'timeout','http','no_usage'} else 0)

def test_missing_key_zero_http(tmp_path,monkeypatch):
    monkeypatch.delenv('DEEPSEEK_API_KEY',raising=False)
    price=tmp_path/'p.json';price.write_text('{}');b=Budget(tmp_path/'b.sqlite',price);rec=Recorder(tmp_path/'ev')
    async def go():
        with rec.install():
            with pytest.raises(EngineError):await DeepSeekEngine(b).extract('x')
    asyncio.run(go());assert len(rec.requests)==0 and b.summary()['calls']==0

def test_wrong_quantity_not_accepted():
    checks=score({'draft':{'action':'ADD','quantity':'2'}},{'inventory_writes':False,'shopping_writes':False,'resolved':{'result':{'draft':{'action':'ADD','quantity':'1'}}}},True,None)
    assert not checks['draft.quantity']

def test_budget_gate_before_wire(tmp_path):
    p=tmp_path/'p.json';p.write_text(json.dumps({'model':'deepseek-flash','input_cny_per_million':2,'output_cny_per_million':8}));b=Budget(tmp_path/'b.sqlite',p,limit=__import__('decimal').Decimal('5'))
    with pytest.raises(EngineError,match='BUDGET_EXCEEDED'):b.reserve('deepseek-flash',3_000_000,1400)
    assert b.summary()['calls']==0
