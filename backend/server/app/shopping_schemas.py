"""Public shopping contracts. Actor and purchase state are server-owned."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

Quantity = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=3)]
Name = Annotated[str, Field(min_length=1, max_length=200)]
Unit = Annotated[str, Field(min_length=1, max_length=30)]


class ShoppingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ShoppingItemCreate(ShoppingInput):
    id: UUID | None = None
    source_inventory_item_id: UUID | None = None
    name: Name
    quantity: Quantity
    unit: Unit = "件"


class ShoppingItemUpdate(ShoppingInput):
    source_inventory_item_id: UUID | None = None
    expected_version: str | None = Field(default=None, min_length=64, max_length=64)
    operation_id: UUID | None = None
    name: Name | None = None
    quantity: Quantity | None = None
    unit: Unit | None = None

    @model_validator(mode="after")
    def require_changes(self):
        changes = self.model_fields_set - {'expected_version', 'operation_id'}
        if not changes:
            raise ValueError("Provide at least one field to update")
        if any(getattr(self, key) is None for key in changes - {'source_inventory_item_id'}):
            raise ValueError("Shopping fields cannot be null")
        if ('source_inventory_item_id' in changes or self.operation_id is not None or self.expected_version is not None) and (
                self.operation_id is None or self.expected_version is None):
            raise ValueError('Source updates require operation_id and expected_version')
        return self

    @field_validator('unit')
    @classmethod
    def supported_unit(cls, value):
        from app.services.ai_inventory import UNIT_CANONICAL
        if value is not None and value not in UNIT_CANONICAL and value != '件':
            raise ValueError('Unsupported shopping unit')
        return value


class PurchaseRequest(ShoppingInput):
    actual_quantity: Quantity | None = None
    storage_location: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    expires_on: date | None = None


class ShoppingListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    household_id: UUID
    name: str
    created_at: datetime


class ShoppingItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    shopping_list_id: UUID
    source_inventory_item_id: UUID | None
    name: str
    quantity: Decimal
    unit: str
    added_by_user_id: UUID | None
    purchased_by_user_id: UUID | None
    is_checked: bool
    checked_at: datetime | None
    created_at: datetime

    @computed_field
    @property
    def version(self) -> str:
        from app.services.ledger import digest
        return digest([str(self.id), str(self.source_inventory_item_id), self.name,
            str(self.quantity.normalize()), self.unit, self.is_checked,
            str(self.checked_at), str(self.purchased_by_user_id)])


class ShoppingPage(BaseModel):
    items: list[ShoppingItemResponse]
    total: int
    limit: int
    offset: int


class StockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    household_id: UUID
    name: str
    specification: str | None = None
    category: str | None
    minimum_quantity: Decimal
    history_json: list
    unit: str
    storage_location: str | None
    expires_on: date | None
    purchased_on: date | None
    created_by_user_id: UUID | None
    source_shopping_list_item_id: UUID | None
    status: str
    version: int
    opened_at: date | None = None


class StockCreateResponse(StockResponse):
    created_count: int = 1
    inventory_item_ids: list[UUID] = Field(default_factory=list)


class PurchaseResponse(BaseModel):
    item: ShoppingItemResponse
    inventory_item: StockResponse
    newly_stocked: bool
    created_count: int = 0
    inventory_item_ids: list[UUID] = Field(default_factory=list)
