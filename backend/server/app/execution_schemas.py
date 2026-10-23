"""Business-owned confirmation DTOs; AI previews and protected fields are not inputs."""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator, field_validator
from app.shopping_schemas import StockResponse


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DraftRevision(Input):
    draft_revision: int = Field(ge=1, strict=True)
    task_revision: int = Field(ge=1, strict=True)


class CommitRequest(DraftRevision):
    operation_id: UUID
    edits: dict[str, JsonValue] = Field(default_factory=dict, max_length=6)


class PreviewRequest(DraftRevision):
    edits: dict[str, JsonValue] = Field(default_factory=dict, max_length=6)


Quantity = Annotated[Decimal, Field(gt=0, le=1_000_000_000, max_digits=16, decimal_places=6)]
ShoppingQuantity = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=3)]
Name = Annotated[str, Field(min_length=1, max_length=200)]
Unit = Annotated[str, Field(min_length=1, max_length=30)]
Location = Annotated[str, Field(min_length=1, max_length=100)]


class AddFields(Input):
    name: Name
    quantity: Quantity
    unit: Unit
    location: Location
    purchased_at: date | None = None
    label_expiry: date | None = None

    @model_validator(mode="after")
    def dates(self):
        if self.purchased_at and self.label_expiry and self.label_expiry < self.purchased_at:
            raise ValueError("Expiry cannot precede purchase")
        return self


class MoveFields(Input):
    to_location: Location


class ConsumeFields(Input):
    quantity: Quantity
    unit: Unit


class OpenFields(Input):
    opened_at: date

    @field_validator("opened_at", mode="before")
    @classmethod
    def date_only(cls, value):
        if type(value) is date or (isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)):
            return value
        raise ValueError("Use an ISO calendar date")


class DiscardFields(Input):
    discard_mode: Literal["partial", "all"]
    quantity: Quantity
    unit: Unit


class PlanFields(Input):
    quantity: ShoppingQuantity
    unit: Unit


class Target(Input):
    name: Name
    batch_id: UUID
    expected_version: int = Field(ge=1, strict=True)


class OpenCommand(Target, OpenFields):
    action: Literal["OPEN"]


class DiscardCommand(Target, DiscardFields):
    action: Literal["DISCARD"]


class ExecutionPreview(BaseModel):
    draft_id: UUID
    task_id: UUID
    draft_revision: int
    task_revision: int
    command: Annotated[OpenCommand | DiscardCommand, Field(discriminator="action")]
    before: StockResponse
    after: StockResponse
    event_type: Literal["Opened", "Discarded"]
    event_quantity: Decimal | None
    quantity_source: Literal["current_batch", "user_input"] | None
    expires_at: str
    prospective: Literal[True] = True
    inventory_written: Literal[False] = False


class ExecutionDetails(BaseModel):
    before: StockResponse
    after: StockResponse
    event_type: Literal["Opened", "Discarded"]
    quantity: Decimal | None
    unit: str
    discard_mode: Literal["partial", "all"] | None
    quantity_source: Literal["current_batch", "user_input"] | None


class OperationReceipt(BaseModel):
    protocol_version: Literal["draft-operation-receipt-1"]
    operation_id: UUID
    draft_id: UUID
    task_id: UUID
    draft_revision: int
    task_revision: int
    scope: dict[str, UUID]
    status: Literal["committed"]
    action: Literal["ADD", "MOVE", "CONSUME", "PLAN_ADD", "OPEN", "DISCARD"]
    committed_at: datetime
    trace_id: str
    batch_versions: dict[str, int]
    event_ids: list[UUID]
    inventory_written: bool
    shopping_written: bool
    result: dict[str, JsonValue]
    execution: ExecutionDetails | None = None


class ReferenceMessage(Input):
    """Reserved selector for the separately gated trusted-reference adapter."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    household_id: UUID
    text: str = Field(min_length=1, max_length=1000, pattern=r"\S")
    request_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")
    household_timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)
    source_task_id: UUID
    source_revision: int = Field(ge=1, strict=True)
    batch_id: UUID
