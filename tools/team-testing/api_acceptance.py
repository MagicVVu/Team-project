"""Live team-only acceptance. Random dedicated accounts; no secrets in output."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import ssl
import urllib.error
import urllib.request
import uuid

p = argparse.ArgumentParser()
p.add_argument("--ca", required=True)
p.add_argument("--output", required=True, type=Path)
args = p.parse_args()
origin = "https://8.134.172.165:8000"
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=args.ca)))
checks = []
fixture = {"run": "team-api-" + uuid.uuid4().hex[:12], "user_ids": [], "household_ids": []}

def check(name, value):
    checks.append({"name": name, "passed": bool(value)})
    if not value:
        raise AssertionError(name)

def call(method, path, body=None, token=None, expected=200):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(origin + path, data=json.dumps(body).encode() if body is not None else None, headers=headers, method=method)
    try:
        with opener.open(request, timeout=60) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as failure:
        status, raw = failure.code, failure.read()
    check(method + " " + path.replace(str(fixture.get("home", "unused")), "{test-home}") + " status " + str(expected), status == expected)
    return json.loads(raw) if raw else {}

def version(item):
    return {"expected_version": item["version"], "operation_id": str(uuid.uuid4())}

tokens = []
logged_out = set()
error = None
try:
    password = secrets.token_urlsafe(24)
    phone_a = "+999" + str(secrets.randbelow(10**11)).zfill(11)
    phone_b = "+999" + str(secrets.randbelow(10**11)).zfill(11)
    for index, phone in enumerate((phone_a, phone_b)):
        user = call("POST", "/api/v1/auth/register", {"phone": phone, "password": password, "display_name": fixture["run"] + str(index)}, expected=201)
        fixture["user_ids"].append(user["id"])
        check("registered_unverified_" + str(index), user["phone_verified"] is False and "password_hash" not in user)
    call("POST", "/api/v1/auth/register", {"phone": phone_a, "password": password, "display_name": "duplicate-test"}, expected=409)
    call("POST", "/api/v1/auth/login", {"phone": phone_a, "password": "wrong-" + password}, expected=401)
    for phone in (phone_a, phone_b):
        tokens.append(call("POST", "/api/v1/auth/login", {"phone": phone, "password": password})["access_token"])
    a, b = tokens
    check("new_account_no_implicit_family", call("GET", "/api/v1/households", token=b) == [])
    home = call("POST", "/api/v1/households", {"name": fixture["run"]}, a, 201)["id"]
    fixture["home"] = home
    fixture["household_ids"].append(home)
    root = "/api/v1/households/" + home
    item = call("POST", root + "/inventory-items", {"id": str(uuid.uuid4()), "name": "牛奶", "quantity": "5", "unit": "盒", "storage_location": "测试冰箱"}, a, 201)
    call("GET", root + "/inventory-items", token=b, expected=404)
    call("PATCH", root + "/inventory-items/" + item["id"], {**version(item), "quantity": "99"}, b, 404)
    call("PATCH", "/api/v1/users/me", {"phone": phone_a}, b, 422)
    item = call("PATCH", root + "/inventory-items/" + item["id"], {**version(item), "quantity": "4"}, a)
    invite = call("POST", root + "/invitations", {}, a, 201)["invite_code"]
    call("POST", "/api/v1/households/join", {"invite_code": invite}, b)
    item = call("POST", root + "/inventory-items/" + item["id"] + "/adjustments", {**version(item), "delta": "-1"}, b)
    check("authorized_shared_inventory_write", item["quantity"] == "3.000000")
    plan = call("POST", root + "/shopping-list/items", {"id": str(uuid.uuid4()), "name": "牛奶", "quantity": "2", "unit": "盒", "source_inventory_item_id": item["id"]}, a, 201)
    bought = call("POST", root + "/shopping-list/items/" + plan["id"] + "/purchase", {"actual_quantity": "1", "storage_location": "测试冰箱"}, b)
    check("purchase_stocked", bought["newly_stocked"] is True)
    caps = call("GET", "/api/v1/agent/execution-capabilities", token=a)
    check("agent_contract", caps["protocol_version"] == "draft-execution-1")
    task = call("POST", "/api/v1/agent/messages", {"text": "牛奶还有多少？", "household_id": home, "household_timezone": "Asia/Shanghai", "request_id": str(uuid.uuid4())}, a)
    fixture["agent_task_id"] = task["task_id"]
    fixture["agent_status"] = task["status"]
    fixture["agent_error_code"] = (task.get("result") or {}).get("error_code")
    check("remote_agent_answered", task["status"] == "answered" and bool(task.get("result", {}).get("reply")))
    call("DELETE", root + "/inventory-items/" + item["id"], version(item), a, 204)
    check("unverified_phone_still_unverified", call("GET", "/api/v1/users/me", token=a)["phone_verified"] is False)
    for token in tokens:
        call("POST", "/api/v1/auth/logout", {}, token)
        logged_out.add(token)
        call("GET", "/api/v1/users/me", token=token, expected=401)
    call("POST", root + "/inventory-items", {"id": str(uuid.uuid4()), "name": "anonymous-rejected", "quantity": "1", "unit": "盒", "storage_location": "测试"}, expected=401)
except Exception as failure:
    error = type(failure).__name__ + (": " + str(failure) if isinstance(failure, AssertionError) else "")
finally:
    for token in tokens:
        if token not in logged_out:
            try:
                call("POST", "/api/v1/auth/logout", {}, token)
            except Exception:
                error = error or "Test session cleanup requires administrator review"
    result = {"utc": datetime.now(timezone.utc).isoformat(), "passed": error is None, "error": error, "checks": checks, "dedicated_fixture": fixture}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": error is None, "checks": len(checks), "error": error}, ensure_ascii=False))
raise SystemExit(0 if error is None else 1)
