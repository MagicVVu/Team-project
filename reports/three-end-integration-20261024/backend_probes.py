"""Read/write ONLY disposable synthetic SQLite fixtures, never production."""
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend/server/tests"), str(ROOT / "agent")]
os.environ["DRAFT_EXECUTION_PG_TEST"] = "no"
from test_v09_execution import execution_state, seed_draft, headers, body, post
from test_backend_p3_open_discard import draft
from app.models import HouseholdMember
from app.services.planning_context import snapshot


@contextmanager
def isolated():
    with TemporaryDirectory(prefix="integration-audit-") as folder:
        generator = execution_state.__wrapped__(Path(folder))
        try:
            yield next(generator)
        finally:
            generator.close()


results = []
with isolated() as (client, Session, ids):
    draft_id, _ = seed_draft(Session, ids)
    receipt = post(client, draft_id, body()).json()
    with Session.begin() as db:
        db.add(HouseholdMember(household_id=ids["home"], user_id=ids["outsider"], role="member"))
    events = client.get(f'/api/v1/households/{ids["home"]}/consumption-events', headers=headers("outsider"))
    lookup = client.get('/api/v1/operations/' + receipt["operation_id"], headers=headers("outsider"))
    results.append(dict(case="shared_event_private_receipt", events_status=events.status_code,
        event_count=events.json()["total"], receipt_status=lookup.status_code, receipt_error=lookup.json()))
with isolated() as (client, Session, ids):
    draft_id, _ = seed_draft(Session, ids, "PLAN_ADD", name="牛奶", unit="盒")
    receipt = post(client, draft_id, body()).json()
    with Session() as db:
        context = snapshot(db, ids["user"], ids["home"])
    results.append(dict(case="manual_ai_plan_loses_inventory_source", committed=receipt["status"],
        source_inventory_item_id=receipt["result"]["shopping_item"]["source_inventory_item_id"],
        pending_complete=context["pending_complete"], planning_pending_count=len(context["pending"])))
with isolated() as (client, Session, ids):
    os.environ["MAGICVVU_DISCARD_EXECUTION"] = "true"
    draft_id, _ = draft(Session, ids, "all")
    receipt = post(client, draft_id, body()).json()
    page = client.get(f'/api/v1/households/{ids["home"]}/inventory-items', headers=headers()).json()
    results.append(dict(case="discarded_batch_not_publicly_listed", committed=receipt["status"],
        lifecycle=receipt["result"]["inventory_item"]["status"], inventory_list_total=page["total"]))

Path(__file__).with_name("backend-probes.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(results, ensure_ascii=False, indent=2))
