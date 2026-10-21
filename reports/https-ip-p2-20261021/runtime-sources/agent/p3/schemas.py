from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator
from p0.schemas import Model, Scope
from p1.schemas import (Answers as P1Answers, ClarificationContext as P1Context,
                        Message, Name, Quantity, Unit)
from p2.schemas import (AgentResult as P2Result, Batch, Parsed as P2Parsed,
                        RiskMessage, RiskSelectionContext, RiskResult)

POLICY_VERSION = "p3-policy-1"
Key = str


class Intent(StrEnum):
    ADD = "ADD"
    CONSUME = "CONSUME"
    QUERY_INVENTORY = "QUERY_INVENTORY"
    QUERY_LOCATION = "QUERY_LOCATION"
    PLAN_ADD = "PLAN_ADD"
    OPEN = "OPEN"
    MOVE = "MOVE"
    DISCARD = "DISCARD"
    QUERY_RISK = "QUERY_RISK"
    QUERY_CONSUMPTION = "QUERY_CONSUMPTION"
    QUERY_FORECAST = "QUERY_FORECAST"
    SUGGEST_PURCHASE = "SUGGEST_PURCHASE"
    UNSUPPORTED = "UNSUPPORTED"


class Parsed(P2Parsed):
    intent: Intent
    window_days: int = Field(default=28, ge=1, le=28)
    draft_mode: bool = False


class Event(Model):
    id: str = Field(min_length=1, max_length=100)
    item_key: str = Field(min_length=1, max_length=100)
    kind: Literal["Consumed", "Discarded", "Added", "Opened", "Moved", "Finished",
                  "Purchased", "Draft", "Reversed", "Corrected", "Adjusted"]
    quantity: Decimal = Field(default=Decimal(0), ge=0, le=1_000_000_000)
    unit: Unit
    occurred_at: AwareDatetime
    recorded_at: AwareDatetime
    committed: bool
    related_event_id: str | None = Field(default=None, min_length=1, max_length=100)


class CoverageDay(Model):
    day: date
    records_complete: bool
    stockout: bool
    unexplained_adjustment: bool = False


class Preferences(Model):
    version: int = Field(ge=1)
    minimum_stock: Decimal | None = Field(default=None, ge=0, le=1_000_000_000)
    coverage_days: int | None = Field(default=None, ge=1, le=365)
    lead_days: int | None = Field(default=None, ge=0, le=365)
    # Explicit quantity of the item's unit per one order_unit.
    order_unit: Unit | None = None
    pack_size: Quantity | None = None

    @model_validator(mode="after")
    def package(self):
        if (self.order_unit is None) != (self.pack_size is None):
            raise ValueError("采购包装单位和容量必须同时提供")
        return self


class Pending(Model):
    id: str = Field(min_length=1, max_length=100)
    item_key: str = Field(min_length=1, max_length=100)
    quantity: Quantity
    unit: Unit
    status: Literal["pending", "purchased", "draft"]
    confirmed: bool
    visibility: Literal["shared"]


class PlanningItem(Model):
    item_key: str = Field(min_length=1, max_length=100)
    name: Name
    unit: Unit
    version: int = Field(ge=1)
    category: Literal["food", "medicine", "household", "unknown"]
    batches: list[Batch] = Field(max_length=1000)
    events: list[Event] = Field(max_length=20000)
    coverage: list[CoverageDay] = Field(max_length=3660)
    recording_completeness_source: str | None = Field(default=None, min_length=1, max_length=200)
    preferences: Preferences
    # Business verification of usable quantity; AI never subtracts risky stock.
    usable_quantity_verified: bool = False


class PlanningSnapshot(Model):
    protocol_version: Literal["p3-planning-context-1"]
    scope: Scope
    snapshot_id: str = Field(min_length=1, max_length=200)
    as_of: AwareDatetime
    event_watermark: str = Field(min_length=1, max_length=200)
    shopping_version: int = Field(ge=1)
    items_complete: bool
    history_complete: bool
    pending_complete: bool
    next_cursor: str | None = None
    items: list[PlanningItem] = Field(max_length=1000)
    pending: list[Pending] = Field(max_length=10000)


class Query(Model):
    name: Name | None = None
    item_key: str | None = Field(default=None, min_length=1, max_length=100)
    household_timezone: str = "Asia/Shanghai"
    window_days: int = Field(default=28, ge=1, le=28)
    mode: Literal["suggest", "draft"] = "suggest"
    _timezone = field_validator("household_timezone")(Message.timezone.__func__)

    @model_validator(mode="after")
    def selector(self):
        if self.name and self.item_key:
            raise ValueError("只接受一种商品选择条件")
        return self


class ConsumptionSummary(Model):
    item_key: str
    name: str
    unit: str
    window_start: date
    window_end_exclusive: date
    observed_days: int
    effective_quantity: Decimal
    effective_events: int
    consumption_dates: int
    status: Literal["complete", "insufficient_data", "needs_review"]
    reason_codes: list[str]
    excluded_events: int = 0
    event_ids: list[str] = Field(default_factory=list)


class Forecast(Model):
    item_key: str
    name: str
    unit: str
    status: Literal["estimated", "insufficient_data", "no_recorded_consumption", "needs_review", "current_zero"]
    current_stock: Decimal | None = None
    daily_recorded_consumption: Decimal | None = None
    remaining_days: Decimal | None = None
    reference_date: date | None = None
    summary: ConsumptionSummary
    reason_codes: list[str]
    policy_version: str = POLICY_VERSION
    conditions: str = "未来不补货，消耗水平与所选完整记录窗口接近；仅按日期粒度估计。"


class Recommendation(Model):
    item_key: str
    name: str
    status: Literal["suggested", "covered", "insufficient_data", "needs_review", "excluded"]
    source: Literal["minimum_stock", "recorded_history"] | None = None
    current_stock: Decimal | None = None
    pending_quantity: Decimal | None = None
    target_stock: Decimal | None = None
    suggested_quantity: Decimal | None = None
    unit: str
    reason_codes: list[str]


class PlanningBasis(Model):
    protocol_version: Literal["p3-planning-basis-1"] = "p3-planning-basis-1"
    item_key: str
    item_version: int
    batch_versions: dict[str, int]
    shopping_version: int
    event_watermark: str
    snapshot_id: str
    as_of: AwareDatetime
    preference_version: int
    policy_version: str = POLICY_VERSION
    calculation: Recommendation
    original_suggested_quantity: Decimal
    human_modified: Literal[False] = False
    confirmation_revalidation_required: Literal[True] = True


class Candidate(Model):
    item_key: str
    name: str
    unit: str
    version: int
    batches: list[Batch]


class SelectionParsed(Model):
    intent: Literal["QUERY_CONSUMPTION", "QUERY_FORECAST", "SUGGEST_PURCHASE"]
    name: Name | None = None
    window_days: int = Field(default=28, ge=1, le=28)
    draft_mode: bool = False


class SelectionContext(Model):
    protocol_version: Literal["p3-item-selection-1"] = "p3-item-selection-1"
    id: str
    revision: int = Field(ge=1)
    scope: Scope
    original_text: str = Field(min_length=1, max_length=1000)
    request_id: str
    trace_id: str
    household_timezone: str
    created_at: AwareDatetime
    expires_at: AwareDatetime
    parsed: SelectionParsed
    candidates: list[Candidate] = Field(default_factory=list, max_length=1000)
    snapshot_id: str | None = None
    selected_item_key: str | None = Field(default=None, min_length=1, max_length=100)
    allowed_fields: list[Literal["name", "item_key"]]
    _timezone = field_validator("household_timezone")(Message.timezone.__func__)


class Answers(P1Answers):
    item_key: str | None = Field(default=None, min_length=1, max_length=100)


class ClarificationRequest(Model):
    context: SelectionContext | RiskSelectionContext | P1Context
    revision: int = Field(ge=1)
    answers: Answers


class AgentResult(P2Result):
    intent: Intent | None = None
    clarification: SelectionContext | RiskSelectionContext | P1Context | None = None
    item_candidates: list[Candidate] = Field(default_factory=list)
    consumption_summary: list[ConsumptionSummary] = Field(default_factory=list)
    forecast: list[Forecast] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    planning_basis: PlanningBasis | None = None
    snapshot_id: str | None = None
    evaluated_at: AwareDatetime | None = None
    inventory_writes: Literal[False] = False
    shopping_writes: Literal[False] = False


class PlanningMessage(RiskMessage):
    """Text-only P3 options are parsed once; no new public gateway fields."""
