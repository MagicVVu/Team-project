"""P8 checks use only disposable SQLite, synthetic users and in-process HTTP."""
import asyncio
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from time import monotonic
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DB_PASSWORD", "p8-unused-isolated-test")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with patch("sqlalchemy.create_engine", return_value=create_engine("sqlite://")):
    from app.database import Base
    from app.dependencies import get_db
    from app.main import app
    from app.models import AuthSession, User
from app.login_guard import LoginGuard
from app.security import hash_password


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path/'p8.sqlite'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    with Session.begin() as db:
        db.add_all([User(id=uuid4(), phone="+15550000001", display_name="Synthetic",
                         password_hash=hash_password("P8-fake-password!")),
                    User(id=uuid4(), phone="+15550000002", display_name="Disabled",
                         is_active=False, password_hash=hash_password("P8-fake-password!"))])
    def database():
        with Session() as db:
            yield db
    app.dependency_overrides[get_db] = database
    monkeypatch.setattr(app.state, "login_guard", LoginGuard())
    try:
        with TestClient(app, client=("192.0.2.20", 12345)) as client:
            yield client, Session
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def attempt(client, phone="+15550000001", password="wrong", headers=None):
    return client.post("/api/v1/auth/login", json={"phone": phone, "password": password}, headers=headers)


def test_wrong_missing_disabled_accounts_have_same_failure_and_argon_cost(isolated):
    client, Session = isolated
    from app import security
    with patch.object(security, "verify_password", wraps=security.verify_password) as verify:
        responses = []
        for phone in ["+15550000001", "+15550000999", "+15550000002"]:
            start = monotonic()
            responses.append(attempt(client, phone))
            assert monotonic() - start >= 0.24
        assert verify.call_count == 3
        assert all(call.args[0].startswith("$argon2id$") for call in verify.call_args_list)
    assert [r.status_code for r in responses] == [401] * 3
    assert all(r.json() == {"detail": "Invalid phone or password"} for r in responses)
    assert all(r.headers["cache-control"] == "no-store" for r in responses)
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(AuthSession)) == 0


def test_login_token_logout_contract_and_password_bound(isolated):
    client, _ = isolated
    login = attempt(client, password="P8-fake-password!")
    assert login.status_code == 200
    assert set(login.json()) == {"access_token", "token_type", "expires_in"}
    assert login.json()["token_type"] == "bearer" and login.json()["expires_in"] == 43200
    assert login.headers["cache-control"] == "no-store"
    auth = {"Authorization": "Bearer " + login.json()["access_token"]}
    assert client.get("/api/v1/users/me", headers=auth).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=auth).status_code == 200
    assert client.get("/api/v1/users/me", headers=auth).status_code == 401
    assert attempt(client, password="x" * 129).status_code == 422


def test_account_throttle_precedes_db_hash_and_success_cannot_reset_it(isolated, monkeypatch):
    client, _ = isolated
    monkeypatch.setattr(app.state, "login_guard", LoginGuard(account_limit=2))
    assert attempt(client).status_code == 401
    assert attempt(client, password="P8-fake-password!").status_code == 200
    with patch("app.routers.auth.verify_login_password", side_effect=AssertionError("must not hash")):
        response = attempt(client, password="P8-fake-password!")
    assert response.status_code == 429
    assert 1 <= int(response.headers["retry-after"]) <= 300
    assert "1555" not in response.text


def test_fake_forwarding_headers_cannot_bypass_peer_limit(isolated, monkeypatch):
    client, _ = isolated
    monkeypatch.setattr(app.state, "login_guard", LoginGuard(ip_limit=2))
    for n in range(2):
        assert attempt(client, f"+1555000090{n}", headers={"X-Forwarded-For": f"198.51.100.{n}"}).status_code == 401
    response = attempt(client, "+15550000902", headers={"Forwarded": "for=203.0.113.7",
                      "X-Forwarded-For": "203.0.113.7", "X-Real-IP": "203.0.113.7",
                      "X-MagicVVu-Client-IP": "203.0.113.7"})
    assert response.status_code == 429
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text()
    assert '"--no-proxy-headers"' in dockerfile


def test_account_normalization_and_unknown_accounts_are_also_limited(isolated, monkeypatch):
    client, _ = isolated
    monkeypatch.setattr(app.state, "login_guard", LoginGuard(account_limit=1))
    assert attempt(client, "13800138000").status_code == 401
    assert attempt(client, "+8613800138000").status_code == 429


def test_guard_account_limit_spans_ips_and_recovers_after_window():
    now = [100.0]
    guard = LoginGuard(account_limit=2, clock=lambda: now[0])
    for peer in ["192.0.2.1", "192.0.2.2"]:
        with guard.attempt(peer, "+15550000000"):
            pass
    with pytest.raises(HTTPException) as exc:
        with guard.attempt("192.0.2.3", "+15550000000"):
            pass
    assert exc.value.status_code == 429 and exc.value.headers["Retry-After"] == "300"
    now[0] += 300
    with guard.attempt("192.0.2.3", "+15550000000"):
        pass


def test_guard_global_capacity_and_exception_cleanup():
    guard = LoginGuard(global_limit=2, max_inflight=1)
    with pytest.raises(ValueError):
        with guard.attempt("a", "one"):
            raise ValueError("synthetic")
    with guard.attempt("b", "two"):
        pass
    with pytest.raises(HTTPException):
        with guard.attempt("c", "three"):
            pass
    assert guard._inflight == 0


def test_guard_does_not_evict_live_keys_to_admit_rotating_attack():
    now = [0.0]
    guard = LoginGuard(max_keys=3, clock=lambda: now[0])
    with guard.attempt("one", "one"):
        pass
    with pytest.raises(HTTPException):
        with guard.attempt("two", "two"):
            pass
    assert len(guard._buckets) == 3
    now[0] = 301
    with guard.attempt("two", "two"):
        pass


def test_parallel_admission_is_atomic_and_bounds_hash_workers():
    guard = LoginGuard(max_inflight=2)
    release, ready = Event(), Event()
    def hold(n):
        with guard.attempt(str(n), str(n)):
            if n == 1:
                ready.set()
            assert release.wait(5)
    with ThreadPoolExecutor(2) as executor:
        first, second = executor.submit(hold, 0), executor.submit(hold, 1)
        assert ready.wait(5)
        try:
            with pytest.raises(HTTPException) as exc:
                with guard.attempt("third", "third"):
                    pass
            assert exc.value.headers["Retry-After"] == "1"
        finally:
            release.set()
        first.result(); second.result()
    assert guard._inflight == 0


@pytest.mark.parametrize("path", ["/openapi.json", "/docs", "/redoc"])
def test_docs_closed_by_default(isolated, path):
    client, _ = isolated
    assert client.get(path).status_code == 404


def test_preflight_with_real_backend_and_disabled_docs(isolated):
    from app.p7_preflight import check_http
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://127.0.0.1:8000") as client:
            # Disable agent branch; this test covers live backend route probing.
            return await check_http(client, {})
    # ready uses main.engine instead of the dependency override; avoid DB access.
    with patch("app.main.engine", create_engine("sqlite://")):
        checks = asyncio.run(run())
    assert checks["backend_p7_version"] and checks["execution_routes"]
