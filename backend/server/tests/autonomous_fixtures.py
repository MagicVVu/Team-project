"""Autonomous tests use the current physical-object schema, not retired batches."""
from datetime import timedelta
from contextlib import contextmanager
from uuid import uuid4
import pytest
from test_physical_inventory import state
from app.models import AuthSession, InventoryItem
from app.security import digest_token
from app.routers import agent_gateway as gateway


@pytest.fixture
def execution_state(tmp_path):
    with contextmanager(state.__wrapped__)(tmp_path) as current:
        client, Session, source=current
        ids={"user":source["owner"],"outsider":source["outsider"],"home":source["home"],
            "foreign_home":source["other_home"],"list":source["list"],"foreign_list":source["other_list"],"batch":uuid4()}
        with Session.begin() as db:
            for key in ("user","outsider"):
                db.add(AuthSession(user_id=ids[key],token_hash=digest_token("synthetic-"+key),
                    expires_at=gateway.now()+timedelta(hours=1)))
            db.add(InventoryItem(id=ids["batch"],household_id=ids["home"],name="牛奶",unit="盒",
                storage_location="冰箱",status="ACTIVE",version=1,created_by_user_id=ids["user"]))
        yield client,Session,ids


def multiple(Session,ids):
    with Session.begin() as db:
        for location in ("厨房","储物柜"):
            db.add(InventoryItem(household_id=ids["home"],name="牛奶",unit="盒",storage_location=location,
                status="ACTIVE",version=1,created_by_user_id=ids["user"]))
