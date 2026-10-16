"""Admin CLI for a dedicated unverified development account; no public signup."""
import argparse
import json
import secrets

from app.database import SessionLocal
from app.models import Household, HouseholdMember, ShoppingList, User
from app.security import hash_password


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--create-debug-account", action="store_true", required=True)
    parser.parse_args()
    password = secrets.token_urlsafe(24)
    # Synthetic login identifier, never a claim of phone ownership.
    phone = "+1999" + str(secrets.randbelow(10**9)).zfill(9)
    with SessionLocal.begin() as db:
        user = User(phone=phone, display_name="拾物联调账号", password_hash=hash_password(password))
        db.add(user)
        db.flush()
        home = Household(name="App 联调家庭", created_by_user_id=user.id)
        db.add(home)
        db.flush()
        db.add(HouseholdMember(household_id=home.id, user_id=user.id, role="owner"))
        db.add(ShoppingList(household_id=home.id, name="家庭共享购物清单", created_by_user_id=user.id))
        user_id, home_id = str(user.id), str(home.id)
    # Redirect stdout into a mode-600 file. Do not print this output to chat/logs.
    print(json.dumps(dict(phone=phone, password=password, user_id=user_id, household_id=home_id,
                          server_url="http://10.0.2.2:18080"), ensure_ascii=False))


if __name__ == "__main__":
    main()
