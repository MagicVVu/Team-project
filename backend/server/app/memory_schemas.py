"""Opt-in session protocol; public requests contain selectors, never trusted facts."""
from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")
    household_id: UUID
    request_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")


class Reset(Input):
    conversation_id: UUID | None = None
    conversation_revision: int = Field(default=0, ge=0, strict=True)


class Message(Input):
    conversation_id: UUID
    conversation_revision: int = Field(ge=0, strict=True)
    text: str = Field(min_length=1, max_length=1000, pattern=r"\S")
    task_id: UUID | None = None
    revision: int | None = Field(default=None, ge=1, strict=True)

    @model_validator(mode="after")
    def selectors(self):
        if (self.task_id is None) != (self.revision is None):
            raise ValueError("task_id and revision must be provided together")
        return self


class CurrentTask(BaseModel):
    task: dict[str, Any]
    execution: dict[str, Any] | None = None


class Turn(BaseModel):
    request_id: str
    original_text: str
    created_at: datetime
    phase: str
    reply: str
    task_id: UUID | None = None
    historical_status: str | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class DialogueCalls(BaseModel):
    model_config = ConfigDict(extra="forbid")
    understanding: int = Field(ge=0,le=1,strict=True)
    response: int = Field(ge=0,le=1,strict=True)
    total: int = Field(ge=0,le=2,strict=True)

    @model_validator(mode="after")
    def count(self):
        if self.total != self.understanding+self.response: raise ValueError("Invalid stage count")
        return self


class DialogueMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_version: Literal["p84-dialogue-1", "p85-dialogue-1"]
    calls: DialogueCalls
    recovery_model_calls: Literal[0] | None = None
    fallback_used: bool
    field_sources: dict[str,Any] = Field(default_factory=dict)
    status: Literal["completed", "needs_input", "needs_confirmation", "stopped"] = "completed"
    stop_reason: str | None = None


class Response(BaseModel):
    protocol_version: Literal["conversation-memory-1"] = "conversation-memory-1"
    conversation_id: UUID
    conversation_revision: int
    current_conversation_revision: int | None = None
    request_id: str
    original_text: str
    reply: str
    kind: str
    task: dict[str, Any] | None = None
    active_task: CurrentTask | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    filled_fields: dict[str, str] = Field(default_factory=dict)
    model_calls: int = Field(ge=0, le=2)
    dialogue: DialogueMetadata | None = None
    truncated: bool = False
    error_code: str | None = None
    inventory_written: Literal[False] = False

    @model_validator(mode="after")
    def counts(self):
        if self.dialogue and self.dialogue.calls.total != self.model_calls:
            raise ValueError("Stage count mismatch")
        if not self.dialogue and self.model_calls > 1:
            raise ValueError("Legacy turns allow at most one call")
        return self


class Page(BaseModel):
    protocol_version: Literal["conversation-memory-1"] = "conversation-memory-1"
    conversation_id: UUID | None
    conversation_revision: int
    household_id: UUID
    messages: list[Turn]
    next_cursor: UUID | None = None
    active_task: CurrentTask | None = None
    retention_days: Literal[30] = 30
    requires_reset: bool = False


class Recovery(BaseModel):
    conversation_id: UUID | None = None
    current_conversation_revision: int | None = None
    phase: Literal["completed", "processing", "result_unknown", "prepared"]
    request_id: str
    original_text: str
    response: Response | None = None
    active_task: CurrentTask | None = None
    recovery_hint: str | None = None


class AIResolution(BaseModel):
    """Independently checked internal response; not a mobile input model."""
    model_config = ConfigDict(extra="forbid")
    protocol_version: Literal["conversation-memory-1"]
    kind: Literal["task", "clarify", "explain", "needs_input", "clear_reference"]
    original_text: str
    reply: str
    result: dict[str, Any] | None = None
    understanding: dict[str, Any] | None = None
    answers: dict[str, str] = Field(default_factory=dict, max_length=9)
    filled_fields: dict[str, str] = Field(default_factory=dict, max_length=8)
    task_revision: int | None = Field(default=None, ge=1, strict=True)
    reference: dict[str, Any] | None = None
    preserve_active: bool = False
    evidence: list[dict[str, Any]] = Field(default_factory=list, max_length=30)
    model_calls: int = Field(ge=0, le=1, strict=True)
    truncated: bool = False
    error_code: str | None = None

    @model_validator(mode="after")
    def shape(self):
        if not set(self.filled_fields) <= {"name", "quantity", "unit", "location", "to_location", "opened_at", "purchased_at", "label_expiry"}:
            raise ValueError("Recovery fields cannot change identity or versions")
        if (self.kind == "task") != (self.result is not None):
            raise ValueError("Only task carries a result")
        if self.kind == "clarify":
            if not self.answers or self.task_revision is None:
                raise ValueError("Missing clarification selector")
        elif self.answers or self.task_revision is not None:
            raise ValueError("Unexpected clarification fields")
        if self.result and (self.result.get("inventory_writes") is not False or self.result.get("shopping_writes") is not False):
            raise ValueError("AI must never claim an inventory or shopping write")
        return self
