"""P4 defects use the original frozen cases and independent inventory evidence."""
import asyncio
import copy
import importlib

import pytest
from fastapi.testclient import TestClient

from eval.p4.verify import SUITE, load_cases, prior_issues, resolution
from p0.engines import RuleEngine as P0Engine
from p0.manager import Manager as P0Manager
from p0.mock import MockBackend
from p0.schemas import Message as P0Message, Parsed as P0Parsed, Scope
from p1.engines import RuleEngine as P1Engine
from p1.manager import Manager as P1Manager
from p1.schemas import Message, Parsed
from eval.p1.fixtures import FixtureReader

SCOPE = Scope(user_id="u1", household_id="h1")
CASES = {case["id"]: case for case in load_cases()}
REPORTED = [(target, case_id) for (target, case_id), row in prior_issues().items()
            if row["classification"] == "程序问题"]
ADAPTERS = {"p0-regression": "local_p0", "p1-regression": "local_p1",
            "android-regression": "android_gateway"}


def seeded_reader():
    return FixtureReader([b.model_dump(mode="json") for b in MockBackend().state["batches"].values()])


@pytest.mark.parametrize("target,case_id", REPORTED, ids=[f"{t}-{c}" for t, c in REPORTED])
def test_every_reported_program_failure(target, case_id, monkeypatch):
    monkeypatch.syspath_prepend(str(SUITE))
    monkeypatch.setenv("APP_AI_ENGINE", "rules")
    monkeypatch.setenv("APP_API_TOKEN", "local-development")
    from run import score
    adapter = importlib.import_module("adapters." + ADAPTERS[target])
    case = CASES[case_id]
    observed = adapter.evaluate(case, {"engine": "rules"})
    errors = score(case, observed)
    assert resolution(target, case_id, observed, errors) != "unresolved", errors


@pytest.mark.parametrize("version", ["p0", "p1"])
@pytest.mark.parametrize("text", ["买了两盒牛奶和五个鸡蛋", "买了2盒牛奶，又喝了1盒",
                                 "买了2盒牛奶和 鸡蛋", "买了2盒牛奶，鸡蛋"])
def test_multiple_items_and_actions_remain_rejected(version, text):
    reader = MockBackend() if version == "p0" else seeded_reader()
    before = copy.deepcopy(reader.state) if version == "p0" else reader.snapshot()
    cls, engine, message = (P0Manager, P0Engine, P0Message) if version == "p0" else (P1Manager, P1Engine, Message)
    result = asyncio.run(cls(engine(), reader).handle(message(text=text, request_id="multi"), SCOPE))
    assert result.status == "unsupported" and result.draft is None
    assert (reader.state if version == "p0" else reader.snapshot()) == before


@pytest.mark.parametrize("version", ["p0", "p1"])
def test_a_literal_product_qualifier_is_not_a_consumption_verb(version):
    cls, engine, message, reader = ((P0Manager, P0Engine, P0Message, MockBackend()) if version == "p0" else
                                    (P1Manager, P1Engine, Message, seeded_reader()))
    result = asyncio.run(cls(engine(), reader).handle(message(
        text="买了2盒低脂减糖牛奶", request_id="qualifier"), SCOPE))
    assert result.status == "needs_confirmation"
    assert result.draft.name == "低脂减糖牛奶" and result.draft.quantity == 2


@pytest.mark.parametrize("version", ["p0", "p1"])
@pytest.mark.parametrize("model_name", [None, "凭空物品"])
def test_model_name_loss_cannot_expand_a_specific_query(version, model_name):
    schema = P0Parsed if version == "p0" else Parsed
    class Model:
        async def extract(self, text):
            return schema(intent="QUERY_INVENTORY", name=model_name)
    reader = MockBackend() if version == "p0" else seeded_reader()
    cls, message = (P0Manager, P0Message) if version == "p0" else (P1Manager, Message)
    result = asyncio.run(cls(Model(), reader).handle(message(text="查果汁库存", request_id="query"), SCOPE))
    assert result.status == "needs_clarification"
    assert "name" in result.missing_fields and not result.facts and result.draft is None


@pytest.mark.parametrize("version", ["p0", "p1"])
def test_model_cannot_drop_a_user_supplied_date(version):
    schema = P0Parsed if version == "p0" else Parsed
    class Model:
        async def extract(self, text):
            return schema(intent="ADD", name="牛奶", quantity="2", unit="盒")
    cls, message, reader = ((P0Manager, P0Message, MockBackend()) if version == "p0" else
                            (P1Manager, Message, seeded_reader()))
    result = asyncio.run(cls(Model(), reader).handle(message(
        text="买了2盒牛奶，购入日期2026-10-08", request_id="date"), SCOPE))
    assert result.status == "needs_clarification" and "purchased_at" in result.missing_fields
    assert result.draft is None


@pytest.mark.parametrize("version", ["p0", "p1"])
def test_vague_quantity_cannot_become_one_even_if_model_proposes_it(version):
    schema = P0Parsed if version == "p0" else Parsed
    class Model:
        async def extract(self, text):
            return schema(intent="CONSUME", name="创可贴", quantity="1", unit="片")
    cls, message, reader = ((P0Manager, P0Message, MockBackend()) if version == "p0" else
                            (P1Manager, Message, seeded_reader()))
    result = asyncio.run(cls(Model(), reader).handle(message(
        text="用了些创可贴，大概一片", request_id="vague"), SCOPE))
    assert result.status == "needs_clarification" and "quantity" in result.missing_fields
    assert result.draft is None


def test_vague_discard_keeps_the_actual_item_and_its_candidate():
    result = asyncio.run(P1Manager(P1Engine(), seeded_reader()).handle(
        Message(text="丢弃一些创可贴", request_id="vague-discard"), SCOPE))
    assert result.status == "needs_clarification" and result.draft is None
    assert {"quantity", "unit"} <= set(result.missing_fields)
    assert [b.id for b in result.candidates] == ["bandage-1"]


@pytest.mark.parametrize("version", ["p0", "p1"])
def test_overlong_literal_name_returns_clarification_without_a_server_error(version):
    cls, engine, message, reader = ((P0Manager, P0Engine, P0Message, MockBackend()) if version == "p0" else
                                    (P1Manager, P1Engine, Message, seeded_reader()))
    result = asyncio.run(cls(engine(), reader).handle(message(
        text="买了2盒" + "某" * 81, request_id="long-name"), SCOPE))
    assert result.status == "needs_clarification" and "name" in result.missing_fields
    assert result.draft is None


@pytest.mark.parametrize("version", ["p0", "p1"])
def test_date_digits_cannot_ground_a_manufactured_quantity(version):
    schema = P0Parsed if version == "p0" else Parsed
    class Model:
        async def extract(self, text):
            return schema(intent="ADD", name="牛奶", quantity="2026", unit="盒", purchased_at="2026-10-08")
    cls, message, reader = ((P0Manager, P0Message, MockBackend()) if version == "p0" else
                            (P1Manager, Message, seeded_reader()))
    result = asyncio.run(cls(Model(), reader).handle(message(
        text="2026-10-08买了牛奶，单位盒", request_id="date-number"), SCOPE))
    assert result.status == "needs_clarification" and "quantity" in result.missing_fields
    assert result.draft is None


@pytest.mark.parametrize("text", ["昨天买了2盒牛奶", "上周买了2盒牛奶", "买了2盒牛奶，购入日期2026-02-30"])
def test_add_date_clarification_can_resume_with_an_absolute_date(text):
    from p1.schemas import Answers, ClarificationRequest
    reader = seeded_reader()
    before = reader.snapshot()
    manager = P1Manager(P1Engine(), reader)
    first = asyncio.run(manager.handle(Message(text=text, request_id="resume"), SCOPE))
    assert first.status == "needs_clarification" and "purchased_at" in first.missing_fields
    result = asyncio.run(manager.clarify(ClarificationRequest(context=first.clarification,
        revision=1, answers=Answers(purchased_at="2026-10-08")), SCOPE))
    assert result.status == "needs_confirmation", result.model_dump()
    assert result.draft.purchased_at.isoformat() == "2026-10-08"
    assert result.draft.quantity == 2 and result.draft.name == "牛奶"
    assert reader.snapshot() == before


@pytest.mark.parametrize("version", ["p2", "p3"])
@pytest.mark.parametrize("text", ["查果汁库存", "买了二十一个鸡蛋", "采购清单加3包饼干"])
def test_later_versions_inherit_the_base_fixes(version, text):
    from p2.knowledge import RuleCatalog
    if version == "p2":
        from eval.p2.fixtures import FixtureReader as Reader
        from p2.engines import RuleEngine
        from p2.manager import Manager
        from p2.schemas import RiskMessage as LaterMessage
        reader = Reader([b.model_dump(mode="json") for b in MockBackend().state["batches"].values()])
    else:
        from eval.p3.fixtures import FixtureReader as Reader
        from p3.engines import RuleEngine
        from p3.manager import Manager
        from p3.schemas import PlanningMessage as LaterMessage
        reader = Reader()
    result = asyncio.run(Manager(RuleEngine(), reader, RuleCatalog.load()).handle(
        LaterMessage(text=text, request_id="inherit"), SCOPE))
    if text == "查果汁库存":
        assert result.status == "answered" and not result.facts
    else:
        assert result.status == "needs_confirmation", result.model_dump()
        assert result.draft.name == ("鸡蛋" if "鸡蛋" in text else "饼干")
        assert result.draft.quantity == (21 if "鸡蛋" in text else 3)


def test_gateway_preserves_brand_and_validation_context(monkeypatch):
    from backend.app import create_app
    monkeypatch.setenv("APP_AI_ENGINE", "rules")
    monkeypatch.setenv("APP_API_TOKEN", "local-development")
    body = {"inventory_revision": 4, "items": [
        {"id": "m1", "name": "牛奶", "quantity": "2", "unit": "盒"}]}
    before = copy.deepcopy(body)
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/agent/messages", headers={"Authorization": "Bearer local-development"},
            json={**body, "text": "买了2盒和润牛奶", "request_id": "brand"})
        assert response.json()["data"]["draft"]["name"] == "和润牛奶"
        result = client.post("/api/v1/agent/messages", headers={"Authorization": "Bearer local-development"},
            json={**body, "text": "采购清单加3包饼干", "request_id": "plan"}).json()["data"]
        assert result["intent"] == "PLAN_ADD" and result["error_code"] == "PLAN_ITEM_REQUIRED"
        assert result["draft"] is None and result["trace_id"] and result["original_text"] == "采购清单加3包饼干"
    assert body == before
