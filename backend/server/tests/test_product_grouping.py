"""Explicit product classification over real routes and isolated database sessions."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, func

from test_v09_execution import execution_state, headers, seed_draft, body, post, PG
from app.models import InventoryItem, ShoppingListItem
from app.product_models import Product, ProductBatch, MutationReceipt
from app.services.product_grouping import name_match
from app.inventory_schemas import InventoryCreate
from app.shopping_schemas import StockResponse
from app.execution_models import BusinessEvent


def root(ids):
    return f'/api/v1/households/{ids["home"]}'


def payload(**changes):
    return {'id': str(uuid4()), 'name': '牛奶', 'quantity': '2.000001', 'unit': '盒',
            'category': 'food', 'storage_location': '冰箱', 'expires_on': '2026-12-01', **changes}


def create(client, ids, value):
    return client.post(root(ids)+'/inventory-items', headers=headers(), json=value)


def choice(candidate, version=1, product_version=None):
    return {'mode': 'existing', 'candidate_inventory_item_id': str(candidate),
            'expected_inventory_version': version, 'expected_product_version': product_version}


@pytest.mark.parametrize('left,right,matched', [
    ('牛奶', '牛奶', True), ('牛', '牛', True), ('纯牛奶', '牛奶饮料', True),
    ('牛奶', '牛肉奶粉', False), ('牛奶', '牛肉', False), ('ab', 'a b', False),
    (' ＭＩＬＫ ', 'milk', True), ('𠀀𠀁', '𠀀𠀁饮料', True), ('abc', 'axbyc', False),
])
def test_unicode_contiguous_name_matching(left, right, matched):
    assert (name_match(left, right) is not None) == matched


def test_candidates_are_scoped_and_paginated_without_hiding_unlinked_or_ended(execution_state):
    client, Session, ids = execution_state
    with Session.begin() as db:
        for name, home, status in [('纯牛奶', ids['home'], 'ACTIVE'), ('牛奶饮料', ids['home'], 'FINISHED'),
                                   ('牛肉奶粉', ids['home'], 'ACTIVE'), ('纯牛奶', ids['foreign_home'], 'ACTIVE')]:
            db.add(InventoryItem(id=uuid4(), household_id=home, name=name, quantity=1,
                                 unit='盒', status=status, version=1))
    path=root(ids)+'/inventory-product-matches'
    with Session() as db:
        before=[db.scalar(select(func.count()).select_from(model)) for model in
                (Product,ProductBatch,MutationReceipt,BusinessEvent)]
    first=client.get(path, params={'name':'牛奶','limit':1}, headers=headers())
    assert first.status_code==200, first.text
    assert first.headers['cache-control']=='no-store'
    page=first.json()
    assert page['total']==3 and page['next_offset']==1
    assert page['items'][0]['name']=='牛奶' and page['items'][0]['match_type']=='exact'
    assert page['items'][0]['product_id'] is None
    rows=client.get(path,params={'name':'牛奶'},headers=headers()).json()['items']
    assert {x['name'] for x in rows}=={'牛奶','纯牛奶','牛奶饮料'}
    assert client.get(path,params={'name':'牛奶'},headers=headers('outsider')).status_code==404
    assert client.get(path,params={'name':'牛奶'}).status_code==401
    with Session() as db:
        assert before==[db.scalar(select(func.count()).select_from(model)) for model in
                        (Product,ProductBatch,MutationReceipt,BusinessEvent)]


@pytest.mark.parametrize('explicit', [False, True])
def test_no_or_no_match_creates_separate_singleton_and_replays(execution_state, explicit):
    client, Session, ids=execution_state
    value=payload(name='牛奶' if explicit else '与候选不同名')
    if explicit:
        value['product_grouping']={'mode':'separate'}
    result=create(client,ids,value)
    assert result.status_code==201, result.text
    assert create(client,ids,value).json()==result.json()
    with Session() as db:
        products=db.scalars(select(Product)).all()
        assert len(products)==1
        p=products[0]
        assert (p.name,p.base_unit,p.category)==(value['name'],'盒','food')
        assert db.get(ProductBatch,UUID(value['id'])).product_id==p.id
        assert db.get(ProductBatch,ids['batch']) is None
        assert db.scalar(select(func.count()).select_from(MutationReceipt))==1


def test_yes_classifies_unlinked_candidate_and_uses_shortest_original_name(execution_state):
    client, Session, ids=execution_state
    with Session.begin() as db: db.get(InventoryItem,ids['batch']).name='纯牛奶饮料'
    value=payload(name='牛奶', product_grouping=choice(ids['batch']))
    result=create(client,ids,value)
    assert result.status_code==201, result.text
    assert create(client,ids,value).json()==result.json()
    with Session() as db:
        product=db.scalar(select(Product))
        assert product.name=='牛奶'
        assert db.get(ProductBatch,ids['batch']).product_id==product.id
        assert db.get(ProductBatch,UUID(value['id'])).product_id==product.id
        assert db.get(InventoryItem,ids['batch']).name=='纯牛奶饮料'
        assert db.get(InventoryItem,ids['batch']).version==2
        assert db.scalar(select(func.count()).select_from(Product))==1
    altered=create(client,ids,{**value,'product_grouping':{'mode':'separate'}})
    assert altered.status_code==409


@pytest.mark.parametrize('permanent_receipt',[False,True])
def test_pre_upgrade_create_hash_and_original_receipt_are_still_replayable(execution_state,permanent_receipt):
    client, Session, ids=execution_state
    value=payload(id=str(ids['batch']),quantity='5')
    old_fields=InventoryCreate.model_validate(value).model_dump(mode='json',exclude={'product_grouping'})
    old_hash=hashlib.sha256(('create'+json.dumps(old_fields,sort_keys=True)).encode()).hexdigest()
    with Session.begin() as db:
        batch=db.get(InventoryItem,ids['batch'])
        batch.history_json=[{'id':str(batch.id),'hash':old_hash,'kind':'create'}]
        if permanent_receipt:
            db.add(MutationReceipt(operation_id=batch.id,household_id=ids['home'],actor_user_id=ids['user'],
                request_hash=old_hash,response_json=StockResponse.model_validate(batch).model_dump(mode='json')))
    with patch('app.services.product_grouping.classify_new',side_effect=AssertionError('Must not reclassify a replay')):
        result=create(client,ids,value)
    assert result.status_code==201,result.text
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(Product))==0
        assert db.scalar(select(func.count()).select_from(InventoryItem))==1


def test_event_failure_rolls_back_new_batch_product_and_candidate_version(execution_state):
    client, Session, ids=execution_state
    value=payload(product_grouping=choice(ids['batch']))
    with patch('app.services.ledger.append',side_effect=RuntimeError('injected event failure')):
        result=create(client,ids,value)
    assert result.status_code==500
    with Session() as db:
        assert db.get(InventoryItem,UUID(value['id'])) is None
        assert db.get(InventoryItem,ids['batch']).version==1
        assert db.scalar(select(func.count()).select_from(Product))==0
        assert db.scalar(select(func.count()).select_from(ProductBatch))==0
        assert db.scalar(select(func.count()).select_from(MutationReceipt))==0
    assert create(client,ids,value).status_code==201


def test_legacy_long_candidate_can_join_under_valid_new_short_name(execution_state):
    client, Session, ids=execution_state
    with Session.begin() as db: db.get(InventoryItem,ids['batch']).name='纯牛奶'+('饮料'*45)
    value=payload(product_grouping=choice(ids['batch']))
    result=create(client,ids,value)
    assert result.status_code==201, result.text
    with Session() as db:
        assert db.scalar(select(Product)).name=='牛奶'
        assert len(db.get(InventoryItem,ids['batch']).name)>80


def test_previously_unlinked_singleton_can_be_selected_again(execution_state):
    client, Session, ids=execution_state
    first=payload(name='纯牛奶'); assert create(client,ids,first).status_code==201
    with Session() as db: old_product=db.get(ProductBatch,UUID(first['id'])).product_id
    unlinked=client.put(root(ids)+'/inventory-items/'+first['id']+'/product',headers=headers(),json={
        'operation_id':str(uuid4()),'expected_inventory_version':1,'product_id':None,'source':'用户明确解除关联'})
    assert unlinked.status_code==200,unlinked.text
    second=payload(product_grouping=choice(first['id'],version=2))
    grouped=create(client,ids,second)
    assert grouped.status_code==201,grouped.text
    with Session() as db:
        link=db.get(ProductBatch,UUID(first['id']))
        assert link.product_id!=old_product
        assert db.get(ProductBatch,UUID(second['id'])).product_id==link.product_id
        assert db.get(Product,link.product_id).name=='牛奶'


def test_existing_product_is_reused_with_all_member_shortest_name_and_version(execution_state):
    client, Session, ids=execution_state
    first=payload(name='纯牛奶饮料')
    assert create(client,ids,first).status_code==201
    match=client.get(root(ids)+'/inventory-product-matches',params={'name':'纯牛奶'},headers=headers()).json()['items']
    selected=next(x for x in match if x['inventory_item_id']==first['id'])
    assert selected['product_name']=='纯牛奶饮料' and selected['product_version']==1
    second=payload(name='纯牛奶',product_grouping=choice(first['id'],product_version=1))
    assert create(client,ids,second).status_code==201
    third=payload(name='牛奶饮品',product_grouping=choice(first['id'],product_version=2))
    assert create(client,ids,third).status_code==201
    with Session() as db:
        product=db.scalar(select(Product))
        assert product.name=='纯牛奶' and product.version==3
        assert db.scalar(select(func.count()).select_from(ProductBatch))==3
    # Candidate's batch version did not change, but its group's membership changed.
    stale=create(client,ids,payload(product_grouping=choice(first['id'],product_version=1)))
    assert stale.status_code==409 and stale.json()['detail']['code']=='GROUPING_PRODUCT_CHANGED'


@pytest.mark.parametrize('problem,code,status',[
    ('version','GROUPING_CANDIDATE_CHANGED',409),
    ('name','GROUPING_NAME_NO_LONGER_MATCHES',409),
    ('foreign','GROUPING_CANDIDATE_NOT_FOUND',404),
    ('product','GROUPING_PRODUCT_CHANGED',409),
])
def test_stale_or_invalid_choice_rolls_back_both_new_batch_and_group(execution_state,problem,code,status):
    client, Session, ids=execution_state
    with Session.begin() as db:
        candidate=db.get(InventoryItem,ids['batch'])
        if problem=='version': candidate.version+=1
        elif problem=='name': candidate.name='苹果'
        elif problem=='foreign': candidate.household_id=ids['foreign_home']
    value=payload(product_grouping=choice(ids['batch'],product_version=1 if problem=='product' else None))
    result=create(client,ids,value)
    assert result.status_code==status, result.text
    assert result.json()['detail']['code']==code
    with Session() as db:
        assert db.get(InventoryItem,UUID(value['id'])) is None
        assert db.scalar(select(func.count()).select_from(Product))==0
        assert db.scalar(select(func.count()).select_from(ProductBatch))==0
        assert db.scalar(select(func.count()).select_from(MutationReceipt))==0


def test_choice_validation_and_long_name_never_leaves_an_unlinked_new_batch(execution_state):
    client, Session, ids=execution_state
    for grouping in ({'mode':'existing'}, {'mode':'separate','candidate_inventory_item_id':str(ids['batch'])}):
        assert create(client,ids,payload(product_grouping=grouping)).status_code==422
    result=create(client,ids,payload(name='超'*81))
    assert result.status_code==422 and result.json()['detail']['code']=='PRODUCT_NAME_TOO_LONG'
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(InventoryItem))==1
        assert db.scalar(select(func.count()).select_from(Product))==0


def test_inventory_rename_recomputes_product_shortest_name(execution_state):
    client, Session, ids=execution_state
    first=payload(name='纯牛奶'); assert create(client,ids,first).status_code==201
    second=payload(name='纯牛奶饮料', product_grouping=choice(first['id'],product_version=1))
    assert create(client,ids,second).status_code==201
    edit=client.patch(root(ids)+'/inventory-items/'+first['id'],headers=headers(),json={
        'operation_id':str(uuid4()),'expected_version':1,'name':'纯牛奶加长包装'})
    assert edit.status_code==200, edit.text
    with Session() as db: assert db.scalar(select(Product)).name=='纯牛奶饮料'


def test_shopping_and_draft_add_create_product_without_name_merging(execution_state):
    client, Session, ids=execution_state
    shopping=client.post(root(ids)+'/shopping-list/items',headers=headers(),json={
        'name':'牛奶','quantity':'2','unit':'盒'}).json()
    bought=client.post(root(ids)+'/shopping-list/items/'+shopping['id']+'/purchase',headers=headers(),json={})
    assert bought.status_code==200, bought.text
    assert client.post(root(ids)+'/shopping-list/items/'+shopping['id']+'/purchase',headers=headers(),json={}).json()['newly_stocked'] is False
    draft,_=seed_draft(Session,ids,'ADD',name='牛奶')
    request=body()
    added=post(client,draft,request)
    assert added.status_code==200,added.text
    assert post(client,draft,request).json()==added.json()
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(Product))==2
        assert db.scalar(select(func.count()).select_from(ProductBatch))==2


def test_trusted_purchase_source_reuses_group_and_refreshes_shortest_name(execution_state):
    client, Session, ids=execution_state
    first=payload(name='纯牛奶饮料'); assert create(client,ids,first).status_code==201
    shopping=client.post(root(ids)+'/shopping-list/items',headers=headers(),json={
        'name':'纯牛奶饮料','quantity':'2','unit':'盒','source_inventory_item_id':first['id']}).json()
    # Existing trusted source names may change between planning and purchase.
    with Session.begin() as db: db.get(ShoppingListItem,UUID(shopping['id'])).name='牛奶'
    bought=client.post(root(ids)+'/shopping-list/items/'+shopping['id']+'/purchase',headers=headers(),json={})
    assert bought.status_code==200,bought.text
    with Session() as db:
        product=db.scalar(select(Product))
        assert product.name=='牛奶' and product.version==2
        assert db.scalar(select(func.count()).select_from(Product))==1
        assert db.scalar(select(func.count()).select_from(ProductBatch))==2


@pytest.mark.skipif(not PG,reason='PostgreSQL row locks required')
def test_concurrent_confirmation_cannot_create_two_products_for_one_candidate(execution_state):
    client, Session, ids=execution_state
    requests=[payload(product_grouping=choice(ids['batch'])) for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda value:create(client,ids,value), requests))
    assert sorted(r.status_code for r in results)==[201,409]
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(Product))==1
        assert db.scalar(select(func.count()).select_from(ProductBatch))==2


@pytest.mark.skipif(not PG,reason='PostgreSQL row locks required')
def test_concurrent_identical_request_replays_without_duplicate_products(execution_state):
    client, Session, ids=execution_state
    value=payload(product_grouping=choice(ids['batch']))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:create(client,ids,value), range(2)))
    assert [r.status_code for r in results]==[201,201]
    assert results[0].json()==results[1].json()
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(Product))==1
        assert db.scalar(select(func.count()).select_from(ProductBatch))==2
