"""Run as root on the server after staging and testing the candidate image.

Only updates backend.image; no migrations. Rollback retains the existing DB.
Private backups and verification evidence remain in the server-only directory.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

import yaml

ROOT=Path("/etc/magicvvu/households-20261022")
CONFIG=Path("/srv/magicvvu/magicvvu-starter/deploy/compose.yaml")
BACKEND="magicvvu-starter-backend-1"
IMAGE="magicvvu/backend:households-20261022"


def run(args,timeout=60):
    r=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    if r.returncode:
        raise RuntimeError("Server command failed: "+args[0])
    return r.stdout.strip()


def containers():
    return {c["Name"].lstrip("/"):c for c in json.loads(run([
        "docker","inspect",BACKEND,"magicvvu-starter-agent-1","magicvvu-starter-db-1"]))}


def snapshot():
    # Only row counts and hashes leave the container, never personal or secret data.
    source='''
import hashlib,json
from sqlalchemy import text
from app.database import engine
with engine.connect() as db:
 tx=db.begin()
 db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
 tables=db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")).scalars().all()
 result={}
 for table in tables:
  quoted='"'+table.replace('"','""')+'"'
  rows=db.execute(text('SELECT row_to_json(t)::text FROM '+quoted+' t')).scalars().all()
  result[table]={'count':len(rows),'sha256':hashlib.sha256(('\\n'.join(sorted(rows))).encode()).hexdigest()}
 tx.rollback()
 print(json.dumps(result,sort_keys=True))
'''
    return json.loads(run(["docker","exec",BACKEND,"python","-B","-c",source]))


def wait_healthy():
    for _ in range(45):
        if containers()[BACKEND]["State"].get("Health",{}).get("Status")=="healthy":
            return
        time.sleep(1)
    raise RuntimeError("Backend did not become healthy")


def main():
    assert os.geteuid()==0
    before=containers()
    original=CONFIG.read_text()
    assert original==(ROOT/"compose.before.yaml").read_text(), "Compose changed since backup"
    assert before[BACKEND]["Config"]["Image"]==(ROOT/"base-image.txt").read_text()
    assert (ROOT/"before.dump").is_file()
    for filename in ("postgres-final.log","sqlite-final.log"):
        assert json.loads((ROOT/filename).read_text())["passed"] is True
    previous=snapshot()
    (ROOT/"data-before.json").write_text(json.dumps(previous,sort_keys=True))
    env_hash=hashlib.sha256((CONFIG.parent/".env").read_bytes()).hexdigest()
    old=yaml.safe_load(original)
    expected=copy.deepcopy(old)
    expected["services"]["backend"]["image"]=IMAGE
    old_image=old["services"]["backend"]["image"]
    candidate,count=re.subn(r"(?m)^(\s*image:\s*)"+re.escape(old_image)+r"(\s*(?:#.*)?)$",
                           lambda m:m[1]+IMAGE+m[2],original)
    assert count==1 and yaml.safe_load(candidate)==expected
    staged=CONFIG.with_suffix(".households.tmp")
    staged.write_text(candidate)
    shutil.copystat(CONFIG,staged)
    os.chown(staged,CONFIG.stat().st_uid,CONFIG.stat().st_gid)
    checks={}
    replaced=False
    try:
        run(["docker","compose","-f",str(staged),"config","--quiet"])
        staged.replace(CONFIG)
        replaced=True
        run(["docker","compose","-f",str(CONFIG),"up","-d","--no-deps","--no-build","--pull","never","backend"])
        wait_healthy()
        after=containers()
        checks["candidate_image_applied"]=after[BACKEND]["Config"]["Image"]==IMAGE
        checks["agent_database_unchanged"]=all(after[k]["Id"]==before[k]["Id"] for k in before if k!=BACKEND)
        def environment(container):
            return dict(value.split("=",1) for value in container["Config"]["Env"])
        checks["backend_environment_unchanged"]=environment(after[BACKEND])==environment(before[BACKEND])
        checks["backend_mounts_unchanged"]=after[BACKEND]["Mounts"]==before[BACKEND]["Mounts"]
        checks["secret_file_unchanged"]=hashlib.sha256((CONFIG.parent/".env").read_bytes()).hexdigest()==env_hash
        checks["all_existing_rows_unchanged_before_acceptance"]=snapshot()==previous
        assert all(checks.values())
        acceptance=subprocess.run(["python3",str(ROOT/"live_verify.py")],capture_output=True,text=True,timeout=150)
        live=json.loads(acceptance.stdout)
        (ROOT/"live-verification.json").write_text(json.dumps(live,sort_keys=True))
        checks["tls_acceptance_passed"]=acceptance.returncode==0 and live["passed"]
        checks["all_existing_rows_unchanged_after_cleanup"]=snapshot()==previous
        assert all(checks.values())
        result={"passed":True,"image":IMAGE,"checks":checks,"live":live,
                "backup_directory":str(ROOT),"all_containers_healthy":all(
                    c["State"].get("Health",{}).get("Status")=="healthy" for c in containers().values())}
        (ROOT/"deployment-verification.json").write_text(json.dumps(result,sort_keys=True))
        print(json.dumps(result,sort_keys=True))
    except Exception as exc:
        if replaced:
            shutil.copy2(ROOT/"compose.before.yaml",CONFIG)
            run(["docker","compose","-f",str(CONFIG),"up","-d","--no-deps","--no-build","--pull","never","backend"])
            wait_healthy()
        print(json.dumps({"passed":False,"rolled_back":replaced,"error_type":type(exc).__name__,"checks":checks}))
        raise
    finally:
        staged.unlink(missing_ok=True)


if __name__=="__main__":
    main()
