"""Server-only read-only, redacted final audit. Never prints environment values."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def run(*args):
    p = subprocess.run(args, capture_output=True, text=True)
    return {"rc": p.returncode, "stdout": p.stdout.strip(), "stderr": p.stderr.strip()}


root = Path("/etc/magicvvu/ip-direct")
old = {c["name"]: c for c in json.loads((root / "before/containers.json").read_text())}
containers = json.loads(subprocess.check_output(["docker", "inspect", *[name.lstrip("/") for name in old]]))
proxy_paths = ["/etc/nginx", "/etc/caddy", "/etc/letsencrypt", "/var/log/nginx", "/var/log/magicvvu-nginx",
               "/var/cache/nginx", "/var/lib/caddy", "/var/snap/certbot", "/root/.acme.sh", "/var/www/letsencrypt", "/etc/apache2"]
result = {
    "utc": datetime.now(timezone.utc).isoformat(),
    "containers": [{"name": c["Name"], "same_image": c["Image"] == old[c["Name"]]["image"],
                    "same_container": c["Id"] == old[c["Name"]]["id"], "image_id": c["Image"],
                    "started_at": c["State"]["StartedAt"], "restart_count": c["RestartCount"],
                    "health": c["State"].get("Health", {}).get("Status"),
                    "ports": c["NetworkSettings"]["Ports"], "restart": c["HostConfig"]["RestartPolicy"]} for c in containers],
    "runtime_env_unchanged": hashlib.sha256(Path("/srv/magicvvu/magicvvu-starter/deploy/.env").read_bytes()).hexdigest() == (root / "before/env.sha256").read_text(),
    "services": {name: run("systemctl", "show", name, "-p", "ActiveState", "-p", "UnitFileState", "-p", "Result")
                 for name in ["docker", "magicvvu-direct", "magicvvu-direct-firewall", "magicvvu-direct-renew.timer"]},
    "proxy_paths": {path: {"exists": Path(path).exists()} for path in proxy_paths},
    "proxy_packages": {name: "Status: install ok installed" in run("dpkg-query", "-s", name)["stdout"]
                       for name in ("nginx", "nginx-common", "caddy", "certbot", "haproxy", "apache2")},
    "retained_apache_config": run("du", "-sb", "/etc/apache2"),
    "snap": run("snap", "list"),
    "listeners": run("ss", "-lnt"),
    "source_guard": run("iptables", "-t", "raw", "-S", "MAGICVVU-TLS"),
    "certificate": run("openssl", "x509", "-in", str(root / "tls/server.crt"), "-noout", "-dates", "-ext", "subjectAltName"),
    "ca_fingerprint": run("openssl", "x509", "-in", str(root / "ca/ca.crt"), "-noout", "-fingerprint", "-sha256"),
    "disk": dict(zip(("total", "used", "free"), shutil.disk_usage("/"))),
    "new_deployment_bytes": run("du", "-sb", "/etc/magicvvu/ip-direct", "/srv/magicvvu/ip-direct"),
    "private_health": run("curl", "-fsS", "http://127.0.0.1:8001/api/v1/health"),
    "private_ready": run("curl", "-fsS", "http://127.0.0.1:8001/api/v1/ready"),
    "agent_health": run("docker", "exec", "magicvvu-starter-agent-1", "python", "-m", "conversation.health"),
}
print(json.dumps(result, indent=2))
