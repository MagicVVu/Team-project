"""Offline audit probes: synthetic data only, no HTTP or model requests.

Run from the repository root with .venv/Scripts/python.exe -X utf8 <this file>.
The fixed extraction outputs isolate orchestration from model quality.
"""
import asyncio
import json
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent"))
from conversation.manager import Manager
from conversation.schemas import Message, ObjectReference
from eval.p3.fixtures import NOW, SCOPE, FixtureReader, snapshot
from p2.knowledge import RuleCatalog
from p3.schemas import Parsed
from p3 import forecast, procurement
from p2.risk import RiskTool
from v1.knowledge import HumanRuleCatalog


class FixedEngine:
    def __init__(self, **parsed):
        self.parsed = Parsed(**parsed)

    async def extract(self, text):
        return self.parsed.model_copy(deep=True)


class TrackedReader(FixtureReader):
    def __init__(self):
        data = snapshot()
        second = data.items[0].model_copy(deep=True)
        second.item_key, second.name = "water", "饮用水"
        second.batches[0].id, second.batches[0].name = "b2", "饮用水"
        for e in second.events:
            e.item_key, e.id = "water", "water-" + e.id
        data.items.append(second)
        super().__init__(data)
        self.selectors = []

    async def planning_context(self, scope, **selectors):
        self.selectors.append(selectors)
        return await super().planning_context(scope, **selectors)


async def main():
    results = []
    cases = [
        ("finish", "这批已经全部用完", dict(intent="CONSUME")),
        ("forecast", "这批还能用多久？", dict(intent="QUERY_FORECAST")),
        ("consumption", "查看它最近28天的消费统计", dict(intent="QUERY_CONSUMPTION")),
        ("risk", "评估这批的风险和缺少的标签储存资料", dict(intent="QUERY_RISK")),
        ("restock", "根据记录计算这批的补货建议，只展示建议，不提交采购", dict(intent="SUGGEST_PURCHASE")),
        ("consume_control", "消耗它 1 盒", dict(intent="CONSUME", quantity="1", unit="盒")),
        ("discard_control", "把这批全部余量丢弃", dict(intent="DISCARD", discard_mode="all")),
    ]
    for label, text, parsed in cases:
        reader = TrackedReader()
        ref = ObjectReference(scope=SCOPE, source_task_id="11111111-1111-4111-8111-111111111111",
            source_revision=1, batch_id="b1", issued_at=NOW, expires_at=NOW + timedelta(minutes=15))
        manager = Manager(FixedEngine(**parsed), reader, RuleCatalog.load(), now=lambda: NOW)
        result = await manager.handle(Message(text=text, request_id="offline-" + label, reference=ref), SCOPE)
        results.append(dict(case=label, text=text, status=result.status, intent=result.intent,
            missing_fields=result.missing_fields, error_code=result.error_code,
            reference_used=result.reference_used.model_dump(mode="json") if result.reference_used else None,
            draft=result.draft.model_dump(mode="json") if result.draft else None,
            fact_batch_ids=[b.id for b in result.facts], planning_selectors=reader.selectors))
    data = snapshot()
    item = data.items[0]
    item.preferences.minimum_stock = Decimal("20")
    item.preferences.pack_size, item.preferences.order_unit = Decimal("6"), "包"
    recommendation = procurement.suggest(item, data, forecast.evaluate(item, data, "Asia/Shanghai"), [])
    results.append(dict(case="pack_units", inventory_unit=item.unit,
        recommendation=recommendation.model_dump(mode="json"),
        frontend_labels={k: f"{getattr(recommendation, k)} {recommendation.unit}" for k in
            ("current_stock", "pending_quantity", "target_stock", "suggested_quantity")}))
    catalog = HumanRuleCatalog.from_catalog(RuleCatalog.load())
    risks = [RiskTool(catalog).evaluate(b, NOW) for b in item.batches]
    result = procurement.suggest(item, data, forecast.evaluate(item, data, "Asia/Shanghai"), risks)
    results.append(dict(case="no_human_rules", active_rules=len(catalog.list_rules()),
        risk_levels=[r.level for r in risks], missing=[r.missing_information for r in risks],
        recommendation_status=result.status, reason_codes=result.reason_codes))
    target = Path(__file__).with_name("offline-probes.json")
    target.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
