import json
import sys
import urllib.request
from .schemas import PROTOCOL


def check(body):
    return (body.get("status") == "ok" and body.get("conversation_dialogue_protocol") == PROTOCOL
        and body.get("dialogue_max_model_calls") is None and body.get("autonomous_fixed_call_limit") is False
        and body.get("inventory_writes") is False and body.get("shopping_writes") is False)


def main():
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open("http://127.0.0.1:8767/health", timeout=3) as response:
            return 0 if check(json.load(response)) else 1
    except (OSError, ValueError): return 1


if __name__ == "__main__": sys.exit(main())
