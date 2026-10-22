"""Enable/disable existing phone-password signup on the source-restricted TLS stack.

Run as root on the server. Default is read-only. Keeps secrets/backups on server,
changes only backend AUTH_ALLOW_UNVERIFIED_SIGNUP, and recreates only backend.
"""
import argparse
import copy
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
import urllib.request

import yaml

CONFIG = Path("/srv/magicvvu/magicvvu-starter/deploy/compose.yaml")
ROOT = Path("/etc/magicvvu/ip-direct")
BACKEND = "magicvvu-starter-backend-1"


def run(*args, timeout=60):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError("Server command failed; private stdout/stderr withheld: " + args[0])
    return result.stdout.strip()


def containers():
    rows = json.loads(run("docker", "inspect", BACKEND, "magicvvu-starter-agent-1", "magicvvu-starter-db-1"))
    return {c["Name"].lstrip("/"): c for c in rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--enable", action="store_true")
    group.add_argument("--disable", action="store_true")
    args = parser.parse_args()
    assert os.geteuid() == 0
    before = containers()
    backend = before[BACKEND]
    env = dict(x.split("=", 1) for x in backend["Config"]["Env"] if "=" in x)
    enabled = env.get("AUTH_ALLOW_UNVERIFIED_SIGNUP", "false").lower() in ("true", "1", "yes")
    checks = {"backend_healthy": backend["State"].get("Health", {}).get("Status") == "healthy"}
    sources = [s.strip() for s in (ROOT / "allowed-sources.txt").read_text().splitlines() if s.strip() and not s.startswith("#")]
    checks["individual_sources_only"] = bool(sources) and all(ipaddress.IPv4Network(s, strict=True).prefixlen == 32 for s in sources)
    run("iptables", "-t", "raw", "-C", "PREROUTING", "-i", "eth0", "-p", "tcp", "--dport", "8000", "-j", "MAGICVVU-TLS")
    rules = run("iptables", "-t", "raw", "-S", "MAGICVVU-TLS").splitlines()
    expected_rules = ["-A MAGICVVU-TLS -s " + s + " -j RETURN" for s in sources] + ["-A MAGICVVU-TLS -j DROP"]
    checks["live_firewall_matches_allowlist"] = [s for s in rules if s.startswith("-A ")] == expected_rules
    checks["tls_listener_present"] = "0.0.0.0:8000:8443" in yaml.safe_load(CONFIG.read_text())["services"]["backend"]["ports"]
    checks["expected_tls_command"] = backend["Config"]["Cmd"] == ["python", "/app/magicvvu_direct.py"]
    if not all(checks.values()):
        print(json.dumps({"checks": checks, "changed": False, "passed": False}))
        raise SystemExit(1)
    if not (args.enable or args.disable):
        print(json.dumps({"checks": checks, "signup_enabled": enabled, "changed": False, "passed": True}))
        return
    desired = args.enable
    if enabled == desired:
        print(json.dumps({"checks": checks, "signup_enabled": enabled, "changed": False, "passed": True}))
        return
    original = CONFIG.read_text()
    old = yaml.safe_load(original)
    expected = copy.deepcopy(old)
    expected["services"]["backend"]["environment"]["AUTH_ALLOW_UNVERIFIED_SIGNUP"] = "true" if desired else "false"
    # Preserve every other byte, including comments and private configuration.
    pattern = r"(?m)^(\s*AUTH_ALLOW_UNVERIFIED_SIGNUP\s*:\s*)[^\r\n#]*(.*)$"
    candidate, count = re.subn(pattern, lambda m: m[1] + ("'true'" if desired else "'false'") + (" " + m[2] if m[2] else ""), original)
    assert count == 1 and yaml.safe_load(candidate) == expected, "Unexpected Compose shape; refusing mutation"
    backup = ROOT / ("auth-before-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    backup.mkdir(mode=0o700)
    shutil.copy2(CONFIG, backup / "compose.yaml")
    (backup / "compose.yaml").chmod(0o600)
    secret_hash = hashlib.sha256((CONFIG.parent / ".env").read_bytes()).hexdigest()
    staged = CONFIG.with_suffix(".signup.tmp")
    staged.write_text(candidate)
    shutil.copystat(CONFIG, staged)
    os.chown(staged, CONFIG.stat().st_uid, CONFIG.stat().st_gid)
    try:
        run("docker", "compose", "-f", str(staged), "config", "--quiet")
        staged.replace(CONFIG)
        run("docker", "compose", "-f", str(CONFIG), "up", "-d", "--no-deps", "--pull", "never", "backend")
        for _ in range(30):
            after = containers()
            if after[BACKEND]["State"].get("Health", {}).get("Status") == "healthy":
                break
            time.sleep(1)
        else:
            raise RuntimeError("Backend did not become healthy")
        with urllib.request.urlopen("http://127.0.0.1:8001/api/v1/ready", timeout=5) as response:
            assert response.status == 200
        new_env = dict(x.split("=", 1) for x in after[BACKEND]["Config"]["Env"] if "=" in x)
        checks["signup_flag_applied"] = new_env["AUTH_ALLOW_UNVERIFIED_SIGNUP"] == ("true" if desired else "false")
        checks["same_backend_image"] = after[BACKEND]["Image"] == backend["Image"]
        checks["agent_and_database_unchanged"] = all(after[n]["Id"] == before[n]["Id"] for n in before if n != BACKEND)
        checks["secret_file_unchanged"] = hashlib.sha256((CONFIG.parent / ".env").read_bytes()).hexdigest() == secret_hash
        assert all(checks.values()), "Post-deployment check failed"
    except Exception:
        shutil.copy2(backup / "compose.yaml", CONFIG)
        run("docker", "compose", "-f", str(CONFIG), "up", "-d", "--no-deps", "--pull", "never", "backend")
        raise
    finally:
        staged.unlink(missing_ok=True)
    print(json.dumps({"checks": checks, "signup_enabled": desired, "changed": True, "backup": str(backup), "passed": True}))


if __name__ == "__main__":
    main()
