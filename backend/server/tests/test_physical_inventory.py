"""Object inventory contract: intake expansion, isolation, retries and lifecycle."""
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event, func, inspect, select, text
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from test_v07_shopping import headers, base, create
from app.database import Base, database_url
from app.dependencies import get_db
from app.main import app
from app.models import AIDraft, AITask, InventoryItem, AuthSession, Household, HouseholdMember, ShoppingList, User
from app.product_models import Product, ProductBatch
from app.execution_models import BusinessEvent
from app.security import digest_token

PG = os.getenv('PHYSICAL_INVENTORY_PG_TEST') == 'yes'


@pytest.fixture
def state(tmp_path):
    """The PostgreSQL mode owns a fresh schema in an explicitly named test DB."""
    admin = schema = None
    if PG:
        assert os.environ.get('DB_NAME') in {'magicvvu_physical_inventory_test', 'magicvvu_p7_execution_test'}
        schema = 'physical_case_' + uuid4().hex
        admin = create_engine(database_url())
        with admin.begin() as connection:
            connection.execute(text('CREATE SCHEMA "' + schema + '"'))
        engine = create_engine(database_url(), connect_args={'options': '-csearch_path=' + schema})
    else:
        engine = create_engine(f"sqlite:///{tmp_path / 'physical.sqlite'}", connect_args={'check_same_thread': False})
        @event.listens_for(engine, 'connect')
        def fks(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    ids = {key: uuid4() for key in ('owner', 'member', 'outsider', 'home', 'other_home', 'list', 'other_list')}
    with Session.begin() as db:
        for key in ('owner', 'member', 'outsider'):
            db.add(User(id=ids[key], email=f'{key}@example.invalid', password_hash='test', display_name=key))
        db.flush()
        for home, owner in (('home', 'owner'), ('other_home', 'outsider')):
            db.add(Household(id=ids[home], name=home, created_by_user_id=ids[owner]))
        db.flush()
        for home, actor, role in (('home', 'owner', 'owner'), ('home', 'member', 'member'), ('other_home', 'outsider', 'owner')):
            db.add(HouseholdMember(household_id=ids[home], user_id=ids[actor], role=role))
        for home, key in (('home', 'list'), ('other_home', 'other_list')):
            db.add(ShoppingList(id=ids[key], household_id=ids[home], name='Shared'))
        for key in ('owner', 'member', 'outsider'):
            db.add(AuthSession(user_id=ids[key], token_hash=digest_token(f'test-{key}'),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
    def isolated_db():
        with Session() as db:
            yield db
    app.dependency_overrides[get_db] = isolated_db
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, Session, ids
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
        if admin is not None:
            assert schema.startswith('physical_case_') and len(schema) == 46
            with admin.begin() as connection:
                connection.execute(text('DROP SCHEMA "' + schema + '" CASCADE'))
            admin.dispose()


def inventory(ids, home='home'):
    return f"/api/v1/households/{ids[home]}/inventory-items"


def add(client, ids, name='苹果', quantity=1, unit='个', actor='owner', home='home', **values):
    body = dict(id=str(uuid4()), name=name, quantity=str(quantity), unit=unit,
                category='食品', storage_location='冰箱', **values)
    return client.post(inventory(ids, home), headers=headers(actor), json=body), body


def products(client, ids):
    return client.get(f"/api/v1/households/{ids['home']}/inventory-products", headers=headers()).json()['items']


def draft(Session, ids, command):
    task_id, draft_id = uuid4(), uuid4()
    with Session.begin() as db:
        db.add(AITask(id=task_id, household_id=ids['home'], user_id=ids['owner'], request_id=uuid4().hex,
            request_hash='fixture', original_text='合成库存契约验收', household_timezone='Asia/Shanghai',
            status='needs_confirmation', revision=1, result_json={'status': 'needs_confirmation', 'draft': command}))
        db.flush()
        db.add(AIDraft(id=draft_id, task_id=task_id, household_id=ids['home'], user_id=ids['owner'],
            status='pending', revision=1, command_json=command, preview_json={}))
    return draft_id


def commit(client, draft_id, body=None):
    body = body or dict(operation_id=str(uuid4()), draft_revision=1, task_revision=1, edits={})
    return client.post(f'/api/v1/drafts/{draft_id}/commit', headers=headers(), json=body), body


def test_two_apple_intakes_are_22_independent_rows_and_one_product(state):
    client, Session, ids = state
    first, body = add(client, ids, quantity=10)
    second, _ = add(client, ids, name='红苹果', quantity=12)
    assert first.status_code == second.status_code == 201, (first.text, second.text)
    assert first.json()['id'] == body['id']
    assert first.json()['created_count'] == 10 and len(first.json()['inventory_item_ids']) == 10
    assert 'quantity' not in first.json()
    assert client.post(inventory(ids), headers=headers(), json=body).json() == first.json()
    group, = products(client, ids)
    assert group['name'] == '苹果' and group['count'] == 22
    assert Counter(row['name'] for row in group['inventory_items']) == {'苹果': 10, '红苹果': 12}
    assert len({row['id'] for row in group['inventory_items']}) == 22
    assert all('quantity' not in row for row in group['inventory_items'])
    pages = [client.get(inventory(ids), headers=headers(), params={'limit': 7, 'offset': offset}).json()
             for offset in (0, 7, 14, 21)]
    assert all(page['total'] == 22 for page in pages)
    assert len({row['id'] for page in pages for row in page['items']}) == 22
    with Session() as db:
        assert 'quantity' not in {column['name'] for column in inspect(db.bind).get_columns('inventory_items')}
        assert db.scalar(select(func.count()).select_from(BusinessEvent)) == 22
        assert db.scalar(select(func.count()).select_from(ProductBatch)) == 22


@pytest.mark.parametrize('quantity', ['0', '-1', '1.5', '10001'])
def test_invalid_object_counts_never_write_partial_stock(state, quantity):
    client, Session, ids = state
    result, _ = add(client, ids, quantity=quantity)
    assert result.status_code == 422, result.text
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(InventoryItem)) == 0
        assert db.scalar(select(func.count()).select_from(Product)) == 0


@pytest.mark.parametrize('quantity,unit,specification', [('500', 'g', '500g'), ('1.5', 'L', '1.5L')])
def test_measured_intake_is_one_portion_with_specification(state, quantity, unit, specification):
    client, _, ids = state
    result, _ = add(client, ids, quantity=quantity, unit=unit)
    assert result.status_code == 201, result.text
    assert result.json()['unit'] == '份'
    assert result.json()['specification'] == specification
    assert result.json()['created_count'] == 1
    group, = products(client, ids)
    assert group['count'] == 1 and group['base_unit'] == '份'


def test_name_grouping_is_household_scoped_and_requires_two_contiguous_characters(state):
    client, Session, ids = state
    for name in ('苹果', '苹果', '红苹果', '青苹', '果'):
        response, _ = add(client, ids, name=name)
        assert response.status_code == 201, response.text
    response, _ = add(client, ids, name='红苹果', actor='outsider', home='other_home')
    assert response.status_code == 201
    assert sorted(group['count'] for group in products(client, ids)) == [1, 1, 3]
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(Product).where(Product.household_id == ids['other_home'])) == 1


def test_consume_one_object_and_retry_leave_other_objects_untouched(state):
    client, Session, ids = state
    stock, _ = add(client, ids, quantity=10)
    stock = stock.json()
    command = dict(action='CONSUME', name='苹果', batch_id=stock['id'], expected_version=1, quantity='1', unit='个')
    draft_id = draft(Session, ids, command)
    execution = client.get(f'/api/v1/drafts/{draft_id}/execution', headers=headers())
    assert execution.json()['editable_fields'] == []
    rejected, _ = commit(client, draft_id, dict(operation_id=str(uuid4()), draft_revision=1,
        task_revision=1, edits={'quantity': '.5'}))
    assert rejected.status_code == 422
    result, body = commit(client, draft_id)
    assert result.status_code == 200, result.text
    after = result.json()['result']['inventory_item']
    assert after['status'] == 'FINISHED' and 'quantity' not in after
    assert commit(client, draft_id, body)[0].json() == result.json()
    group, = products(client, ids)
    assert group['count'] == 9 and len(group['inventory_items']) == 9
    assert Counter(row['status'] for row in group['inventory_items']) == {'ACTIVE': 9}


def test_half_an_object_cannot_be_consumed(state):
    client, Session, ids = state
    response, _ = add(client, ids)
    command = dict(action='CONSUME', name='苹果', batch_id=response.json()['id'],
                   expected_version=1, quantity='.5', unit='个')
    result, _ = commit(client, draft(Session, ids, command))
    assert result.status_code == 422, result.text
    assert products(client, ids)[0]['count'] == 1


def test_ai_add_expands_all_objects_and_replays_entire_receipt(state):
    client, Session, ids = state
    for name, quantity in [('苹果', '10'), ('红苹果', '12')]:
        draft_id = draft(Session, ids, dict(action='ADD', name=name, quantity=quantity, unit='个', location='冰箱'))
        result, body = commit(client, draft_id)
        assert result.status_code == 200, result.text
        data = result.json()
        assert data['result']['created_count'] == int(quantity)
        assert len(data['event_ids']) == len(data['batch_versions']) == int(quantity)
        assert commit(client, draft_id, body)[0].json() == data
        summary = client.get(f"/api/v1/households/{ids['home']}/operations/{body['operation_id']}/summary", headers=headers())
        assert summary.status_code == 200, summary.text
        assert Decimal(summary.json()['quantity']) == Decimal(quantity)
    group, = products(client, ids)
    assert group['name'] == '苹果' and group['count'] == 22
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(BusinessEvent)) == 22


def test_shopping_purchase_expands_then_replays_without_restocking(state):
    client, Session, ids = state
    add(client, ids, quantity=10)
    item = create(client, ids, name='红苹果', quantity='12', unit='个')
    path = base(ids) + '/items/' + item['id'] + '/purchase'
    result = client.post(path, headers=headers('member'), json={'storage_location': '冰箱'})
    assert result.status_code == 200, result.text
    data = result.json()
    assert data['created_count'] == len(data['inventory_item_ids']) == 12
    repeated = client.post(path, headers=headers(), json={'actual_quantity': '5'})
    assert repeated.status_code == 200 and repeated.json()['newly_stocked'] is False
    assert repeated.json()['inventory_item']['id'] == data['inventory_item']['id']
    assert set(repeated.json()['inventory_item_ids']) == set(data['inventory_item_ids'])
    group, = products(client, ids)
    assert group['count'] == 22
    with Session() as db:
        assert len(db.scalars(select(InventoryItem).where(InventoryItem.source_shopping_list_item_id == UUID(item['id']))).all()) == 12


def test_version_checks_and_single_object_metadata_edit(state):
    client, _, ids = state
    response, _ = add(client, ids, quantity=2)
    row = response.json()
    path = inventory(ids) + '/' + row['id']
    body = dict(expected_version=1, operation_id=str(uuid4()), specification='大果', storage_location='餐桌')
    edited = client.patch(path, headers=headers(), json=body)
    assert edited.status_code == 200 and edited.json()['specification'] == '大果'
    assert client.patch(path, headers=headers(), json=body).json() == edited.json()
    assert client.patch(path, headers=headers(), json={**body, 'operation_id': str(uuid4())}).status_code == 409
    assert client.patch(path, headers=headers(), json={**body, 'expected_version': 2, 'operation_id': str(uuid4()), 'quantity': 20}).status_code == 422
    group, = products(client, ids)
    assert group['count'] == 2
    assert Counter(item['storage_location'] for item in group['inventory_items']) == {'餐桌': 1, '冰箱': 1}


def test_intake_rolls_back_every_object_on_ledger_failure(state, monkeypatch):
    client, Session, ids = state
    from app.services import ledger
    def fail(*args, **kwargs):
        raise RuntimeError('synthetic failure')
    monkeypatch.setattr(ledger, 'append', fail)
    response, _ = add(client, ids, quantity=10)
    assert response.status_code == 500
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(InventoryItem)) == 0
        assert db.scalar(select(func.count()).select_from(Product)) == 0


def test_renaming_one_object_reclassifies_it_without_renaming_peers(state):
    client, _, ids = state
    response, _ = add(client, ids, quantity=2)
    item_id = response.json()['id']
    path = inventory(ids) + '/' + item_id
    body = dict(expected_version=1, operation_id=str(uuid4()), name='牛奶')
    renamed = client.patch(path, headers=headers(), json=body)
    assert renamed.status_code == 200, renamed.text
    assert client.patch(path, headers=headers(), json=body).json() == renamed.json()
    groups = {group['name']: group for group in products(client, ids)}
    assert groups['苹果']['count'] == groups['牛奶']['count'] == 1
    assert groups['牛奶']['inventory_items'][0]['id'] == item_id
    assert groups['苹果']['inventory_items'][0]['name'] == '苹果'
    back = client.patch(path, headers=headers(), json=dict(expected_version=2,
        operation_id=str(uuid4()), name='红苹果'))
    assert back.status_code == 200, back.text
    groups = {group['name']: group for group in products(client, ids)}
    assert groups['苹果']['count'] == 2 and '牛奶' not in groups


@pytest.mark.skipif(not PG, reason='Row-lock concurrency requires disposable PostgreSQL')
def test_concurrent_intake_and_duplicate_request_share_one_product(state):
    from concurrent.futures import ThreadPoolExecutor
    client, Session, ids = state
    body = dict(id=str(uuid4()), name='苹果', quantity='10', unit='个', category='食品', storage_location='冰箱')
    other = {**body, 'id': str(uuid4()), 'name': '红苹果', 'quantity': '12'}
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda value: client.post(inventory(ids), headers=headers(), json=value),
                                  [body, body, other, other]))
    assert all(response.status_code == 201 for response in responses), [r.text for r in responses]
    group, = products(client, ids)
    assert group['count'] == 22
    assert Counter(row['name'] for row in group['inventory_items']) == {'苹果': 10, '红苹果': 12}
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(BusinessEvent)) == 22


def test_move_open_and_discard_affect_only_the_selected_object(state, monkeypatch):
    client, Session, ids = state
    monkeypatch.setenv('MAGICVVU_OPEN_EXECUTION', 'true')
    monkeypatch.setenv('MAGICVVU_DISCARD_EXECUTION', 'true')
    response, _ = add(client, ids, quantity=2)
    item_id = response.json()['id']
    move = dict(action='MOVE', name='苹果', batch_id=item_id, expected_version=1, to_location='餐桌')
    assert commit(client, draft(Session, ids, move))[0].status_code == 200
    opened = dict(action='OPEN', name='苹果', batch_id=item_id, expected_version=2, opened_at='2026-01-01')
    assert commit(client, draft(Session, ids, opened))[0].status_code == 200
    discarded = dict(action='DISCARD', name='苹果', batch_id=item_id, expected_version=3,
                     discard_mode='all', quantity='1', unit='个')
    draft_id = draft(Session, ids, discarded)
    preview = client.post(f'/api/v1/drafts/{draft_id}/execution-preview', headers=headers(),
        json=dict(draft_revision=1, task_revision=1, edits={}))
    assert preview.status_code == 200, preview.text
    assert preview.json()['after']['status'] == 'DISCARDED'
    assert 'quantity' not in preview.json()['after']
    assert products(client, ids)[0]['count'] == 2
    committed, body = commit(client, draft_id)
    assert committed.status_code == 200, committed.text
    assert commit(client, draft_id, body)[0].json() == committed.json()
    group, = products(client, ids)
    assert group['count'] == 1
    untouched, = [row for row in group['inventory_items'] if row['id'] != item_id]
    assert untouched['version'] == 1 and untouched['storage_location'] == '冰箱' and untouched['opened_at'] is None


# Reuse the real P8.5 HTTP stages with deterministic understanding, while keeping
# the new physical-object fixture rather than the historical five-unit batch.
from test_backend_p2_conversation import p7
from test_p84_dialogue import p84
from test_p85_dialogue import p85


@pytest.fixture
def execution_state(state):
    client, Session, ids = state
    with Session.begin() as db:
        db.add(AuthSession(user_id=ids['owner'], token_hash=digest_token('synthetic-user'),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
    return client, Session, {**ids, 'user': ids['owner'], 'foreign_home': ids['other_home']}


def test_user_apple_sentences_through_p85_saved_drafts_and_real_commits(execution_state, p85, monkeypatch):
    from conversation.p85.schemas import P85Plan
    from test_session_memory import start, send, ok
    client, Session, ids = execution_state
    sentences = {'我买了10个苹果放在冰箱里': ('10', '苹果'), '我买了12个红苹果放在冰箱里': ('12', '红苹果')}
    async def understanding(text, context, episodes, memory):
        p85[0].understanding_calls += 1
        amount, name = sentences[text]
        return P85Plan(speech_act='request', action='ADD', write_count=1,
            fields={'name': {'value': name, 'quote': name},
                    'quantity': {'value': amount, 'quote': amount + '个'},
                    'unit': {'value': '个', 'quote': amount + '个'},
                    'location': {'value': '冰箱', 'quote': '冰箱'}})
    monkeypatch.setattr(p85[0], 'p85_understand', understanding)
    session = ok(start(client, ids))
    for sentence, (amount, name) in sentences.items():
        session = ok(send(client, ids, session, sentence))
        task = session['task']
        assert task['status'] == 'needs_confirmation', session
        with Session() as db:
            saved = db.get(AIDraft, UUID(task['draft_id']))
            assert saved.command_json['name'] == name and Decimal(saved.command_json['quantity']) == Decimal(amount)
        response, _ = commit(client, task['draft_id'], dict(operation_id=str(uuid4()),
            draft_revision=1, task_revision=task['revision'], edits={}))
        assert response.status_code == 200, response.text
        assert response.json()['result']['created_count'] == int(amount)
    group, = products(client, ids)
    assert group['name'] == '苹果' and group['count'] == 22
    assert Counter(row['name'] for row in group['inventory_items']) == {'苹果': 10, '红苹果': 12}
    assert p85[0].understanding_calls == 2
    assert any(path == '/agent/dialogue/p85/resolve' for _, path in p85[1])
