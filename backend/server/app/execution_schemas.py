"""Business-owned confirmation DTOs; AI previews and protected fields are not inputs."""
from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DraftRevision(Input):
    draft_revision: int = Field(ge=1, strict=True)
    task_revision: int = Field(ge=1, strict=True)


class CommitRequest(DraftRevision):
    operation_id: UUID
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


class PlanFields(Input):
    quantity: ShoppingQuantity
    unit: Unit


class Target(Input):
    name: Name
    batch_id: UUID
    expected_version: int = Field(ge=1, strict=True)


class ReferenceMessage(Input):
<<<<<<< HEAD
<<<<<<< HEAD
    """Public selector; identity and validity are always supplied by the backend."""
<<<<<<< Updated upstream
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    household_id: UUID
    text: str = Field(min_length=1, max_length=1000, pattern=r'\S')
=======
    household_id: UUID
    text: str = Field(min_length=1, max_length=1000)
>>>>>>> Stashed changes
    request_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")
    household_timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)
=======
    """Reserved adapter input, deliberately unavailable until source binding ships."""
    household_id: UUID
    text: str = Field(min_length=1, max_length=1000)
    request_id: str = Field(min_length=1, max_length=100)
    household_timezone: str = "Asia/Shanghai"
>>>>>>> parent of 3aa98be (feat: integrate P72 clarification references and open discard execution)
=======
    """Reserved adapter input, deliberately unavailable until source binding ships."""
    household_id: UUID
    text: str = Field(min_length=1, max_length=1000)
    request_id: str = Field(min_length=1, max_length=100)
    household_timezone: str = "Asia/Shanghai"
>>>>>>> parent of 3aa98be (feat: integrate P72 clarification references and open discard execution)
    source_task_id: UUID
    source_revision: int = Field(ge=1, strict=True)
    batch_id: UUID
