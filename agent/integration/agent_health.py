"""Container probe for release, selected engine and read-only capabilities."""
import json
import os
from urllib.request import ProxyHandler, Request, build_opener


def validate(body, expected_engine):
    return (body.get("status") == "ok" and body.get("release_version") == "V1-P2"
        and body.get("engine") == expected_engine and body.get("inventory_writes") is False
        and "p2-risk-selection-1" in body.get("clarification_protocols", [])
        and bool(body.get("ruleset_sha256")))


def main():
    try:
        request = Request("http://127.0.0.1:8767/health")
        with build_opener(ProxyHandler({})).open(request, timeout=3) as response:
            body = json.load(response)
        return 0 if validate(body, os.getenv("P2_ENGINE", "rules")) else 1
    except (OSError, ValueError, TypeError, AttributeError):
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
