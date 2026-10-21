from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Amount = Annotated[Decimal, Field(ge=0, le=1_000_000_000, max_digits=16, decimal_places=6)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class InventoryCreate(Input):
    id: UUID
    name: str = Field(min_length=1, max_length=200)
    quantity: Amount
    unit: str = Field(min_length=1, max_length=30)
    category: str = Field(default="其他", min_length=1, max_length=64)
    storage_location: str = Field(min_length=1, max_length=100)
    minimum_quantity: Amount = Decimal(0)
    expires_on: date | None = None
    purchased_on: date | None = None


class Versioned(Input):
    expected_version: int = Field(ge=1)
    operation_id: UUID


class InventoryUpdate(Versioned):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    quantity: Amount | None = None
    unit: str | None = Field(default=None, min_length=1, max_length=30)
    category: str | None = Field(default=None, min_length=1, max_length=64)
    storage_location: str | None = Field(default=None, min_length=1, max_length=100)
    minimum_quantity: Amount | None = None
    expires_on: date | None = None
    purchased_on: date | None = None

    @model_validator(mode="after")
    def valid_changes(self):
        changes = self.model_fields_set - {"expected_version", "operation_id"}
        if not changes:
            raise ValueError("Provide changes")
        for key in changes - {"expires_on", "purchased_on"}:
            if getattr(self, key) is None:
                raise ValueError("Field cannot be null")
        return self


class Adjustment(Versioned):
    delta: Decimal = Field(ge=-1_000_000_000, le=1_000_000_000, max_digits=16, decimal_places=6)

    @model_validator(mode="after")
    def nonzero(self):
        if self.delta == 0:
            raise ValueError("Adjustment cannot be zero")
        return self
