"""Run inside the deployed backend. All fixture writes are rolled back."""
import json
import os
from datetime import date, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.database import engine
from app.dependencies import Identity, get_db, get_identity
from app.main import app
from app.models import Household, HouseholdMember, InventoryItem, User
from app.services.physical_inventory import intake_date

user_id, home_id = uuid4(), uuid4()
created_ids = []
old_overrides = dict(app.dependency_overrides)
with engine.connect() as connection:
    transaction = connection.begin()
    db = Session(bind=connection, join_transaction_mode='create_savepoint', autoflush=False)
    try:
        user = User(id=user_id, email=f'intake-{user_id.hex}@example.invalid',
                    password_hash='non-login-test-fixture', display_name='Rollback intake check')
        db.add(user)
        db.flush()
        db.add(Household(id=home_id, name='Rollback intake check', created_by_user_id=user_id))
        db.flush()
        db.add(HouseholdMember(household_id=home_id, user_id=user_id, role='owner'))
        db.commit()
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_identity] = lambda: Identity(user, uuid4())
        client = TestClient(app, headers={'X-MagicVVu-App-Key': os.environ['MAGICVVU_APP_API_KEY']})
        root = f'/api/v1/households/{home_id}'
        yesterday = (intake_date() - timedelta(days=1)).isoformat()
        for index, supplied in enumerate((yesterday, None, 'omitted')):
            body = dict(id=str(uuid4()), name=f'Intake check {index}', quantity=2, storage_location='Test')
            if supplied != 'omitted':
                body['purchased_on'] = supplied
            response = client.post(root + '/inventory-items', json=body)
            assert response.status_code == 201, response.status_code
            result = response.json()
            expected = yesterday if supplied == yesterday else intake_date().isoformat()
            assert result['purchased_on'] == expected
            created_ids.extend(result['inventory_item_ids'])
            assert client.post(root + '/inventory-items', json=body).json() == result
            read = client.get(root + '/inventory-items/' + body['id'])
            assert read.status_code == 200 and read.json()['purchased_on'] == expected
            edit = client.patch(root + '/inventory-items/' + body['id'], json={
                'expected_version': 1, 'operation_id': str(uuid4()), 'specification': 'date preserved'})
            assert edit.status_code == 200 and edit.json()['purchased_on'] == expected
        result = client.get(root + '/inventory-products').json()['items']
        assert sum(p['count'] for p in result) == 6
        assert all(row['purchased_on'] for p in result for row in p['inventory_items'])
        assert 'quantity' not in {c['name'] for c in inspect(connection).get_columns('inventory_items')}
        assert 'quantity' not in {c['name'] for c in inspect(connection).get_columns('products')}
        client.close()
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(old_overrides)
        db.close()
        transaction.rollback()
with Session(engine) as verification:
    assert verification.get(User, user_id) is None
    assert verification.get(Household, home_id) is None
    assert not verification.scalars(select(InventoryItem).where(InventoryItem.household_id == home_id)).all()
print(json.dumps(dict(passed=True, deployed_api_checked=True, created_objects_checked=6,
                     explicit_date_preserved=True, null_and_omitted_date_defaulted=True,
                     replay_and_edit_preserve_date=True, product_realtime_counts_unchanged=True,
                     all_fixture_writes_rolled_back=True, business_day=intake_date().isoformat())))
