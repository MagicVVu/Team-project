"""Optional P8.5 localhost probe; never reuse the P8.4 maintenance check."""
import json
import sys
import urllib.request


def check(body):
    return (body.get("status") == "ok" and body.get("maintenance_release") == "V1-P8.5"
            and body.get("conversation_dialogue_protocol") == "p85-dialogue-1"
            and body.get("inventory_writes") is False and body.get("shopping_writes") is False
            and body.get("memory_persistence_owner") == "business_backend")


def main():
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open("http://127.0.0.1:8767/health", timeout=3) as response:
            body = json.load(response)
        return 0 if check(body) else 1
    except (OSError, ValueError): return 1


if __name__ == "__main__": sys.exit(main())
