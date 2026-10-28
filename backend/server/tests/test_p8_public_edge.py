"""Optional real-nginx gateway test, never uses Funnel or any remote service.

Set P8_NGINX_EXE to a local nginx binary. The fixture uses temporary config,
dynamic loopback ports, synthetic PROXY v2 addresses and a fake upstream.
"""
import json
import os
import socket
import struct
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def edge(tmp_path_factory):
    binary = os.getenv("P8_NGINX_EXE")
    if not binary:
        pytest.skip("Set P8_NGINX_EXE to run actual gateway acceptance")
    binary = str(Path(binary).resolve(strict=True))
    forwarded = []
    class Upstream(BaseHTTPRequestHandler):
        def do_GET(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            forwarded.append(self.path)
            payload = json.dumps({"path": self.path, "headers": dict(self.headers)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        do_POST = do_GET
        def log_message(self, *_):
            pass
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    worker = threading.Thread(target=upstream.serve_forever, daemon=True)
    worker.start()
    temp = tmp_path_factory.mktemp("p8-edge")
    for folder in ["logs", "temp"]:
        (temp / folder).mkdir()
    port = free_port()
    candidate = Path(__file__).resolve().parents[3] / "deploy/p8/nginx-public.conf.candidate"
    config = candidate.read_text().replace("127.0.0.1:18081", f"127.0.0.1:{port}")
    config = config.replace("127.0.0.1:8000", f"127.0.0.1:{upstream.server_port}")
    (temp / "nginx.conf").write_text(config)
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    args = [binary, "-p", temp.as_posix() + "/", "-c", "nginx.conf"]
    check = subprocess.run(args + ["-t"], capture_output=True, text=True, creationflags=flags)
    assert check.returncode == 0, check.stderr
    log = (temp / "process.log").open("wb")
    process = subprocess.Popen(args + ["-g", "daemon off; master_process off;"],
                               stdout=log, stderr=log, creationflags=flags)
    try:
        for _ in range(100):
            if process.poll() is not None:
                pytest.fail((temp / "process.log").read_text())
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            pytest.fail("temporary nginx failed to listen")
        yield port, forwarded
    finally:
        subprocess.run(args + ["-s", "quit"], capture_output=True, creationflags=flags)
        try:
            process.wait(5)
        except subprocess.TimeoutExpired:
            process.kill()  # Only the process created by this fixture.
            process.wait(5)
        log.close()
        upstream.shutdown()
        upstream.server_close()
        worker.join(5)


def request(edge, path, ip="198.51.100.10", extra="", proxy=True, method="GET"):
    port, _ = edge
    header = (b"\r\n\r\n\0\r\nQUIT\n" + bytes([0x21, 0x11]) + struct.pack("!H", 12)
              + socket.inet_aton(ip) + socket.inet_aton("127.0.0.1") + struct.pack("!HH", 12000, port))
    http = f"{method} {path} HTTP/1.1\r\nHost: synthetic.invalid\r\nConnection: close\r\n{extra}\r\n".encode()
    with socket.create_connection(("127.0.0.1", port), timeout=3) as sock:
        sock.sendall((header if proxy else b"") + http)
        data = b""
        try:
            while part := sock.recv(65536):
                data += part
        except ConnectionResetError:
            pass
    return data


@pytest.mark.parametrize("path", ["/internal/v1/inventory/search", "/internal/v1/operations/00000000-0000-0000-0000-000000000000",
    "/openapi.json", "/docs", "/redoc", "/api/v1/ready", "/admin", "/debug",
    "/api/v1/../../internal/v1/inventory/search", "/api/v1/%2e%2e/%2e%2e/internal/v1/inventory/search",
    "/api/v1/..%2f..%2finternal/v1/inventory/search", "//internal/v1/inventory/search"])
def test_gateway_denies_paths_before_upstream(edge, path):
    _, forwarded = edge
    before = len(forwarded)
    response = request(edge, path)
    assert b" 404 " in response.split(b"\r\n", 1)[0], response[:300]
    assert len(forwarded) == before


def test_gateway_allows_app_and_strips_untrusted_claims(edge):
    response = request(edge, "/api/v1/health", extra="X-Forwarded-For: 203.0.113.7\r\n"
        "X-Real-IP: 203.0.113.7\r\nForwarded: for=203.0.113.7\r\n"
        "X-MagicVVu-Client-IP: 203.0.113.7\r\nAuthorization: Bearer synthetic-test-only\r\n")
    assert b" 200 " in response.split(b"\r\n", 1)[0]
    body = json.loads(response.split(b"\r\n\r\n", 1)[1])
    headers = {k.lower(): v for k, v in body["headers"].items()}
    assert "x-forwarded-for" not in headers and "forwarded" not in headers
    assert "x-real-ip" not in headers and "x-magicvvu-client-ip" not in headers
    assert headers["authorization"] == "Bearer synthetic-test-only"


def test_gateway_real_ip_throttle_cannot_be_bypassed_by_headers(edge):
    for n in range(5):
        response = request(edge, "/api/v1/auth/login", ip="198.51.100.71",
                           extra=f"X-Forwarded-For: 203.0.113.{n}\r\n", method="POST")
        assert b" 200 " in response.split(b"\r\n", 1)[0]
    limited = request(edge, "/api/v1/auth/login", ip="198.51.100.71",
                      extra="X-Forwarded-For: 203.0.113.99\r\n", method="POST")
    assert b" 429 " in limited.split(b"\r\n", 1)[0]
    assert b"Retry-After: 10" in limited
    assert b" 200 " in request(edge, "/api/v1/auth/login", ip="198.51.100.72", method="POST").split(b"\r\n", 1)[0]


def test_gateway_refuses_plain_http_without_proxy_metadata(edge):
    assert not request(edge, "/api/v1/health", proxy=False).startswith(b"HTTP/1.1 200")


def test_gateway_refuses_public_signup(edge):
    assert b" 403 " in request(edge, "/api/v1/auth/register", method="POST").split(b"\r\n", 1)[0]
