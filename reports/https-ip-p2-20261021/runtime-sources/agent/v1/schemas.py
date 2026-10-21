from typing import Literal, Annotated
from datetime import datetime
from pydantic import AwareDatetime, Field, model_validator, field_validator
from p0.schemas import Model, Scope
from p1.schemas import Answers, ConsumeCommand, Name, Location
from p2.schemas import Batch
from p3.schemas import Intent as P3Intent, PlanningItem, PlanningSnapshot as P3Snapshot
from interaction.schemas import (AgentResult as P5Result, ClarificationRequest as P5Request,
    ContinuationContext, ReviewContext, Receipt, Message)
from interaction.schemas import DelegateContext

POLICY_VERSION = "v1-completion-1"
PUBLIC_FIELDS = {"name", "quantity", "unit", "location", "purchased_at", "label_expiry",
                 "opened_at", "to_location", "batch_id"}


class LocalContext(Model):
    protocol_version: Literal["v1-local-1"] = "v1-local-1"
    id: str
    revision: int = Field(ge=1, strict=True)
    scope: Scope
    original_text: str
    request_id: str
    trace_id: str
    household_timezone: str
    created_at: AwareDatetime
    expires_at: AwareDatetime
    kind: Literal["finish", "location"]
    name: Name | None = None
    location: Location | None = None
    unlocated: bool = False
    candidates: list[Batch] = Field(default_factory=list, max_length=1000)
    selected_batch_id: str | None = None
    allowed_fields: list[Literal["name", "location", "batch_id"]]
    input_receipt: Receipt | None = None

    @model_validator(mode="after")
    def consistent(self):
        if self.expires_at <= self.created_at:
            raise ValueError("Invalid context interval")
        if any(b.household_id != self.scope.household_id for b in self.candidates):
            raise ValueError("Cross-household candidates")
        permitted = {"name", "batch_id"} if self.kind == "finish" else {"location"}
        if not set(self.allowed_fields) <= permitted:
            raise ValueError("Fields do not match action")
        if self.selected_batch_id and self.selected_batch_id not in {b.id for b in self.candidates}:
            raise ValueError("Selected batch not in candidates")
        return self


class SelectionEnvelope(Model):
    protocol_version: Literal["v1-batch-selection-1"] = "v1-batch-selection-1"
    id: str
    revision: int = Field(ge=1, strict=True)
    scope: Scope
    original_text: str
    request_id: str
    trace_id: str
    household_timezone: str
    created_at: AwareDatetime
    expires_at: AwareDatetime
    allowed_fields: list[Literal["batch_id", "name"]]
    delegate: ContinuationContext
    input_receipt: Receipt | None = None

    @model_validator(mode="after")
    def mirrors(self):
        from p3.schemas import SelectionContext
        for key in ("id", "revision", "scope", "original_text", "request_id", "trace_id",
                    "household_timezone", "created_at", "expires_at"):
            if getattr(self, key) != getattr(self.delegate, key):
                raise ValueError("Selection envelope mismatch")
        inner = self.delegate.delegate
        if not isinstance(inner, SelectionContext) or inner.allowed_fields != ["item_key"]:
            raise ValueError("Only item selection can be adapted")
        has_batches = any(c.batches for c in inner.candidates)
        if self.allowed_fields != (["batch_id"] if has_batches else ["name"]):
            raise ValueError("Public selection fields mismatch")
        if self.input_receipt != self.delegate.input_receipt:
            raise ValueError("Input receipt mismatch")
        return self


Context = LocalContext | SelectionEnvelope | P5Request.model_fields["context"].annotation


class ClarificationRequest(Model):
    context: Context
    revision: int = Field(ge=1, strict=True)
    # Public-safe fields. Old internal item_key requests remain on the P3/P5 entry.
    answers: Answers


class Decision(Model):
    node: Literal["intent_router", "event_classifier", "clarification_gate", "action_gate"]
    source: Literal["literal_rules", "llm", "deterministic", "input_guard"]
    outcome: str
    reason_codes: list[str] = Field(default_factory=list)


class Guidance(Model):
    batch_id: str
    missing_fields: list[str]
    instructions: list[str]
    fact_write_required: bool = True
    inventory_written: Literal[False] = False


class StockVerification(Model):
    checked_at: AwareDatetime
    source: str = Field(min_length=1, max_length=200, pattern=r"\S")


class Item(PlanningItem):
    stock_verification: StockVerification | None = None


class PlanningSnapshot(P3Snapshot):
    protocol_version: Literal["p3-planning-context-1", "v1-planning-context-1"]
    items: list[Item] = Field(max_length=1000)


class Section(Model):
    name: Literal["risk", "planning"]
    status: Literal["available", "partial", "unavailable"]
    snapshot_id: str | None = None
    evaluated_at: AwareDatetime | None = None
    reason_codes: list[str] = Field(default_factory=list)


class CommitReceipt(Model):
    protocol_version: Literal["v1-operation-receipt-1"]
    scope: Scope
    operation_id: str = Field(min_length=1, max_length=100)
    status: Literal["committed", "processing", "rejected"]
    committed_at: AwareDatetime | None = None
    batch_versions: dict[str, Annotated[int, Field(strict=True, ge=1)]] = Field(default_factory=dict, max_length=100)
    event_ids: list[str] = Field(default_factory=list, max_length=100)
    trace_id: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def versions(self):
        if any(not k.strip() or isinstance(v, bool) or v < 1 for k,v in self.batch_versions.items()):
            raise ValueError("Invalid committed versions")
        if len(self.event_ids) != len(set(self.event_ids)) or any(not v.strip() for v in self.event_ids):
            raise ValueError("Invalid event references")
        if self.status == "committed" and (self.committed_at is None or not self.batch_versions or not self.event_ids):
            raise ValueError("Committed operation requires time")
        return self


class FeedbackRequest(Model):
    operation_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")
    household_timezone: str = "Asia/Shanghai"
    _timezone = field_validator("household_timezone")(Message.timezone.__func__)


class Feedback(Model):
    operation_id: str
    business_committed: Literal[True] = True
    committed_trace_id: str
    committed_at: AwareDatetime
    later_changes: bool = False
    refresh_required: bool = False


class RuntimeInfo(Model):
    release: Literal["V1-P6"] = "V1-P6"
    prompt_version: str
    ruleset_sha256: str
    model: str | None = None
    model_calls: int = Field(ge=0, le=1)


class AgentResult(P5Result):
    intent: P3Intent | Literal["QUERY_LOCATION_ITEMS", "QUERY_OVERVIEW"] | None = None
    clarification: Context | None = None
    request_id: str | None = None
    runtime: RuntimeInfo | None = None
    decisions: list[Decision] = Field(default_factory=list)
    guidance: list[Guidance] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)
    location_options: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    feedback: Feedback | None = None
    truncated: bool = False
    total_count: int | None = Field(default=None, ge=0)
    quantity_source: Literal["user_input", "current_batch", "planning_calculation"] | None = None
    policy_version: Literal["v1-completion-1"] = POLICY_VERSION
    jev_status: Literal["deferred_by_user"] = "deferred_by_user"
