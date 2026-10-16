"""App cloud integration: versions, retries, actual purchase amount and scopes."""
from uuid import UUID, uuid4
from decimal import Decimal

from sqlalchemy import select

from test_v07_shopping import state, headers, base, create
from app.models import InventoryItem


def stock_base(ids):
    return f"/api/v1/households/{ids['home']}/inventory-items"


def add_stock(client, ids):
    body = dict(id=str(uuid4()), name="牛奶", quantity="4.500001", unit="盒", category="食品",
                storage_location="冰箱", minimum_quantity="2", expires_on="2027-01-01")
    response = client.post(stock_base(ids), headers=headers(), json=body)
    assert response.status_code == 201, response.text
    return response.json(), body


def test_inventory_retries_versions_and_household_permissions(state):
    client, Session, ids = state
    stock, body = add_stock(client, ids)
    url = stock_base(ids) + "/" + stock["id"]
    assert client.post(stock_base(ids), headers=headers(), json=body).json()["id"] == stock["id"]
    assert client.get(stock_base(ids), headers=headers("member")).json()["total"] == 1
    operation = dict(expected_version=stock["version"], operation_id=str(uuid4()), delta="-1.25")
    adjusted = client.post(url + "/adjustments", headers=headers("member"), json=operation)
    assert adjusted.status_code == 200, adjusted.text
    assert adjusted.json()["quantity"] == "3.250001"
    assert adjusted.json()["version"] == 2
    assert client.post(url + "/adjustments", headers=headers("member"), json=operation).json()["quantity"] == "3.250001"
    assert client.post(url + "/adjustments", headers=headers(), json={**operation, "operation_id": str(uuid4())}).status_code == 409
    assert client.post(url + "/adjustments", headers=headers(), json={**operation, "delta": "-2"}).status_code == 409
    for method, suffix, payload in (("get", "", None), ("post", "", body),
                                    ("patch", "/" + stock["id"], {"expected_version": 2, "operation_id": str(uuid4()), "name": "x"}),
                                    ("delete", "/" + stock["id"], {"expected_version": 2, "operation_id": str(uuid4())}),
                                    ("post", "/" + stock["id"] + "/adjustments", operation)):
        kwargs = {"json": payload} if payload is not None else {}
        assert client.request(method, stock_base(ids) + suffix, headers=headers("outsider"), **kwargs).status_code == 404
        assert client.request(method, stock_base(ids) + suffix, **kwargs).status_code == 401
    assert client.post(url + "/adjustments", headers=headers(), json={"expected_version": 2, "operation_id": str(uuid4()), "delta": -20}).status_code == 422
    edit = dict(expected_version=2, operation_id=str(uuid4()), minimum_quantity="5", category="其他", expires_on=None)
    response = client.patch(url, headers=headers(), json=edit)
    assert response.status_code == 200 and response.json()["minimum_quantity"] == "5"
    assert response.json()["expires_on"] is None
    deletion = dict(expected_version=3, operation_id=str(uuid4()))
    assert client.request("DELETE", url, headers=headers(), json=deletion).status_code == 204
    assert client.request("DELETE", url, headers=headers(), json=deletion).status_code == 204
    assert client.get(stock_base(ids), headers=headers()).json()["total"] == 0
    with Session() as db:
        assert db.get(InventoryItem, UUID(stock["id"])).status == "DISCARDED"


def test_purchase_actual_amount_is_atomic_and_uses_independent_batch(state):
    client, Session, ids = state
    stock, _ = add_stock(client, ids)
    item = create(client, ids, id=str(uuid4()), quantity="3", source_inventory_item_id=stock["id"])
    url = base(ids) + "/items/" + item["id"] + "/purchase"
    response = client.post(url, headers=headers("member"), json={"actual_quantity": "1.250"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["inventory_item"]["id"] != stock["id"]
    assert result["inventory_item"]["quantity"] == "1.250000"
    assert result["inventory_item"]["storage_location"] == "冰箱"
    assert result["inventory_item"]["minimum_quantity"] == "2.000000"
    assert result["item"]["quantity"] == "1.250"
    assert client.post(url, headers=headers(), json={"actual_quantity": "10"}).json()["newly_stocked"] is False
    with Session() as db:
        assert db.get(InventoryItem, UUID(stock["id"])).quantity == Decimal("4.500001")
        assert len(db.scalars(select(InventoryItem)).all()) == 2


def test_cross_household_source_and_profile_rules(state):
    client, _, ids = state
    stock, _ = add_stock(client, ids)
    response = client.post(base(ids, "other_home") + "/items", headers=headers("outsider"),
                           json=dict(name="牛奶", quantity=1, unit="盒", source_inventory_item_id=stock["id"]))
    assert response.status_code == 404
    home_url = f"/api/v1/households/{ids['home']}"
    assert client.patch(home_url, headers=headers("member"), json={"name": "Changed"}).status_code == 403
    assert client.patch(home_url, headers=headers(), json={"name": "Changed"}).json()["name"] == "Changed"
    assert client.patch("/api/v1/users/me", headers=headers(), json={"display_name": "New name"}).json()["display_name"] == "New name"


def test_shopping_create_with_stable_id_and_validation(state):
    client, _, ids = state
    stable_id = str(uuid4())
    item = create(client, ids, id=stable_id)
    assert create(client, ids, id=stable_id)["id"] == item["id"]
    response = client.post(base(ids) + "/items", headers=headers(), json=dict(id=stable_id, name="Other", quantity=1))
    assert response.status_code == 409
    for invalid in (0, -1, "0.0001", "NaN"):
        assert client.post(base(ids) + "/items/" + item["id"] + "/purchase", headers=headers(), json={"actual_quantity": invalid}).status_code == 422


def test_migration_0006_preserves_existing_inventory(tmp_path):
    from pathlib import Path
    from unittest.mock import patch
    from sqlalchemy import create_engine, text
    from alembic import command
    from alembic.config import Config
    engine = create_engine(f"sqlite:///{tmp_path / 'upgrade.sqlite'}")
    path = Path(__file__).resolve().parents[1]
    cfg = Config(str(path / "alembic.ini"))
    cfg.set_main_option("script_location", str(path / "alembic"))
    with patch("sqlalchemy.create_engine", return_value=engine):
        command.upgrade(cfg, "20261014_0005")
        with engine.begin() as db:
            user_id, home_id, item_id = [uuid4().hex for _ in range(3)]
            db.execute(text("INSERT INTO users(id,email,password_hash,display_name) VALUES(:u,'legacy@example.invalid','test','Legacy')"), {"u": user_id})
            db.execute(text("INSERT INTO households(id,name,created_by_user_id) VALUES(:h,'Legacy',:u)"), {"h": home_id, "u": user_id})
            db.execute(text("INSERT INTO inventory_items(id,household_id,name,quantity,unit) VALUES(:i,:h,'Milk',3,'box')"), {"i": item_id, "h": home_id})
        command.upgrade(cfg, "head")
    with engine.connect() as db:
        row = db.execute(text("SELECT name,quantity,minimum_quantity,history_json FROM inventory_items WHERE id=:i"), {"i": item_id}).one()
        assert row[0] == "Milk" and row[1] == 3 and row[2] == 0 and row[3] == "[]"
    engine.dispose()
