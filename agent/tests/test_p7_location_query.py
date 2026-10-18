import asyncio
from decimal import Decimal
from conversation.manager import Manager
from conversation.engines import RuleEngine
from conversation.schemas import Message
from eval.p3.fixtures import NOW, SCOPE, snapshot, FixtureReader
from p2.knowledge import RuleCatalog


def test_inventory_listing_is_not_misread_as_a_location_name():
    result = asyncio.run(Manager(RuleEngine(), FixtureReader(), RuleCatalog.load(), now=lambda: NOW).handle(
        Message(text="库存有什么", request_id="inventory-list", household_timezone="Asia/Shanghai"), SCOPE))
    assert result.status == "answered" and "牛奶" in result.reply and result.facts
    assert result.original_text == "库存有什么" and result.draft is None
    assert result.runtime.model_calls == 0 and result.inventory_writes is False


def test_literal_location_query_keeps_original_and_filters_real_batches():
    reader = FixtureReader()
    original = reader.data.items[0].batches[0]
    reader.data.items[0].batches.append(original.model_copy(update={"id": "kitchen-copy", "location": "厨房", "quantity": Decimal("7")}))
    text = f"{original.location}里还有多少{original.name}？"
    result = asyncio.run(Manager(RuleEngine(), reader, RuleCatalog.load(), now=lambda: NOW).handle(
        Message(text=text, request_id="location-query", household_timezone="Asia/Shanghai"), SCOPE))
    assert result.status == "answered" and result.original_text == text
    assert [b.id for b in result.facts] == [original.id]
    assert result.draft is None and result.runtime.model_calls == 0
    assert result.inventory_writes is False and result.shopping_writes is False


def test_unknown_location_does_not_fall_back_to_other_stock():
    reader = FixtureReader()
    result = asyncio.run(Manager(RuleEngine(), reader, RuleCatalog.load(), now=lambda: NOW).handle(
        Message(text="不存在位置里还有多少牛奶？", request_id="missing-location", household_timezone="Asia/Shanghai"), SCOPE))
    assert result.status == "answered" and result.facts == [] and result.draft is None


def test_location_query_still_rejects_foreign_tool_facts():
    reader = FixtureReader()
    reader.data.items[0].batches[0].household_id = "foreign"
    result = asyncio.run(Manager(RuleEngine(), reader, RuleCatalog.load(), now=lambda: NOW).handle(
        Message(text="冰箱里还有多少牛奶？", request_id="foreign-location", household_timezone="Asia/Shanghai"), SCOPE))
    assert result.error_code == "HOUSEHOLD_FORBIDDEN" and result.facts == [] and result.draft is None


def test_qualified_move_filters_source_without_rewriting_original():
    reader = FixtureReader()
    original = reader.data.items[0].batches[0]
    reader.data.items[0].batches.append(original.model_copy(update={"id": "other-location", "location": "厨房"}))
    text = "把冰箱的牛奶移动到储藏室。"
    result = asyncio.run(Manager(RuleEngine(), reader, RuleCatalog.load(), now=lambda: NOW).handle(
        Message(text=text, request_id="qualified-move", household_timezone="Asia/Shanghai"), SCOPE))
    assert result.status == "needs_confirmation" and result.original_text == text
    assert result.draft.batch_id == original.id and result.draft.to_location == "储藏室"


def test_multiple_batches_in_same_source_still_require_selection():
    reader = FixtureReader()
    original = reader.data.items[0].batches[0]
    reader.data.items[0].batches.append(original.model_copy(update={"id": "same-location"}))
    result = asyncio.run(Manager(RuleEngine(), reader, RuleCatalog.load(), now=lambda: NOW).handle(
        Message(text="把冰箱的牛奶移动到储藏室。", request_id="ambiguous-move", household_timezone="Asia/Shanghai"), SCOPE))
    assert result.status == "needs_clarification" and result.draft is None
    assert {b.id for b in result.candidates} == {original.id, "same-location"}


def test_qualified_move_does_not_select_another_source():
    result = asyncio.run(Manager(RuleEngine(), FixtureReader(), RuleCatalog.load(), now=lambda: NOW).handle(
        Message(text="把不存在位置的牛奶移动到储藏室。", request_id="no-source-move", household_timezone="Asia/Shanghai"), SCOPE))
    assert result.status == "needs_clarification" and result.draft is None
