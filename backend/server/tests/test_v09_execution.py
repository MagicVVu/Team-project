"""Real auth, durable execution and rollback; optionally run on isolated PostgreSQL.

DRAFT_EXECUTION_PG_TEST=yes requires DB_NAME=magicvvu_p7_execution_test.
Every test then owns a fresh schema; no production or earlier test volume is used.
"""
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DB_PASSWORD", "isolated-test-only")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with patch("sqlalchemy.create_engine", return_value=create_engine("sqlite://")):
    from app.database import Base, database_url
    from app.dependencies import get_db
    from app.main import app
    from app.models import AIDraft, AITask, AuthSession, Household, HouseholdMember, InventoryItem, ShoppingList, ShoppingListItem, User
    from app.execution_models import BusinessEvent, DraftDecision, DraftOperation
    from app.routers import agent_gateway
    from app.services import draft_execution
from app.security import digest_token

PG = os.getenv("DRAFT_EXECUTION_PG_TEST") == "yes"


@pytest.fixture
def execution_state(tmp_path):
    admin, schema = None, None
    if PG:
        assert os.environ.get("DB_NAME") == "magicvvu_p7_execution_test"
        assert os.environ.get("DB_HOST") == "db"
        schema = "p7_case_" + uuid4().hex
        admin = create_engine(database_url())
        with admin.begin() as db:
            db.execute(text('CREATE SCHEMA "' + schema + '"'))
        engine = create_engine(database_url(), connect_args={"options": "-csearch_path=" + schema}, pool_size=10, max_overflow=0)
    else:
        engine = create_engine(f"sqlite:///{tmp_path/'execution.sqlite'}", connect_args={"check_same_thread": False})
        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False)
    ids = {k: uuid4() for k in ("user", "outsider", "home", "foreign_home", "batch", "list", "foreign_list")}
    with Session.begin() as db:
        for name in ("user", "outsider"):
            db.add(User(id=ids[name], email=name+"@example.invalid", password_hash="fixture", display_name=name))
        db.flush()
        for home, who in (("home", "user"), ("foreign_home", "outsider")):
            db.add(Household(id=ids[home], name=home, created_by_user_id=ids[who]))
        db.flush()
        for home, who, key in (("home", "user", "list"), ("foreign_home", "outsider", "foreign_list")):
            db.add(HouseholdMember(household_id=ids[home], user_id=ids[who], role="owner"))
            db.add(ShoppingList(id=ids[key], household_id=ids[home], name="Shared"))
            db.add(AuthSession(user_id=ids[who], token_hash=digest_token("synthetic-"+who),
                expires_at=datetime.now(timezone.utc)+timedelta(hours=1)))
        db.add(InventoryItem(id=ids["batch"], household_id=ids["home"], name="牛奶", quantity=Decimal(5),
            unit="盒", storage_location="冰箱", status="ACTIVE", version=1, created_by_user_id=ids["user"]))

    def isolated():
        with Session() as db:
            yield db
    app.dependency_overrides[get_db] = isolated
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, Session, ids
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
        if admin is not None:
            assert schema.startswith("p7_case_") and len(schema) == 40
            with admin.begin() as db:
                db.execute(text('DROP SCHEMA "'+schema+'" CASCADE'))
            admin.dispose()


def headers(who="user"):
    return {"Authorization": "Bearer synthetic-"+who}


def seed_draft(Session, ids, action="CONSUME", **updates):
    if action == "ADD":
        command = {"action": action, "name": "纸巾", "quantity": "2", "unit": "包", "location": "储物柜", "purchased_at": None, "label_expiry": None}
    elif action == "PLAN_ADD":
        command = {"action": action, "name": "纸巾", "quantity": "2", "unit": "包"}
    else:
        command = {"action": action, "name": "牛奶", "batch_id": str(ids["batch"]), "expected_version": 1}
        command.update({"to_location": "书房"} if action == "MOVE" else {"quantity": "1", "unit": "盒"})
    command.update(updates)
    task_id, draft_id = uuid4(), uuid4()
    with Session.begin() as db:
        db.add(AITask(id=task_id, user_id=ids["user"], household_id=ids["home"], request_id=uuid4().hex,
            request_hash="fixture", original_text="合成执行夹具", household_timezone="Asia/Shanghai",
            status="needs_confirmation", revision=1,
            result_json={"status": "needs_confirmation", "draft": command}))
        db.flush()
        db.add(AIDraft(id=draft_id, task_id=task_id, user_id=ids["user"], household_id=ids["home"],
            status="pending", revision=1, command_json=command, preview_json={"quantity": "999999"}))
    return draft_id, task_id


def body(**updates):
    return {"operation_id": str(uuid4()), "draft_revision": 1, "task_revision": 1, "edits": {}, **updates}


def url(draft, suffix="commit"):
    return f"/api/v1/drafts/{draft}/{suffix}"


def post(client, draft, payload, who="user"):
    return client.post(url(draft), headers=headers(who), json=payload)


@pytest.mark.parametrize("action", ["ADD", "MOVE", "PLAN_ADD", "CONSUME"])
def test_each_action_receipt_and_exact_replay(execution_state, action):
    client, Session, ids = execution_state
    draft, _ = seed_draft(Session, ids, action)
    request = body()
    result = post(client, draft, request)
    assert result.status_code == 200, result.text
    receipt = result.json()
    assert receipt["status"] == "committed" and receipt["action"] == action
    assert post(client, draft, request).json() == receipt
    assert client.get("/api/v1/operations/"+request["operation_id"], headers=headers()).json() == receipt
    assert client.get(url(draft, "execution"), headers=headers()).json()["receipt"] == receipt
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(DraftOperation)) == 1
        assert db.scalar(select(func.count()).select_from(BusinessEvent)) == 1
        assert db.get(DraftDecision, draft).status == "committed"
        stock = db.get(InventoryItem, ids["batch"])
        if action == "CONSUME":
            assert stock.quantity == Decimal(4) and stock.version == 2
            event = db.scalar(select(BusinessEvent))
            assert event.event_type == "Consumed" and event.quantity == 1
            assert Decimal(event.before_json["quantity"])-Decimal(event.after_json["quantity"]) == event.quantity
        elif action == "MOVE":
            assert stock.quantity == 5 and stock.storage_location == "书房" and stock.version == 2
            event = db.scalar(select(BusinessEvent))
            assert event.quantity is None
            changed = {k for k in event.before_json if event.before_json[k] != event.after_json[k]}
            assert changed <= {"storage_location", "version", "history_json"}
        elif action == "ADD":
            assert db.scalar(select(func.count()).select_from(InventoryItem)) == 2
        else:
            shopping = db.scalar(select(ShoppingListItem))
            assert shopping.quantity == 2 and not shopping.is_checked
            assert stock.quantity == 5 and stock.version == 1
    # The legacy AI read remains prospective; execution has a separate authority.
    assert client.get(f"/api/v1/drafts/{draft}", headers=headers()).json()["inventory_written"] is False


def test_cancel_is_terminal_and_idempotent(execution_state):
    client, Session, ids = execution_state
    draft, _ = seed_draft(Session, ids)
    cancel = {"draft_revision": 1, "task_revision": 1}
    assert client.post(url(draft, "cancel"), headers=headers(), json=cancel).json()["status"] == "cancelled"
    assert client.post(url(draft, "cancel"), headers=headers(), json=cancel).status_code == 200
    assert post(client, draft, body()).status_code == 409
    with Session() as db:
        assert db.get(InventoryItem, ids["batch"]).quantity == 5
        assert db.scalar(select(func.count()).select_from(DraftOperation)) == 0


@pytest.mark.parametrize("stock_unit,input_unit,amount,remaining,delta", [
    ("吨", "kg", "500", "4.5", "0.5"),
    ("台", "台", "1", "4", "1"),
])
def test_extended_units_have_exact_consumption_events(execution_state, stock_unit, input_unit, amount, remaining, delta):
    client, Session, ids = execution_state
    with Session.begin() as db:
        db.get(InventoryItem, ids["batch"]).unit = stock_unit
    draft, _ = seed_draft(Session, ids, unit=stock_unit)
    request = body(edits={"quantity": amount, "unit": input_unit})
    result = post(client, draft, request)
    assert result.status_code == 200, result.text
    assert post(client, draft, request).json() == result.json()
    with Session() as db:
        item = db.get(InventoryItem, ids["batch"])
        event = db.scalar(select(BusinessEvent))
        assert item.quantity == Decimal(remaining) and item.unit == stock_unit and item.version == 2
        assert event.quantity == Decimal(delta) and event.unit == stock_unit
        assert db.scalar(select(func.count()).select_from(BusinessEvent)) == 1


def test_machine_unit_does_not_alias_individual_items(execution_state):
    client, Session, ids = execution_state
    with Session.begin() as db:
        db.get(InventoryItem, ids["batch"]).unit = "台"
    draft, _ = seed_draft(Session, ids, unit="台")
    assert post(client, draft, body(edits={"unit":"个"})).status_code == 422
    with Session() as db:
        assert db.get(InventoryItem, ids["batch"]).quantity == 5
        assert db.scalar(select(func.count()).select_from(BusinessEvent)) == 0


def test_tonne_conversion_rejects_subprecision_without_stock_or_event_write(execution_state):
    client, Session, ids = execution_state
    with Session.begin() as db:
        db.get(InventoryItem, ids["batch"]).unit = "吨"
    draft, _ = seed_draft(Session, ids, unit="吨")
    result = post(client, draft, body(edits={"quantity":"0.000001", "unit":"kg"}))
    assert result.status_code == 422 and result.json()["detail"]["code"] == "CONVERTED_QUANTITY_INVALID"
    with Session() as db:
        assert db.get(InventoryItem, ids["batch"]).quantity == 5
        assert db.scalar(select(func.count()).select_from(BusinessEvent)) == 0


def test_auth_and_ownership_for_every_new_route(execution_state):
    client, Session, ids = execution_state
    draft, _ = seed_draft(Session, ids)
    request = body()
    for suffix, payload in (("commit", request), ("cancel", {"draft_revision": 1, "task_revision": 1})):
        assert client.post(url(draft, suffix), json=payload).status_code == 401
        assert client.post(url(draft, suffix), headers=headers("outsider"), json=payload).status_code == 404
    assert post(client, draft, request).status_code == 200
    for path in (url(draft,"execution"), "/api/v1/operations/"+request["operation_id"],
                 f"/api/v1/households/{ids['home']}/consumption-events"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers=headers("outsider")).status_code == 404
    with Session.begin() as db:
        db.delete(db.get(HouseholdMember, (ids["home"], ids["user"])))
    assert post(client, draft, request).status_code == 404


@pytest.mark.parametrize("change", [{"action":"ADD"}, {"batch_id":str(uuid4())}, {"expected_version":2},
    {"household_id":str(uuid4())}, {"preview":{}}, {"source_task_id":str(uuid4())}, {"name":"伪造目标"}])
def test_protected_edits_rejected(execution_state, change):
    client, Session, ids = execution_state
    draft, _ = seed_draft(Session, ids)
    assert post(client, draft, body(edits=change)).status_code == 422


@pytest.mark.parametrize("field", ["draft_revision", "task_revision"])
def test_revision_conflict(execution_state, field):
    client, Session, ids = execution_state
    draft, _ = seed_draft(Session, ids)
    assert post(client, draft, body(**{field:2})).status_code == 409
    assert post(client, draft, body(**{field:True})).status_code == 422


def test_stale_stock_and_other_household_target(execution_state):
    client, Session, ids = execution_state
    draft, _ = seed_draft(Session, ids)
    with Session.begin() as db:
        db.get(InventoryItem, ids["batch"]).version = 2
    assert post(client, draft, body()).json()["detail"]["code"] == "INVENTORY_VERSION_CONFLICT"
    draft, _ = seed_draft(Session, ids)
    with Session.begin() as db:
        db.get(InventoryItem, ids["batch"]).household_id = ids["foreign_home"]
    assert post(client, draft, body()).status_code == 404


@pytest.mark.parametrize("action,edits", [("ADD",{"location":""}), ("ADD",{"location":"x"*101}),
    ("ADD",{"quantity":"0.0000001"}), ("PLAN_ADD",{"quantity":"1.0001"}),
    ("PLAN_ADD",{"unit":"kg"}),
    ("CONSUME",{"quantity":"6"}), ("CONSUME",{"quantity":"0"}),
    ("CONSUME",{"unit":"kg"}), ("CONSUME",{"quantity":True})])
def test_business_validation_without_rounding(execution_state, action, edits):
    client, Session, ids = execution_state
    draft, _ = seed_draft(Session, ids, action)
    assert post(client, draft, body(edits=edits)).status_code == 422
    with Session() as db:
        assert db.get(InventoryItem, ids["batch"]).quantity == 5
        assert db.scalar(select(func.count()).select_from(DraftOperation)) == 0


def test_convert_compatible_unit_and_finished_state(execution_state):
    client, Session, ids = execution_state
    with Session.begin() as db:
        row = db.get(InventoryItem, ids["batch"]);row.unit="L";row.quantity=Decimal("0.5")
    draft, _ = seed_draft(Session, ids, quantity="500", unit="ml")
    result = post(client, draft, body())
    assert result.status_code == 200, result.text
    with Session() as db:
        assert db.get(InventoryItem, ids["batch"]).status == "FINISHED"
        event = db.scalar(select(BusinessEvent));assert event.quantity == Decimal("0.5") and event.unit == "L"


def test_retry_changed_body_or_different_key_never_reexecutes(execution_state):
    client, Session, ids = execution_state
    draft, _ = seed_draft(Session, ids)
    request=body();assert post(client,draft,request).status_code == 200
    assert post(client,draft,{**request,"edits":{"quantity":"2"}}).status_code == 409
    assert post(client,draft,body()).status_code == 409
    other,_ = seed_draft(Session,ids)
    assert post(client,other,request).status_code == 409
    with Session() as db:assert db.get(InventoryItem,ids["batch"]).quantity == 4


@pytest.mark.parametrize("action", ["OPEN", "DISCARD"])
def test_unsupported_actions_fail_closed(execution_state, action):
    client,Session,ids=execution_state
    draft,_=seed_draft(Session,ids,action)
    assert client.get(url(draft,"execution"),headers=headers()).json()["status"] == "unavailable"
    assert post(client,draft,body()).json()["detail"]["code"] == "ACTION_NOT_EXECUTABLE"


def test_planning_basis_cannot_be_removed_or_executed(execution_state):
    client,Session,ids=execution_state
    draft,task=seed_draft(Session,ids,"PLAN_ADD")
    with Session.begin() as db:
        row=db.get(AITask,task);row.result_json={**row.result_json,"planning_basis":{"snapshot_id":"old"}}
    assert post(client,draft,body()).json()["detail"]["code"] == "PLANNING_REVALIDATION_UNAVAILABLE"
    assert post(client,draft,body(edits={"planning_basis":None})).status_code == 422


def test_expired_or_inconsistent_source_fails(execution_state):
    client,Session,ids=execution_state
    draft,task=seed_draft(Session,ids)
    with Session.begin() as db:db.get(AITask,task).expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
    assert post(client,draft,body()).json()["detail"]["code"] == "DRAFT_EXPIRED"
    draft,task=seed_draft(Session,ids)
    with Session.begin() as db:db.get(AIDraft,draft).command_json={"action":"ADD"}
    assert post(client,draft,body()).json()["detail"]["code"] == "DRAFT_SOURCE_CHANGED"


def test_entire_transaction_rolls_back_on_event_failure(execution_state, monkeypatch):
    client,Session,ids=execution_state
    draft,_=seed_draft(Session,ids);request=body()
    def broken(*args,**kwargs):raise RuntimeError("synthetic event persistence failure")
    with monkeypatch.context() as m:
        m.setattr(draft_execution,"persist_event",broken)
        assert post(client,draft,request).status_code == 500
    with Session() as db:
        assert db.get(InventoryItem,ids["batch"]).quantity == 5
        assert db.get(InventoryItem,ids["batch"]).version == 1
        assert db.scalar(select(func.count()).select_from(DraftOperation)) == 0
        assert db.get(DraftDecision,draft) is None
    assert post(client,draft,request).status_code == 200


def test_internal_receipt_auth_and_semantic_event_query(execution_state, monkeypatch):
    client,Session,ids=execution_state
    monkeypatch.setenv("BACKEND_TOOL_TOKEN","synthetic-tool-token")
    draft,_=seed_draft(Session,ids);request=body();receipt=post(client,draft,request).json()
    path="/internal/v1/operations/"+request["operation_id"]
    auth={"Authorization":"Bearer synthetic-tool-token","X-User-Id":str(ids["user"]),"X-Household-Id":str(ids["home"])}
    assert client.get(path).status_code == 401
    assert client.get(path,headers=auth).json()["data"]["event_ids"] == receipt["event_ids"]
    auth["X-User-Id"]=str(ids["outsider"]);assert client.get(path,headers=auth).status_code == 404
    page=client.get(f"/api/v1/households/{ids['home']}/consumption-events",headers=headers()).json()
    assert page["total"] == 1 and page["items"][0]["event_type"] == "Consumed"


def test_plan_delete_keeps_audit_and_plan_is_not_inventory_receipt(execution_state, monkeypatch):
    client,Session,ids=execution_state;draft,_=seed_draft(Session,ids,"PLAN_ADD");request=body()
    receipt=post(client,draft,request).json();item=receipt["result"]["shopping_item"]["id"]
    assert client.delete(f"/api/v1/households/{ids['home']}/shopping-list/items/{item}",headers=headers()).status_code == 204
    with Session() as db:
        event=db.scalar(select(BusinessEvent));assert event.after_json["id"] == item
        assert event.shopping_item_id is None


def test_reference_adapter_disabled_without_ai_call(execution_state, monkeypatch):
    client,_,ids=execution_state
    async def forbidden(*args,**kwargs):raise AssertionError("Must not call AI")
    monkeypatch.setattr(agent_gateway,"_call_ai",forbidden)
    payload={"household_id":str(ids["home"]),"text":"它在哪里","request_id":"r", "source_task_id":str(uuid4()),"source_revision":1,"batch_id":str(ids["batch"])}
    result=client.post("/api/v1/agent/reference-messages",headers=headers(),json=payload)
    assert result.status_code == 503 and result.json()["detail"]["code"] == "TRUSTED_REFERENCE_ADAPTER_UNAVAILABLE"
    assert client.get("/api/v1/agent/execution-capabilities",headers=headers()).json()["trusted_reference_messages"] is False


def test_receipt_survives_expiry_and_later_stock_changes(execution_state):
    client,Session,ids=execution_state;draft,task=seed_draft(Session,ids);request=body()
    receipt=post(client,draft,request).json()
    with Session.begin() as db:
        db.get(AITask,task).expires_at=datetime.now(timezone.utc)-timedelta(days=1)
        item=db.get(InventoryItem,ids["batch"]);item.quantity=Decimal(3);item.version=3
    assert post(client,draft,request).json() == receipt
    assert client.get("/api/v1/operations/"+request["operation_id"],headers=headers()).json() == receipt
    with Session() as db:assert db.get(InventoryItem,ids["batch"]).quantity==3


def test_database_requires_quantity_for_consumed_event(execution_state):
    from sqlalchemy.exc import IntegrityError
    client,Session,ids=execution_state;draft,_=seed_draft(Session,ids)
    assert post(client,draft,body()).status_code==200
    with pytest.raises(IntegrityError):
        with Session.begin() as db:
            db.scalar(select(BusinessEvent)).quantity=None
            db.flush()
    with Session() as db:assert db.scalar(select(BusinessEvent)).quantity==1


def test_top_level_injection_and_foreign_key_reuse(execution_state):
    client,Session,ids=execution_state;draft,_=seed_draft(Session,ids);request=body()
    assert post(client,draft,{**request,"action":"ADD"}).status_code == 422
    assert post(client,draft,request).status_code == 200
    foreign=dict(ids,user=ids["outsider"],home=ids["foreign_home"])
    other,_=seed_draft(Session,foreign,"ADD")
    assert post(client,other,request,who="outsider").status_code == 409
    with Session() as db:assert db.scalar(select(func.count()).select_from(InventoryItem))==1


def test_migration_preserves_legacy_and_refuses_audit_loss(tmp_path):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect
    engine=create_engine(f"sqlite:///{tmp_path/'migration.sqlite'}")
    root=Path(__file__).resolve().parents[1]
    cfg=Config(str(root/'alembic.ini'));cfg.set_main_option('script_location',str(root/'alembic'))
    with patch('sqlalchemy.create_engine',return_value=engine):
        command.upgrade(cfg,'20261016_0006')
    Session=sessionmaker(bind=engine,autoflush=False);ids={'user':uuid4(),'home':uuid4(),'batch':uuid4()}
    with Session.begin() as db:
        db.add(User(id=ids['user'],email='legacy@example.invalid',display_name='Legacy',password_hash='fixture'));db.flush()
        db.add(Household(id=ids['home'],name='Legacy',created_by_user_id=ids['user']))
    draft,_=seed_draft(Session,ids,'ADD')
    with patch('sqlalchemy.create_engine',return_value=engine):
        command.upgrade(cfg,'head')
        assert {'draft_operations','draft_decisions','business_events'} <= set(inspect(engine).get_table_names())
        with Session() as db:assert db.get(AIDraft,draft).command_json['action']=='ADD'
        command.downgrade(cfg,'20261016_0006')
        command.upgrade(cfg,'head')
        with Session.begin() as db:db.add(DraftDecision(draft_id=draft,draft_revision=1,task_revision=1,status='cancelled'))
        with pytest.raises(RuntimeError,match='audit data exists'):
            command.downgrade(cfg,'20261016_0006')
    with Session() as db:assert db.get(DraftDecision,draft).status=='cancelled'
    engine.dispose()


@pytest.mark.skipif(not PG, reason="Real PostgreSQL row locks required")
@pytest.mark.parametrize("kind", ["same_key", "different_keys", "different_drafts", "same_key_two_drafts", "cancel_race"])
def test_postgres_concurrent_commit(execution_state, kind):
    client,Session,ids=execution_state;draft,_=seed_draft(Session,ids);request=body()
    if kind == "same_key_two_drafts":
        draft,_=seed_draft(Session,ids,"ADD");second,_=seed_draft(Session,ids,"ADD")
        jobs=[(draft,request),(second,request)]
    elif kind == "different_drafts":
        second,_=seed_draft(Session,ids)
        jobs=[(draft,body()),(second,body())]
    else:
        jobs=[(draft,request if kind=="same_key" else body()) for _ in range(6)]
    if kind=="cancel_race":
        def invoke(n):
            if n==0:return client.post(url(draft,"cancel"),headers=headers(),json={"draft_revision":1,"task_revision":1})
            return post(client,draft,request)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(invoke,[0,1]))
        assert sorted(r.status_code for r in results)==[200,409]
    else:
        with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(lambda job:post(client,*job),jobs))
        statuses=[r.status_code for r in results]
        assert statuses.count(200)==(6 if kind=="same_key" else 1),[r.text for r in results]
        assert all(s in (200,409) for s in statuses)
        if kind=="same_key":assert all(r.json()==results[0].json() for r in results)
    with Session() as db:
        count=db.scalar(select(func.count()).select_from(DraftOperation))
        assert count<=1 and db.scalar(select(func.count()).select_from(BusinessEvent))==count
        assert db.get(InventoryItem,ids["batch"]).quantity == (5 if kind=="same_key_two_drafts" else 5-count)
        if kind=="same_key_two_drafts":assert db.scalar(select(func.count()).select_from(InventoryItem))==2
