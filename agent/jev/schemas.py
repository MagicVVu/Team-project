"""Lab contracts; deliberately separate from the existing Agent wire types."""
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, StrictBool, field_validator, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


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
    QUERY_LOCATION_ITEMS = "QUERY_LOCATION_ITEMS"
    QUERY_OVERVIEW = "QUERY_OVERVIEW"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


class Node(StrEnum):
    INTENT = "intent_router"
    EVENT = "event_classifier"
    CLARIFICATION = "clarification_gate"
    ACTION = "action_gate"


class Action(StrEnum):
    READ = "READ"
    CONFIRM = "CONFIRM"
    CLARIFY = "CLARIFY"
    WAIT = "WAIT"


class Fields(Model):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    quantity: Decimal | None = Field(default=None, gt=0, le=1_000_000_000)
    unit: str | None = Field(default=None, min_length=1, max_length=20)
    location: str | None = Field(default=None, min_length=1, max_length=100)
    to_location: str | None = Field(default=None, min_length=1, max_length=100)
    purchased_at: date | None = None
    label_expiry: date | None = None
    opened_at: date | None = None

    @field_validator("name", "unit", "location", "to_location")
    @classmethod
    def nonblank(cls, value):
        if value is not None and not value.strip():
            raise ValueError("blank field")
        return value.strip() if value is not None else None

    @field_validator("quantity", mode="before")
    @classmethod
    def numeric_quantity(cls, value):
        if isinstance(value, bool):
            raise ValueError("quantity is not boolean")
        return value


class Candidate(Model):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=80)
    quantity: Decimal = Field(ge=0, le=1_000_000_000)
    unit: str = Field(min_length=1, max_length=20)
    location: str | None = Field(default=None, max_length=100)
    version: int = Field(ge=1, strict=True)
    status: Literal["ACTIVE", "FINISHED", "DISCARDED", "REVERSED"] = "ACTIVE"


class Facts(Model):
    """Caller-supplied synthetic facts, never an authentication attestation."""
    known: StrictBool = False
    fields: Fields = Field(default_factory=Fields)
    candidates: list[Candidate] = Field(default_factory=list, max_length=20)
    selected_id: str | None = Field(default=None, max_length=100)
    scope_valid: StrictBool | None = None
    version_current: StrictBool | None = None
    unit_compatible: StrictBool | None = None
    has_reference: StrictBool = False
    reference_valid: StrictBool | None = None
    missing_fields: list[str] = Field(default_factory=list, max_length=20)
    conflicts: list[str] = Field(default_factory=list, max_length=20)
    task_status: Literal["ready", "processing", "expired", "unknown"] = "unknown"
    capabilities: list[Intent] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_candidates(self):
        ids = [c.id for c in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate candidate IDs")
        if self.selected_id is not None and self.selected_id not in ids:
            raise ValueError("selected ID must belong to supplied candidates")
        return self


class DecisionRequest(Model):
    synthetic: Literal[True]
    request_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=1000)
    now: AwareDatetime
    timezone: str = "Asia/Shanghai"
    facts: Facts = Field(default_factory=Facts)

    @field_validator("timezone")
    @classmethod
    def timezone_exists(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("invalid timezone") from None
        return value

    @field_validator("synthetic", mode="before")
    @classmethod
    def explicitly_synthetic(cls, value):
        if value is not True:
            raise ValueError("only explicitly synthetic requests are accepted")
        return value

    @field_validator("text")
    @classmethod
    def text_nonblank(cls, value):
        if not value.strip():
            raise ValueError("empty text")
        return value


Probability = Annotated[float, Field(strict=True, ge=0, le=1)]


class Answer(Model):
    type: Literal["choice", "noul"]
    choice: str | None = None
    probabilities: dict[str, Probability] | None = None
    confidence: Probability | None = None
    noul: Probability | None = None

    @model_validator(mode="after")
    def valid_distribution(self):
        if self.type == "choice":
            if not self.choice or not self.probabilities or self.confidence is None or self.noul is not None:
                raise ValueError("incomplete choice")
            if self.choice not in self.probabilities:
                raise ValueError("choice missing from distribution")
            if abs(sum(self.probabilities.values()) - 1) > 0.00001:
                raise ValueError("probabilities must sum to one")
            if self.probabilities[self.choice] + 0.000001 < max(self.probabilities.values()):
                raise ValueError("choice must be a maximum")
        elif self.noul is None or any(x is not None for x in (self.choice, self.probabilities, self.confidence)):
            raise ValueError("invalid noul")
        return self


class Usage(Model):
    input_tokens: int = Field(ge=0, strict=True)
    output_tokens: int = Field(ge=0, strict=True)


class WireResponse(Model):
    model: str
    answers: dict[str, Answer]
    usage: Usage


class NodeState(Model):
    request: DecisionRequest
    upstream: dict[str, Answer] = Field(default_factory=dict)


class CallTrace(Model):
    phase: int
    source: Literal["live", "mock", "replay"]
    fingerprint: str
    attempted: bool = False
    status: Literal["pending", "ok", "error"] = "pending"
    error_code: str | None = None
    model: str | None = None
    elapsed_ms: float = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    charged_usd: Decimal = Decimal(0)
    usage_measured: bool = False
    reservation_id: str | None = None
    recording_error: str | None = None


class NodeResult(Model):
    node: Node
    status: Literal["ok", "skipped", "error"] = "skipped"
    source: Literal["live", "mock", "replay"] | None = None
    answer: Answer | None = None
    model: str | None = None
    error_code: str | None = None


class DecisionResult(Model):
    protocol_version: Literal["jev-lab-1"] = "jev-lab-1"
    request_id: str
    input_sha256: str
    question_version: str
    policy_version: str
    status: Literal["ok", "needs_review", "unavailable"]
    nodes: dict[Node, NodeResult]
    auxiliary: dict[str, Answer] = Field(default_factory=dict)
    raw_action: Action | None = None
    final_action: Action = Action.WAIT
    reasons: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    calls: list[CallTrace] = Field(default_factory=list)
    elapsed_ms: float = 0
    inventory_writes: Literal[False] = False
    shopping_writes: Literal[False] = False
    calibrated: Literal[False] = False

    @property
    def charged_usd(self):
        return sum((c.charged_usd for c in self.calls), Decimal(0))


class JevError(Exception):
    """Public error codes never contain HTTP bodies, keys or user text."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)
