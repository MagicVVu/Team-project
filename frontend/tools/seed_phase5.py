"""stdin inside the verified stage-3 backend only. Capture private output, never log it."""
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
keys = ("owner", "other", "member", "legacy", "legacy_other", "legacy_ui")
ids = {k: uuid4() for k in keys}
phones = {k: "+1997" + str(secrets.randbelow(10**9)).zfill(9) for k in keys}
homes = [uuid4(), uuid4(), uuid4()]
with SessionLocal.begin() as db:
    for k in keys:
        db.add(User(id=ids[k], phone=phones[k], password_hash=hash_password(password), display_name="P5 synthetic " + k))
    db.flush()
    for i, h in enumerate(homes):
        owner = ids["owner" if i < 2 else "other"]
        db.add(Household(id=h, name="P5 synthetic " + h.hex[:8], created_by_user_id=owner))
        db.flush()
        db.add(HouseholdMember(household_id=h, user_id=owner, role="owner"))
        db.add(ShoppingList(household_id=h, name="P5 shared", created_by_user_id=owner))
    db.add(HouseholdMember(household_id=homes[0], user_id=ids["member"], role="member"))
    for name, quantity, unit, location in (("纸巾", 200, "包", "书房"), ("牛奶", 2, "盒", "冰箱"), ("牛奶", 3, "盒", "厨房")):
        db.add(InventoryItem(id=uuid4(), household_id=homes[0], name=name, quantity=quantity, unit=unit,
            storage_location=location, status="ACTIVE", version=1, purchased_on=date.today(),
            expires_on=date.today() + timedelta(days=14), created_by_user_id=ids["owner"]))
print(json.dumps({"phone": phones["owner"], "other_phone": phones["other"], "member_phone": phones["member"],
    "legacy_phone": phones["legacy"], "legacy_other_phone": phones["legacy_other"], "legacy_ui_phone": phones["legacy_ui"],
    "password": password, "household": str(homes[0]), "second_household": str(homes[1]), "other_household": str(homes[2])}))
