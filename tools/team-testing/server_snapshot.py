"""Root-only backup and original-row integrity audit; never exports DB content."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

p = argparse.ArgumentParser()
p.add_argument("--root", required=True, type=Path)
p.add_argument("--verify", action="store_true")
args = p.parse_args()
assert os.geteuid() == 0
root = args.root.resolve()
assert str(root).startswith("/etc/magicvvu/team-testing-")
inspect = json.loads(subprocess.check_output(["docker", "inspect", "magicvvu-starter-db-1", "magicvvu-starter-backend-1", "magicvvu-starter-agent-1"]))
env = dict(x.split("=", 1) for x in inspect[0]["Config"]["Env"])
base = ["docker", "exec", "magicvvu-starter-db-1"]
db = ["--username", env["POSTGRES_USER"], "--dbname", env["POSTGRES_DB"]]
tables = ("users", "households", "household_members", "inventory_items", "shopping_lists", "shopping_list_items")
rows = {}
for table in tables:
    value = subprocess.check_output(base + ["psql", *db, "-At", "-c", f"SELECT md5(row_to_json(t)::text) FROM {table} t ORDER BY 1"], text=True)
    rows[table] = value.splitlines()
state = {"utc": datetime.now(timezone.utc).isoformat(), "row_hashes": rows,
         "whitelist_sha256": hashlib.sha256(Path("/etc/magicvvu/ip-direct/allowed-sources.txt").read_bytes()).hexdigest(),
         "raw_firewall": subprocess.check_output(["iptables", "-t", "raw", "-S"], text=True),
         "images": {x["Name"]: x["Image"] for x in inspect}}
if args.verify:
    before = json.loads((root / "baseline.json").read_text())
    guard = lambda text: [line for line in text.splitlines() if "MAGICVVU-TLS" in line]
    result = {"original_rows_unchanged": {t: set(before["row_hashes"][t]).issubset(rows[t]) for t in tables},
              "whitelist_unchanged": before["whitelist_sha256"] == state["whitelist_sha256"],
              "source_guard_rules_unchanged": guard(before["raw_firewall"]) == guard(state["raw_firewall"]),
              "images_unchanged": before["images"] == state["images"]}
    (root / "verification.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
    assert all(result["original_rows_unchanged"].values()) and all(v for k, v in result.items() if k != "original_rows_unchanged")
else:
    root.mkdir(mode=0o700)
    for name in ("compose.yaml", ".env"):
        shutil.copy2(Path("/srv/magicvvu/magicvvu-starter/deploy") / name, root / name)
        (root / name).chmod(0o600)
    with (root / "database.dump").open("wb") as stream:
        subprocess.run(base + ["pg_dump", *db, "-Fc", "--no-owner", "--no-acl"], stdout=stream, check=True)
    (root / "database.dump").chmod(0o600)
    # Verify the archive is readable; do not restore into the running database.
    with (root / "database.dump").open("rb") as stream:
        subprocess.run(["docker", "exec", "-i", "magicvvu-starter-db-1", "pg_restore", "--list"], stdin=stream, stdout=subprocess.DEVNULL, check=True)
    (root / "baseline.json").write_text(json.dumps(state, indent=2))
    print(json.dumps({"backup": str(root), "backup_bytes": (root / "database.dump").stat().st_size, "archive_readable": True,
                      "original_counts": {t: len(v) for t, v in rows.items()}}))
