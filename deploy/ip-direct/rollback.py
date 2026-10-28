"""Explicit network-only rollback. Retains certificates and protected backups."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

p = argparse.ArgumentParser()
p.add_argument("--execute", action="store_true", required=True)
p.parse_args()
assert os.geteuid() == 0
root = Path("/etc/magicvvu/ip-direct")
config = Path("/srv/magicvvu/magicvvu-starter/deploy/compose.yaml")
subprocess.run(["systemctl", "disable", "--now", "magicvvu-direct-renew.timer"], check=True)
shutil.copy2(root / "before/compose.yaml", config)
config.chmod(0o660)
os.chdir(config.parent)
subprocess.run(["docker", "compose", "up", "-d", "--no-deps", "backend"], check=True)
# Remove only our Docker dependency, before stopping the firewall unit.
Path("/etc/systemd/system/docker.service.d/magicvvu-direct.conf").unlink(missing_ok=True)
subprocess.run(["systemctl", "daemon-reload"], check=True)
subprocess.run(["systemctl", "disable", "--now", "magicvvu-direct.service", "magicvvu-direct-firewall.service"], check=True)
subprocess.run(["iptables", "-t", "raw", "-D", "PREROUTING", "-i", "eth0", "-p", "tcp", "--dport", "8000", "-j", "MAGICVVU-TLS"], check=True)
subprocess.run(["iptables", "-t", "raw", "-F", "MAGICVVU-TLS"], check=True)
subprocess.run(["iptables", "-t", "raw", "-X", "MAGICVVU-TLS"], check=True)
print("Restored original loopback HTTP :8000; remove the Alibaba Cloud TCP 8000 rule. CA and backups retained.")
