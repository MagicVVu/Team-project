"""Exact 2 -> 1.5 -> +1.5 cloud business flow on disposable SQLite."""
import json,pathlib,sys
from decimal import Decimal
from uuid import uuid4
ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'.snapshot/backend/server/tests'))
from test_v07_shopping import state,headers,base

def test_garin_inventory_purchase_and_retry_reference(state):
    client,Session,ids=state;trace=[]
    stock_url=f"/api/v1/households/{ids['home']}/inventory-items"
    def call(method,url,**kw):
        r=client.request(method,url,headers=kw.pop('headers',headers()),**kw)
        trace.append({'method':method,'path':url,'request':kw.get('json'),'http':r.status_code,'response':r.json() if r.content else None})
        return r
    try:
        stock=call('POST',stock_url,json={'id':str(uuid4()),'name':'牛奶','quantity':'2','unit':'盒','category':'食品','storage_location':'冰箱','minimum_quantity':'3'})
        assert stock.status_code==201
        item=stock.json();adjustment={'expected_version':item['version'],'operation_id':str(uuid4()),'delta':'-0.5'}
        url=stock_url+'/'+item['id']+'/adjustments'
        first=call('POST',url,json=adjustment);assert first.status_code==200 and Decimal(first.json()['quantity'])==Decimal('1.5')
        again=call('POST',url,json=adjustment);assert again.status_code==200 and Decimal(again.json()['quantity'])==Decimal('1.5')
        stale=call('POST',url,json={**adjustment,'operation_id':str(uuid4())});assert stale.status_code==409
        planned=call('POST',base(ids)+'/items',json={'id':str(uuid4()),'name':'牛奶','quantity':'2','unit':'盒','source_inventory_item_id':item['id']})
        assert planned.status_code==201
        purchase_url=base(ids)+'/items/'+planned.json()['id']+'/purchase'
        bought=call('POST',purchase_url,json={'actual_quantity':'1.5','storage_location':'厨房'});assert bought.status_code==200 and bought.json()['newly_stocked']
        retry=call('POST',purchase_url,json={'actual_quantity':'20','storage_location':'其他位置'})
        assert retry.status_code==200 and not retry.json()['newly_stocked'] and retry.json()['inventory_item']['id']==bought.json()['inventory_item']['id']
        final=call('GET',stock_url).json()
        assert len(final['items'])==2 and sum(Decimal(x['quantity']) for x in final['items'])==3
        assert bought.json()['inventory_item']['id']!=item['id']
        purchased=call('GET',base(ids)+'/items?status=purchased').json();assert len(purchased['items'])==1
        assert call('GET',stock_url,headers=headers('outsider')).status_code==404
    finally:
        with (ROOT/'evidence/backend-special-http.jsonl').open('w',encoding='utf-8') as f:
            for row in trace:f.write(json.dumps(row,ensure_ascii=False)+'\n')
