"""Unit-free inventory forms retain product counts and per-object records."""
from uuid import uuid4
from sqlalchemy import inspect
from test_physical_inventory import state, inventory, products, add
from test_v07_shopping import headers


def test_omitted_unit_defaults_to_internal_item_unit_and_preserves_product_count(state):
    client, Session, ids = state
    body=dict(id=str(uuid4()),name='苹果',quantity=10,storage_location='冰箱')
    first=client.post(inventory(ids),headers=headers(),json=body)
    assert first.status_code == 201, first.text
    assert 'quantity' not in first.json()
    assert first.json()['created_count'] == 10
    assert client.post(inventory(ids),headers=headers(),json=body).json()==first.json()
    second=client.post(inventory(ids),headers=headers(),json={**body,'id':str(uuid4()),'name':'红苹果','quantity':12})
    assert second.status_code == 201, second.text
    group,=products(client,ids)
    assert group['count']==22 and len(group['inventory_items'])==22
    assert all(row['unit']=='件' and 'quantity' not in row for row in group['inventory_items'])
    with Session() as db:
        assert 'quantity' not in {c['name'] for c in inspect(db.bind).get_columns('inventory_items')}


def test_metadata_edit_without_unit_never_rewrites_existing_unit_or_count(state):
    client, _, ids = state
    response,_=add(client,ids,unit='瓶',quantity=2)
    row=response.json()
    edited=client.patch(inventory(ids)+'/'+row['id'],headers=headers(),json={
        'expected_version':1,'operation_id':str(uuid4()),'specification':'500ml'})
    assert edited.status_code==200,edited.text
    assert edited.json()['unit']=='瓶' and edited.json()['specification']=='500ml'
    group,=products(client,ids)
    assert group['count']==2
