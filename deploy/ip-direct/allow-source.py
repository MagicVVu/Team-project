"""Root-only /32 allowlist maintenance. Also add/remove the same cloud rule manually."""
import argparse
import ipaddress
import os
from pathlib import Path
import subprocess

p = argparse.ArgumentParser()
group = p.add_mutually_exclusive_group(required=True)
group.add_argument("--add")
group.add_argument("--remove")
args = p.parse_args()
assert os.geteuid() == 0
address = str(ipaddress.IPv4Address(args.add or args.remove)) + "/32"
path = Path("/etc/magicvvu/ip-direct/allowed-sources.txt")
before = path.read_text()
sources = {str(ipaddress.IPv4Network(s.strip(), strict=True)) for s in before.splitlines() if s.strip() and not s.startswith("#")}
if args.add:
    sources.add(address)
else:
    sources.discard(address)
if not sources:
    raise SystemExit("Refusing to remove the last allowed source")
staged = path.with_suffix(".new")
staged.write_text("\n".join(sorted(sources)) + "\n")
staged.chmod(0o600)
staged.replace(path)
try:
    subprocess.run(["systemctl", "reload", "magicvvu-direct-firewall.service"], check=True)
except Exception:
    path.write_text(before)
    subprocess.run(["systemctl", "reload", "magicvvu-direct-firewall.service"], check=True)
    raise
print("Host allowlist updated; apply the matching /32 rule in Alibaba Cloud too.")
