import json
import os
from urllib.request import ProxyHandler, Request, build_opener


def validate(body, engine):
    return (body.get("status") == "ok" and body.get("release_version") == "V1-P3"
        and body.get("engine") == engine and body.get("policy_version") == "p3-policy-1"
        and body.get("inventory_writes") is False and body.get("shopping_writes") is False
        and "p3-item-selection-1" in body.get("clarification_protocols", []))


def main():
    try:
        with build_opener(ProxyHandler({})).open(Request("http://127.0.0.1:8767/health"), timeout=3) as response:
            return 0 if validate(json.load(response), os.getenv("P3_ENGINE", "rules")) else 1
    except (OSError, ValueError, TypeError, AttributeError):
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
