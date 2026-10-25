import json
import os
from urllib.request import ProxyHandler, Request, build_opener


def validate(body, engine):
    return (body.get("status") == "ok" and body.get("release_version") == "V1-P7"
        and body.get("engine") == engine and body.get("input_policy_version") == "p7-limited-context-1"
        and body.get("inventory_writes") is False and body.get("shopping_writes") is False
        and body.get("rule_review_policy") == "human_review_only"
        and body.get("reference_ttl_seconds") == 900
        and body.get("maintenance_release") == "V1-P8.2"
        and body.get("conversation_memory_protocol") == "conversation-memory-1"
        and "p7-reference-continuation-1" in body.get("clarification_protocols", []))


def main():
    try:
        with build_opener(ProxyHandler({})).open(Request("http://127.0.0.1:8767/health"), timeout=3) as response:
            return 0 if validate(json.load(response), os.getenv("P3_ENGINE", "rules")) else 1
    except (OSError, ValueError, TypeError, AttributeError): return 1


if __name__ == "__main__": raise SystemExit(main())
