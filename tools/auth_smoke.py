"""Exercise the deployed image in a network-isolated, disposable SQLite runner.

Run with AUTH_TEST_ISOLATED=yes, DB_PASSWORD=unused, --network none and /tmp
as tmpfs. Optionally mount the deployed TLS wrapper at /tmp/direct.py.
Only check names and booleans are printed; credentials never leave this process.
"""
import importlib.util
import json
import os
import secrets
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

assert os.environ.get("AUTH_TEST_ISOLATED") == "yes"
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

engine = create_engine("sqlite:////tmp/auth-smoke.sqlite", connect_args={"check_same_thread": False})
with patch("sqlalchemy.create_engine", return_value=engine):
    from app.database import Base
    from app.dependencies import get_db
    from app.main import app
    from app.models import AuthSession, User
from app.security import digest_token, now_utc, verify_password

Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine, autoflush=False)


def database():
    with Session() as db:
        yield db


app.dependency_overrides[get_db] = database
checks = {}
completed = False


def check(name, condition):
    checks[name] = bool(condition)
    if not condition:
        raise AssertionError(name)


payload = {"phone": "19900000001", "password": secrets.token_urlsafe(24), "display_name": " Auth smoke "}
try:
    with TestClient(app) as client:
        os.environ["AUTH_ALLOW_UNVERIFIED_SIGNUP"] = "false"
        check("signup_can_be_disabled", client.post("/api/v1/auth/register", json=payload).status_code == 403)
        os.environ["AUTH_ALLOW_UNVERIFIED_SIGNUP"] = "true"
        for label, changed in {
            "invalid_phone": {"phone": "invalid"},
            "short_password": {"password": "short"},
            "long_password": {"password": "x" * 129},
            "blank_name": {"display_name": "   "},
            "extra_fields": {"is_active": True},
        }.items():
            check(label, client.post("/api/v1/auth/register", json={**payload, **changed}).status_code == 422)
        registered = client.post("/api/v1/auth/register", json=payload)
        check("register_201", registered.status_code == 201)
        user_id = registered.json()["id"]
        check("phone_normalized", registered.json()["phone"] == "+8619900000001")
        check("phone_remains_unverified", registered.json()["phone_verified"] is False)
        check("name_trimmed", registered.json()["display_name"] == "Auth smoke")
        check("response_contains_no_password", not ({"password", "password_hash"} & registered.json().keys()))
        canonical = {**payload, "phone": "+8619900000001"}
        check("duplicate_phone_409", client.post("/api/v1/auth/register", json=canonical).status_code == 409)
        credentials = {k: canonical[k] for k in ("phone", "password")}
        wrong = client.post("/api/v1/auth/login", json={**credentials, "password": "wrong"})
        missing = client.post("/api/v1/auth/login", json={**credentials, "phone": "+199900000099"})
        check("wrong_password_401", wrong.status_code == 401)
        check("missing_account_same_error", missing.status_code == 401 and missing.json() == wrong.json())
        check("anonymous_profile_401", client.get("/api/v1/users/me").status_code == 401)
        login = client.post("/api/v1/auth/login", json=credentials)
        check("login_200", login.status_code == 200)
        token = login.json()["access_token"]
        auth = {"Authorization": "Bearer " + token}
        check("token_contract", login.json()["token_type"] == "bearer" and login.json()["expires_in"] == 43200)
        check("profile_matches_registered_user", client.get("/api/v1/users/me", headers=auth).json()["id"] == user_id)
        check("new_user_has_no_other_households", client.get("/api/v1/households", headers=auth).json() == [])
        with Session() as db:
            user = db.scalar(select(User).where(User.phone == canonical["phone"]))
            check("argon2id_password_at_rest", user.password_hash.startswith("$argon2id$") and verify_password(user.password_hash, payload["password"]))
            session = db.scalar(select(AuthSession).where(AuthSession.user_id == user.id))
            check("only_token_digest_at_rest", session.token_hash == digest_token(token) and session.token_hash != token)
        check("logout_200", client.post("/api/v1/auth/logout", headers=auth).status_code == 200)
        check("revoked_token_401", client.get("/api/v1/users/me", headers=auth).status_code == 401)
        again = client.post("/api/v1/auth/login", json=credentials)
        check("login_again_200", again.status_code == 200)
        with Session.begin() as db:
            user = db.scalar(select(User).where(User.phone == canonical["phone"]))
            user.is_active = False
        disabled = client.post("/api/v1/auth/login", json=credentials)
        check("disabled_account_401", disabled.status_code == 401 and disabled.json() == wrong.json())
        with Session.begin() as db:
            user = db.scalar(select(User).where(User.phone == canonical["phone"]))
            user.is_active = True
            for session in db.scalars(select(AuthSession).where(AuthSession.user_id == user.id)):
                session.expires_at = now_utc() - timedelta(seconds=1)
        check("expired_token_401", client.get("/api/v1/users/me", headers={"Authorization": "Bearer " + again.json()["access_token"]}).status_code == 401)

    if Path("/tmp/direct.py").is_file():
        spec = importlib.util.spec_from_file_location("direct", "/tmp/direct.py")
        direct = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(direct)
        def public_test_app():
            edge = direct.PublicAPI(app)

            async def asgi(scope, receive, send):
                # Production runs this edge with lifespan="off"; delegate the
                # TestClient startup/shutdown to FastAPI for the test only.
                await (app if scope["type"] == "lifespan" else edge)(scope, receive, send)

            return asgi

        with TestClient(public_test_app()) as public:
            for path in ("/docs", "/openapi.json", "/api/v1/ready", "/internal/v1/inventory/search"):
                check("public_blocks_" + path, public.get(path).status_code == 404)
            for n in range(8):
                check("public_auth_attempt_" + str(n + 1), public.post("/api/v1/auth/register", json={}).status_code == 422)
            check("public_signup_throttled_429", public.post("/api/v1/auth/register", json={}, headers={"X-Forwarded-For": "192.0.2.100"}).status_code == 429)
        with TestClient(public_test_app()) as public:
            check("public_login_throttled_429", all(public.post("/api/v1/auth/login", json={}).status_code == 422 for _ in range(8)) and public.post("/api/v1/auth/login", json={}).status_code == 429)
            check("public_body_limit_413", public.post("/api/v1/users/me", content=b"x" * 65537).status_code == 413)
    completed = True
finally:
    app.dependency_overrides.clear()
    engine.dispose()
    print(json.dumps({"isolated": True, "production_database_accessed": False, "checks": checks, "passed": completed and all(checks.values())}, sort_keys=True))
