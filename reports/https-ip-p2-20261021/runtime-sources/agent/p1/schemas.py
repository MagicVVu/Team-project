from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, AwareDatetime, Field, field_validator, model_validator

from p0.domain import normalize_unit
from p0.schemas import Model, Scope


def valid_quantity(value: Decimal) -> Decimal:
    if not value.is_finite() or value <= 0 or value > Decimal("1000000000") or value.normalize().as_tuple().exponent < -6:
        raise ValueError("数量须为正数，最多六位小数且不超过 10 亿")
    return value


def valid_unit(value: str) -> str:
    # DomainError is deliberately translated into a schema validation error.
    try:
        return normalize_unit(value)
    except Exception as error:
        raise ValueError("不支持的单位") from error


Quantity = Annotated[Decimal, AfterValidator(valid_quantity)]
Unit = Annotated[str, Field(min_length=1, max_length=20), AfterValidator(valid_unit)]
Name = Annotated[str, Field(min_length=1, max_length=80, pattern=r"\S")]
Location = Annotated[str, Field(min_length=1, max_length=120, pattern=r"\S")]


class Intent(StrEnum):
    ADD = "ADD"
    CONSUME = "CONSUME"
    QUERY_INVENTORY = "QUERY_INVENTORY"
    QUERY_LOCATION = "QUERY_LOCATION"
    PLAN_ADD = "PLAN_ADD"
    OPEN = "OPEN"
    MOVE = "MOVE"
    DISCARD = "DISCARD"
    UNSUPPORTED = "UNSUPPORTED"


class Parsed(Model):
    intent: Intent
    name: str | None = Field(default=None, max_length=80)
    quantity: Decimal | None = None
    unit: str | None = Field(default=None, max_length=20)
    location: str | None = Field(default=None, max_length=120)
    purchased_at: str | None = Field(default=None, max_length=40)
    label_expiry: str | None = Field(default=None, max_length=40)
    opened_at: str | None = Field(default=None, max_length=40)
    to_location: str | None = Field(default=None, max_length=120)
    discard_mode: Literal["partial", "all"] = "partial"
    partial_batch: bool = False
    multiple_items: bool = False
    multiple_actions: bool = False
    uncertainties: list[str] = Field(default_factory=list, max_length=10)


class Batch(Model):
    id: str = Field(min_length=1, max_length=100)
    household_id: str
    name: Name
    quantity: Decimal = Field(ge=0, le=1_000_000_000)
    unit: Unit
    location: str | None = Field(default=None, max_length=120)
    purchased_at: date | None = None
    label_expiry: date | None = None
    opened_at: date | None = None
    status: Literal["ACTIVE", "FINISHED", "REVERSED", "DISCARDED"] = "ACTIVE"
    version: int = Field(ge=1)


class AddCommand(Model):
    action: Literal["ADD"] = "ADD"
    name: Name
    quantity: Quantity
    unit: Unit
    location: Location | None = None
    purchased_at: date | None = None
    label_expiry: date | None = None

    @model_validator(mode="after")
    def dates(self):
        if self.purchased_at and self.label_expiry and self.label_expiry < self.purchased_at:
            raise ValueError("标签日期早于购入日期")
        return self


class PlanCommand(Model):
    action: Literal["PLAN_ADD"] = "PLAN_ADD"
    name: Name
    quantity: Quantity
    unit: Unit


class TargetCommand(Model):
    name: Name
    batch_id: str = Field(min_length=1, max_length=100)
    expected_version: int = Field(ge=1)


class ConsumeCommand(TargetCommand):
    action: Literal["CONSUME"] = "CONSUME"
    quantity: Quantity
    unit: Unit


class OpenCommand(TargetCommand):
    action: Literal["OPEN"] = "OPEN"
    opened_at: date


class MoveCommand(TargetCommand):
    action: Literal["MOVE"] = "MOVE"
    to_location: Location


class DiscardCommand(TargetCommand):
    action: Literal["DISCARD"] = "DISCARD"
    discard_mode: Literal["partial", "all"]
    quantity: Quantity
    unit: Unit


Command = Annotated[AddCommand | PlanCommand | ConsumeCommand | OpenCommand | MoveCommand | DiscardCommand,
                    Field(discriminator="action")]


class Message(Model):
    text: str = Field(min_length=1, max_length=1000, pattern=r"\S")
    request_id: str = Field(min_length=1, max_length=100)
    household_timezone: str = "Asia/Shanghai"

    @field_validator("household_timezone")
    @classmethod
    def timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("必须提供有效 IANA 家庭时区") from None
        return value


AnswerField = Literal["name", "quantity", "unit", "location", "purchased_at", "label_expiry", "opened_at", "to_location", "batch_id"]


class ClarificationContext(Model):
    id: str
    revision: int = Field(ge=1)
    scope: Scope
    original_text: str = Field(min_length=1, max_length=1000)
    request_id: str
    trace_id: str
    household_timezone: str
    created_at: AwareDatetime
    expires_at: AwareDatetime
    parsed: Parsed
    candidates: list[Batch] = Field(default_factory=list, max_length=1000)
    selected_batch_id: str | None = None
    allowed_fields: list[AnswerField] = Field(default_factory=list)

    _valid_timezone = field_validator("household_timezone")(Message.timezone.__func__)


class Answers(Model):
    name: Name | None = None
    quantity: Decimal | None = None
    unit: str | None = Field(default=None, min_length=1, max_length=20)
    location: Location | None = None
    purchased_at: str | None = Field(default=None, max_length=40)
    label_expiry: str | None = Field(default=None, max_length=40)
    opened_at: str | None = Field(default=None, max_length=40)
    to_location: Location | None = None
    batch_id: str | None = Field(default=None, min_length=1, max_length=100)


class ClarificationRequest(Model):
    context: ClarificationContext
    revision: int = Field(ge=1)
    answers: Answers


class ProposedState(Model):
    quantity: Decimal
    unit: str
    location: str | None = None
    opened_at: date | None = None
    status: Literal["ACTIVE", "FINISHED", "DISCARDED"]


class ChangePreview(Model):
    batch_id: str | None = None
    before: Batch | None = None
    after: ProposedState | None = None
    event_type: Literal["Added", "Consumed", "Opened", "Moved", "Discarded"] | None = None
    quantity_delta: Decimal = Decimal(0)
    inventory_changes: bool = True
    prospective: Literal[True] = True


class TraceStep(Model):
    step: str
    outcome: str
    elapsed_ms: float


class AgentResult(Model):
    status: Literal["needs_clarification", "needs_confirmation", "answered", "unsupported", "error"]
    intent: Intent | None = None
    reply: str
    trace_id: str
    original_text: str
    draft: Command | None = None
    preview: ChangePreview | None = None
    candidates: list[Batch] = Field(default_factory=list)
    facts: list[Batch] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    clarification: ClarificationContext | None = None
    error_code: str | None = None
    retryable: bool = False
    manual_entry: bool = False
    trace: list[TraceStep] = Field(default_factory=list)
