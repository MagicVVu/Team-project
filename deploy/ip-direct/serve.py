"""One backend process: private HTTP for Agent, source-restricted public TLS.

Mount beside the existing image; do not replace business code or migrate data.
"""
import asyncio
from collections import defaultdict, deque
from contextlib import contextmanager
import signal
import time

import uvicorn
from uvicorn.importer import import_from_string


class PublicAPI:
    def __init__(self, app):
        self.app = app
        self.attempts = defaultdict(deque)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            return
        path = scope["path"]
        status = None
        if not (path.startswith("/api/v1/") or path == "/health") or path == "/api/v1/ready":
            status = 404
        # Actual TCP peer only. Forwarded headers are never trusted.
        now = time.monotonic()
        for key in list(self.attempts):
            while self.attempts[key] and self.attempts[key][0] <= now - 60:
                self.attempts[key].popleft()
            if not self.attempts[key]:
                del self.attempts[key]
        peer = (scope.get("client") or ("unknown",))[0]
        key = (peer, "auth" if path.startswith("/api/v1/auth/") else "api")
        limit = 8 if key[1] == "auth" else 120
        if len(self.attempts) >= 1024 and key not in self.attempts:
            status = 429
        elif len(self.attempts[key]) >= limit:
            status = 429
        else:
            self.attempts[key].append(now)
        if status:
            await send({"type": "http.response.start", "status": status,
                        "headers": [(b"content-type", b"application/json"), (b"cache-control", b"no-store")]})
            await send({"type": "http.response.body", "body": b'{"detail":"Public request rejected"}'})
            return
        # Validate before reading a body, including public health probes.
        # Imported lazily so the standalone edge tests can supply the backend path.
        from app.app_access import app_key_error
        error = app_key_error(scope)
        if error is not None:
            await error(scope, receive, send)
            return
        # Bound request memory before handing a complete body to the existing app.
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > 65536:
                await send({"type": "http.response.start", "status": 413, "headers": []})
                await send({"type": "http.response.body", "body": b""})
                return
            if not message.get("more_body"):
                break
        delivered = False

        async def buffered_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        if path == "/health":
            scope = {**scope, "path": "/api/v1/health", "raw_path": b"/api/v1/health"}
        await self.app(scope, buffered_receive, send)


class ManagedServer(uvicorn.Server):
    @contextmanager
    def capture_signals(self):
        # Both listeners are stopped together by main(), never two signal owners.
        yield


async def main():
    app = import_from_string("app.main:app")
    common = dict(host="0.0.0.0", workers=1, proxy_headers=False,
                  access_log=False, timeout_keep_alive=5, timeout_graceful_shutdown=20)
    internal = ManagedServer(uvicorn.Config(app, port=8000, **common))
    external = ManagedServer(uvicorn.Config(
        PublicAPI(app), port=8443, lifespan="off", limit_concurrency=32,
        ssl_certfile="/run/magicvvu-tls/server.crt",
        ssl_keyfile="/run/magicvvu-tls/server.key", **common))
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    running = [asyncio.create_task(s.serve()) for s in (internal, external)]
    stopping = asyncio.create_task(stop.wait())
    done, _ = await asyncio.wait([*running, stopping], return_when=asyncio.FIRST_COMPLETED)
    failed = stopping not in done
    internal.should_exit = external.should_exit = True
    try:
        await asyncio.wait_for(asyncio.gather(*running), timeout=25)
    finally:
        stopping.cancel()
    if failed:
        raise RuntimeError("A backend listener stopped unexpectedly")


if __name__ == "__main__":
    asyncio.run(main())
