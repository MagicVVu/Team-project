"""Explicit observations only: omitted sections stay unchanged; null clears them."""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from app.services.ai_inventory import UNIT_CANONICAL


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


Amount = Annotated[Decimal, Field(ge=0, le=1_000_000_000, max_digits=16, decimal_places=6)]
Positive = Annotated[Decimal, Field(gt=0, le=1_000_000_000, max_digits=16, decimal_places=6)]


class PlanningPreferences(Model):
    minimum_stock: Amount | None = None
    coverage_days: int | None = Field(default=None, ge=1, le=365, strict=True)
    lead_days: int | None = Field(default=None, ge=0, le=365, strict=True)
    order_unit: str | None = Field(default=None, min_length=1, max_length=20)
    pack_size: Positive | None = None

    @field_validator("order_unit")
    @classmethod
    def unit(cls, value):
        if value is not None and value not in UNIT_CANONICAL:
            raise ValueError("Unsupported order unit")
        return UNIT_CANONICAL.get(value) if value is not None else None

    @model_validator(mode="after")
    def paired_package(self):
        if (self.order_unit is None) != (self.pack_size is None):
            raise ValueError("order_unit and pack_size must be provided together")
        return self


class RecordingDay(Model):
    day: date
    records_complete: StrictBool
    stockout: StrictBool
    unexplained_adjustment: StrictBool

    @field_validator("day", mode="before")
    @classmethod
    def calendar_date(cls, value):
        if isinstance(value, datetime) or not isinstance(value, (str, date)):
            raise ValueError("Use a calendar date in YYYY-MM-DD format")
        if isinstance(value, str) and (len(value) != 10 or value[4] != "-" or value[7] != "-"):
            raise ValueError("Use a calendar date in YYYY-MM-DD format")
        return value


class StockCount(Model):
    quantity: Amount
    unit: str = Field(min_length=1, max_length=20)

    @field_validator("unit")
    @classmethod
    def canonical_unit(cls, value):
        if value not in UNIT_CANONICAL:
            raise ValueError("Unsupported inventory unit")
        return UNIT_CANONICAL[value]


class RiskFacts(Model):
    category: Literal["food", "medicine", "household", "unknown"] = "unknown"
    label_date_type: Literal["use_by", "best_before", "expiry", "unknown"] = "unknown"
    label_context_valid: StrictBool | None = None
    storage_condition: Literal["ambient", "refrigerated", "frozen"] | None = None
    label_storage_condition: Literal["ambient", "refrigerated", "frozen"] | None = None
    is_opened: StrictBool | None = None


class PlanningFactsPatch(Model):
    operation_id: UUID
    expected_inventory_version: int = Field(ge=1, strict=True)
    expected_facts_version: int = Field(ge=0, strict=True)
    source: str = Field(min_length=1, max_length=200, pattern=r"\S")
    preferences: PlanningPreferences | None = None
    coverage: list[RecordingDay] | None = Field(default=None, min_length=1, max_length=366)
    stock_verification: StockCount | None = None
    risk_facts: RiskFacts | None = None

    @model_validator(mode="after")
    def explicit_sections(self):
        if not self.model_fields_set & {"preferences", "coverage", "stock_verification", "risk_facts"}:
            raise ValueError("Provide at least one facts section")
        if "coverage" in self.model_fields_set:
            if self.coverage is None:
                raise ValueError("Revoke coverage explicitly using records_complete=false")
            if len({row.day for row in self.coverage}) != len(self.coverage):
                raise ValueError("Duplicate coverage days")
        return self


class VerifiedStock(StockCount):
    checked_at: datetime
    source: str
    inventory_version: int


class PlanningFactsResponse(Model):
    protocol_version: Literal["backend-planning-facts-1"] = "backend-planning-facts-1"
    household_id: UUID
    inventory_item_id: UUID
    inventory_version: int
    facts_version: int
    household_timezone: str
    preferences: PlanningPreferences | None
    coverage: list[RecordingDay]
    stock_verification: VerifiedStock | None
    risk_facts: RiskFacts | None
    invalidated_sections: list[str]
    provenance: dict
    inventory_written: Literal[False] = False
