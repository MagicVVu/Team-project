import unittest
import os
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend/server"))
from serve import PublicAPI


class PublicAPITest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        env = patch.dict(os.environ, MAGICVVU_APP_API_KEY="synthetic-team-key")
        env.start()
        self.addCleanup(env.stop)

    async def request(self, path, *, app=None, body=b"", peer="192.0.2.1", headers=None, key=True):
        seen = []
        async def business(scope, receive, send):
            seen.append((scope["path"], await receive()))
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})
        app = app or PublicAPI(business)
        output = []
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}
        async def send(message):
            output.append(message)
        access = [(b"x-magicvvu-app-key", b"synthetic-team-key")] if key else []
        await app({"type": "http", "path": path, "client": (peer, 123), "headers": access + (headers or [])}, receive, send)
        return output[0]["status"], seen

    async def test_public_health_and_business_require_key(self):
        for path in ("/health", "/api/v1/health", "/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/users/me"):
            status, seen = await self.request(path, key=False)
            self.assertEqual(status, 403)
            self.assertEqual(seen, [])

    async def test_internal_and_admin_routes_never_reach_business(self):
        for path in ("/internal/v1/inventory/search", "/api/v1/ready", "/docs", "/openapi.json", "/admin", "/"):
            status, seen = await self.request(path)
            self.assertEqual(status, 404)
            self.assertEqual(seen, [])

    async def test_health_alias_and_original_api_preserve_body(self):
        status, seen = await self.request("/health")
        self.assertEqual(status, 200)
        self.assertEqual(seen[0][0], "/api/v1/health")
        _, seen = await self.request("/api/v1/agent/messages", body=b'{"text":"test"}')
        self.assertEqual(seen[0][1]["body"], b'{"text":"test"}')

    async def test_oversized_request_rejected_before_business(self):
        status, seen = await self.request("/api/v1/agent/messages", body=b"x" * 65537)
        self.assertEqual(status, 413)
        self.assertEqual(seen, [])

    async def test_login_limit_does_not_trust_forwarded_headers(self):
        async def business(scope, receive, send):
            await send({"type": "http.response.start", "status": 401, "headers": []})
        app = PublicAPI(business)
        for _ in range(8):
            status, _ = await self.request("/api/v1/auth/login", app=app)
            self.assertEqual(status, 401)
        status, _ = await self.request("/api/v1/auth/login", app=app, headers=[(b"x-forwarded-for", b"192.0.2.9")])
        self.assertEqual(status, 429)
        status, _ = await self.request("/api/v1/auth/login", app=app, peer="192.0.2.2")
        self.assertEqual(status, 401)


if __name__ == "__main__":
    unittest.main()
