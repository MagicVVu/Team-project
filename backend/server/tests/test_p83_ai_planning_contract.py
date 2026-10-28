"""P8.3 reader against the real backend serializer and isolated database."""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys
from uuid import uuid4

from test_v09_execution import execution_state, headers
from test_backend_p4_planning import planning, get
from test_p9_integration import product, link, add_batch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]/"agent"))
from conversation.planning_schemas import BackendSnapshot
from conversation.planning import checked_snapshot
from conversation.manager import Manager
from conversation.engines import RuleEngine
from p0.schemas import Scope
from p2.knowledge import RuleCatalog
from p3.schemas import Query


def test_decimal_export_comparison_preserves_business_constraints():
    import pytest
    from contract_compatibility import assert_backend_contract
    old = {'anyOf':[{'type':'number', 'minimum':0}, {'type':'string'}]}
    local = {'anyOf':[{'type':'number', 'minimum':0}, {'type':'string','pattern':r'^(?!^[-+.]*$)[+-]?0*\d+'}]}
    assert_backend_contract(old, local)
    with pytest.raises(AssertionError):
        assert_backend_contract(old, {'anyOf':[{'type':'number','minimum':-1},{'type':'string'}]})
    with pytest.raises(AssertionError):
        assert_backend_contract({'type':'string','pattern':'uuid-rule'}, {'type':'string','pattern':'changed'})


def test_actual_product_snapshot_is_accepted_without_stock_writes(planning):
    client, Session, ids = planning
    other = add_batch(Session, ids)
    p = product(client, ids)
    link(client, ids, ids['batch'], p['product_id'])
    link(client, ids, other, p['product_id'])
    payload = get(planning).json()
    scope = Scope(user_id=str(ids['user']), household_id=str(ids['home']))
    snapshot = BackendSnapshot.model_validate({**payload['data'], 'provenance':payload['provenance']})
    checked_snapshot(snapshot, scope)
    class Reader:
        async def planning_context(self, scope, **kw): return snapshot.model_copy(deep=True)
    manager = Manager(RuleEngine(), Reader(), RuleCatalog.load(), now=lambda: snapshot.as_of)
    result = asyncio.run(manager.query(Query(item_key='product:'+p['product_id']), scope, 'QUERY_FORECAST'))
    assert result.status == 'answered', result
    assert result.product_planning[0].product.total_quantity == 8
    assert result.product_planning[0].product.usable_quantity is None
    assert not result.inventory_writes and not result.shopping_writes
    after = get(planning).json()
    assert payload['data']['items'] == after['data']['items']
    assert payload['provenance']['revalidation_basis'] == after['provenance']['revalidation_basis']


def test_actual_unmapped_pending_does_not_disappear_in_ai(planning):
    client, Session, ids = planning
    response = client.post(f'/api/v1/households/{ids["home"]}/shopping-list/items', headers=headers(),
        json={'name':'牛奶', 'quantity':'2', 'unit':'盒'})
    assert response.status_code == 201
    payload = get(planning).json()
    scope = Scope(user_id=str(ids['user']), household_id=str(ids['home']))
    snapshot = BackendSnapshot.model_validate({**payload['data'], 'provenance':payload['provenance']})
    checked_snapshot(snapshot, scope)
    class Reader:
        async def planning_context(self, scope, **kw): return snapshot.model_copy(deep=True)
    manager = Manager(RuleEngine(), Reader(), RuleCatalog.load(), now=lambda:snapshot.as_of)
    result = asyncio.run(manager.query(Query(), scope, 'SUGGEST_PURCHASE'))
    assert result.planning_context.pending_state == 'association_unknown'
    assert result.planning_context.pending_count == 1
    assert result.draft is None
    assert all(v.pending_quantity is None for v in result.recommendations)


def test_new_ai_http_reader_uses_real_backend_envelope_get_only(planning, monkeypatch):
    import httpx
    from app.main import app as backend
    from conversation.app import create_app
    from conversation.planning import RemoteReader
    client, Session, ids = planning
    p = product(client, ids)
    link(client, ids, ids['batch'], p['product_id'])
    before = get(planning).json()
    monkeypatch.setenv('AI_SERVICE_TOKEN', 'p83-fixture-service')
    ai = create_app(reader=RemoteReader('http://fixture-backend', 'synthetic-p4-tool-token-not-a-production-secret'), engine=RuleEngine())
    original, requests = httpx.AsyncClient, []
    transport = httpx.ASGITransport(app=backend)
    async def dispatch(request):
        requests.append((request.method, request.url.path))
        return await transport.handle_async_request(request)
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw:original(transport=httpx.MockTransport(dispatch)))
    async def invoke():
        async with original(transport=httpx.ASGITransport(app=ai), base_url='http://fixture-ai') as api:
            return await api.post('/forecast/evaluate', json={'item_key':'product:'+p['product_id']},
                headers={'Authorization':'Bearer p83-fixture-service','X-User-Id':str(ids['user']),'X-Household-Id':str(ids['home'])})
    response = asyncio.run(invoke())
    assert response.status_code == 200, response.text
    assert response.json()['product_planning'][0]['product']['total_quantity'] == '5.000000'
    assert requests == [('GET','/internal/v1/planning/context')]
    after = get(planning).json()
    assert before['data']['items'] == after['data']['items']
    assert before['provenance']['revalidation_basis'] == after['provenance']['revalidation_basis']
