from datetime import datetime, timedelta, timezone
from decimal import Decimal
from p0.schemas import Scope
from p2.schemas import Batch
from p3.schemas import PlanningSnapshot

NOW = datetime(2026, 10, 15, 2, tzinfo=timezone.utc)
SCOPE = Scope(user_id="u1", household_id="h1")


def snapshot():
    today = NOW.date()
    batch = {"id":"b1", "household_id":"h1", "name":"牛奶", "quantity":"2", "unit":"盒", "version":4,
        "category":"food", "product_id":"sku-milk", "location":"冰箱", "label_expiry":"2026-11-20",
        "label_date_type":"use_by", "label_context_valid":True, "is_opened":False,
        "storage_condition":"refrigerated", "label_storage_condition":"refrigerated"}
    events = [{"id":f"e{i}", "item_key":"milk", "kind":"Consumed", "quantity":"1", "unit":"盒",
        "occurred_at":NOW-timedelta(days=i+1), "recorded_at":NOW-timedelta(days=i+1), "committed":True} for i in range(7)]
    return PlanningSnapshot.model_validate({"protocol_version":"p3-planning-context-1", "scope":SCOPE,
        "snapshot_id":"snapshot-1", "as_of":NOW, "event_watermark":"w7", "shopping_version":3,
        "items_complete":True, "history_complete":True, "pending_complete":True,
        "items":[{"item_key":"milk", "name":"牛奶", "unit":"盒", "version":2, "category":"food",
            "batches":[batch], "events":events,
            "coverage":[{"day":today-timedelta(days=i+1), "records_complete":True, "stockout":False} for i in range(28)],
            "recording_completeness_source":"synthetic-test-only",
            "preferences":{"version":1, "minimum_stock":"3", "coverage_days":14, "lead_days":2},
            "usable_quantity_verified":True}],
        "pending":[{"id":"s1", "item_key":"milk", "quantity":"1", "unit":"盒", "status":"pending", "confirmed":True, "visibility":"shared"}]})


class FixtureReader:
    """Test-local immutable copies, no network or write API."""
    def __init__(self, data=None):
        self.data = data or snapshot()
        self.reads = 0

    async def planning_context(self, scope, **kwargs):
        self.reads += 1
        return self.data.model_copy(deep=True)

    async def search(self, scope, name):
        return [b.model_copy(deep=True) for i in self.data.items for b in i.batches if not name or name in b.name]

    async def get_batch(self, scope, batch_id):
        return next(b.model_copy(deep=True) for i in self.data.items for b in i.batches if b.id == batch_id)
