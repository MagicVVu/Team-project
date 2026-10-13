import asyncio
from datetime import date
import json

import httpx
import pytest

from p0.budget import Budget
from p0.deepseek import DeepSeekEngine
from p0.engines import EngineError
from p0.manager import Manager
from p0.mock import MockBackend
from p0.schemas import Message, Scope
from p0.tools import RemoteInventoryReader


@pytest.mark.parametrize("http_status,content,code", [(200,"","EMPTY_MODEL_OUTPUT"),(200,'{"intent":"BAD"}',"INVALID_MODEL_OUTPUT"),(429,None,"MODEL_HTTP_429")])
def test_provider_failure_single_call_budget_and_no_writes(tmp_path,monkeypatch,http_status,content,code):
    pricing=tmp_path/"price.json"
    pricing.write_text(json.dumps({"model":"deepseek-flash","verified_on":date.today().isoformat(),"input_cny_per_million":2,"output_cny_per_million":8}))
    budget=Budget(tmp_path/"budget.sqlite",pricing)
    monkeypatch.setenv("DEEPSEEK_API_KEY","unit-test-not-a-real-key")
    calls=[]
    async def handler(request):
        calls.append(request)
        body=json.loads(request.content)
        assert body["thinking"]["type"]=="disabled"
        assert body["response_format"]["type"]=="json_object"
        return httpx.Response(http_status,json={"choices":[{"message":{"content":content}}],"usage":{"prompt_tokens":100,"completion_tokens":20}})
    real_client=httpx.AsyncClient
    monkeypatch.setattr("p0.deepseek.httpx.AsyncClient",lambda **kwargs:real_client(transport=httpx.MockTransport(handler),**kwargs))
    store=MockBackend()
    result=asyncio.run(Manager(DeepSeekEngine(budget),store).handle(Message(text="买了2盒牛奶",request_id="test"),Scope(user_id="u1",household_id="h1")))
    assert result.status=="error" and result.error_code==code
    assert result.manual_entry and result.original_text=="买了2盒牛奶"
    assert len(calls)==1 and budget.summary()["calls"]==1
    assert store.state["events"]==[]


def test_wall_clock_timeout_retains_input_and_no_writes(monkeypatch):
    class Slow:
        async def extract(self,text):
            await asyncio.sleep(10)
    original=asyncio.timeout
    monkeypatch.setattr("p0.manager.asyncio.timeout",lambda seconds:original(.01))
    store=MockBackend()
    result=asyncio.run(Manager(Slow(),store).handle(Message(text="买了2盒牛奶",request_id="test"),Scope(user_id="u1",household_id="h1")))
    assert result.error_code=="MODEL_TIMEOUT" and result.manual_entry
    assert store.state["events"]==[]


def test_remote_reader_forwards_authenticated_scope_and_rejects_wrong_household(monkeypatch):
    async def handler(request):
        assert request.headers["Authorization"]=="Bearer tool-token"
        assert request.headers["X-User-Id"]=="u1"
        assert request.headers["X-Household-Id"]=="h1"
        return httpx.Response(200,json={"data":{"batches":[{"id":"private","household_id":"h2","name":"牛奶","quantity":2,"unit":"盒","version":1}]}})
    real_client=httpx.AsyncClient
    monkeypatch.setattr("p0.tools.httpx.AsyncClient",lambda **kwargs:real_client(transport=httpx.MockTransport(handler),**kwargs))
    from p0.domain import DomainError
    with pytest.raises(DomainError) as error:
        asyncio.run(RemoteInventoryReader("http://backend","tool-token").search(Scope(user_id="u1",household_id="h1"),"牛奶"))
    assert error.value.code=="HOUSEHOLD_FORBIDDEN"
