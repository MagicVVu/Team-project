"""Unit compatibility without mutating stored quantities or guessing count units."""
import asyncio
from decimal import Decimal

import pytest

from p0.domain import DomainError, convert, normalize_unit
from p0.text import fields
from p1.engines import RuleEngine
from p1.manager import Manager
from p1.schemas import Message
from eval.p1.fixtures import FixtureReader
from eval.p3.fixtures import NOW, SCOPE, FixtureReader as P7Reader
from conversation.engines import RuleEngine as P7Engine
from conversation.manager import Manager as P7Manager
from conversation.schemas import Message as P7Message
from p2.knowledge import RuleCatalog


@pytest.mark.parametrize("unit", ["吨", "台"])
def test_same_unit_preserves_decimal_and_literal_evidence(unit):
    assert normalize_unit(unit) == unit
    assert convert(Decimal("1.000001"), unit, unit) == Decimal("1.000001")
    parsed = fields("新增2"+unit+"物资放仓库", "ADD")
    assert parsed["quantity"] == 2 and parsed["unit"] == unit and parsed["name"] == "物资"


@pytest.mark.parametrize("quantity,source,target,expected", [
    ("1", "吨", "kg", "1000"), ("500", "kg", "吨", "0.5"),
    ("1", "g", "吨", "0.000001"), ("0.000001", "吨", "g", "1"),
])
def test_metric_tonnes_are_exact(quantity, source, target, expected):
    assert convert(Decimal(quantity), source, target) == Decimal(expected)


@pytest.mark.parametrize("source,target", [("台", "个"), ("台", "吨"), ("吨", "L"), ("台", "盒")])
def test_count_units_and_dimensions_cannot_be_guessed(source, target):
    with pytest.raises(DomainError):
        convert(Decimal(1), source, target)


@pytest.mark.parametrize("unit", ["吨", "台"])
def test_consume_draft_preserves_original_unit_and_never_writes(unit):
    reader = FixtureReader([{"id":"b1", "household_id":SCOPE.household_id,
        "name":"物资", "quantity":"3", "unit":unit, "location":"仓库", "version":7}])
    before = reader.snapshot()
    result = asyncio.run(Manager(RuleEngine(), reader, now=lambda:NOW).handle(
        Message(text="消耗1"+unit+"物资", request_id="unit-draft"), SCOPE))
    assert result.status == "needs_confirmation" and result.draft.unit == unit
    assert result.preview.after.quantity == 2 and result.draft.expected_version == 7
    assert reader.snapshot() == before and result.preview.prospective


def test_p7_reads_all_supported_units_as_current_facts_without_model_calls():
    reader = P7Reader()
    item = reader.data.items[0]
    original = item.batches[0]
    item.batches = [original.model_copy(update={"id":"b"+str(i), "unit":unit})
                    for i,unit in enumerate(["吨", "台", "个"])]
    before = reader.data.model_dump_json()
    result = asyncio.run(P7Manager(P7Engine(), reader, RuleCatalog.load(), now=lambda:NOW).handle(
        P7Message(text="库存有什么", request_id="all-units"), SCOPE))
    assert result.status == "answered" and {b.unit for b in result.facts} == {"吨", "台", "个"}
    assert result.runtime.model_calls == 0 and not result.inventory_writes
    assert reader.data.model_dump_json() == before


def test_tonne_conversion_rejects_subprecision_without_crashing_or_rounding():
    reader = FixtureReader([{"id":"b1", "household_id":SCOPE.household_id,
        "name":"物资", "quantity":"3", "unit":"吨", "location":"仓库", "version":7}])
    before = reader.snapshot()
    result = asyncio.run(Manager(RuleEngine(), reader, now=lambda:NOW).handle(
        Message(text="消耗0.000001kg物资", request_id="subprecision"), SCOPE))
    assert result.status == "needs_clarification" and result.error_code == "VALIDATION_ERROR" and result.draft is None
    assert result.missing_fields == ["quantity"]
    assert reader.snapshot() == before
