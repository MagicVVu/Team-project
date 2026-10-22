"""Candidate-image regression; disposable SQLite or dedicated empty PostgreSQL only."""
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import sessionmaker

assert os.environ.get("HOUSEHOLD_TEST_ISOLATED") == "yes"
PG = os.environ.get("HOUSEHOLD_TEST_PG") == "yes"
if PG:
    assert os.environ.get("DB_NAME") == "household_management_test"
    from sqlalchemy.engine import URL
    engine = create_engine(URL.create("postgresql+psycopg", username="test",
        password=os.environ["DB_PASSWORD"], host="household-pg", database="household_management_test"),
        pool_size=8, max_overflow=0, connect_args={"options": "-c statement_timeout=10000"})
else:
    folder = tempfile.TemporaryDirectory()
    engine = create_engine("sqlite:///" + str(Path(folder.name) / "test.sqlite"),
                           connect_args={"check_same_thread": False})
    @event.listens_for(engine, "connect")
    def fks(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

with patch("sqlalchemy.create_engine", return_value=engine):
    from app.database import Base
    from app.dependencies import get_db
    from app.main import app
    from app.models import (AIDraft, AITask, AuthSession, BusinessEvent, DraftDecision,
        DraftOperation, Household, HouseholdInvitation, HouseholdMember, InventoryItem,
        ShoppingList, ShoppingListItem, User)
from app.security import digest_token, now_utc

Session = sessionmaker(bind=engine, autoflush=False)


def isolated_db():
    with Session() as db:
        yield db


class ManagementTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.create_all(engine)
        self.ids = {k: uuid4() for k in ("owner", "admin", "admin2", "member", "outsider", "home", "other", "list")}
        self.ids["missing"] = uuid4()
        with Session.begin() as db:
            for actor in ("owner", "admin", "admin2", "member", "outsider"):
                db.add(User(id=self.ids[actor], email=actor+"@example.invalid",
                            password_hash="fixture", display_name=actor))
            db.flush()
            db.add(Household(id=self.ids["home"], name="Test Home", created_by_user_id=self.ids["owner"]))
            db.add(Household(id=self.ids["other"], name="Other Home", created_by_user_id=self.ids["outsider"]))
            db.flush()
            for actor, role in (("owner", "owner"), ("admin", "admin"), ("admin2", "admin"), ("member", "member")):
                db.add(HouseholdMember(household_id=self.ids["home"], user_id=self.ids[actor], role=role))
            db.add(HouseholdMember(household_id=self.ids["other"], user_id=self.ids["outsider"], role="owner"))
            db.add(ShoppingList(id=self.ids["list"], household_id=self.ids["home"], name="Shared"))
            for actor in ("owner", "admin", "admin2", "member", "outsider"):
                db.add(AuthSession(user_id=self.ids[actor], token_hash=digest_token("fixture-"+actor),
                                   expires_at=now_utc()+timedelta(hours=1)))
        app.dependency_overrides[get_db] = isolated_db
        self.client = TestClient(app)
        self.root = "/api/v1/households/"+str(self.ids["home"])

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        # Dedicated test DB only: cycles are SET NULL and the ledger uses RESTRICT.
        with engine.begin() as db:
            for table in (BusinessEvent, DraftDecision, DraftOperation, AIDraft, AITask,
                          HouseholdInvitation, InventoryItem, ShoppingListItem, ShoppingList,
                          HouseholdMember, Household, AuthSession, User):
                db.execute(table.__table__.delete())

    def request(self, method, suffix="", actor="owner", body=None):
        kwargs = {"headers": {"Authorization": "Bearer fixture-"+actor}} if actor else {}
        if body is not None:
            kwargs["json"] = body
        return self.client.request(method, self.root+suffix, **kwargs)

    def role(self, actor):
        with Session() as db:
            m = db.get(HouseholdMember, (self.ids["home"], self.ids[actor]))
            return m.role if m else None

    def test_auth_and_cross_household(self):
        cases = [("POST", "/leave", None), ("DELETE", "/members/"+str(self.ids["member"]), None),
                 ("PATCH", "/members/"+str(self.ids["member"]), {"role":"admin"}),
                 ("POST", "/transfer-ownership", {"new_owner_user_id":str(self.ids["member"])}),
                 ("DELETE", "", {"confirmation_name":"Test Home"})]
        for method, suffix, body in cases:
            self.assertEqual(self.request(method,suffix,None,body).status_code,401)
            self.assertEqual(self.request(method,suffix,"outsider",body).status_code,404)

    def test_leave_and_revocation(self):
        code = self.request("POST","/invitations","admin").json()["invite_code"]
        self.assertEqual(self.request("POST","/leave","admin").status_code,204)
        self.assertIsNone(self.role("admin"))
        for suffix in ("/members", "/inventory-items", "/shopping-list"):
            self.assertEqual(self.request("GET",suffix,"admin").status_code,404)
        r = self.client.post("/api/v1/households/join",json={"invite_code":code},
                             headers={"Authorization":"Bearer fixture-outsider"})
        self.assertEqual(r.status_code,400)
        self.assertEqual(self.request("POST","/leave").status_code,409)
        self.assertEqual(self.role("owner"),"owner")

    def test_remove_permission_matrix(self):
        member = "/members/"+str(self.ids["member"])
        self.assertEqual(self.request("DELETE",member,"member").status_code,403)
        self.assertEqual(self.request("DELETE","/members/"+str(self.ids["owner"]),"admin").status_code,403)
        self.assertEqual(self.request("DELETE","/members/"+str(self.ids["admin2"]),"admin").status_code,403)
        self.assertEqual(self.request("DELETE","/members/"+str(self.ids["admin"]),"admin").status_code,409)
        self.assertEqual(self.request("DELETE",member,"admin").status_code,204)
        self.assertIsNone(self.role("member"))
        self.assertEqual(self.request("GET","/inventory-items","member").status_code,404)
        self.assertEqual(self.request("DELETE",member).status_code,404)
        self.assertEqual(self.request("DELETE","/members/"+str(self.ids["admin"])).status_code,204)

    def test_role_management(self):
        suffix = "/members/"+str(self.ids["member"])
        for actor in ("admin","member"):
            self.assertEqual(self.request("PATCH",suffix,actor,{"role":"admin"}).status_code,403)
        for role in ("owner","invalid",None):
            self.assertEqual(self.request("PATCH",suffix,body={"role":role}).status_code,422)
        self.assertEqual(self.request("PATCH",suffix,body={"role":"admin","user_id":"fake"}).status_code,422)
        for role in ("admin","admin","member"):
            r = self.request("PATCH",suffix,body={"role":role})
            self.assertEqual(r.status_code,200,r.text)
            self.assertEqual(r.json()["role"],role)
        self.assertEqual(self.request("PATCH","/members/"+str(self.ids["owner"]),body={"role":"member"}).status_code,409)
        self.assertEqual(self.request("PATCH","/members/"+str(self.ids["missing"]),body={"role":"admin"}).status_code,404)

    def test_create_invite_join_and_shared_data_survives_removal(self):
        auth={"Authorization":"Bearer fixture-owner"}
        r=self.client.post("/api/v1/households",headers=auth,json={"name":" Another Home "})
        self.assertEqual(r.status_code,201,r.text)
        root="/api/v1/households/"+r.json()["id"]
        self.assertEqual(r.json()["name"],"Another Home")
        code=self.client.post(root+"/invitations",headers=auth).json()["invite_code"]
        other_auth={"Authorization":"Bearer fixture-outsider"}
        r=self.client.post("/api/v1/households/join",headers=other_auth,json={"invite_code":code})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.client.post("/api/v1/households/join",headers=other_auth,json={"invite_code":code}).status_code,400)
        r=self.client.post(root+"/shopping-list/items",headers=other_auth,json={"name":"Fixture","quantity":"2","unit":"box"})
        self.assertEqual(r.status_code,201,r.text)
        self.assertEqual(self.client.delete(root+"/members/"+str(self.ids["outsider"]),headers=auth).status_code,204)
        self.assertEqual(self.client.get(root+"/shopping-list/items",headers=other_auth).status_code,404)
        self.assertEqual(self.client.get(root+"/shopping-list/items",headers=auth).json()["total"],1)
        self.assertEqual(self.client.request("DELETE",root,headers=auth,json={"confirmation_name":"Another Home"}).status_code,204)

    def test_transfer_and_old_owner_leave(self):
        body={"new_owner_user_id":str(self.ids["member"])}
        self.assertEqual(self.request("POST","/transfer-ownership","admin",body).status_code,403)
        self.assertEqual(self.request("POST","/transfer-ownership",body={"new_owner_user_id":str(self.ids["outsider"])}).status_code,404)
        self.assertEqual(self.request("POST","/transfer-ownership",body={"new_owner_user_id":str(self.ids["owner"])}).status_code,409)
        with Session.begin() as db:
            db.get(User,self.ids["member"]).is_active=False
        self.assertEqual(self.request("POST","/transfer-ownership",body=body).status_code,409)
        with Session.begin() as db:
            db.get(User,self.ids["member"]).is_active=True
        r=self.request("POST","/transfer-ownership",body=body)
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.role("owner"),"member")
        self.assertEqual(self.role("member"),"owner")
        self.assertEqual(self.request("POST","/transfer-ownership",body=body).status_code,403)
        self.assertEqual(self.request("POST","/leave").status_code,204)

    def test_dissolve_confirmation_and_ledger(self):
        for actor in ("admin","member"):
            self.assertEqual(self.request("DELETE",actor=actor,body={"confirmation_name":"Test Home"}).status_code,403)
        self.assertEqual(self.request("DELETE",body={"confirmation_name":"wrong"}).status_code,409)
        self.assertEqual(self.request("DELETE").status_code,422)
        now=now_utc()
        task,draft,operation,stock,item=[uuid4() for _ in range(5)]
        with Session.begin() as db:
            db.add(InventoryItem(id=stock,household_id=self.ids["home"],name="Fixture",quantity=2,unit="box"))
            db.add(ShoppingListItem(id=item,shopping_list_id=self.ids["list"],name="Fixture",quantity=1,unit="box"))
            db.add(AITask(id=task,user_id=self.ids["owner"],household_id=self.ids["home"],request_id=uuid4().hex,
                request_hash="fixture",original_text="fixture",household_timezone="Asia/Shanghai",status="needs_confirmation"))
            db.flush()
            db.add(AIDraft(id=draft,task_id=task,user_id=self.ids["owner"],household_id=self.ids["home"],command_json={}))
            db.flush()
            db.add(DraftOperation(id=operation,draft_id=draft,user_id=self.ids["owner"],household_id=self.ids["home"],
                draft_revision=1,task_revision=1,action="CONSUME",request_hash="fixture",command_json={},receipt_json={},committed_at=now))
            db.flush()
            db.add(DraftDecision(draft_id=draft,draft_revision=1,task_revision=1,status="committed",operation_id=operation))
            db.add(BusinessEvent(operation_id=operation,household_id=self.ids["home"],actor_user_id=self.ids["owner"],
                inventory_item_id=stock,shopping_item_id=item,event_type="Consumed",quantity=1,unit="box",before_json={},after_json={},occurred_at=now))
        r=self.request("DELETE",body={"confirmation_name":"Test Home"})
        self.assertEqual(r.status_code,204,r.text)
        with Session() as db:
            for model,pk in ((Household,self.ids["home"]),(AITask,task),(AIDraft,draft),(DraftOperation,operation),(InventoryItem,stock),(ShoppingListItem,item)):
                self.assertIsNone(db.get(model,pk))
            self.assertIsNotNone(db.get(Household,self.ids["other"]))
            self.assertEqual(db.scalar(select(func.count()).select_from(User)),5)
            self.assertEqual(db.scalar(select(func.count()).select_from(AuthSession)),5)
        self.assertEqual(self.request("GET","/members").status_code,404)

    def test_dissolve_transaction_rolls_back_on_failure(self):
        stock=uuid4()
        with Session.begin() as db:
            db.add(InventoryItem(id=stock,household_id=self.ids["home"],name="Fixture",quantity=2,unit="box"))
        code=self.request("POST","/invitations").json()["invite_code"]
        # The SQL deletes have executed, but a failed transaction must retain all data.
        with patch.object(Session.class_,"commit",side_effect=RuntimeError("injected failure")):
            with TestClient(app,raise_server_exceptions=False) as client:
                r=client.request("DELETE",self.root,headers={"Authorization":"Bearer fixture-owner"},
                                 json={"confirmation_name":"Test Home"})
        self.assertEqual(r.status_code,500)
        with Session() as db:
            self.assertIsNotNone(db.get(Household,self.ids["home"]))
            self.assertIsNotNone(db.get(InventoryItem,stock))
            self.assertIsNotNone(db.get(ShoppingList,self.ids["list"]))
            self.assertEqual(db.scalar(select(func.count()).select_from(HouseholdInvitation).where(
                HouseholdInvitation.code_hash==digest_token(code))),1)
        self.assertEqual(self.role("owner"),"owner")

    @unittest.skipUnless(PG,"PostgreSQL row lock test")
    def test_removal_waits_for_authorized_transaction(self):
        from app.routers.households import membership_or_404
        with ThreadPoolExecutor(1) as pool:
            with Session.begin() as db:
                membership_or_404(db,self.ids["home"],self.ids["member"])
                pending=pool.submit(self.request,"DELETE","/members/"+str(self.ids["member"]))
                with self.assertRaises(TimeoutError):
                    pending.result(timeout=0.5)
            self.assertEqual(pending.result(timeout=10).status_code,204)
        self.assertEqual(self.request("GET","/inventory-items","member").status_code,404)

    @unittest.skipUnless(PG,"PostgreSQL row lock test")
    def test_concurrent_transfers_keep_exactly_one_owner(self):
        def transfer(target):
            return self.request("POST","/transfer-ownership",body={"new_owner_user_id":str(self.ids[target])}).status_code
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(transfer,["member","admin"]))
        self.assertEqual(sorted(results),[200,403])
        with Session() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(HouseholdMember).where(
                HouseholdMember.household_id==self.ids["home"],HouseholdMember.role=="owner")),1)


if __name__ == "__main__":
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ManagementTests))
    print(json.dumps({"passed":result.wasSuccessful(),"tests":result.testsRun,"skipped":len(result.skipped),"postgres":PG}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
