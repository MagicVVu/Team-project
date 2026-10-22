"""Mount reviewed, public pricing metadata into the SAME existing Agent image."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import yaml

assert os.geteuid() == 0
source = Path(sys.argv[1])
pricing = json.loads(source.read_text())
assert pricing["model"] == "deepseek-flash" and pricing["input_cny_per_million"] == 2 and pricing["output_cny_per_million"] == 8
assert pricing["verified_on"] == "2026-10-22"
config = Path("/srv/magicvvu/magicvvu-starter/deploy/compose.yaml")
backup = Path("/etc/magicvvu/team-testing-20261022-unify")
shutil.copy2(config, backup / "compose-before-pricing.yaml")
with (backup / "pricing-before.json").open("wb") as stream:
    subprocess.run(["docker", "exec", "magicvvu-starter-agent-1", "cat", "/app/agent/eval/pricing.json"], stdout=stream, check=True)
data = yaml.safe_load(config.read_text())
image = json.loads(subprocess.check_output(["docker", "inspect", "magicvvu-starter-agent-1"]))[0]["Image"]
target = Path("/srv/magicvvu/team-agent/pricing.json")
target.parent.mkdir(mode=0o755, exist_ok=True)
shutil.copyfile(source, target)
target.chmod(0o644)
volumes = data["services"]["agent"].setdefault("volumes", [])
assert not any("/app/agent/eval/pricing.json" in str(v) for v in volumes)
volumes.append(str(target) + ":/app/agent/eval/pricing.json:ro")
temp = config.with_suffix(".pricing.tmp")
temp.write_text(yaml.safe_dump(data, sort_keys=False))
shutil.copystat(config, temp)
os.chown(temp, config.stat().st_uid, config.stat().st_gid)
subprocess.run(["docker", "compose", "-f", str(temp), "config", "--quiet"], cwd=config.parent, check=True)
temp.replace(config)
subprocess.run(["docker", "compose", "up", "-d", "--no-deps", "agent"], cwd=config.parent, check=True)
after = json.loads(subprocess.check_output(["docker", "inspect", "magicvvu-starter-agent-1"]))[0]
assert after["Image"] == image
print(json.dumps({"agent_image_unchanged": True, "pricing_verified_on": pricing["verified_on"], "pricing_mount": str(target)}))
