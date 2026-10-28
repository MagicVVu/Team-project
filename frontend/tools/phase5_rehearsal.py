"""Run as admin via SSH. Only new databases in the existing stage-3 test PostgreSQL.

No production names, keys, ports or volumes are changed. Credentials remain in memory.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from uuid import uuid4

ROOT = Path("/home/admin/magicvvu-p7-rc-20261017")
ROOT.mkdir(exist_ok=True)
PROJECT = "magicvvu-p7-execution-20261017"
BACKEND = PROJECT + "-backend-1"
DB = PROJECT + "-db-1"
NET = PROJECT + "_test_net"

def docker(args, **kwargs):
    assert os.geteuid() == 0, "Invoke via the existing authorized sudo python permission"
    return subprocess.run(["docker", *args], capture_output=True, **kwargs)

data = json.loads(docker(["inspect", BACKEND]).stdout)[0]
config = dict(x.split("=", 1) for x in data["Config"]["Env"])
assert config["DB_NAME"] == "magicvvu_p7_execution_test" and config["ISOLATED_APP_TEST"] == "yes"
assert NET in data["NetworkSettings"]["Networks"]
dbconfig = dict(x.split("=", 1) for x in json.loads(docker(["inspect", DB]).stdout)[0]["Config"]["Env"])
run_id = uuid4().hex[:8]
name = "magicvvu_p7_rc_" + run_id
restored = name + "_restore"
dbuser = dbconfig["POSTGRES_USER"]
for dbname in (name, restored):
    assert re.fullmatch(r"magicvvu_p7_rc_[a-f0-9]{8}(_restore)?", dbname)
    p = docker(["exec", DB, "psql", "-U", dbuser, "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-c", 'CREATE DATABASE "' + dbname + '"'])
    assert p.returncode == 0, "Test database creation failed"

env = dict(os.environ)
env.update({k: config[k] for k in ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD") if k in config})
env.update(DB_NAME=name, ISOLATED_APP_TEST="yes", AUTH_ALLOW_UNVERIFIED_SIGNUP="false")
env_names = ["DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME", "ISOLATED_APP_TEST", "AUTH_ALLOW_UNVERIFIED_SIGNUP"]
OLD, NEW = "magicvvu/backend:app-v0.8", "magicvvu/backend:draft-v0.9-test"
logs = []

def run(image, command, stdin=None, ok=True):
    args = ["run", "--rm", "-i", "--network", NET, "--read-only", "--tmpfs", "/tmp:rw,nosuid,size=64m"]
    for key in env_names:
        if key in env: args += ["-e", key]
    p = docker([*args, image, *command], input=stdin.encode() if isinstance(stdin, str) else stdin, env=env)
    logs.append(p.stdout.decode(errors="replace") + p.stderr.decode(errors="replace"))
    (ROOT / "rehearsal-attempt.log").write_text("\n".join(logs))
    if ok: assert p.returncode == 0, "Rehearsal step failed; see private-free log"
    return p

run(OLD, ["alembic", "upgrade", "20261016_0006"])
actor, home, task, draft = [str(uuid4()) for _ in range(4)]
seed = f'''
from uuid import UUID,uuid4
from app.database import SessionLocal
from app.models import User,Household,HouseholdMember,ShoppingList,InventoryItem,AITask,AIDraft
from app.security import hash_password
import secrets
with SessionLocal.begin() as db:
 u=UUID('{actor}');h=UUID('{home}');t=UUID('{task}')
 db.add(User(id=u,phone='+1996'+str(secrets.randbelow(10**9)).zfill(9),password_hash=hash_password(secrets.token_urlsafe(24)),display_name='RC synthetic'))
 db.flush();db.add(Household(id=h,name='RC synthetic',created_by_user_id=u));db.flush()
 db.add(HouseholdMember(household_id=h,user_id=u,role='owner'))
 db.add(ShoppingList(household_id=h,name='RC shared',created_by_user_id=u))
 db.add(InventoryItem(id=uuid4(),household_id=h,name='RC legacy',quantity=5,unit='盒',storage_location='测试库',created_by_user_id=u,status='ACTIVE',version=1))
 command={{'action':'ADD','name':'RC approved','quantity':'1','unit':'盒','location':'测试库','purchased_at':None,'label_expiry':None}}
 db.add(AITask(id=t,user_id=u,household_id=h,request_id='rc-rehearsal',request_hash='a'*64,original_text='合成测试',household_timezone='Asia/Shanghai',status='needs_confirmation',revision=1,result_json={{'status':'needs_confirmation','draft':command}}))
 db.flush();db.add(AIDraft(id=UUID('{draft}'),task_id=t,user_id=u,household_id=h,revision=1,status='pending',command_json=command))
'''
run(OLD, ["python", "-"], seed)
digest = '''
import json
from sqlalchemy import text
from app.database import SessionLocal
with SessionLocal() as db:
 db.execute(text('SET TRANSACTION READ ONLY'))
 names=['users','households','household_members','shopping_lists','inventory_items','ai_tasks','ai_drafts']
 values={n:list(db.execute(text("SELECT count(*),md5(coalesce(string_agg(h,',' ORDER BY h),'')) FROM (SELECT md5(row_to_json(r)::text) h FROM "+n+" r) s")).one()) for n in names}
 print(json.dumps(values));db.rollback()
'''
before = json.loads(run(OLD, ["python", "-"], digest).stdout)
backup = docker(["exec", DB, "pg_dump", "-U", dbuser, "-Fc", name])
assert backup.returncode == 0
backup_path = ROOT / (name + ".dump"); backup_path.write_bytes(backup.stdout)
p = docker(["exec", "-i", DB, "pg_restore", "-U", dbuser, "-d", restored, "--exit-on-error"], input=backup.stdout)
assert p.returncode == 0
env["DB_NAME"] = restored
restore_hashes = json.loads(run(OLD, ["python", "-"], digest).stdout)
assert restore_hashes == before
env["DB_NAME"] = name
run(NEW, ["alembic", "upgrade", "head"])
assert json.loads(run(NEW, ["python", "-"], digest).stdout) == before
check = run(NEW, ["alembic", "check"], ok=False)
old_compat = json.loads(run(OLD, ["python", "-"], digest).stdout) == before
commit = f'''
import json
from types import SimpleNamespace
from uuid import UUID,uuid4
from app.database import SessionLocal
from app.models import User
from app.execution_schemas import CommitRequest
from app.services.draft_execution import execute
with SessionLocal() as db:
 receipt=execute(db,SimpleNamespace(user=db.get(User,UUID('{actor}'))),UUID('{draft}'),CommitRequest(operation_id=uuid4(),draft_revision=1,task_revision=1,edits={{}}));db.commit()
 print(json.dumps({{'status':receipt['status'],'action':receipt['action'],'operation_id':receipt['operation_id']}}))
'''
receipt = json.loads(run(NEW, ["python", "-"], commit).stdout)
assert receipt["status"] == "committed"
downgrade = run(NEW, ["alembic", "downgrade", "20261016_0006"], ok=False)
assert downgrade.returncode != 0 and b"Execution audit data exists" in downgrade.stderr + downgrade.stdout
run(OLD, ["python", "-"], digest)  # Old application can still read after a new-style commit.
summary = {"database": name, "restore_database": restored, "backup_file": backup_path.name,
    "backup_sha256": hashlib.sha256(backup.stdout).hexdigest(), "restore_verified": True,
    "legacy_hashes_preserved_on_upgrade": True, "old_backend_compatible": old_compat,
    "alembic_check_exit": check.returncode, "alembic_check_output": (check.stdout + check.stderr).decode(),
    "new_business_receipt": receipt, "downgrade_guard_verified": True, "production_modified": False}
(ROOT / "rehearsal.log").write_text("\n".join(logs))
(ROOT / "rehearsal.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary))
