"""Explicit decisions override automatic name classification without merging rows."""
from uuid import uuid4
from test_physical_inventory import state, add, products, inventory
from test_v07_shopping import headers


def choice(row, product):
    return dict(mode='existing', candidate_inventory_item_id=row['id'],
                expected_inventory_version=row['version'], expected_product_version=product['version'])


def test_separate_then_explicitly_selected_product_and_retry(state):
    client, _, ids = state
    first, _ = add(client, ids, quantity=10)
    second, _ = add(client, ids, name='红苹果', quantity=12, product_grouping={'mode': 'separate'})
    assert first.status_code == second.status_code == 201
    groups = products(client, ids)
    assert len(groups) == 2
    red = next(p for p in groups if p['name'] == '红苹果')
    third, body = add(client, ids, name='大红苹果', quantity=2,
                      product_grouping=choice(second.json(), red))
    assert third.status_code == 201, third.text
    assert client.post(inventory(ids), headers=headers(), json=body).json() == third.json()
    assert sorted(p['count'] for p in products(client, ids)) == [10, 14]


def test_stale_candidate_is_rejected_without_creating_items(state):
    client, _, ids = state
    first, _ = add(client, ids)
    group, = products(client, ids)
    decision = choice(first.json(), group)
    decision['expected_inventory_version'] += 1
    response, _ = add(client, ids, name='红苹果', quantity=12, product_grouping=decision)
    assert response.status_code == 409
    assert products(client, ids)[0]['count'] == 1


def test_foreign_candidate_is_not_visible(state):
    client, _, ids = state
    foreign, _ = add(client, ids, actor='outsider', home='other_home')
    response, _ = add(client, ids, product_grouping=dict(mode='existing',
        candidate_inventory_item_id=foreign.json()['id'], expected_inventory_version=1))
    assert response.status_code == 404
    assert products(client, ids) == []


def test_match_rule_exact_shared_pair_and_unrelated_names(state):
    client, _, ids = state
    add(client, ids, name='苹果')
    root = inventory(ids).rsplit('/', 1)[0]
    for name in ('苹果', '红苹果'):
        page = client.get(root+'/inventory-product-matches', headers=headers(), params={'name': name}).json()
        assert page['total'] == 1
    page = client.get(root+'/inventory-product-matches', headers=headers(), params={'name': '苹大果'}).json()
    assert page['total'] == 0
