"""Exact Android text through real orchestration; synthetic read-only facts."""
from datetime import timedelta
from decimal import Decimal
import pytest

from test_conversation import Reader, reference, send, resume
from test_v1 import data, reviewed_catalog, run
from conversation.engines import RuleEngine
from conversation.manager import Manager
from p0.domain import DomainError
from p3.schemas import Parsed
from eval.p3.fixtures import NOW, SCOPE

BUTTONS = [
    ("查看它最近28天的消费统计", "QUERY_CONSUMPTION"),
    ("这批还能用多久？", "QUERY_FORECAST"),
    ("评估这批的风险和缺少的标签储存资料", "QUERY_RISK"),
    ("根据记录计算这批的补货建议，只展示建议，不提交采购", "SUGGEST_PURCHASE"),
]


class Engine(RuleEngine):
    calls = 0
    parsed = None
    async def extract(self, text):
        self.calls += 1
        return self.parsed.model_copy(deep=True) if self.parsed else await super().extract(text)


def service(*, reviewed=False):
    from p2.knowledge import RuleCatalog
    reader, engine = Reader(), Engine()
    reader.data = data()
    other = reader.data.items[0].model_copy(deep=True)
    other.item_key = "other-item"
    other.batches[0].id = "b2"
    reader.data.items.append(other)
    return Manager(engine, reader, reviewed_catalog() if reviewed else RuleCatalog.load(), now=lambda: NOW), engine, reader


@pytest.mark.parametrize("text,intent", BUTTONS)
def test_exact_button_query_is_scoped_fresh_zero_model(text, intent):
    manager, engine, reader = service()
    before = reader.data.model_dump_json()
    result = send(manager, text, reference())
    assert result.status == "answered", result
    assert result.intent == intent
    assert [b.id for b in result.facts] == ["b1"]
    assert result.reference_used.batch_id == "b1" and result.original_text == text
    assert engine.calls == result.runtime.model_calls == 0
    assert reader.batch_reads >= 1 and not reader.searches
    assert not result.inventory_writes and not result.shopping_writes
    assert reader.data.model_dump_json() == before


@pytest.mark.parametrize("text,intent", BUTTONS)
def test_unbound_button_never_expands_to_household_and_resumes(text, intent):
    manager, engine, reader = service()
    result = send(manager, text)
    assert result.status == "needs_clarification", result
    assert result.intent == intent and not result.facts and not result.draft
    assert result.missing_fields == ["name"] and engine.calls == 0
    assert reader.reads == reader.batch_reads == reader.searches == 0
    # Risk may return every explicitly named batch; planning asks for selection.
    continued = resume(manager, result, name="牛奶")
    assert continued.status in {"answered", "needs_clarification"}, continued
    assert engine.calls == 0 and continued.original_text == text


@pytest.mark.parametrize("text,intent", BUTTONS)
def test_expired_and_cross_family_reference_is_not_read(text, intent):
    from p0.schemas import Scope
    manager, engine, reader = service()
    expired = reference(issued_at=NOW-timedelta(minutes=15), expires_at=NOW)
    assert send(manager, text, expired).error_code == "REFERENCE_EXPIRED"
    denied = send(manager, text, reference(scope=Scope(user_id="u1", household_id="foreign")))
    assert denied.error_code == "HOUSEHOLD_FORBIDDEN" and not denied.facts and denied.original_text == ""
    assert engine.calls == reader.batch_reads == 0


def test_pronoun_planning_with_grouped_history_fails_closed():
    manager, engine, reader = service()
    reader.data.items[0].batches.append(reader.data.items[1].batches[0])
    reader.data.items = reader.data.items[:1]
    result = send(manager, BUTTONS[0][0], reference())
    assert result.error_code == "BATCH_PLANNING_SCOPE_UNAVAILABLE" and not result.facts


def test_snapshot_version_mismatch_requires_recheck():
    manager, _, reader = service()
    original = reader.get_batch
    async def changed(scope, batch_id):
        b = await original(scope, batch_id)
        b.version += 1
        return b
    reader.get_batch = changed
    result = send(manager, BUTTONS[1][0], reference())
    assert result.error_code == "VERSION_CONFLICT" and not result.forecast


@pytest.mark.parametrize("text", ["这批已经全部用完", "它全部用完了", "这一批用完了"])
def test_finish_uses_current_batch_quantity_without_model(text):
    manager, engine, reader = service()
    reader.data.items[0].batches[0].quantity = Decimal("3.125")
    result = send(manager, text, reference())
    assert result.status == "needs_confirmation", result
    assert result.draft.quantity == Decimal("3.125") and result.draft.unit == "盒"
    assert result.draft.expected_version == 4 and result.preview.after.status == "FINISHED"
    assert result.consume_mode == "all" and result.quantity_source == "current_batch"
    assert engine.calls == 0 and reader.batch_reads >= 2


def test_finish_changed_between_reads_requires_selection():
    manager, engine, reader = service()
    original = reader.get_batch
    async def changed(scope, batch_id):
        b = await original(scope, batch_id)
        if reader.batch_reads > 1:
            b.version += 1
            b.quantity += 1
        return b
    reader.get_batch = changed
    result = send(manager, "这批已经全部用完", reference())
    assert result.error_code == "VERSION_CONFLICT" and result.draft is None
    result = resume(manager, result, batch_id="b1")
    assert result.draft.quantity == 3 and result.draft.expected_version == 5
    assert result.consume_mode == "all" and engine.calls == 0


def test_pack_units_and_verified_preference_basis():
    manager, _, reader = service(reviewed=True)
    pref = reader.data.items[0].preferences
    pref.minimum_stock, pref.coverage_days, pref.lead_days = Decimal(20), None, None
    pref.pack_size, pref.order_unit = Decimal(6), "包"
    result = send(manager, BUTTONS[3][0], reference())
    assert result.status == "answered", result
    rec = result.recommendations[0]
    assert rec.current_stock == 2 and rec.pending_quantity == 1 and rec.target_stock == 20
    assert rec.suggested_quantity == 3 and rec.unit == rec.order_unit == "包"
    assert rec.inventory_unit == "盒" and rec.pack_size == 6 and rec.pack_size_source == "saved_preferences"


def test_source_survives_structured_plan_supplement_without_model():
    manager, engine, reader = service()
    engine.parsed = Parsed(intent="PLAN_ADD")
    first = send(manager, "计划买它", reference())
    assert first.status == "needs_clarification", first
    result = resume(manager, first, quantity="2", unit="盒")
    assert result.status == "needs_confirmation", result
    assert result.procurement_source.batch_id == "b1" and result.procurement_source.expected_version == 4
    assert result.draft.action == "PLAN_ADD" and engine.calls == 1 and result.runtime.model_calls == 0


def test_platform_rule_gap_is_not_a_fact_write_instruction():
    manager, _, _ = service()
    result = send(manager, BUTTONS[2][0], reference())
    assert "HUMAN_RULE_REVIEW_REQUIRED" in result.data_gaps
    guidance = next(g for g in result.guidance if "applicable_reviewed_rule" in g.missing_fields)
    assert not guidance.fact_write_required and "规则负责人" in guidance.instructions[0]


@pytest.mark.parametrize("text,intent", BUTTONS)
@pytest.mark.parametrize("state", ["deleted", "FINISHED", "DISCARDED"])
def test_read_reference_cannot_reuse_deleted_or_terminal_object(text, intent, state):
    manager, engine, reader = service()
    if state == "deleted":
        reader.data.items[0].batches = []
    else:
        reader.data.items[0].batches[0].status = state
        reader.data.items[0].batches[0].quantity = Decimal(0)
    result = send(manager, text, reference())
    assert result.status == "needs_clarification" and not result.facts and not result.draft
    assert result.error_code == ("REFERENCE_NOT_FOUND" if state == "deleted" else "REFERENCE_TERMINAL")
    assert engine.calls == 0


def test_finish_name_then_batch_selection_keeps_all_semantics():
    manager, engine, _ = service()
    first = send(manager, "这批已经全部用完")
    assert first.missing_fields == ["name"]
    second = resume(manager, first, name="牛奶")
    assert second.missing_fields == ["batch_id"]
    last = resume(manager, second, batch_id="b1")
    assert last.draft.quantity == 2 and last.consume_mode == "all" and engine.calls == 0


def test_nonliteral_read_extracts_once_without_rewriting_original_text():
    manager, engine, _ = service()
    engine.parsed = Parsed(intent="QUERY_CONSUMPTION", window_days=14)
    text = "查一下它最近两周的消耗情况"
    result = send(manager, text, reference())
    assert result.status == "answered" and result.original_text == text
    assert result.reference_used.batch_id == "b1" and engine.calls == result.runtime.model_calls == 1


@pytest.mark.parametrize("parsed", [Parsed(intent="QUERY_CONSUMPTION", window_days=14),
    Parsed(intent="SUGGEST_PURCHASE", draft_mode=True)])
def test_model_cannot_invent_query_window_or_draft_request(parsed):
    manager, engine, _ = service()
    engine.parsed = parsed
    result = send(manager, "查一下它的记录", reference())
    assert result.error_code == "INVALID_MODEL_OUTPUT" and result.draft is None and engine.calls == 1


def test_source_version_change_preserves_supplement_but_requires_reselection():
    manager, engine, reader = service()
    engine.parsed = Parsed(intent="PLAN_ADD")
    first = send(manager, "计划买它", reference())
    reader.data.items[0].batches[0].version += 1
    result = resume(manager, first, quantity="2", unit="盒")
    assert result.error_code == "VERSION_CONFLICT" and result.missing_fields == ["batch_id"]
    last = resume(manager, result, batch_id="b1")
    assert last.draft.quantity == 2 and last.procurement_source.expected_version == 5 and engine.calls == 1


def test_source_finishes_during_supplement_does_not_loop_or_create_plan():
    manager, engine, reader = service()
    engine.parsed = Parsed(intent="PLAN_ADD")
    first = send(manager, "计划买它", reference())
    reader.data.items[0].batches[0].status = "FINISHED"
    reader.data.items[0].batches[0].quantity = Decimal(0)
    last = resume(manager, first, quantity="2", unit="盒")
    assert last.status == "answered" and not last.draft and last.clarification is None
    assert last.error_code == "BATCH_TERMINAL" and engine.calls == 1


def test_exported_local_contracts_match_factory_and_models(monkeypatch):
    from eval.session_memory.compatibility import assert_legacy_schema
    import json
    from pathlib import Path
    from conversation.app import create_app
    from conversation.schemas import AgentResult, ProcurementSource, Recommendation
    from review.rules import Approval
    monkeypatch.setenv("AI_SERVICE_TOKEN", "local-contract-not-a-credential")
    monkeypatch.setenv("P3_ENGINE", "rules")
    root = Path(__file__).resolve().parents[2]/"docs/versions/V1-P8.1/contracts"
    api = json.loads((root/"ai-openapi.json").read_text(encoding="utf-8"))
    assert api.pop("x-deployment-status") == "local_source_contract"
    current = create_app(reader=object()).openapi()
    # P8.1 is a frozen release artifact. Additive session endpoints get a new
    # contract export, while every published legacy path/schema must stay exact.
    assert api["info"] == current["info"]
    for path, value in api["paths"].items():
        assert current["paths"][path] == value
    for name, value in api["components"]["schemas"].items():
        assert_legacy_schema(value, current["components"]["schemas"][name])
    for name, model in [("agent-result", AgentResult), ("procurement-source", ProcurementSource),
                        ("recommendation", Recommendation), ("rule-approval", Approval)]:
        assert_legacy_schema(json.loads((root/(name+".schema.json")).read_text(encoding="utf-8")), model.model_json_schema())


@pytest.mark.parametrize("kind", ["planning", "risk"])
@pytest.mark.parametrize("failure", ["timeout", "tool"])
def test_read_failure_retains_original_query_fields_without_retry(kind, failure):
    import asyncio
    manager, engine, reader = service()
    manager.timeout_seconds = .02
    async def fail(*args, **kwargs):
        if failure == "timeout": await asyncio.sleep(1)
        raise DomainError("TOOL_UNAVAILABLE", "合成读取失败", 503)
    if kind == "planning":
        reader.planning_context = fail
        text = BUTTONS[0][0]
    else:
        original = reader.get_batch
        async def risk_read(scope, batch_id):
            if reader.batch_reads: return await fail()
            return await original(scope, batch_id)
        reader.get_batch = risk_read
        text = BUTTONS[2][0]
    ref = reference(expires_at=NOW+timedelta(minutes=2))
    result = send(manager, text, ref)
    assert result.status == "error" and result.original_text == text and result.clarification is not None
    assert result.clarification.original_text == text
    assert result.clarification.expires_at <= ref.expires_at
    if kind == "planning": assert result.clarification.parsed.window_days == 28
    assert result.error_code == ("AGENT_TIMEOUT" if failure == "timeout" else "TOOL_UNAVAILABLE")
    assert not result.draft and engine.calls == 0


@pytest.mark.parametrize("gap", ["history", "coverage", "pending", "preferences", "verification"])
def test_missing_data_never_manufactures_forecast_or_purchase(gap):
    manager, _, reader = service(reviewed=True)
    item = reader.data.items[0]
    if gap == "history": reader.data.history_complete = False
    if gap == "coverage": item.coverage = []
    if gap == "pending": reader.data.pending_complete = False
    if gap == "preferences":
        item.preferences.minimum_stock = item.preferences.coverage_days = item.preferences.lead_days = None
    if gap == "verification": item.stock_verification = None
    result = send(manager, BUTTONS[3][0], reference())
    if gap in {"history", "coverage"}:
        assert result.forecast[0].reference_date is None
    else:
        assert result.recommendations[0].suggested_quantity is None
    assert result.facts[0].quantity == 2 and not result.draft
