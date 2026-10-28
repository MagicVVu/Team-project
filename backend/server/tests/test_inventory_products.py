from uuid import uuid4

from test_v09_execution import execution_state, headers
from app.models import InventoryItem
from app.product_models import Product, ProductBatch


def test_products_use_explicit_links_include_terminal_and_paginate(execution_state):
    client, Session, ids = execution_state
    first, second, foreign, ended, unlinked = [uuid4() for _ in range(5)]
    with Session.begin() as db:
        for pid, home, user in [(first, 'home', 'user'), (second, 'home', 'user'), (foreign, 'foreign_home', 'outsider')]:
            db.add(Product(id=pid, household_id=ids[home], name='same name', base_unit='盒',
                           category='food', source='test', actor_user_id=ids[user]))
        db.add(InventoryItem(id=ended, household_id=ids['home'], name='牛奶', quantity=0,
                             unit='盒', status='DISCARDED', version=1))
        db.add(InventoryItem(id=unlinked, household_id=ids['home'], name='牛奶', quantity=3,
                             unit='盒', status='ACTIVE', version=1))
        db.flush()
        for bid in [ids['batch'], ended]:
            db.add(ProductBatch(inventory_item_id=bid, product_id=first, source='test', actor_user_id=ids['user']))
    path = f"/api/v1/households/{ids['home']}/inventory-products"
    result = client.get(path, headers=headers())
    assert result.status_code == 200, result.text
    assert result.headers['cache-control'] == 'no-store'
    page = result.json()
    assert page['total'] == 2
    products = {p['product_id']: p for p in page['items']}
    batches = products[str(first)]['inventory_items']
    assert {b['id'] for b in batches} == {str(ids['batch']), str(ended)}
    assert {b['status'] for b in batches} == {'ACTIVE', 'DISCARDED'}
    assert products[str(second)]['inventory_items'] == []
    a = client.get(path+'?limit=1&offset=0', headers=headers()).json()
    b = client.get(path+'?limit=1&offset=1', headers=headers()).json()
    assert a['items'][0]['product_id'] != b['items'][0]['product_id']
    assert client.get(path, headers=headers('outsider')).status_code == 404
    assert client.get(path).status_code == 401


def test_cross_household_bad_link_is_not_exposed(execution_state):
    client, Session, ids = execution_state
    pid = uuid4()
    with Session.begin() as db:
        db.add(Product(id=pid, household_id=ids['foreign_home'], name='foreign', base_unit='盒',
                       category='food', source='test', actor_user_id=ids['outsider']))
        db.flush()
        db.add(ProductBatch(product_id=pid, inventory_item_id=ids['batch'], source='test', actor_user_id=ids['outsider']))
    page = client.get(f"/api/v1/households/{ids['foreign_home']}/inventory-products", headers=headers('outsider')).json()
    assert page['items'][0]['inventory_items'] == []
