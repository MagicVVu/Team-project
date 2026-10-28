"""Business-attested memory, distinct from phone input and live inventory."""
from datetime import timedelta
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator
from p0.schemas import Model, Scope
from ..schemas import ObjectReference
from ..dialogue_schemas import Request, Plan, Resolved, RespondRequest

PROTOCOL = "p85-dialogue-1"


class P85Subject(Model):
    name: str = Field(min_length=1, max_length=80)
    quote: str = Field(min_length=1, max_length=1000)


class P85Episode(Model):
    memory_id: str = Field(min_length=1, max_length=100)
    request_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=1000)
    reply: str = Field(default="", max_length=8000)
    created_at: AwareDatetime
    subjects: list[P85Subject] = Field(default_factory=list, max_length=4)
    # Only a business-verified original reference, never a model-generated ID.
    reference: ObjectReference | None = None

    @model_validator(mode="after")
    def literal_subjects(self):
        if any(s.quote not in self.text or s.name not in s.quote for s in self.subjects):
            raise ValueError("Memory subject must quote its original user text")
        if len({s.name for s in self.subjects}) != len(self.subjects):
            raise ValueError("Duplicate memory subjects")
        return self


class P85Archive(Model):
    protocol_version: Literal["conversation-episodes-1"] = "conversation-episodes-1"
    scope: Scope
    conversation_id: UUID
    revision: int = Field(ge=0, strict=True)
    episodes: list[P85Episode] = Field(default_factory=list, max_length=100)
    # Caller must disclose incomplete pagination; AI cannot retrieve unseen pages.
    has_more: bool = False


class P85Plan(Plan):
    memory_id: str | None = Field(default=None, min_length=1, max_length=100)


class P85Request(Request):
    archive: P85Archive | None = None

    @model_validator(mode="after")
    def memory_scope(self):
        archive, ctx = self.archive, self.context
        if archive is None:
            return self
        if (archive.scope != ctx.scope or archive.conversation_id != ctx.conversation_id
                or archive.revision != ctx.revision):
            raise ValueError("Memory archive scope/conversation/revision mismatch")
        if len({e.memory_id for e in archive.episodes}) != len(archive.episodes):
            raise ValueError("Duplicate memory IDs")
        if len({e.request_id for e in archive.episodes}) != len(archive.episodes):
            raise ValueError("Duplicate source requests")
        if any(not ctx.trusted_now-timedelta(days=30) < e.created_at <= ctx.trusted_now
               for e in archive.episodes):
            raise ValueError("Memory outside thirty-day window")
        for episode in archive.episodes:
            if episode.reference and (episode.reference.scope != ctx.scope
                                      or episode.reference.issued_at > episode.created_at):
                raise ValueError("Memory reference scope or original issue time mismatch")
        return self


class P85MemoryUse(Model):
    selected_ids: list[str] = Field(default_factory=list, max_length=8)
    omitted_episodes: int = Field(default=0, ge=0)
    truncated: bool = False
    archive_available: bool = False
    summary: dict = Field(default_factory=dict)


class P85Understood(Model):
    protocol_version: Literal["p85-dialogue-1"] = PROTOCOL
    original_text: str
    plan: P85Plan
    context_revision: int = Field(ge=0, strict=True)
    understanding_calls: int = Field(ge=0, le=1, strict=True)
    memory: P85MemoryUse


class P85ResolveRequest(P85Request):
    plan: P85Plan
    plan_context_revision: int = Field(ge=0, strict=True)


class P85MemoryDelta(Model):
    protocol_version: Literal["conversation-episode-delta-1"] = "conversation-episode-delta-1"
    scope: Scope
    conversation_id: UUID
    expected_revision: int = Field(ge=0, strict=True)
    episode: P85Episode
    source_text_sha256: str


class P85Resolved(Resolved):
    protocol_version: Literal["p85-dialogue-1"] = PROTOCOL
    memory: P85MemoryUse = Field(default_factory=P85MemoryUse)
    memory_delta: P85MemoryDelta | None = None
    # An already-understood discussion needs no second model invocation.
    expression_required: bool = True


class P85RespondRequest(RespondRequest):
    resolved: P85Resolved


class P85Responded(Model):
    protocol_version: Literal["p85-dialogue-1"] = PROTOCOL
    reply: str
    response_calls: int = Field(ge=0, le=1, strict=True)
    fallback_used: bool = False
    error_code: str | None = None
