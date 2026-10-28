"""Additive read adapters; no task storage or business transaction redesign."""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, JsonValue


class SharedOperationSummary(BaseModel):
    protocol_version: Literal["household-operation-summary-1"] = "household-operation-summary-1"
    operation_id: UUID
    household_id: UUID
    actor_user_id: UUID
    action: str
    event_id: UUID
    event_type: str
    inventory_item_id: UUID | None
    shopping_item_id: UUID | None
    name: str | None
    quantity: Decimal | None
    unit: str | None
    occurred_at: datetime
    before: dict[str, JsonValue]
    after: dict[str, JsonValue]


class OperationFeedback(BaseModel):
    protocol_version: Literal["operation-feedback-1"] = "operation-feedback-1"
    operation_id: UUID
    business_committed: Literal[True] = True
    feedback_status: Literal["available", "partial", "unavailable", "not_applicable"]
    reason_code: str | None = None
    message: str
    result: dict[str, JsonValue] | None = None
    inventory_written: Literal[False] = False
    shopping_written: Literal[False] = False


class CompatibilityIssue(BaseModel):
    batch_id: UUID
    inventory_version: int
    field: str
    code: Literal["AI_INVENTORY_INCOMPATIBLE"] = "AI_INVENTORY_INCOMPATIBLE"
    message: str
    manual_action: str = "请在库存详情核对原始资料并显式修正；不会自动换算或忽略该记录。"


class CompatibilityPage(BaseModel):
    issues: list[CompatibilityIssue]
    total: int
    scanned_count: int
    limit: int
    offset: int
    next_offset: int | None
    page_compatible: bool
    scope: Literal["page_only"] = "page_only"
