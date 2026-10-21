"""Run as root on the inspected server, after reviewing source addresses.

No package installs, image changes, database changes, or secret output.
"""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import yaml


def run(*args):
    return subprocess.check_output(args, stderr=subprocess.STDOUT, text=True).strip()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--public-ip", required=True)
    p.add_argument("--allow-source", action="append", required=True)
    args = p.parse_args()
    ip = str(ipaddress.IPv4Address(args.public_ip))
    sources = [str(ipaddress.IPv4Network(x, strict=True)) for x in args.allow_source]
    if any(ipaddress.IPv4Network(x).prefixlen != 32 for x in sources):
        raise SystemExit("Only reviewed individual /32 sources accepted by initial installer")
    assert os.geteuid() == 0
    source = Path(__file__).resolve().parent
    config = Path("/srv/magicvvu/magicvvu-starter/deploy/compose.yaml")
    root = Path("/etc/magicvvu/ip-direct")
    if root.exists():
        raise SystemExit("Already prepared; inspect existing state rather than overwrite keys/backups")
    d = yaml.safe_load(config.read_text())
    assert d["services"]["backend"]["ports"] == ["127.0.0.1:8000:8000"]
    root.mkdir(parents=True, mode=0o700)
    backup = root / "before"
    backup.mkdir(mode=0o700)
    shutil.copy2(config, backup / "compose.yaml")
    shutil.copy2(config.parent / ".env", backup / "runtime.env")
    for f in backup.iterdir():
        f.chmod(0o600)
    inventory = json.loads(run("docker", "inspect", "magicvvu-starter-backend-1", "magicvvu-starter-agent-1", "magicvvu-starter-db-1"))
    (backup / "containers.json").write_text(json.dumps([
        {"name": c["Name"], "id": c["Id"], "image": c["Image"],
         "restart": c["HostConfig"]["RestartPolicy"]} for c in inventory], indent=2))
    (backup / "env.sha256").write_text(hashlib.sha256((config.parent / ".env").read_bytes()).hexdigest())
    (root / "public-ip").write_text(ip + "\n")
    (root / "allowed-sources.txt").write_text("\n".join(sources) + "\n")
    ca = root / "ca"
    ca.mkdir(mode=0o700)
    run("openssl", "req", "-x509", "-newkey", "rsa:3072", "-nodes", "-sha256", "-days", "730",
        "-subj", "/CN=MagicVVu Internal Test CA", "-addext", "basicConstraints=critical,CA:TRUE,pathlen:0",
        "-addext", "keyUsage=critical,keyCertSign,cRLSign",
        "-keyout", str(ca / "ca.key"), "-out", str(ca / "ca.crt"))
    (ca / "ca.key").chmod(0o600)
    tls = root / "tls"
    tls.mkdir(mode=0o500)
    os.chown(tls, 10001, 10001)
    # Certificate issuance is separately reusable by the renewal timer.
    shutil.copy2(source / "renew.py", root / "renew.py")
    for name in ("allow-source.py", "rollback.py"):
        shutil.copy2(source / name, root / name)
    run("python3", str(root / "renew.py"), "--initial")
    runtime = Path("/srv/magicvvu/ip-direct")
    runtime.mkdir(mode=0o755, exist_ok=True)
    shutil.copy2(source / "serve.py", runtime / "serve.py")
    (runtime / "serve.py").chmod(0o644)
    shutil.copy2(source / "firewall.sh", "/usr/local/sbin/magicvvu-direct-firewall")
    Path("/usr/local/sbin/magicvvu-direct-firewall").chmod(0o750)
    for name in ("magicvvu-direct-firewall.service", "magicvvu-direct.service", "magicvvu-direct-renew.service", "magicvvu-direct-renew.timer"):
        shutil.copy2(source / name, Path("/etc/systemd/system") / name)
    dropin = Path("/etc/systemd/system/docker.service.d")
    dropin.mkdir(exist_ok=True)
    (dropin / "magicvvu-direct.conf").write_text("[Unit]\nRequires=magicvvu-direct-firewall.service\nAfter=magicvvu-direct-firewall.service\n")
    run("systemctl", "daemon-reload")
    run("systemctl", "enable", "--now", "magicvvu-direct-firewall.service")
    backend = d["services"]["backend"]
    backend["ports"] = ["0.0.0.0:8000:8443", "127.0.0.1:8001:8000"]
    backend["command"] = ["python", "/app/magicvvu_direct.py"]
    backend.setdefault("volumes", []).extend([
        "/srv/magicvvu/ip-direct/serve.py:/app/magicvvu_direct.py:ro",
        "/etc/magicvvu/ip-direct/tls:/run/magicvvu-tls:ro"])
    backend["restart"] = "unless-stopped"
    candidate = config.with_suffix(".ip-direct.tmp")
    candidate.write_text(yaml.safe_dump(d, sort_keys=False))
    shutil.copystat(config, candidate)
    os.chown(candidate, config.stat().st_uid, config.stat().st_gid)
    run("docker", "compose", "-f", str(candidate), "config", "--quiet")
    candidate.replace(config)
    os.chdir(config.parent)
    try:
        run("docker", "compose", "up", "-d", "--no-deps", "backend")
        run("systemctl", "enable", "--now", "magicvvu-direct.service", "magicvvu-direct-renew.timer")
        for _ in range(30):
            try:
                result = run("curl", "--fail", "--silent", "--max-time", "3", "http://127.0.0.1:8001/api/v1/health")
                assert json.loads(result)["service"] == "magicvvu-backend"
                break
            except Exception:
                time.sleep(1)
        else:
            raise RuntimeError("Backend health did not recover")
    except Exception:
        shutil.copy2(backup / "compose.yaml", config)
        run("docker", "compose", "up", "-d", "--no-deps", "backend")
        raise
    print(json.dumps({"installed": True, "public_tls": f"https://{ip}:8000", "private_http": "http://127.0.0.1:8001",
                      "sources": sources, "backup": str(backup)}))


if __name__ == "__main__":
    main()
