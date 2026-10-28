"""Client possession gate, independent of user identity and business permissions."""

import os
import secrets

from starlette.responses import JSONResponse

HEADER = b"x-magicvvu-app-key"
PROBES = {"/api/v1/health", "/api/v1/ready"}


def app_key_error(scope):
    expected = os.getenv("MAGICVVU_APP_API_KEY", "")
    if not expected or not expected.isascii() or expected.strip() != expected:
        return JSONResponse(status_code=503, content={"detail": {"code": "APP_KEY_NOT_CONFIGURED"}},
                            headers={"Cache-Control": "no-store"})
    values = [value for name, value in scope.get("headers", []) if name.lower() == HEADER]
    if len(values) != 1 or not secrets.compare_digest(values[0], expected.encode("ascii")):
        return JSONResponse(status_code=403, content={"detail": {"code": "APP_KEY_INVALID"}},
                            headers={"Cache-Control": "no-store"})
    return None


class AppKeyMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        # Private probes support Docker health checks and internal AI preflight.
        # The TLS wrapper independently gates public health and its /health alias.
        path = scope.get("path", "")
        if scope["type"] == "http" and (path == "/api/v1" or path.startswith("/api/v1/")) and path not in PROBES:
            error = app_key_error(scope)
            if error is not None:
                await error(scope, receive, send)
                return
        await self.app(scope, receive, send)
