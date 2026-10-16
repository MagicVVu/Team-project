"""Run against an EMPTY disposable PostgreSQL DB, never the deployed database.

Requires DB_NAME=magicvvu_shopping_test and SHOPPING_TEST_ISOLATED=yes.
Migrate the disposable database to head before invoking this script.
No pytest dependency; usable with the production backend image.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from unittest.mock import patch
from uuid import UUID, uuid4

if os.getenv("DB_NAME") != "magicvvu_shopping_test" or os.getenv("SHOPPING_TEST_ISOLATED") != "yes":
    raise SystemExit("Refusing to run outside the explicitly isolated test database")

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal, engine
from app.main import app
from app.models import AuthSession, Household, HouseholdMember, InventoryItem, ShoppingList, ShoppingListItem, User
from app.routers import shopping
from app.security import digest_token


def request(method, url, actor="owner", **kwargs):
    with TestClient(app, raise_server_exceptions=False) as client:
        return client.request(method, url, headers={"Authorization": f"Bearer isolated-{actor}"}, **kwargs)


def main():
    owner, member, outsider, home, other_home = [uuid4() for _ in range(5)]
    with SessionLocal.begin() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0, "Expected an empty test DB"
        for user_id, name in ((owner, "owner"), (member, "member"), (outsider, "outsider")):
            db.add(User(id=user_id, email=f"{name}@isolated.invalid", password_hash="test-only", display_name=name))
        db.flush()
        db.add_all([Household(id=home, name="Test home", created_by_user_id=owner),
                    Household(id=other_home, name="Other home", created_by_user_id=outsider)])
        db.flush()
        db.add_all([HouseholdMember(household_id=home, user_id=owner, role="owner"),
                    HouseholdMember(household_id=home, user_id=member, role="member"),
                    HouseholdMember(household_id=other_home, user_id=outsider, role="owner"),
                    ShoppingList(household_id=home, name="Test list"),
                    ShoppingList(household_id=other_home, name="Other list")])
        for uid, name in ((owner, "owner"), (member, "member"), (outsider, "outsider")):
            db.add(AuthSession(user_id=uid, token_hash=digest_token(f"isolated-{name}"),
                               expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
    base = f"/api/v1/households/{home}/shopping-list/items"

    def add_item():
        response = request("POST", base, json={"name": "牛奶", "quantity": "2.125", "unit": "盒"})
        assert response.status_code == 201, response.text
        return base + "/" + response.json()["id"], UUID(response.json()["id"])

    url, item_id = add_item()
    barrier = Barrier(8)
    def buy(index):
        barrier.wait(timeout=10)
        return request("POST", url + "/purchase", actor="owner" if index % 2 else "member", json={})
    with ThreadPoolExecutor(max_workers=8) as pool:
        purchases = list(pool.map(buy, range(8)))
    assert all(r.status_code == 200 for r in purchases), [(r.status_code, r.text) for r in purchases]
    assert sum(r.json()["newly_stocked"] for r in purchases) == 1
    assert len({r.json()["inventory_item"]["id"] for r in purchases}) == 1
    with SessionLocal() as db:
        stocks = db.scalars(select(InventoryItem).where(InventoryItem.source_shopping_list_item_id == item_id)).all()
        assert len(stocks) == 1 and str(stocks[0].quantity) == "2.125000"
    print("PASS: eight concurrent purchases create exactly one stock batch")

    # Editing and purchasing must serialize on the same shopping item lock.
    url, item_id = add_item()
    barrier = Barrier(2)
    def edit():
        barrier.wait(timeout=10)
        return request("PATCH", url, actor="member", json={"quantity": "9.500"})
    def purchase():
        barrier.wait(timeout=10)
        return request("POST", url + "/purchase", json={})
    with ThreadPoolExecutor(max_workers=2) as pool:
        edit_future, buy_future = pool.submit(edit), pool.submit(purchase)
        edited, bought = edit_future.result(), buy_future.result()
    assert edited.status_code in (200, 409), edited.text
    assert bought.status_code == 200, bought.text
    with SessionLocal() as db:
        item = db.get(ShoppingListItem, item_id)
        stock = db.scalar(select(InventoryItem).where(InventoryItem.source_shopping_list_item_id == item_id))
        assert item.quantity == stock.quantity
        assert item.is_checked
    print("PASS: concurrent edit/purchase leaves stock quantity consistent")

    url, item_id = add_item()
    barrier = Barrier(2)
    def delete():
        barrier.wait(timeout=10)
        return request("DELETE", url, actor="member")
    with ThreadPoolExecutor(max_workers=2) as pool:
        delete_future, buy_future = pool.submit(delete), pool.submit(purchase)
        deleted, bought = delete_future.result(), buy_future.result()
    assert (deleted.status_code, bought.status_code) in ((204, 404), (409, 200)), (deleted.text, bought.text)
    print("PASS: concurrent delete/purchase preserves purchased history")

    url, item_id = add_item()
    original = shopping.purchase_and_stock
    def failure(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Injected failure after INSERT")
    with patch.object(shopping, "purchase_and_stock", side_effect=failure):
        assert request("POST", url + "/purchase", json={}).status_code == 500
    with SessionLocal() as db:
        assert db.get(ShoppingListItem, item_id).is_checked is False
        assert db.scalar(select(InventoryItem.id).where(InventoryItem.source_shopping_list_item_id == item_id)) is None
    print("PASS: PostgreSQL rolls back shopping state and stock on failure")

    assert request("POST", url + "/purchase", actor="outsider", json={}).status_code == 404
    foreign_url = f"/api/v1/households/{other_home}/shopping-list/items/{item_id}/purchase"
    assert request("POST", foreign_url, actor="outsider", json={}).status_code == 404
    assert request("GET", base + "?status=all").status_code == 200
    print("PASS: actual PostgreSQL household isolation and authenticated HTTP flow")
    engine.dispose()


if __name__ == "__main__":
    main()
