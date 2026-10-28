"""Real middleware, bearer sessions, and household permissions in one chain."""
import pytest

from test_v07_shopping import state, headers, base


@pytest.mark.parametrize("path", ["/api/v1/auth/login", "/api/v1/auth/register",
    "/api/v1/users/me", "/api/v1/agent/messages", "/api/v1/future-route"])
@pytest.mark.parametrize("method", ["GET", "POST", "PATCH", "DELETE", "OPTIONS"])
def test_gate_precedes_routes_identity_and_body(state, path, method):
    client, _, _ = state
    client.headers.pop("X-MagicVVu-App-Key")
    response = client.request(method, path, content=b"invalid-json")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "APP_KEY_INVALID"
    assert response.headers["cache-control"] == "no-store"


def test_wrong_duplicate_and_unconfigured_key(state, monkeypatch):
    client, _, _ = state
    for value in ("", "wrong", "synthetic-team-key, synthetic-team-key"):
        response = client.get("/api/v1/users/me", headers={"X-MagicVVu-App-Key": value})
        assert response.status_code == 403
    client.headers.pop("X-MagicVVu-App-Key")
    response = client.get("/api/v1/users/me", headers=[("X-MagicVVu-App-Key", "synthetic-team-key")] * 2)
    assert response.status_code == 403
    monkeypatch.delenv("MAGICVVU_APP_API_KEY")
    response = client.get("/api/v1/users/me", headers={"X-MagicVVu-App-Key": "synthetic-team-key"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "APP_KEY_NOT_CONFIGURED"


def test_key_never_grants_identity_or_household_access(state):
    client, _, ids = state
    assert client.get(base(ids)).status_code == 401
    assert client.get(base(ids), headers=headers("outsider")).status_code == 404
    assert client.get(base(ids), headers=headers("member")).status_code == 200
    url = f"/api/v1/households/{ids['home']}"
    assert client.patch(url, headers=headers("member"), json={"name": "Changed"}).status_code == 403
    assert client.patch(url, headers=headers(), json={"name": "Changed"}).status_code == 200
    client.headers.pop("X-MagicVVu-App-Key")
    assert client.get(base(ids), headers=headers()).status_code == 403


def test_private_health_remains_available(state, monkeypatch):
    client, _, _ = state
    monkeypatch.delenv("MAGICVVU_APP_API_KEY")
    assert client.get("/api/v1/health").status_code == 200
