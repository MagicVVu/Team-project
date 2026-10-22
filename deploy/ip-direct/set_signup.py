"""Change only the existing team's unverified-registration switch, never images/data."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import yaml

p = argparse.ArgumentParser()
p.add_argument("--allow", choices=("true", "false"), required=True)
args = p.parse_args()
assert os.geteuid() == 0
config = Path("/srv/magicvvu/magicvvu-starter/deploy/compose.yaml")
state = json.loads(subprocess.check_output(["docker", "inspect", "magicvvu-starter-backend-1"]))[0]
before_image = state["Image"]
runtime = dict(x.split("=", 1) for x in state["Config"]["Env"])
data = yaml.safe_load(config.read_text())
environment = data["services"]["backend"]["environment"]
assert isinstance(environment, dict)
backup = Path("/etc/magicvvu") / ("signup-backup-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
backup.mkdir(mode=0o700)
shutil.copy2(config, backup / "compose.yaml")
(backup / "compose.yaml").chmod(0o600)
changed = str(environment.get("AUTH_ALLOW_UNVERIFIED_SIGNUP", "")).lower() != args.allow
if changed:
    environment["AUTH_ALLOW_UNVERIFIED_SIGNUP"] = args.allow
    temp = config.with_suffix(".signup.tmp")
    temp.write_text(yaml.safe_dump(data, sort_keys=False))
    shutil.copystat(config, temp)
    os.chown(temp, config.stat().st_uid, config.stat().st_gid)
    subprocess.run(["docker", "compose", "-f", str(temp), "config", "--quiet"], cwd=config.parent, check=True)
    temp.replace(config)
if changed or runtime.get("AUTH_ALLOW_UNVERIFIED_SIGNUP", "").lower() != args.allow:
    subprocess.run(["docker", "compose", "up", "-d", "--no-deps", "backend"], cwd=config.parent, check=True)
after = json.loads(subprocess.check_output(["docker", "inspect", "magicvvu-starter-backend-1"]))[0]
assert after["Image"] == before_image
effective = dict(x.split("=", 1) for x in after["Config"]["Env"])["AUTH_ALLOW_UNVERIFIED_SIGNUP"]
assert effective.lower() == args.allow
print(json.dumps({"allow_unverified_signup": effective, "compose_changed": changed,
                  "backend_image_unchanged": True, "backup": str(backup)}))
