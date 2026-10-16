"""Live PostgreSQL AI read-contract smoke; never commits any test rows.

Run AFTER applying Alembic 0004 and after configuring BACKEND_TOOL_TOKEN.
Does not invoke DeepSeek or modify existing household inventory.
"""
import os
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.database import engine
from app.models import Household, HouseholdMember, InventoryItem, User
from app.routers.ai_inventory import _authorize, get_batch, search_batches


def main() -> None:
    token = os.getenv("BACKEND_TOOL_TOKEN", "")
    if len(token) < 32:
        raise RuntimeError("BACKEND_TOOL_TOKEN must be configured with a high-entropy secret before live smoke")
    with engine.connect() as conn:
        inspector = inspect(conn)
        cols = {c["name"] for c in inspector.get_columns("inventory_items")}
        assert {"opened_at", "status", "version"}.issubset(cols), "Run Alembic upgrade to 0004 first"

    with engine.connect() as conn:
        outer = conn.begin()
        try:
            with Session(bind=conn, join_transaction_mode="create_savepoint") as db:
                actor = User(email=f"ai-read-{uuid4().hex}@example.invalid",
                             display_name="AI Smoke", password_hash="not-a-password")
                outsider = User(email=f"ai-other-{uuid4().hex}@example.invalid",
                                display_name="AI Smoke Outsider", password_hash="not-a-password")
                db.add_all([actor, outsider])
                db.flush()
                home = Household(name="temporary-ai-test-household", created_by_user_id=actor.id)
                db.add(home)
                db.flush()
                db.add(HouseholdMember(household_id=home.id, user_id=actor.id, role="owner"))
                batch = InventoryItem(household_id=home.id, name="烟测牛奶", quantity=Decimal("2.123456"),
                                      unit="盒", storage_location="冰箱", version=4)
                db.add(batch)
                db.flush()
                scope = dict(x_user_id=str(actor.id), x_household_id=str(home.id), db=db)
                allowed_household = _authorize(authorization=f"Bearer {token}", **scope)
                assert allowed_household == home.id
                result = search_batches(name="烟测牛奶", household_id=home.id, db=db)
                assert len(result["data"]["batches"]) == 1
                b = result["data"]["batches"][0]
                assert b["quantity"] == "2.123456" and b["version"] == 4
                assert get_batch(batch.id, household_id=home.id, db=db)["data"]["batch"] == b
                try:
                    _authorize(authorization=f"Bearer {token}", x_user_id=str(outsider.id),
                               x_household_id=str(home.id), db=db)
                except HTTPException as exc:
                    assert exc.status_code == 404
                else:
                    raise AssertionError("Non-member can access household inventory")
                print("AI READ SMOKE PASSED: precision, batch contract, read-by-ID, membership")
        finally:
            outer.rollback()
            print("AI READ TEST DATA ROLLED BACK")


if __name__ == "__main__":
    main()
