"""Live, rules-only acceptance. Run INSIDE the dedicated stage-3 backend.

Creates a new synthetic household per run. Never clears data, touches another
database, reads provider secrets, or calls a paid model. JSON output is safe evidence.
"""
import hashlib
import json
import os
import secrets
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from uuid import UUID, uuid4

import httpx
from sqlalchemy import func, select, text

from app.database import SessionLocal
from app.execution_models import BusinessEvent, DraftOperation
from app.models import Household, HouseholdMember, InventoryItem, ShoppingList, User
from app.security import hash_password


def main():
    assert os.environ.get("DB_NAME") == "magicvvu_p7_execution_test"
    assert os.environ.get("DB_HOST") == "db" and os.environ.get("ISOLATED_APP_TEST") == "yes"
    run_id = uuid4().hex
    ids = {k: uuid4() for k in ("user", "other", "home", "other_home", "paper", "milk1", "milk2")}
    phones = {k: "+1999" + str(secrets.randbelow(10**8)).zfill(8) for k in ("user", "other")}
    with SessionLocal.begin() as db:
        for actor in ("user", "other"):
            db.add(User(id=ids[actor], phone=phones[actor], password_hash=hash_password("synthetic-stage3-only"), display_name="Synthetic "+actor))
        db.flush()
        for home, actor in (("home", "user"), ("other_home", "other")):
            db.add(Household(id=ids[home], name="Synthetic "+run_id, created_by_user_id=ids[actor]))
        db.flush()
        for home, actor in (("home", "user"), ("other_home", "other")):
            db.add(HouseholdMember(household_id=ids[home], user_id=ids[actor], role="owner"))
            db.add(ShoppingList(household_id=ids[home], name="Synthetic shared", created_by_user_id=ids[actor]))
        for key, name, quantity, unit, location in (("paper", "纸巾", 5, "包", "储物柜"),
                ("milk1", "牛奶", 2, "盒", "冰箱"), ("milk2", "牛奶", 3, "盒", "厨房")):
            db.add(InventoryItem(id=ids[key], household_id=ids["home"], name=name, quantity=quantity,
                unit=unit, storage_location=location, status="ACTIVE", version=1,
                purchased_on=date.today(), expires_on=date.today()+timedelta(days=14), created_by_user_id=ids["user"]))
    client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=20, trust_env=False)
    checks, examples = [], {}

    def check(name, value):
        assert value, name
        checks.append(name)

    sessions = {}
    for actor in ("user", "other"):
        response = client.post("/api/v1/auth/login", json={"phone": phones[actor], "password": "synthetic-stage3-only"})
        check("real_login_"+actor, response.status_code == 200)
        sessions[actor] = {"Authorization": "Bearer "+response.json()["access_token"]}
    auth = sessions["user"]

    def digest():
        with SessionLocal() as db:
            return {table:tuple(db.execute(text("SELECT count(*),md5(coalesce(string_agg(h,',' ORDER BY h),'')) FROM (SELECT md5(row_to_json(r)::text) h FROM "+table+" r) s")).one())
                    for table in ("inventory_items", "shopping_list_items", "shopping_lists")}

    def quantity():
        with SessionLocal() as db:
            return db.get(InventoryItem, ids["paper"]).quantity

    def draft(label, words):
        before = digest()
        result = client.post("/api/v1/agent/messages", headers=auth, json={"household_id": str(ids["home"]),
            "text": words, "request_id": run_id+"-"+label, "household_timezone": "Asia/Shanghai"})
        check(label+"_message_http", result.status_code == 200)
        task = result.json()
        check(label+"_draft_ready", task["status"] == "needs_confirmation")
        check(label+"_no_business_write_before_confirm", before == digest())
        state = client.get("/api/v1/drafts/"+task["draft_id"]+"/execution", headers=auth).json()
        return task, {"operation_id": str(uuid4()), "draft_revision": state["draft_revision"],
                      "task_revision": state["task_revision"], "edits": {}}

    def commit(task, request):
        return client.post("/api/v1/drafts/"+task["draft_id"]+"/commit", headers=auth, json=request)

    check("backend_090", client.get("/api/v1/health").json()["version"] == "0.9.0")
    check("database_ready", client.get("/api/v1/ready").status_code == 200)
    agent = httpx.Client(base_url="http://agent:8767", timeout=15, trust_env=False)
    health = agent.get("/health").json()
    check("p7_rules_only", health["release_version"] == "V1-P7" and health["engine"] == "rules")
    for label, words in (("ADD", "添加2袋饼干"), ("MOVE", "把纸巾移到书房"),
                         ("PLAN_ADD", "采购清单加2包纸巾"), ("CONSUME", "纸巾消耗1包")):
        task, request = draft(label, words)
        if label == "ADD":
            request["edits"] = {"location": "储物柜"}
        result = commit(task, request)
        check(label+"_committed", result.status_code == 200)
        receipt = result.json()
        check(label+"_durable_replay", commit(task, request).json() == receipt)
        check(label+"_recover_get", client.get("/api/v1/operations/"+request["operation_id"], headers=auth).json() == receipt)
        examples[label] = {"request": request, "receipt": receipt}
        if label == "MOVE":
            row = receipt["result"]["inventory_item"]
            check("MOVE_quantity_unchanged", row["storage_location"] == "书房" and float(row["quantity"]) == 5)
        if label == "PLAN_ADD":
            check("PLAN_not_purchased", receipt["shopping_written"] and not receipt["inventory_written"] and not receipt["result"]["shopping_item"]["is_checked"])
        if label == "CONSUME":
            check("CONSUME_stock", quantity() == 4)
            events = client.get(f"/api/v1/households/{ids['home']}/consumption-events", headers=auth).json()
            check("CONSUME_formal_event", events["total"] == 1 and events["items"][0]["event_type"] == "Consumed" and float(events["items"][0]["quantity"]) == 1)
    task, request = draft("cancel", "纸巾消耗1包")
    cancel = {k:request[k] for k in ("draft_revision", "task_revision")}
    check("cancel_success", client.post("/api/v1/drafts/"+task["draft_id"]+"/cancel", headers=auth, json=cancel).status_code == 200)
    check("cancel_blocks_commit", commit(task, request).status_code == 409 and quantity() == 4)
    task, request = draft("stale", "纸巾消耗1包")
    check("cross_family_commit_denied", client.post("/api/v1/drafts/"+task["draft_id"]+"/commit", headers=sessions["other"], json=request).status_code == 404)
    with SessionLocal() as db:
        version = db.get(InventoryItem, ids["paper"]).version
    changed = client.patch(f"/api/v1/households/{ids['home']}/inventory-items/{ids['paper']}", headers=auth,
        json={"expected_version":version,"operation_id":str(uuid4()),"storage_location":"厨房"})
    check("manual_inventory_regression", changed.status_code == 200)
    check("stale_inventory_denied", commit(task, request).status_code == 409 and quantity() == 4)
    task, request = draft("concurrent", "纸巾消耗1包")
    requests = [{**request,"operation_id":str(uuid4())} for _ in range(6)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(lambda value:commit(task, value), requests))
    check("http_concurrent_once", sum(r.status_code==200 for r in responses)==1 and all(r.status_code in (200,409) for r in responses) and quantity()==3)
    task, request = draft("lost-response", "纸巾消耗1包")
    data = json.dumps(request).encode()
    path = "/api/v1/drafts/"+task["draft_id"]+"/commit"
    wire = ("POST "+path+" HTTP/1.1\r\nHost: localhost\r\nAuthorization: "+auth["Authorization"]+
            "\r\nContent-Type: application/json\r\nContent-Length: "+str(len(data))+"\r\nConnection: close\r\n\r\n").encode()+data
    with socket.create_connection(("127.0.0.1",8000), timeout=5) as connection:
        connection.sendall(wire)
        connection.shutdown(socket.SHUT_WR)
        # Intentionally close without reading any HTTP response bytes.
    recovered = None
    for _ in range(30):
        result = client.get("/api/v1/operations/"+request["operation_id"],headers=auth)
        if result.status_code == 200:
            recovered = result.json();break
        assert result.status_code==404
        time.sleep(0.1)
    check("lost_http_response_recovered", recovered is not None and quantity()==2)
    check("lost_response_same_key_no_reexecution", commit(task,request).json()==recovered and quantity()==2)
    tool_headers = {"Authorization":"Bearer "+os.environ["BACKEND_TOOL_TOKEN"],
                    "X-User-Id":str(ids["user"]),"X-Household-Id":str(ids["home"])}
    receipt = client.get("/internal/v1/operations/"+request["operation_id"],headers=tool_headers)
    check("internal_trusted_receipt", receipt.status_code==200 and receipt.json()["data"]["event_ids"]==recovered["event_ids"])
    for action, words in (("OPEN","纸巾昨天开封"),("DISCARD","把纸巾全部丢弃")):
        task, request=draft(action,words)
        result=commit(task,request)
        check(action+"_explicitly_unavailable",result.status_code==409 and result.json()["detail"]["code"]=="ACTION_NOT_EXECUTABLE" and quantity()==2)
    check("legacy_household_get", client.get("/api/v1/households",headers=auth).status_code==200)
    check("legacy_shopping_get", client.get(f"/api/v1/households/{ids['home']}/shopping-list/items",headers=auth).status_code==200)
    with SessionLocal() as db:
        consumed=db.scalars(select(BusinessEvent).where(BusinessEvent.household_id==ids["home"],BusinessEvent.event_type=="Consumed")).all()
        check("semantic_events_match_final_stock",len(consumed)==3 and sum(row.quantity for row in consumed)==3)
    print(json.dumps({"passed":True,"run_id":run_id,"checks":checks,"examples":examples,
                      "final_paper_quantity":"2","paid_model_calls":0},ensure_ascii=False))


if __name__ == "__main__":
    main()
