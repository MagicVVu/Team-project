"""Independent business-side P8.5 wire types; no AI package dependency."""
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class Wire(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Scope(Wire):
    user_id: str
    household_id: str


class FieldSource(Wire):
    value: str = Field(max_length=120)
    source: Literal["current_text", "current_task"] = "current_text"
    quote: str = Field(default="", max_length=1000)


class Selector(Wire):
    name: str | None = Field(default=None, max_length=80)
    location: str | None = Field(default=None, max_length=100)
    choice_index: int | None = Field(default=None, ge=0, strict=True)
    use_reference: bool = False


class Read(Wire):
    kind: Literal["quantity", "location", "dates", "risk", "consumption", "forecast", "purchase"]


class Plan(Wire):
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
    memory_id: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def fields_known(self):
        if not set(self.fields) <= {"name", "quantity", "unit", "location", "to_location", "opened_at", "purchased_at", "label_expiry"}:
            raise ValueError("Unknown task field")
        return self


class MemoryUse(Wire):
    selected_ids: list[str] = Field(default_factory=list, max_length=8)
    omitted_episodes: int = Field(default=0, ge=0)
    truncated: bool = False
    archive_available: bool = False
    summary: dict = Field(default_factory=dict)


class Subject(Wire):
    name: str = Field(min_length=1, max_length=80)
    quote: str = Field(min_length=1, max_length=1000)


class Episode(Wire):
    memory_id: str = Field(min_length=1, max_length=100)
    request_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=1000)
    reply: str = Field(default="", max_length=8000)
    created_at: AwareDatetime
    subjects: list[Subject] = Field(default_factory=list, max_length=4)
    reference: dict | None = None

    @model_validator(mode="after")
    def literal_subjects(self):
        if any(s.quote not in self.text or s.name not in s.quote for s in self.subjects):
            raise ValueError("Subject must quote original text")
        if len({s.name for s in self.subjects}) != len(self.subjects):
            raise ValueError("Duplicate subjects")
        return self


class MemoryDelta(Wire):
    protocol_version: Literal["conversation-episode-delta-1"]
    scope: Scope
    conversation_id: UUID
    expected_revision: int = Field(ge=0, strict=True)
    episode: Episode
    source_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Understanding(Wire):
    protocol_version: Literal["p85-dialogue-1"]
    original_text: str
    plan: Plan
    context_revision: int = Field(ge=0, strict=True)
    understanding_calls: int = Field(ge=0, le=1, strict=True)
    memory: MemoryUse


class Expression(Wire):
    protocol_version: Literal["p84-dialogue-1", "p85-dialogue-1"]
    reply: str
    response_calls: int = Field(ge=0, le=1, strict=True)
    fallback_used: bool = False
    error_code: str | None = None
