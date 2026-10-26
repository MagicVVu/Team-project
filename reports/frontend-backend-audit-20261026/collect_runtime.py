"""Read-only audit collector; run inside the deployed backend container."""
import datetime
import hashlib
import json
import pathlib
import subprocess
import urllib.error
import urllib.request

from app.main import app
from app.routers.agent_gateway import check_config
from app.routers.draft_execution import capabilities


def probe(url):
    try:
        with urllib.request.urlopen(url, timeout=12) as response:
            return {"status": response.status, "body": json.load(response)}
    except urllib.error.HTTPError as error:
        return {"status": error.code, "body": json.loads(error.read())}


files = [
    "app/routers/products.py", "app/routers/shopping.py",
    "app/routers/inventory.py", "app/routers/draft_execution.py",
    "app/routers/assistant_reads.py", "app/routers/session_memory.py",
    "app/services/draft_execution.py",
]
preflight = subprocess.run(
    ["python", "-m", "app.p9_preflight"], capture_output=True, text=True, check=True
)
print(json.dumps({
    "checked_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "business_mutations_performed": False,
    "model_calls_performed": 0,
    "backend_health_http": probe("http://127.0.0.1:8000/api/v1/health"),
    "capabilities_without_auth_http": probe("http://127.0.0.1:8000/api/v1/agent/execution-capabilities"),
    "capabilities_from_deployed_function": capabilities(None),
    "capabilities_method": "Direct invocation of the deployed read-only function; not an authenticated HTTP acceptance test",
    "agent_health_http": probe(check_config()[0].rstrip("/") + "/health"),
    "p9_read_only_preflight": json.loads(preflight.stdout),
    "production_source_sha256": {
        name: hashlib.sha256(pathlib.Path(name).read_bytes()).hexdigest() for name in files
    },
    "openapi_path_count": len(app.openapi()["paths"]),
}, ensure_ascii=False, indent=2))
