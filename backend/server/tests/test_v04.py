"""Integration tests against isolated SQLite, never the cloud database."""

import os
import sys
import tempfile
from uuid import UUID, uuid4
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("DB_PASSWORD", "sqlite-test-only")
os.environ["AUTH_ALLOW_UNVERIFIED_SIGNUP"] = "true"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sqlalchemy
from sqlalchemy import create_engine as original_create_engine, inspect, select
from sqlalchemy.orm import sessionmaker
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient


def test_migrated_phone_auth():
    with tempfile.TemporaryDirectory() as td:
        db_url = f"sqlite:///{td}/magicvvu.sqlite"
        engine = original_create_engine(db_url, connect_args={"check_same_thread": False})
        # Existing database.py expects psycopg in real deployments. For local
        # tests only, intercept creation of the engine before the module loads.
        with patch("sqlalchemy.create_engine", return_value=engine):
            import app.database as database
        database.database_url = lambda: db_url
        database.engine = engine
        database.SessionLocal = sessionmaker(bind=engine, autoflush=False)
        import app.models as models
        from app import dependencies
        import app.main as main
        main.engine = engine
        dependencies.SessionLocal = database.SessionLocal
        cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
        with patch("sqlalchemy.create_engine", return_value=engine):
            command.upgrade(cfg, "20261014_0002")
        previous_user_id = uuid4()
        with engine.begin() as con:
            con.execute(sqlalchemy.text(
                "INSERT INTO users(id, email, password_hash, display_name) "
                "VALUES(:id, :email, :password_hash, :display_name)"
            ), dict(id=previous_user_id.hex, email="old@example.test", password_hash="legacy", display_name="Legacy"))
        with patch("sqlalchemy.create_engine", return_value=engine):
            command.upgrade(cfg, "head")
        with engine.connect() as con:
            legacy = con.execute(sqlalchemy.text(
                "SELECT email, phone FROM users WHERE id=:id"
            ), {"id": previous_user_id.hex}).one()
            assert legacy == ("old@example.test", None)
        tables = set(inspect(engine).get_table_names())
        assert {"users", "households", "shopping_lists", "shopping_list_items", "inventory_items", "auth_sessions", "household_invitations"}.issubset(tables)
        with TestClient(main.app) as client:
            assert client.get("/api/v1/health").json()["version"] == main.app.version
            assert client.get("/api/v1/ready").status_code == 200
            u1={"phone":"13800138000","password":"Pass1234","display_name":"Evan"}
            u2={"phone":"13900139000","password":"Passphrase1234","display_name":"Teammate"}
            with patch.dict(os.environ, {"AUTH_ALLOW_UNVERIFIED_SIGNUP": "false"}):
                assert client.post("/api/v1/auth/register", json=u1).status_code==403
            assert client.post("/api/v1/auth/register", json=u1).status_code==201
            assert client.post("/api/v1/auth/register", json=u2).status_code==201
            assert client.post("/api/v1/auth/register", json=u1).status_code==409
            assert client.post("/api/v1/auth/login", json={"phone":u1['phone'],"password":"bad"}).status_code==401
            r=client.post("/api/v1/auth/login", json={"phone":u1['phone'],"password":u1['password']})
            assert r.status_code==200, r.text
            h1={"Authorization":"Bearer "+r.json()['access_token']}
            assert client.get('/api/v1/users/me',headers=h1).json()['phone_verified'] is False
            h=client.post('/api/v1/households', headers=h1, json={"name":"Home"})
            assert h.status_code==201, h.text
            household_id=h.json()['id']
            assert client.get('/api/v1/households',headers=h1).json()[0]['my_role']=='owner'
            with database.SessionLocal() as s:
                household=s.get(models.Household,UUID(household_id))
                assert household
                assert s.scalar(select(models.ShoppingList).where(models.ShoppingList.household_id==household.id))
            r2=client.post('/api/v1/auth/login',json={"phone":u2['phone'],"password":u2['password']})
            assert r2.status_code==200,r2.text
            h2={"Authorization":"Bearer "+r2.json()['access_token']}
            assert client.get(f'/api/v1/households/{household_id}/members',headers=h2).status_code==404
            invite=client.post(f'/api/v1/households/{household_id}/invitations',headers=h1)
            assert invite.status_code==201, invite.text
            code=invite.json()['invite_code']
            joined=client.post('/api/v1/households/join',headers=h2,json={"invite_code":code})
            assert joined.status_code==200,joined.text
            assert joined.json()['my_role']=='member'
            assert client.post('/api/v1/households/join',headers=h2,json={"invite_code":code}).status_code==400
            assert len(client.get(f'/api/v1/households/{household_id}/members',headers=h2).json())==2
            assert client.post(f'/api/v1/households/{household_id}/invitations',headers=h2).status_code==403
            assert client.post('/api/v1/auth/logout',headers=h1).status_code==200
            assert client.get('/api/v1/users/me',headers=h1).status_code==401
            assert client.get('/api/v1/households').status_code==401
            print("V0.4 SMOKE PASSED: register/login/session/logout, unique phone, unverified status, family, list, invite, access control")
        engine.dispose()


if __name__ == "__main__":
    test_migrated_phone_auth()
