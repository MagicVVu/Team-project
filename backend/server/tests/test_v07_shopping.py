"""Shopping API regression against a disposable database with real bearer auth."""

import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DB_PASSWORD", "isolated-test-only")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with patch("sqlalchemy.create_engine", return_value=create_engine("sqlite://")):
    from app.database import Base
    from app.dependencies import get_db
    from app.main import app
    from app.models import AuthSession, Household, HouseholdMember, InventoryItem, ShoppingList, ShoppingListItem, User
    from app.routers import shopping
from app.security import digest_token


@pytest.fixture
def state(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'shopping.sqlite'}", connect_args={"check_same_thread": False})
    @event.listens_for(engine, "connect")
    def enforce_fks(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    ids = {key: uuid4() for key in ("owner", "member", "outsider", "home", "other_home", "list", "other_list")}
    with Session.begin() as db:
        for key in ("owner", "member", "outsider"):
            db.add(User(id=ids[key], email=f"{key}@example.invalid", password_hash="test", display_name=key))
        db.flush()
        for home, owner in (("home", "owner"), ("other_home", "outsider")):
            db.add(Household(id=ids[home], name=home, created_by_user_id=ids[owner]))
        db.flush()
        for home, actor, role in (("home", "owner", "owner"), ("home", "member", "member"),
                                  ("other_home", "outsider", "owner")):
            db.add(HouseholdMember(household_id=ids[home], user_id=ids[actor], role=role))
        for home, key in (("home", "list"), ("other_home", "other_list")):
            db.add(ShoppingList(id=ids[key], household_id=ids[home], name="Shared"))
        for key in ("owner", "member", "outsider"):
            db.add(AuthSession(user_id=ids[key], token_hash=digest_token(f"test-{key}"),
                               expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))

    def isolated_db():
        with Session() as db:
            yield db
    app.dependency_overrides[get_db] = isolated_db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, Session, ids
    app.dependency_overrides.clear()
    engine.dispose()


def headers(actor="owner"):
    return {"Authorization": f"Bearer test-{actor}"}


def base(ids, home="home"):
    return f"/api/v1/households/{ids[home]}/shopping-list"


def create(client, ids, actor="owner", **values):
    response = client.post(base(ids) + "/items", headers=headers(actor),
                           json={"name": "牛奶", "quantity": "2.125", "unit": "盒", **values})
    assert response.status_code == 201, response.text
    return response.json()


def test_shared_crud_purchase_history_and_retries(state):
    client, Session, ids = state
    url = base(ids)
    assert client.get(url, headers=headers()).json()["id"] == str(ids["list"])
    item = create(client, ids, name=" 牛奶 ")
    assert item["name"] == "牛奶" and item["added_by_user_id"] == str(ids["owner"])
    item_url = url + "/items/" + item["id"]
    assert client.get(url + "/items", headers=headers("member")).json()["items"][0]["id"] == item["id"]
    updated = client.patch(item_url, headers=headers("member"), json={"quantity": "3.125"})
    assert updated.status_code == 200 and updated.json()["quantity"] == "3.125"
    purchased = client.post(item_url + "/purchase", headers=headers("member"),
                            json={"storage_location": " 冰箱 ", "expires_on": "2027-01-01"})
    assert purchased.status_code == 200, purchased.text
    result = purchased.json()
    assert result["newly_stocked"] is True
    assert result["item"]["purchased_by_user_id"] == str(ids["member"])
    assert result["item"]["is_checked"] is True and result["item"]["checked_at"]
    stock = result["inventory_item"]
    assert stock["name"] == "牛奶" and Decimal(stock["quantity"]) == Decimal("3.125")
    assert stock["unit"] == "盒" and stock["storage_location"] == "冰箱"
    assert stock["expires_on"] == "2027-01-01" and stock["purchased_on"]
    assert stock["source_shopping_list_item_id"] == item["id"]
    assert stock["created_by_user_id"] == str(ids["member"])
    repeated = client.post(item_url + "/purchase", headers=headers(), json={"storage_location": "不同位置"})
    assert repeated.status_code == 200 and repeated.json()["newly_stocked"] is False
    assert repeated.json()["inventory_item"]["id"] == stock["id"]
    assert repeated.json()["inventory_item"]["storage_location"] == "冰箱"
    assert client.get(url + "/items", headers=headers()).json()["total"] == 0
    assert client.get(url + "/items?status=purchased", headers=headers()).json()["total"] == 1
    assert client.get(url + "/items?status=all", headers=headers()).json()["total"] == 1
    assert client.patch(item_url, headers=headers(), json={"name": "Changed"}).status_code == 409
    assert client.delete(item_url, headers=headers()).status_code == 409
    second = create(client, ids)
    assert client.post(url + "/items/" + second["id"] + "/purchase", headers=headers(), json={}).status_code == 200
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(InventoryItem)) == 2
    pending = create(client, ids)
    assert client.delete(url + "/items/" + pending["id"], headers=headers("member")).status_code == 204
    assert client.post(url + "/items/" + pending["id"] + "/purchase", headers=headers(), json={}).status_code == 404


@pytest.mark.parametrize("actor,expected", [(None, 401), ("outsider", 404)])
def test_all_routes_enforce_identity_and_household(state, actor, expected):
    client, Session, ids = state
    item = create(client, ids)
    url = base(ids)
    auth = {} if actor is None else headers(actor)
    for method, path, payload in (
        ("get", url, None), ("get", url + "/items", None),
        ("post", url + "/items", {"name": "x", "quantity": 1}),
        ("patch", url + "/items/" + item["id"], {"quantity": 2}),
        ("delete", url + "/items/" + item["id"], None),
        ("post", url + "/items/" + item["id"] + "/purchase", {}),
    ):
        kwargs = {"headers": auth}
        if payload is not None:
            kwargs["json"] = payload
        response = client.request(method, path, **kwargs)
        assert response.status_code == expected, (path, response.text)
    # Even a valid member of another family cannot use an item from this home.
    foreign_url = base(ids, "other_home") + "/items/" + item["id"]
    assert client.patch(foreign_url, headers=headers("outsider"), json={"name": "x"}).status_code == 404
    assert client.delete(foreign_url, headers=headers("outsider")).status_code == 404
    assert client.post(foreign_url + "/purchase", headers=headers("outsider"), json={}).status_code == 404
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(InventoryItem)) == 0


@pytest.mark.parametrize("payload", [
    {"name": " "}, {"quantity": 0}, {"quantity": -1}, {"quantity": "0.0001"},
    {"quantity": "1000000000"}, {"quantity": "NaN"}, {"unit": " "},
    {"added_by_user_id": str(uuid4())}, {"is_checked": True},
])
def test_create_rejects_invalid_data_and_spoofed_fields(state, payload):
    client, _, ids = state
    response = client.post(base(ids) + "/items", headers=headers(),
                           json={"name": "x", "quantity": 1, **payload})
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("payload", [{}, {"name": None}, {"quantity": None}, {"unit": None},
                                     {"is_checked": False}, {"name": " "}, {"quantity": 0}])
def test_patch_rejects_empty_null_and_server_owned_values(state, payload):
    client, _, ids = state
    item = create(client, ids)
    assert client.patch(base(ids) + "/items/" + item["id"], headers=headers(), json=payload).status_code == 422


def test_pagination_and_purchase_validation(state):
    client, _, ids = state
    for _ in range(3):
        create(client, ids)
    url = base(ids) + "/items"
    page1 = client.get(url + "?limit=1", headers=headers()).json()
    page2 = client.get(url + "?limit=1&offset=1", headers=headers()).json()
    assert page1["total"] == page2["total"] == 3
    assert page1["items"][0]["id"] != page2["items"][0]["id"]
    for query in ("limit=101", "limit=0", "offset=-1", "status=invalid"):
        assert client.get(url + "?" + query, headers=headers()).status_code == 422
    purchase_url = url + "/" + page1["items"][0]["id"] + "/purchase"
    for payload in ({"storage_location": " "}, {"expires_on": "bad-date"}, {"actor_user_id": str(ids["outsider"])}):
        assert client.post(purchase_url, headers=headers(), json=payload).status_code == 422


def test_legacy_purchased_item_requires_reconciliation(state):
    client, Session, ids = state
    item = create(client, ids)
    with Session.begin() as db:
        db.get(ShoppingListItem, UUID(item["id"])).is_checked = True
    response = client.post(base(ids) + "/items/" + item["id"] + "/purchase", headers=headers(), json={})
    assert response.status_code == 409
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(InventoryItem)) == 0


def test_failure_after_stock_flush_rolls_back_both_changes(state, monkeypatch):
    client, Session, ids = state
    item = create(client, ids)
    original = shopping.purchase_and_stock
    def failing_purchase(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Injected failure after stock INSERT")
    monkeypatch.setattr(shopping, "purchase_and_stock", failing_purchase)
    response = client.post(base(ids) + "/items/" + item["id"] + "/purchase", headers=headers(), json={})
    assert response.status_code == 500
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(InventoryItem)) == 0
        row = db.get(ShoppingListItem, UUID(item["id"]))
        assert row.is_checked is False and row.purchased_by_user_id is None and row.checked_at is None


def test_disabled_and_expired_sessions_cannot_purchase(state):
    client, Session, ids = state
    item = create(client, ids)
    url = base(ids) + "/items/" + item["id"] + "/purchase"
    with Session.begin() as db:
        db.get(User, ids["owner"]).is_active = False
        session = db.scalar(select(AuthSession).where(AuthSession.user_id == ids["member"]))
        session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert client.post(url, headers=headers(), json={}).status_code == 401
    assert client.post(url, headers=headers("member"), json={}).status_code == 401
