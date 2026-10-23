"""Backend-owned V1 read DTOs, tested against the published and Agent schema.

Provenance stays outside data because V1 forbids additional properties.
"""
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from app.services.ai_inventory import UNIT_CANONICAL


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


Name = Annotated[str, Field(min_length=1, max_length=80, pattern=r"\S")]
Key = Annotated[str, Field(min_length=1, max_length=100)]
Amount = Annotated[Decimal, Field(ge=0, le=1_000_000_000, decimal_places=6)]
Positive = Annotated[Decimal, Field(gt=0, le=1_000_000_000, decimal_places=6)]
Category = Literal["food", "medicine", "household", "unknown"]


class Scope(Model):
    user_id: str
    household_id: str


class Batch(Model):
    id: Key
    household_id: str
    name: Name
    quantity: Amount
    unit: str
    location: str | None = Field(default=None, max_length=120)
    purchased_at: date | None = None
    label_expiry: date | None = None
    opened_at: date | None = None
    status: Literal["ACTIVE", "FINISHED", "REVERSED", "DISCARDED"]
    version: int = Field(ge=1)
    category: Category = "unknown"
    product_id: Key | None = None
    label_date_type: Literal["use_by", "best_before", "expiry", "unknown"] = "unknown"
    label_context_valid: bool | None = None
    storage_condition: Literal["ambient", "refrigerated", "frozen"] | None = None
    label_storage_condition: Literal["ambient", "refrigerated", "frozen"] | None = None
    is_opened: bool | None = None


class Event(Model):
    id: Key
    item_key: Key
    kind: Literal["Consumed", "Discarded", "Added", "Opened", "Moved", "Finished",
                  "Purchased", "Draft", "Reversed", "Corrected", "Adjusted"]
    quantity: Amount
    unit: str
    occurred_at: AwareDatetime
    recorded_at: AwareDatetime
    committed: bool
    related_event_id: Key | None = None


class CoverageDay(Model):
    day: date
    records_complete: bool
    stockout: bool
    unexplained_adjustment: bool = False


class Preferences(Model):
    version: int = Field(ge=1)
    minimum_stock: Amount | None = None
    coverage_days: int | None = Field(default=None, ge=1, le=365)
    lead_days: int | None = Field(default=None, ge=0, le=365)
    order_unit: str | None = None
    pack_size: Positive | None = None

    @model_validator(mode="after")
    def package(self):
        if (self.order_unit is None) != (self.pack_size is None):
            raise ValueError("Order unit and pack size must be provided together")
        return self


class StockVerification(Model):
    checked_at: AwareDatetime
    source: str = Field(min_length=1, max_length=200, pattern=r"\S")


class Item(Model):
    item_key: Key
    name: Name
    unit: str
    version: int = Field(ge=1)
    category: Category
    batches: list[Batch] = Field(max_length=1000)
    events: list[Event] = Field(max_length=20000)
    coverage: list[CoverageDay] = Field(max_length=3660)
    recording_completeness_source: str | None = None
    preferences: Preferences
    usable_quantity_verified: bool = False
    stock_verification: StockVerification | None = None


class Pending(Model):
    id: Key
    item_key: Key
    quantity: Positive
    unit: str
    status: Literal["pending", "purchased", "draft"]
    confirmed: bool
    visibility: Literal["shared"]


class PlanningSnapshot(Model):
    protocol_version: Literal["v1-planning-context-1"]
    scope: Scope
    snapshot_id: str = Field(min_length=1, max_length=200)
    as_of: AwareDatetime
    event_watermark: str = Field(min_length=1, max_length=200)
    shopping_version: int = Field(ge=1)
    items_complete: bool
    history_complete: bool
    pending_complete: bool
    next_cursor: str | None = None
    items: list[Item] = Field(max_length=1000)
    pending: list[Pending] = Field(max_length=10000)

    @model_validator(mode="after")
    def canonical_units(self):
        units = [i.unit for i in self.items]
        units += [b.unit for i in self.items for b in i.batches]
        units += [e.unit for i in self.items for e in i.events]
        units += [p.unit for p in self.pending]
        if any(u not in UNIT_CANONICAL.values() for u in units):
            raise ValueError("Unsupported planning unit")
        return self


class PlanningResponse(Model):
    data: PlanningSnapshot
    provenance: dict
