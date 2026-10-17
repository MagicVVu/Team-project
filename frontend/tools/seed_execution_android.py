"""Run via stdin INSIDE the exact stage-3 backend. Outputs private fixture credentials.

The runner must capture stdout into a private local file, never a test log/report.
Only creates a new synthetic cohort; never truncates, migrates or modifies old data.
"""
import json
import os
import secrets
from datetime import date, timedelta
from uuid import uuid4

from app.database import SessionLocal
from app.models import User, Household, HouseholdMember, ShoppingList, InventoryItem
from app.security import hash_password

assert os.environ.get("DB_NAME") == "magicvvu_p7_execution_test"
assert os.environ.get("DB_HOST") == "db" and os.environ.get("ISOLATED_APP_TEST") == "yes"
password = secrets.token_urlsafe(24)
phones = ["+1998" + str(secrets.randbelow(10**9)).zfill(9) for _ in range(2)]
users = [uuid4(), uuid4()]
homes = [uuid4(), uuid4(), uuid4()]
with SessionLocal.begin() as db:
    for i, uid in enumerate(users):
        db.add(User(id=uid, phone=phones[i], password_hash=hash_password(password), display_name="Android P4 synthetic"))
    db.flush()
    for i, hid in enumerate(homes):
        uid = users[0 if i < 2 else 1]
        db.add(Household(id=hid, name="Android P4 " + hid.hex[:8], created_by_user_id=uid))
        db.flush()
        db.add(HouseholdMember(household_id=hid, user_id=uid, role="owner"))
        db.add(ShoppingList(household_id=hid, name="Android shared", created_by_user_id=uid))
    for name, quantity, unit, location in (("纸巾", 8, "包", "书房"), ("牛奶", 2, "盒", "冰箱"), ("牛奶", 3, "盒", "厨房")):
        db.add(InventoryItem(id=uuid4(), household_id=homes[0], name=name, quantity=quantity, unit=unit,
            storage_location=location, status="ACTIVE", version=1, purchased_on=date.today(),
            expires_on=date.today() + timedelta(days=14), created_by_user_id=users[0]))
print(json.dumps({"phone": phones[0], "other_phone": phones[1], "password": password,
    "household": str(homes[0]), "second_household": str(homes[1]), "other_household": str(homes[2])}))
