import hashlib
import json
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator
from p0.schemas import Model, Scope
from p1.schemas import ClarificationContext as P1Context
from p2.schemas import RiskSelectionContext
from p3.schemas import (AgentResult as P3Result, Answers, PlanningMessage,
                        SelectionContext, ClarificationRequest as P3Request)

POLICY_VERSION = "p5-reviewed-text-1"
DelegateContext = SelectionContext | RiskSelectionContext | P1Context


class InputProvenance(Model):
    source: Literal["text", "voice", "manual_fallback"]
    input_session_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")
    transcript_revision: int = Field(ge=1)
    user_confirmed: bool
    user_edited: bool = False


class Message(PlanningMessage):
    # No raw transcript/audio/confidence field: removed words cannot ground
    # commands. The authenticated business caller owns this attestation.
    input: InputProvenance | None = None


class Receipt(Model):
    policy_version: Literal["p5-reviewed-text-1"] = POLICY_VERSION
    source: Literal["text", "voice", "manual_fallback"]
    provenance: InputProvenance | None = None
    review_attestation_received: bool
    final_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    deduplication_owner: Literal["business_backend"] = "business_backend"

    @model_validator(mode="after")
    def provenance_consistent(self):
        if self.provenance is None:
            if self.source != "text" or self.review_attestation_received:
                raise ValueError("缺少来源证明时仅可标为普通文字")
        elif self.source != self.provenance.source or self.review_attestation_received != self.provenance.user_confirmed:
            raise ValueError("输入来源记录不一致")
        return self


def receipt(message, scope):
    canonical = {"scope":scope.model_dump(), "text":message.text,
        "household_timezone":message.household_timezone, "reminder_days":message.reminder_days,
        "input":message.input.model_dump() if message.input else None}
    return Receipt(source=message.input.source if message.input else "text", provenance=message.input,
        review_attestation_received=bool(message.input and message.input.user_confirmed),
        final_text_sha256=hashlib.sha256(message.text.encode()).hexdigest(),
        request_fingerprint=hashlib.sha256(json.dumps(canonical,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest())


class ReviewContext(Model):
    protocol_version: Literal["p5-text-review-1"] = "p5-text-review-1"
    id: str
    revision: Literal[1] = 1
    scope: Scope
    original_text: str
    request_id: str
    trace_id: str
    household_timezone: str
    created_at: AwareDatetime
    expires_at: AwareDatetime
    allowed_fields: list[str] = Field(default_factory=list, max_length=0)
    input_receipt: Receipt
    resubmit_required: Literal[True] = True


class ContinuationContext(Model):
    protocol_version: Literal["p5-continuation-1"] = "p5-continuation-1"
    id: str
    revision: int = Field(ge=1)
    scope: Scope
    original_text: str
    request_id: str
    trace_id: str
    household_timezone: str
    created_at: AwareDatetime
    expires_at: AwareDatetime
    allowed_fields: list[str]
    delegate: DelegateContext
    input_receipt: Receipt | None = None

    @model_validator(mode="after")
    def mirrors(self):
        for field in ("id", "revision", "scope", "request_id", "trace_id",
                      "household_timezone", "created_at", "expires_at", "allowed_fields"):
            if getattr(self, field) != getattr(self.delegate, field):
                raise ValueError("续接封套与内部上下文不一致")
        from .policy import extraction_text
        if self.delegate.original_text not in {self.original_text,extraction_text(self.original_text)}:
            raise ValueError("内部文字不是原文的保守口语规范形式")
        if self.input_receipt and self.input_receipt.final_text_sha256 != hashlib.sha256(self.original_text.encode()).hexdigest():
            raise ValueError("确认文字已改变，必须创建新消息")
        return self


class ClarificationRequest(Model):
    context: ContinuationContext | ReviewContext | SelectionContext | RiskSelectionContext | P1Context
    revision: int = Field(ge=1)
    answers: Answers


class ReviewAdvice(Model):
    reason_code: str
    resubmit_required: Literal[True] = True
    replacement_request_id_required: Literal[True] = True


class AgentResult(P3Result):
    clarification: ContinuationContext | ReviewContext | SelectionContext | RiskSelectionContext | P1Context | None = None
    input_receipt: Receipt | None = None
    input_review: ReviewAdvice | None = None
