"""Deployed backend envelope fixtures, never a running inventory service."""
import asyncio
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from uuid import UUID
import httpx
import pytest

from conversation.app import create_app
from conversation.manager import Manager
from conversation.engines import RuleEngine
from conversation.planning import RemoteReader, Reader, checked_snapshot
from conversation.planning_schemas import BackendSnapshot, Basis, RevalidationRequest
from conversation.schemas import AgentResult
from p0.domain import DomainError, convert
from p0.schemas import Scope
from p2.knowledge import RuleCatalog
from p3.schemas import Query
from test_v1 import data, NOW, SCOPE, reviewed_catalog

PRODUCT = "11111111-1111-4111-8111-111111111111"
BATCH = "22222222-2222-4222-8222-222222222222"
SECOND = "33333333-3333-4333-8333-333333333333"


def envelope(*, second=True, pending_unknown=False):
    value = data().model_dump(mode="json")
    item = value["items"][0]
    item["item_key"] = item["batches"][0]["id"] = BATCH
    item["batches"][0]["product_id"] = PRODUCT
    for event in item["events"]: event["item_key"] = BATCH
    value["pending"] = []
    if second:
        other = deepcopy(item)
        other["item_key"] = other["batches"][0]["id"] = SECOND
        other["batches"][0]["quantity"] = "3"
        other["events"] = []
        value["items"].append(other)
    versions = {b["id"]:b["version"] for i in value["items"] for b in i["batches"]}
    risk = {"review_status":"unknown", "version":None, "source":"ai_rule_owner_required"}
    basis = dict(protocol_version="planning-revalidation-1", snapshot_id=value["snapshot_id"],
        event_watermark=value["event_watermark"], shopping_version=value["shopping_version"],
        inventory_versions=versions, facts_versions={k:0 for k in versions}, product_versions={PRODUCT:1}, risk_rules=risk)
    sources = {}
    for i in value["items"]:
        for e in i["events"]:
            sources[e["id"]] = dict(batch_id=i["item_key"], household_id=SCOPE.household_id,
                relation_support="inventory-ledger-1", event_type=e["kind"], quantity=e["quantity"],
                unit=e["unit"], occurred_at=e["occurred_at"], recorded_at=e["recorded_at"], related_event_id=e.get("related_event_id"))
    batches = [dict(batch_id=b["id"], version=b["version"], quantity=b["quantity"], unit=b["unit"],
        base_quantity=b["quantity"], location=b["location"], label_expiry=b["label_expiry"],
        opened_at=b.get("opened_at"), status=b["status"], expired=False, expiry_known=True,
        facts_version=0, stock_verification=None, mapping_status="household_attested") for i in value["items"] for b in i["batches"]]
    product = dict(product_id=PRODUCT, item_key="product:"+PRODUCT, name="牛奶", specification="家庭核对包装",
        base_unit="盒", category="food", version=1, identity_status="household_attested", tag_source="household_attested",
        platform_rule_review_status="unknown", batches=batches, quantity_complete=True,
        total_quantity="5" if second else "2", nonexpired_active_quantity="5" if second else "2",
        usable_quantity=None, consumption_coverage_days=None, version_token="explicit-mapping-1")
    value["pending_complete"] = not pending_unknown
    value["provenance"] = dict(schema_version="backend-planning-provenance-1", pending_state="association_unknown" if pending_unknown else "none",
        pending_count=1 if pending_unknown else 0, product_aggregates_v1=[product], revalidation_basis=basis,
        events=sources, ledger_coverage="durable_since_p9_plus_existing_draft_events_no_legacy_crud_backfill", risk_rules=risk)
    return value


class Fixture:
    def __init__(self, value): self.value, self.reads = value, 0
    async def planning_context(self, scope, **kw):
        self.reads += 1
        return BackendSnapshot.model_validate(deepcopy(self.value))
    async def get_batch(self, scope, batch_id):
        return next(b for i in BackendSnapshot.model_validate(self.value).items for b in i.batches if b.id == batch_id)


def service(value=None, *, reviewed=False, timeout=10):
    reader = Fixture(value or envelope())
    class Engine(RuleEngine):
        calls = 0
        async def extract(self, text):
            self.calls += 1
            return await super().extract(text)
    engine = Engine()
    return Manager(engine, reader, reviewed_catalog() if reviewed else RuleCatalog.load(), now=lambda:NOW, timeout_seconds=timeout), engine, reader


def query(manager, intent="QUERY_FORECAST", **kw):
    return asyncio.run(manager.query(Query(**kw), SCOPE, intent))


def test_complete_explicit_product_keeps_batches_and_does_not_claim_usable_stock():
    manager, engine, reader = service()
    before = deepcopy(reader.value)
    result = query(manager, name="牛奶")
    assert result.status == "answered", result
    row = result.product_planning[0]
    assert row.product.total_quantity == 5 and row.product.nonexpired_active_quantity == 5
    assert row.product.usable_quantity is None and row.remaining_days is row.reference_date is row.suggested_quantity is None
    assert row.recorded_consumption_quantity == 7 and len(row.recorded_consumption_event_ids) == 7
    assert {b.batch_id for b in row.product.batches} == {BATCH, SECOND}
    assert row.product.platform_rule_review_status == "unknown"
    assert result.runtime.maintenance_release == "V1-P8.3"
    assert not result.inventory_writes and not result.shopping_writes and engine.calls == 0
    assert reader.reads == 1 and reader.value == before


def test_natural_planning_question_keeps_original_and_understands_once():
    from conversation.schemas import Message
    manager, engine, reader = service()
    text = "牛奶还能用多久"
    result = asyncio.run(manager.handle(Message(text=text, request_id="p83-natural"), SCOPE))
    assert result.status == "answered", result
    assert result.original_text == text and len(result.product_planning) == 1
    assert result.runtime.model_calls == engine.calls == 1 and reader.reads == 1


def test_legacy_backend_without_new_basis_cannot_claim_revalidation():
    from test_v1 import ReaderFixture
    manager = Manager(RuleEngine(), ReaderFixture(), RuleCatalog.load(), now=lambda:NOW)
    request = RevalidationRequest(original_basis=envelope()["provenance"]["revalidation_basis"], query=Query())
    result = asyncio.run(manager.review_planning(request, SCOPE))
    assert result.status == "error" and result.error_code == "PLANNING_REVALIDATION_UNAVAILABLE"
    assert result.planning_review is None and result.draft is None


def test_explicit_product_selector_never_selects_first_batch_for_a_draft():
    manager, engine, _ = service()
    result = query(manager, item_key="product:"+PRODUCT)
    assert result.status == "answered" and len(result.product_planning) == 1
    assert {b.id for b in result.facts} == {BATCH, SECOND}
    rejected = query(manager, "SUGGEST_PURCHASE", item_key="product:"+PRODUCT, mode="draft")
    assert rejected.error_code == "PROCUREMENT_SOURCE_REQUIRED" and rejected.draft is None and engine.calls == 0


def test_same_name_different_product_stays_ambiguous():
    value = envelope()
    first = value["provenance"]["product_aggregates_v1"][0]
    other = deepcopy(first)
    other_id = "44444444-4444-4444-8444-444444444444"
    other.update(product_id=other_id, item_key="product:"+other_id, batches=[first["batches"].pop()], total_quantity="3", nonexpired_active_quantity="3")
    first.update(total_quantity="2", nonexpired_active_quantity="2")
    value["items"][1]["batches"][0]["product_id"] = other_id
    value["provenance"]["product_aggregates_v1"].append(other)
    value["provenance"]["revalidation_basis"]["product_versions"][other_id] = 1
    result = query(service(value)[0], name="牛奶")
    assert result.status == "needs_clarification" and len(result.product_planning) == 2
    assert sorted(r.product.total_quantity for r in result.product_planning) == [2, 3]


def test_pending_unknown_is_not_zero_and_has_repair_guidance():
    result = query(service(envelope(pending_unknown=True))[0], "SUGGEST_PURCHASE")
    assert result.planning_context.pending_state == "association_unknown" and result.planning_context.pending_count == 1
    assert all(r.pending_quantity is None and r.suggested_quantity is None for r in result.recommendations)
    assert result.product_planning[0].pending_quantity is None and "修正来源" in result.reply
    assert result.draft is None


def test_product_selector_filters_unrelated_pending_without_losing_its_own():
    value = envelope()
    original = value["provenance"]["product_aggregates_v1"][0]
    other_id = "44444444-4444-4444-8444-444444444444"
    other = deepcopy(original)
    other.update(product_id=other_id, item_key="product:"+other_id, batches=[original["batches"].pop()], total_quantity="3", nonexpired_active_quantity="3")
    original.update(total_quantity="2", nonexpired_active_quantity="2")
    value["items"][1]["batches"][0]["product_id"] = other_id
    value["provenance"]["product_aggregates_v1"].append(other)
    value["provenance"]["revalidation_basis"]["product_versions"][other_id] = 1
    value["provenance"].update(pending_state="linked_complete", pending_count=2)
    value["pending"] = [dict(id="p1",item_key=BATCH,quantity="1",unit="盒",status="pending",confirmed=True,visibility="shared"),
                        dict(id="p2",item_key=SECOND,quantity="2",unit="盒",status="pending",confirmed=True,visibility="shared")]
    result = query(service(value)[0], item_key="product:"+PRODUCT)
    assert result.status == "answered", result
    assert result.product_planning[0].pending_quantity == 1
    assert {b.id for b in result.facts} == {BATCH}


def test_exact_product_name_does_not_require_a_batch_name_alias():
    value = envelope()
    value["provenance"]["product_aggregates_v1"][0]["name"] = "家庭早餐饮品"
    result = query(service(value)[0], name="家庭早餐饮品")
    assert result.status == "answered" and len(result.product_planning) == 1
    assert {b.id for b in result.facts} == {BATCH, SECOND}


@pytest.mark.parametrize("unit,amount,base,expected", [("kg","2","g",2500), ("L","2","ml",2500), ("盒","2","瓶",None)])
def test_compatible_conversions_and_unknown_container_capacity(unit, amount, base, expected):
    value = envelope()
    product = value["provenance"]["product_aggregates_v1"][0]
    product["base_unit"] = base
    for index, item in enumerate(value["items"]):
        b = item["batches"][0]
        b["unit"], b["quantity"] = (base, "500") if index == 0 else (unit, amount)
        item["unit"] = b["unit"]
        row = product["batches"][index]
        row["unit"], row["quantity"] = b["unit"], b["quantity"]
        row["base_quantity"] = b["quantity"] if index == 0 else "2000" if expected is not None else None
        for event in item["events"]:
            event["unit"] = base
            value["provenance"]["events"][event["id"]]["unit"] = base
    product.update(quantity_complete=expected is not None, total_quantity=expected, nonexpired_active_quantity=expected)
    result = query(service(value)[0], item_key="product:"+PRODUCT)
    assert result.status == "answered", result
    assert result.product_planning[0].product.total_quantity == expected
    if expected is None: assert "PRODUCT_UNIT_CONFLICT" in result.product_planning[0].reason_codes


@pytest.mark.parametrize("mode", ["expired", "unknown_expiry", "terminal"])
def test_expiry_and_terminal_status_remain_explicit(mode):
    value = envelope()
    product = value["provenance"]["product_aggregates_v1"][0]
    b, row = value["items"][1]["batches"][0], product["batches"][1]
    if mode == "expired":
        b["label_expiry"] = row["label_expiry"] = "2026-01-01"
        row["expired"] = True
    elif mode == "unknown_expiry":
        b["label_expiry"] = row["label_expiry"] = None
        row["expiry_known"] = False
    else: b["status"] = row["status"] = "DISCARDED"
    if mode != "unknown_expiry": product["nonexpired_active_quantity"] = "2"
    result = query(service(value)[0], item_key="product:"+PRODUCT)
    assert result.status == "answered" and result.product_planning[0].product.total_quantity == 5
    assert result.product_planning[0].product.usable_quantity is None
    assert result.product_planning[0].remaining_days is None


@pytest.mark.parametrize("kind", ["Adjusted", "Corrected", "Archived", "Counted", "Purchased", "Discarded"])
def test_inventory_ledger_non_consumption_never_replaces_or_adds_consumption(kind):
    value = envelope(second=False)
    item, p = value["items"][0], value["provenance"]
    original = item["events"][0]
    event = {**original, "id":"ledger-extra", "quantity":"100", "related_event_id":original["id"]}
    source = {**p["events"][original["id"]], "event_type":kind, "quantity":"100", "related_event_id":original["id"]}
    p["events"][event["id"]] = source
    if kind != "Counted":
        event["kind"] = "Corrected" if kind == "Corrected" else "Adjusted" if kind == "Archived" else kind
        item["events"].append(event)
    result = query(service(value)[0], "QUERY_CONSUMPTION", item_key="product:"+PRODUCT)
    assert result.product_planning[0].recorded_consumption_quantity == 7
    assert "ledger-extra" not in result.product_planning[0].recorded_consumption_event_ids
    assert "已登记消费小计 7" in result.reply and "不代表完整实际消费" in result.reply


@pytest.mark.parametrize("field", ["snapshot_id", "event_watermark", "shopping_version", "inventory_versions", "facts_versions", "product_versions", "risk_rules"])
def test_revalidation_compares_every_basis_dimension_and_rereads(field):
    manager, engine, reader = service()
    saved = Basis.model_validate(reader.value["provenance"]["revalidation_basis"])
    old = saved.model_dump()
    old[field] = {"old":1} if isinstance(old[field], dict) else old[field]+1 if isinstance(old[field], int) else "previous"
    request = RevalidationRequest(original_basis=old, query=Query(item_key="product:"+PRODUCT))
    result = asyncio.run(manager.review_planning(request, SCOPE))
    assert result.planning_review.status == "stale" and field in result.planning_review.mismatches
    assert result.planning_review.current_basis == saved
    assert result.draft is None and engine.calls == 0 and reader.reads == 1


def test_equal_basis_stays_blocked_not_authorized_to_write():
    value = envelope()
    request = RevalidationRequest(original_basis=value["provenance"]["revalidation_basis"], query=Query(item_key="product:"+PRODUCT))
    result = asyncio.run(service(value)[0].review_planning(request, SCOPE))
    assert result.planning_review.status == "blocked" and not result.planning_review.mismatches
    assert "AUTOMATIC_PLANNING_NOT_APPROVED" in result.planning_review.blockers
    assert result.draft is None and not result.inventory_writes and not result.shopping_writes


@pytest.mark.parametrize("status", ["stale", "blocked"])
def test_backend_diagnostic_reasons_survive_fresh_regeneration(status):
    value = envelope()
    basis = value["provenance"]["revalidation_basis"]
    request = RevalidationRequest(original_basis=basis, query=Query(item_key="product:"+PRODUCT), diagnostic={
        "protocol_version":"planning-revalidation-1", "status":status, "mismatches":["PROCUREMENT_SOURCE_REQUIRED"] if status == "stale" else [],
        "blockers":["CONSUMPTION_COVERAGE_UNKNOWN"], "current_basis":basis,
        "inventory_written":False, "shopping_written":False, "automatic_planning_commit":False})
    result = asyncio.run(service(value)[0].review_planning(request, SCOPE))
    assert result.planning_review.status == status
    assert "CONSUMPTION_COVERAGE_UNKNOWN" in result.planning_review.blockers
    assert result.draft is None
    if status == "stale": assert result.error_code == "PLANNING_BASIS_STALE"


def test_unknown_rule_snapshot_cannot_use_a_synthetic_reviewed_catalog_to_get_a_draft():
    result = query(service(envelope(second=False), reviewed=True)[0], "SUGGEST_PURCHASE", name="牛奶", mode="draft")
    assert result.draft is None and "HUMAN_RULE_REVIEW_REQUIRED" in result.data_gaps
    assert all(row.suggested_quantity is None for row in result.recommendations)
    assert "建议新增待购" not in result.reply


@pytest.mark.parametrize("field", ["inventory_versions", "facts_versions", "product_versions"])
def test_basis_rejects_boolean_versions(field):
    from pydantic import ValidationError
    value = envelope()["provenance"]["revalidation_basis"]
    value[field][next(iter(value[field]))] = True
    with pytest.raises(ValidationError): Basis.model_validate(value)


def test_new_basis_exact_keys_preserves_calculation_and_real_batch_source():
    value = envelope(second=False)
    value["provenance"]["risk_rules"] = value["provenance"]["revalidation_basis"]["risk_rules"] = {"review_status":"human_reviewed", "version":"fixture-only", "source":"synthetic"}
    result = query(service(value, reviewed=True)[0], "SUGGEST_PURCHASE", name="牛奶", mode="draft")
    assert result.draft is not None, result
    assert result.planning_basis.model_dump(mode="json") == value["provenance"]["revalidation_basis"]
    assert result.planning_calculation.original_suggested_quantity == result.draft.quantity
    assert result.procurement_source.batch_id == BATCH and result.procurement_source.expected_version == 4
    assert AgentResult.model_validate(result.model_dump()).planning_basis == result.planning_basis


@pytest.mark.parametrize("mutation", ["foreign", "version", "quantity", "missing_mapping", "duplicate_mapping", "event_scope", "event_quantity", "event_missing", "pending_zero"])
def test_inconsistent_trusted_envelope_fails_closed(mutation):
    value = envelope()
    p = value["provenance"]
    if mutation == "foreign": value["scope"]["household_id"] = "foreign"
    elif mutation == "version": p["revalidation_basis"]["inventory_versions"][BATCH] = 99
    elif mutation == "quantity": p["product_aggregates_v1"][0]["total_quantity"] = "999"
    elif mutation == "missing_mapping": p["product_aggregates_v1"][0]["batches"].pop()
    elif mutation == "duplicate_mapping": p["product_aggregates_v1"][0]["batches"].append(deepcopy(p["product_aggregates_v1"][0]["batches"][0]))
    elif mutation == "event_scope": next(iter(p["events"].values()))["household_id"] = "foreign"
    elif mutation == "event_quantity": next(iter(p["events"].values()))["quantity"] = "1000"
    elif mutation == "event_missing": p["events"].pop(next(iter(p["events"])))
    else: p["pending_count"] = 1
    result = query(service(value)[0], item_key="product:"+PRODUCT)
    assert result.status == "error" and not result.product_planning and result.planning_context is None
    if mutation == "foreign": assert result.error_code == "HOUSEHOLD_FORBIDDEN" and result.original_text == ""
    else: assert result.error_code == "PLANNING_CONTRACT_INVALID"


def test_batch_selector_does_not_expand_to_other_batches():
    result = query(service()[0], item_key=BATCH)
    assert not result.product_planning and {b.id for b in result.facts} == {BATCH}


def test_stale_snapshot_and_total_tool_deadline():
    value = envelope()
    value["as_of"] = (NOW-timedelta(minutes=6)).isoformat()
    assert query(service(value)[0], item_key="product:"+PRODUCT).error_code == "STALE_PLANNING_SNAPSHOT"
    manager, engine, reader = service(timeout=.02)
    async def slow(*args, **kw): await asyncio.sleep(.5)
    reader.planning_context = slow
    result = query(manager, item_key="product:"+PRODUCT)
    assert result.error_code == "AGENT_TIMEOUT" and engine.calls == 0


def test_remote_reader_preserves_envelope_one_get_and_auth(monkeypatch):
    value, requests = envelope(), []
    original = httpx.AsyncClient
    def respond(request):
        requests.append(request)
        assert request.method == "GET" and not request.url.query
        assert request.headers["X-Household-Id"] == SCOPE.household_id
        return httpx.Response(200, json={"data":{k:v for k,v in value.items() if k != "provenance"}, "provenance":value["provenance"]})
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw:original(transport=httpx.MockTransport(respond)))
    result = asyncio.run(RemoteReader("https://backend.invalid", "test-service-token").planning_context(SCOPE, name="牛奶"))
    assert isinstance(result, BackendSnapshot) and len(requests) == 1
    assert result.provenance.product_aggregates_v1[0].total_quantity == 5


def test_internal_revalidation_requires_service_auth(monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("AI_SERVICE_TOKEN", "fixture-service")
    app = create_app(reader=Fixture(envelope()), engine=RuleEngine(), now=lambda:NOW)
    with TestClient(app) as client:
        body = RevalidationRequest(original_basis=envelope()["provenance"]["revalidation_basis"], query=Query(item_key="product:"+PRODUCT)).model_dump(mode="json")
        assert client.post("/planning/revalidate", json=body).status_code == 401
        response = client.post("/planning/revalidate", json=body, headers={"Authorization":"Bearer fixture-service", "X-User-Id":SCOPE.user_id, "X-Household-Id":SCOPE.household_id})
        assert response.status_code == 200
        assert response.json()["planning_review"]["status"] == "blocked"
