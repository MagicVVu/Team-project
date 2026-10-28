"""Read-only network acceptance; no login credentials, mutations, or TLS bypass."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import ssl
import urllib.error
import urllib.request
import uuid

p = argparse.ArgumentParser()
p.add_argument("--url", default="https://8.134.172.165:8000")
p.add_argument("--ca", type=Path, required=True)
p.add_argument("--output", type=Path)
args = p.parse_args()
context = ssl.create_default_context(cafile=str(args.ca))
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))
results = {"utc": datetime.now(timezone.utc).isoformat(), "origin": args.url, "checks": []}
cases = [("GET", "/health", 200), ("GET", "/api/v1/health", 200),
         ("GET", "/api/v1/users/me", 401), ("POST", "/api/v1/agent/messages", 401),
         ("GET", "/internal/v1/inventory/search", 404), ("GET", "/api/v1/ready", 404),
         ("GET", "/docs", 404), ("GET", "/openapi.json", 404)]
for method, path, expected in cases:
    data = json.dumps({"text": "只读库存查询", "household_id": str(uuid.uuid4()),
                       "request_id": str(uuid.uuid4()), "household_timezone": "Asia/Shanghai"}).encode() if method == "POST" else None
    req = urllib.request.Request(args.url + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with opener.open(req, timeout=10) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, body = error.code, error.read()
    item = {"method": method, "path": path, "status": status, "expected": expected, "passed": status == expected}
    if path.endswith("health") and status == 200:
        value = json.loads(body)
        item["health"] = value
        item["passed"] &= value.get("service") == "magicvvu-backend" and value.get("version") == "0.9.0" and value.get("isolated_test") is False
    results["checks"].append(item)
# System trust alone must reject this project-private CA, proving it was not bypassed.
default = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
try:
    default.open(args.url + "/health", timeout=10)
    rejected = False
except urllib.error.URLError as error:
    rejected = isinstance(error.reason, ssl.SSLCertVerificationError)
results["private_ca_not_globally_trusted"] = rejected
results["passed"] = rejected and all(x["passed"] for x in results["checks"])
text = json.dumps(results, ensure_ascii=False, indent=2)
if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text + "\n", encoding="utf-8")
print(text)
raise SystemExit(0 if results["passed"] else 1)
