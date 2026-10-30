from typing import Literal
from pydantic import Field, model_validator
from p0.schemas import Model
from ..p85.schemas import P85Request, P85Plan, P85Resolved
from ..p85.render import Expression

PROTOCOL = "inventory-autonomous-1"


class RunRequest(P85Request):
    remaining_seconds: float = Field(default=58, gt=0, le=58)


class Decision(Model):
    action: Literal["resolve", "finish", "ask"]
    plan: P85Plan | None = None
    expression: Expression | None = None
    clarification: Literal["intent", "object", "quantity", "unit", "date", "location", "priority"] | None = None
    finish_after_resolve: bool = False

    @model_validator(mode="after")
    def shape(self):
        if (self.action == "resolve") != (self.plan is not None):
            raise ValueError("Only resolve accepts plan")
        if (self.action == "ask") != (self.clarification is not None):
            raise ValueError("Only ask accepts clarification code")
        if self.expression is not None and self.action != "finish":
            raise ValueError("Only finish accepts expression")
        if self.finish_after_resolve and self.action != "resolve":
            raise ValueError("Only resolve can finish after successful verification")
        return self


class Step(Model):
    step: int = Field(ge=1)
    action: Literal["resolve", "finish", "ask", "model_error"]
    model_call: bool
    plan_sha256: str | None = None
    error_code: str | None = None


class RunResponse(Model):
    protocol_version: Literal["inventory-autonomous-1"] = PROTOCOL
    request_id: str
    context_revision: int = Field(ge=0)
    original_text: str
    reply: str
    status: Literal["completed", "needs_input", "needs_confirmation", "stopped"]
    stop_reason: Literal["completed", "user_input_required", "confirmation_required", "data_unavailable",
                         "repeated_plan", "no_progress", "deadline", "model_error", "context_limit", "boundary",
                         "context_refresh_required"]
    resolved: P85Resolved | None = None
    plan: P85Plan | None = None
    # All successful reads, not just the last one, are replayed without a model.
    verified_plans: list[P85Plan] = Field(default_factory=list)
    filled_fields: dict[str, str] = Field(default_factory=dict)
    model_calls: int = Field(ge=0, strict=True)
    tool_reads: int = Field(ge=0, strict=True)
    elapsed_ms: float = Field(ge=0)
    fallback_used: bool = False
    error_code: str | None = None
    trace: list[Step] = Field(default_factory=list)
    inventory_writes: Literal[False] = False
    shopping_writes: Literal[False] = False

    @model_validator(mode="after")
    def provenance(self):
        if self.resolved and self.resolved.original_text != self.original_text:
            raise ValueError("Original text mismatch")
        if self.model_calls != sum(s.model_call for s in self.trace):
            raise ValueError("Call count mismatch")
        if self.status == "needs_confirmation" and not (
            self.resolved and (self.resolved.result or {}).get("status") == "needs_confirmation"
        ):
            raise ValueError("Missing pending draft")
        return self
