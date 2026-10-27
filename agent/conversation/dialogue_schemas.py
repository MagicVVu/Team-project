"""P8.4 internal stages. Trusted context and user text have separate origins."""
from typing import Literal
from pydantic import Field, model_validator
from p0.schemas import Model
from p1.schemas import Message
from .memory_schemas import MemoryContext

PROTOCOL = "p84-dialogue-1"
FIELDS = {"name", "quantity", "unit", "location", "to_location", "opened_at", "purchased_at", "label_expiry"}


class FieldSource(Model):
    value: str = Field(max_length=120)
    source: Literal["current_text", "current_task"] = "current_text"
    quote: str = Field(default="", max_length=1000)


class Selector(Model):
    name: str | None = Field(default=None, max_length=80)
    location: str | None = Field(default=None, max_length=100)
    choice_index: int | None = Field(default=None, ge=0, strict=True)
    use_reference: bool = False


class Read(Model):
    kind: Literal["quantity", "location", "dates", "risk", "consumption", "forecast", "purchase"]


class Plan(Model):
    speech_act: Literal["request", "discuss", "hypothesis", "negation", "correction", "supplement", "question", "social", "status", "basis", "recall", "new_task"]
    selector: Selector = Field(default_factory=Selector)
    reads: list[Read] = Field(default_factory=list, max_length=4)
    action: Literal["ADD", "CONSUME", "OPEN", "MOVE", "DISCARD", "PLAN_ADD"] | None = None
    fields: dict[str, FieldSource] = Field(default_factory=dict, max_length=8)
    amount_mode: Literal["literal", "half", "all", "unknown"] = "literal"
    write_count: int = Field(default=0, ge=0, le=10, strict=True)
    task_index: int | None = Field(default=None, ge=0, strict=True)
    preserve_active: bool = True
    social_reply: str | None = Field(default=None, max_length=800)

    @model_validator(mode="after")
    def names(self):
        if not set(self.fields) <= FIELDS:
            raise ValueError("Unknown task field")
        return self


class Request(Model):
    text: str = Field(min_length=1, max_length=1000, pattern=r"\S")
    request_id: str = Field(min_length=1, max_length=100)
    household_timezone: str = "Asia/Shanghai"
    context: MemoryContext
    current_task_plan: Plan | None = None
    remaining_seconds: float = Field(default=18, gt=0, le=18)

    @model_validator(mode="after")
    def timezone_valid(self):
        Message.timezone(self.household_timezone)
        return self


class Understood(Model):
    protocol_version: Literal["p84-dialogue-1"] = PROTOCOL
    original_text: str
    plan: Plan
    understanding_calls: int = Field(ge=0, le=1, strict=True)
    truncated: bool = False


class DialogueResolveRequest(Request):
    plan: Plan


ResolveRequest = DialogueResolveRequest


class Resolved(Model):
    protocol_version: Literal["p84-dialogue-1"] = PROTOCOL
    original_text: str
    kind: Literal["task", "clarify", "edit", "explain", "needs_input", "clear_reference"]
    reply: str
    result: dict | None = None
    answers: dict[str, str] = Field(default_factory=dict)
    task_revision: int | None = None
    reference: dict | None = None
    preserve_active: bool = True
    evidence: list[dict] = Field(default_factory=list)
    field_sources: dict[str, dict] = Field(default_factory=dict)
    filled_fields: dict[str, str] = Field(default_factory=dict)
    facts: dict[str, str] = Field(default_factory=dict)
    edit: dict | None = None
    error_code: str | None = None
    truncated: bool = False
    model_calls: Literal[0] = 0


class RespondRequest(Model):
    text: str = Field(min_length=1, max_length=1000)
    resolved: Resolved
    remaining_seconds: float = Field(default=8, gt=0, le=18)


class Responded(Model):
    protocol_version: Literal["p84-dialogue-1"] = PROTOCOL
    reply: str
    response_calls: int = Field(ge=0, le=1, strict=True)
    fallback_used: bool = False
    error_code: str | None = None
