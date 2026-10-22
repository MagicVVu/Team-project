"""Rate metadata never expires calls; accounting still uses configured rates."""
import asyncio
import json
from decimal import Decimal

import httpx
import pytest

from p0.budget import Budget
from p0.deepseek import DeepSeekEngine
from p0.engines import EngineError


def make_budget(tmp_path, verified_on="2000-01-01", **kwargs):
    pricing = tmp_path / "pricing.json"
    value = dict(model="deepseek-flash", input_cny_per_million=2, output_cny_per_million=8)
    if verified_on is not None:
        value["verified_on"] = verified_on
    pricing.write_text(json.dumps(value), encoding="utf-8")
    return Budget(tmp_path / "budget.sqlite", pricing, **kwargs)


@pytest.mark.parametrize("verified_on", ["2000-01-01", "2999-01-01", "metadata-only", None])
def test_date_metadata_does_not_block_accounting_or_reset_history(tmp_path, verified_on):
    budget = make_budget(tmp_path, verified_on)
    call_id, amount, pricing = budget.reserve("deepseek-flash", 100, 50)
    assert amount == Decimal("0.0006")
    budget.settle(call_id, {"prompt_tokens": 100, "completion_tokens": 20}, pricing)
    reopened = Budget(budget.path, budget.pricing_path)
    summary = reopened.summary()
    assert summary["calls"] == 1 and summary["unknown_usage_calls"] == 0
    assert Decimal(str(summary["conservative_cost_cny"])) == Decimal("0.00036")


def test_model_mismatch_still_rejects_an_inapplicable_rate(tmp_path):
    budget = make_budget(tmp_path)
    with pytest.raises(EngineError) as error:
        budget.reserve("another-model", 100, 50)
    assert error.value.code == "PRICING_NOT_VERIFIED"
    assert budget.summary()["calls"] == 0


def test_cumulative_budget_is_still_enforced_with_old_date(tmp_path):
    budget = make_budget(tmp_path, limit=Decimal("0.001"))
    budget.reserve("deepseek-flash", 100, 50)
    with pytest.raises(EngineError) as error:
        budget.reserve("deepseek-flash", 100, 50)
    assert error.value.code == "BUDGET_EXCEEDED"
    assert budget.summary()["calls"] == 1


def test_old_rate_date_reaches_provider_once_and_records_usage(tmp_path, monkeypatch):
    budget = make_budget(tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "unit-test-not-a-real-key")
    monkeypatch.setenv("LLM_MODEL", "deepseek-flash")
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={
            "model": "deepseek-flash",
            "choices": [{"message": {"content": '{"intent":"QUERY_INVENTORY","name":"牛奶"}'}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
        })

    real_client = httpx.AsyncClient
    monkeypatch.setattr("p0.deepseek.httpx.AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    parsed = asyncio.run(DeepSeekEngine(budget).extract("牛奶还有多少"))
    assert parsed.intent == "QUERY_INVENTORY" and parsed.name == "牛奶"
    assert len(calls) == 1 and budget.summary()["calls"] == 1
    assert budget.summary()["unknown_usage_calls"] == 0
