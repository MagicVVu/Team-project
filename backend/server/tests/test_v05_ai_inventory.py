"""v0.5 read tool and migration regression tests. Uses disposable SQLite only."""
import os
import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DB_PASSWORD", "isolated-sqlite-test-not-secret")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# The production DB module builds a PostgreSQL engine at import time.
# Intercept it while importing so local tests need no psycopg/server.
import sqlalchemy  # noqa: E402
with patch("sqlalchemy.create_engine", return_value=create_engine("sqlite://")):
    from app.database import Base  # noqa: E402
    from app.dependencies import get_db  # noqa: E402
    from app.main import app  # noqa: E402
    from app.models import Household, HouseholdMember, InventoryItem, User  # noqa: E402


def _h(token="tool-v05-test-secret", user=None, home=None):
    h = {"Authorization": f"Bearer {token}"}
    if user is not None:
        h["X-User-Id"] = str(user)
    if home is not None:
        h["X-Household-Id"] = str(home)
    return h


@pytest.fixture
def state(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'api.sqlite'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    owner_id, outsider_id, disabled_id = uuid4(), uuid4(), uuid4()
    family_id, other_family_id = uuid4(), uuid4()
    good_id, same_id, other_id, zero_id, unknown_unit_id = [uuid4() for _ in range(5)]
    with Session.begin() as db:
        for uid, email, active in ((owner_id, "owner@example.test", True),
                                   (outsider_id, "outsider@example.test", True),
                                   (disabled_id, "disabled@example.test", False)):
            db.add(User(id=uid, email=email, password_hash="dummy-test-hash", display_name=email, is_active=active))
        db.flush()
        db.add_all([Household(id=family_id, name="Alpha", created_by_user_id=owner_id),
                    Household(id=other_family_id, name="Beta", created_by_user_id=outsider_id)])
        db.flush()
        db.add_all([
            HouseholdMember(household_id=family_id, user_id=owner_id, role="owner"),
            HouseholdMember(household_id=other_family_id, user_id=outsider_id, role="owner"),
            HouseholdMember(household_id=family_id, user_id=disabled_id, role="member"),
        ])
        db.add_all([
            InventoryItem(id=good_id, household_id=family_id, name="牛奶", quantity=Decimal("2.000001"), unit="盒", storage_location="冰箱", status="ACTIVE", version=7),
            InventoryItem(id=same_id, household_id=family_id, name="牛奶", quantity=Decimal("3.250000"), unit="瓶", status="ACTIVE", version=2),
            InventoryItem(id=other_id, household_id=other_family_id, name="牛奶", quantity=Decimal("8"), unit="瓶"),
            InventoryItem(id=zero_id, household_id=family_id, name="咖啡", quantity=Decimal("0"), unit="g", status="FINISHED"),
            InventoryItem(id=unknown_unit_id, household_id=family_id, name="老物品", quantity=Decimal("1"), unit="件"),
        ])
    monkeypatch.setenv("BACKEND_TOOL_TOKEN", "tool-v05-test-secret")
    def test_db():
        with Session() as session:
            yield session
    app.dependency_overrides[get_db] = test_db
    with TestClient(app) as client:
        yield client, Session, {
            "owner": owner_id, "outsider": outsider_id, "disabled": disabled_id,
            "family": family_id, "other": other_family_id,
            "good": good_id, "same": same_id, "other_item": other_id,
            "zero": zero_id, "legacy_unit": unknown_unit_id,
        }
    app.dependency_overrides.clear()
    engine.dispose()


def test_auth_fail_closed(state, monkeypatch):
    client, _, ids = state
    url = "/internal/v1/inventory/search"
    valid = _h(user=ids["owner"], home=ids["family"])
    assert client.get(url).status_code == 401
    assert client.get(url, headers=_h("wrong", ids["owner"], ids["family"])).status_code == 401
    monkeypatch.delenv("BACKEND_TOOL_TOKEN")
    assert client.get(url, headers=valid).status_code == 401
    monkeypatch.setenv("BACKEND_TOOL_TOKEN", "tool-v05-test-secret")
    assert client.get(url, headers=_h(user=ids["owner"])).status_code == 404
    assert client.get(url, headers=_h(user=ids["owner"], home=ids["other"])).status_code == 404
    assert client.get(url, headers=_h(user=ids["disabled"], home=ids["family"])).status_code == 404
    assert client.get(url, headers=_h(user=ids["outsider"], home=ids["family"])).status_code == 404
    assert client.get(url, headers=_h(user="not-uuid", home=ids["family"])).status_code == 404
    # Tool-token by itself is never an end-user login session.
    assert client.get("/api/v1/users/me", headers=valid).status_code == 401


def test_search_name_and_batch_contract(state):
    client, _, ids = state
    h = _h(user=ids["owner"], home=ids["family"])
    response = client.get("/internal/v1/inventory/search", headers=h, params={"name": "牛奶"})
    assert response.status_code == 200, response.text
    batches = response.json()["data"]["batches"]
    assert len(batches) == 2
    assert {b["id"] for b in batches} == {str(ids["good"]), str(ids["same"])}
    assert all(b["household_id"] == str(ids["family"]) for b in batches)
    b = next(b for b in batches if b["id"] == str(ids["good"]))
    assert b == {
        "id": str(ids["good"]), "household_id": str(ids["family"]),
        "name": "牛奶", "quantity": "2.000001", "unit": "盒", "location": "冰箱",
        "purchased_at": None, "label_expiry": None, "opened_at": None,
        "status": "ACTIVE", "version": 7,
    }
    exact = client.get(f"/internal/v1/inventory/batches/{ids['good']}", headers=h)
    assert exact.status_code == 200 and exact.json()["data"]["batch"] == b
    assert client.get(f"/internal/v1/inventory/batches/{ids['other_item']}", headers=h).status_code == 404
    assert client.get(f"/internal/v1/inventory/batches/{uuid4()}", headers=h).status_code == 404
    assert client.get("/internal/v1/inventory/search", headers=h, params={"name": "咖啡"}).json()["data"]["batches"][0]["status"] == "FINISHED"
    assert client.get("/internal/v1/inventory/search", headers=h, params={"name": "%"}).json()["data"]["batches"] == []
    assert client.get("/internal/v1/inventory/search", headers=h, params={"name": "  "}).status_code == 422
    assert client.get("/internal/v1/inventory/search", headers=h, params={"name": "老物品"}).status_code == 409
    assert client.get(f"/internal/v1/inventory/batches/{ids['legacy_unit']}", headers=h).status_code == 409
    # Unfiltered query intentionally fails on incompatible legacy units: no silent drop.
    assert client.get("/internal/v1/inventory/search", headers=h).status_code == 409


def test_more_than_1000_rejected(state):
    client, Session, ids = state
    with Session.begin() as db:
        db.add_all([InventoryItem(
            household_id=ids["family"], name="批量测试", quantity=Decimal("1"), unit="盒"
        ) for _ in range(1001)])
    r = client.get("/internal/v1/inventory/search", headers=_h(user=ids["owner"], home=ids["family"]), params={"name": "批量测试"})
    assert r.status_code == 409


def test_v04_to_v05_migration_preserves_rows(tmp_path):
    from uuid import uuid4
    engine = create_engine(f"sqlite:///{tmp_path / 'upgrade.sqlite'}", connect_args={"check_same_thread": False})
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    with patch("sqlalchemy.create_engine", return_value=engine):
        command.upgrade(cfg, "20261014_0003")
    uid, hid, positive, empty = [uuid4() for _ in range(4)]
    with engine.begin() as c:
        c.execute(text("INSERT INTO users(id,email,password_hash,display_name) VALUES(:id,'migrate@test.invalid','dummy','Migrated')"), {"id": uid.hex})
        c.execute(text("INSERT INTO households(id,name,created_by_user_id) VALUES(:id,'Home',:uid)"), {"id": hid.hex, "uid": uid.hex})
        c.execute(text("INSERT INTO inventory_items(id,household_id,name,quantity,unit,storage_location) VALUES (:id,:hid,'牛奶',:q,'盒','冰箱')"), {"id":positive.hex, "hid":hid.hex, "q":"2.125"})
        c.execute(text("INSERT INTO inventory_items(id,household_id,name,quantity,unit) VALUES (:id,:hid,'旧零库存',0,'件')"), {"id":empty.hex, "hid":hid.hex})
    with patch("sqlalchemy.create_engine", return_value=engine):
        command.upgrade(cfg, "20261014_0004")
    info = {c["name"]:c for c in inspect(engine).get_columns("inventory_items")}
    assert {"opened_at", "status", "version"}.issubset(info)
    assert info["quantity"]["type"].precision == 16
    assert info["quantity"]["type"].scale == 6
    with engine.connect() as c:
        row = c.execute(text("SELECT quantity,unit,storage_location,status,version,opened_at FROM inventory_items WHERE id=:id"), {"id": positive.hex}).one()
        assert Decimal(str(row[0])) == Decimal("2.125") and row[1:]==("盒","冰箱","ACTIVE",1,None)
        row2 = c.execute(text("SELECT status,version FROM inventory_items WHERE id=:id"), {"id":empty.hex}).one()
        assert row2 == ("FINISHED",1)
        assert c.execute(text("SELECT version_num FROM alembic_version")).scalar() == "20261014_0004"
    engine.dispose()


def test_live_read_smoke_rolls_back(tmp_path, monkeypatch, capsys):
    from app import ai_inventory_smoke
    engine = create_engine(f"sqlite:///{tmp_path / 'smoke.sqlite'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    monkeypatch.setattr(ai_inventory_smoke, "engine", engine)
    monkeypatch.setenv("BACKEND_TOOL_TOKEN", "test-smoke-private-tool-key-with-enough-entropy")
    ai_inventory_smoke.main()
    output = capsys.readouterr().out
    assert "AI READ SMOKE PASSED" in output
    assert "AI READ TEST DATA ROLLED BACK" in output
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM users")).scalar() == 0
        assert connection.execute(text("SELECT count(*) FROM inventory_items")).scalar() == 0
    engine.dispose()
