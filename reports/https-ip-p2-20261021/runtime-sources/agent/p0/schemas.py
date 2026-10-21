from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Intent(StrEnum):
    ADD = "ADD"
    CONSUME = "CONSUME"
    QUERY_INVENTORY = "QUERY_INVENTORY"
    QUERY_LOCATION = "QUERY_LOCATION"
    PLAN_ADD = "PLAN_ADD"
    UNSUPPORTED = "UNSUPPORTED"


class Parsed(Model):
    intent: Intent
    name: str | None = Field(default=None, max_length=80)
    quantity: Decimal | None = None
    unit: str | None = Field(default=None, max_length=20)
    location: str | None = Field(default=None, max_length=120)
    purchased_at: date | None = None
    label_expiry: date | None = None
    multiple_items: bool = False
    uncertainties: list[str] = Field(default_factory=list, max_length=10)


class Message(Model):
    text: str = Field(min_length=1, max_length=1000)
    request_id: str = Field(min_length=1, max_length=100)


class Scope(Model):
    user_id: str
    household_id: str


class Batch(Model):
    id: str
    household_id: str
    name: str
    quantity: Decimal = Field(ge=0)
    unit: str
    location: str | None = None
    purchased_at: date | None = None
    label_expiry: date | None = None
    status: Literal["ACTIVE", "FINISHED", "REVERSED"] = "ACTIVE"
    version: int = Field(ge=1)


class Command(Model):
    action: Literal["ADD", "CONSUME", "PLAN_ADD"]
    name: str = Field(min_length=1, max_length=80)
    quantity: Decimal = Field(gt=0)
    unit: str = Field(min_length=1, max_length=20)
    batch_id: str | None = None
    expected_version: int | None = Field(default=None, ge=1)
    location: str | None = Field(default=None, max_length=120)
    purchased_at: date | None = None
    label_expiry: date | None = None


class AgentResult(Model):
    status: Literal["needs_clarification", "needs_confirmation", "answered", "unsupported", "error"]
    intent: Intent | None = None
    reply: str
    trace_id: str
    original_text: str
    draft_id: str | None = None
    draft: Command | None = None
    candidates: list[Batch] = Field(default_factory=list)
    facts: list[Batch] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    error_code: str | None = None
    retryable: bool = False
    manual_entry: bool = False


class DraftEdit(Model):
    revision: int = Field(ge=1)
    command: Command


class Confirm(Model):
    revision: int = Field(ge=1)


class Undo(Model):
    expected_version: int = Field(ge=1)


class EngineSetting(Model):
    engine: Literal["rules", "deepseek", "failure"]


class PlanItem(Model):
    name: str = Field(min_length=1, max_length=80)
    quantity: Decimal = Field(gt=0)
    unit: str = Field(min_length=1, max_length=20)


class PlanUpdate(Model):
    revision: int = Field(ge=1)
    items: list[PlanItem] = Field(max_length=100)


T = TypeVar("T")


class Envelope(Model, Generic[T]):
    success: bool
    data: T
    error: dict | None = None
    mode: Literal["mock", "service"]


class DraftRecord(Model):
    id: str
    household_id: str
    revision: int
    status: Literal["DRAFT", "CONFIRMED", "CANCELLED"]
    command: Command
    trace_id: str


class InventoryData(Model):
    batches: list[Batch]


class Event(Model):
    id: str
    batch_id: str
    household_id: str
    type: Literal["Added", "Consumed", "Correction"]
    quantity_delta: Decimal
    unit: str
    before: Batch | None
    after: Batch
    actor_id: str
    request_id: str
    trace_id: str
    source: str
    created_at: str
    original_event_id: str | None


class EventData(Model):
    events: list[Event]


class PlanRecord(Model):
    id: str
    revision: int
    status: Literal["DRAFT", "CONFIRMED"]
    items: list[PlanItem]


class InventoryCommit(Model):
    batch: Batch
    event: Event
    trace_id: str
    draft_id: str | None = None


class PlanCommit(Model):
    plan: PlanRecord
    draft_id: str
    trace_id: str
