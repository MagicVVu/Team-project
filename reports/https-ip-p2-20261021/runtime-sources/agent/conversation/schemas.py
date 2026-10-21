from datetime import timedelta
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator
from p0.schemas import Model, Scope
from p1.schemas import ClarificationContext, Answers
from interaction.schemas import Message as BaseMessage
from interaction.schemas import Receipt
from v1.schemas import (AgentResult as BaseResult, RuntimeInfo as OldRuntime,
                        Context as OldContext)

POLICY_VERSION = "p7-limited-context-1"


class ObjectReference(Model):
    """Attestation from an authenticated business caller, never a phone fact."""
    protocol_version: Literal["p7-object-reference-1"] = "p7-object-reference-1"
    scope: Scope
    source_task_id: UUID
    source_revision: int = Field(ge=1, strict=True)
    batch_id: str = Field(min_length=1, max_length=100)
    issued_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def interval(self):
        if not timedelta(0) < self.expires_at-self.issued_at <= timedelta(minutes=15):
            raise ValueError("Object reference must expire within fifteen minutes")
        return self


class Message(BaseMessage):
    reference: ObjectReference | None = None


class ReferenceContext(Model):
    protocol_version: Literal["p7-reference-continuation-1"] = "p7-reference-continuation-1"
    id: str
    revision: int = Field(ge=1, strict=True)
    scope: Scope
    original_text: str
    request_id: str
    trace_id: str
    household_timezone: str
    created_at: AwareDatetime
    expires_at: AwareDatetime
    allowed_fields: list[str]
    reference: ObjectReference
    delegate: ClarificationContext
    input_receipt: Receipt | None = None

    @model_validator(mode="after")
    def consistent(self):
        for key in ("id", "revision", "scope", "original_text", "request_id", "trace_id",
                    "household_timezone", "created_at", "expires_at", "allowed_fields"):
            if getattr(self, key) != getattr(self.delegate, key):
                raise ValueError("Reference continuation envelope mismatch")
        if self.scope != self.reference.scope or self.expires_at > self.reference.expires_at:
            raise ValueError("Reference continuation scope/expiry mismatch")
        if any(b.household_id != self.scope.household_id or b.id != self.reference.batch_id
               for b in self.delegate.candidates):
            raise ValueError("Reference continuation targets another batch")
        if self.delegate.selected_batch_id not in (None, self.reference.batch_id):
            raise ValueError("Reference continuation changes target")
        if self.input_receipt:
            import hashlib
            if self.input_receipt.final_text_sha256 != hashlib.sha256(self.original_text.encode()).hexdigest():
                raise ValueError("Reference continuation original text changed")
        return self


class ClarificationRequest(Model):
    context: ReferenceContext | OldContext
    revision: int = Field(ge=1, strict=True)
    answers: Answers


class RuntimeInfo(OldRuntime):
    release: Literal["V1-P7"] = "V1-P7"


class ReferenceUse(Model):
    source_task_id: UUID
    source_revision: int = Field(ge=1, strict=True)
    batch_id: str


class AgentResult(BaseResult):
    clarification: ReferenceContext | OldContext | None = None
    runtime: RuntimeInfo | OldRuntime | None = None
    policy_version: Literal["p7-limited-context-1", "v1-completion-1"] = POLICY_VERSION
    object_source: Literal["user_input", "trusted_reference"] | None = None
    reference_used: ReferenceUse | None = None
    clear_reference: bool = False
