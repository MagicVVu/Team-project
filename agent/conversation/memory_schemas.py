"""Trusted, bounded session context. No mobile-supplied history or write commands."""
from datetime import timedelta
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator, field_validator
from p0.schemas import Model, Scope
from p3.schemas import Parsed
from .schemas import AgentResult, ObjectReference
from .replies import BoundTask

MEMORY_PROTOCOL = "conversation-memory-1"
MAX_CONTEXT_BYTES = 48000


class HistoryTurn(Model):
    request_id: str = Field(min_length=1, max_length=100)
    text: str = Field(max_length=1000)
    reply: str = Field(max_length=8000)
    created_at: AwareDatetime
    task_id: UUID | None = None


class TaskEvidence(Model):
    task_id: UUID
    revision: int = Field(ge=1, strict=True)
    status: str = Field(max_length=50)
    action: str | None = Field(default=None, max_length=30)
    missing_fields: list[str] = Field(default_factory=list, max_length=9)
    draft_id: UUID | None = None
    operation_id: UUID | None = None
    # Fresh business read, distinct from the historical AI task status.
    execution_status: str | None = Field(default=None, max_length=50)
    receipt_verified: bool = False
    basis: list[str] = Field(default_factory=list, max_length=30)
    checked_at: AwareDatetime


class MemoryContext(Model):
    protocol_version: Literal["conversation-memory-1"] = MEMORY_PROTOCOL
    scope: Scope
    conversation_id: UUID
    revision: int = Field(ge=0, strict=True)
    trusted_now: AwareDatetime
    history: list[HistoryTurn] = Field(default_factory=list, max_length=10)
    active: BoundTask | None = None
    reference: ObjectReference | None = None
    reference_error: str | None = Field(default=None, max_length=100)
    choices: list[ObjectReference] = Field(default_factory=list, max_length=1000)
    tasks: list[TaskEvidence] = Field(default_factory=list, max_length=20)
    truncated: bool = False

    @model_validator(mode="after")
    def consistency(self):
        if self.active and self.active.scope != self.scope:
            raise ValueError("Cross-scope task")
        if any(r.scope != self.scope for r in [*self.choices, *([self.reference] if self.reference else [])]):
            raise ValueError("Cross-scope reference")
        if len({t.task_id for t in self.tasks}) != len(self.tasks):
            raise ValueError("Duplicate task evidence")
        if any(not self.trusted_now-timedelta(days=30) < t.created_at <= self.trusted_now for t in self.history):
            raise ValueError("History outside the thirty-day read window")
        if any(t.checked_at != self.trusted_now for t in self.tasks):
            raise ValueError("Task evidence must be read for this request")
        return self


class MemoryParsed(Parsed):
    """Distinct schema name keeps the released P1 Parsed OpenAPI refs stable."""


class Understanding(Model):
    kind: Literal["task", "status", "basis", "recall", "needs_input"] = "task"
    parsed: MemoryParsed | None = None
    reference_index: int | None = Field(default=None, ge=0, strict=True)
    task_id: UUID | None = None

    @field_validator("parsed", mode="before")
    @classmethod
    def parsed_value(cls, value):
        return value.model_dump() if isinstance(value, Parsed) else value


class TurnRequest(Model):
    text: str = Field(min_length=1, max_length=1000, pattern=r"\S")
    request_id: str = Field(min_length=1, max_length=100)
    household_timezone: str = "Asia/Shanghai"
    context: MemoryContext
    # Trusted backend-only replay of saved understanding; always rereads tools.
    replay: Understanding | None = None

    @model_validator(mode="after")
    def replay_shape(self):
        if self.replay and (self.replay.kind != "task" or self.replay.parsed is None):
            raise ValueError("Only understood inventory tasks may replay")
        return self


class TurnResult(Model):
    protocol_version: Literal["conversation-memory-1"] = MEMORY_PROTOCOL
    kind: Literal["task", "clarify", "explain", "needs_input", "clear_reference"]
    original_text: str
    reply: str
    result: AgentResult | None = None
    understanding: Understanding | None = None
    answers: dict[str, str] = Field(default_factory=dict)
    filled_fields: dict[str, str] = Field(default_factory=dict, max_length=8)
    task_revision: int | None = None
    reference: ObjectReference | None = None
    preserve_active: bool = False
    evidence: list[dict[str, str | int]] = Field(default_factory=list)
    model_calls: int = Field(ge=0, le=1)
    truncated: bool = False
    error_code: str | None = None

    @model_validator(mode="after")
    def shape(self):
        if (self.kind == "task") != (self.result is not None):
            raise ValueError("Only task route carries a task result")
        if self.kind == "clarify":
            if not self.answers or self.task_revision is None:
                raise ValueError("Clarification requires revision and answers")
        elif self.answers or self.task_revision is not None:
            raise ValueError("Only clarification carries answers")
        return self
