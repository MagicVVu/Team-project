"""Existing API regressions run as clients holding a synthetic team key."""
import httpx
import pytest


@pytest.fixture(autouse=True)
def team_client_access(monkeypatch):
    monkeypatch.setenv("MAGICVVU_APP_API_KEY", "synthetic-team-key")
    for cls in (httpx.Client, httpx.AsyncClient):
        original = cls.__init__

        def init(self, *args, _original=original, **kwargs):
            headers = httpx.Headers(kwargs.pop("headers", None))
            headers.setdefault("X-MagicVVu-App-Key", "synthetic-team-key")
            kwargs["headers"] = headers
            _original(self, *args, **kwargs)

        monkeypatch.setattr(cls, "__init__", init)
