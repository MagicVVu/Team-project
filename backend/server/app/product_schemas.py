from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.services.ai_inventory import UNIT_CANONICAL


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    id: UUID
    name: str = Field(min_length=1, max_length=200, pattern=r'\S')
    specification: str | None = Field(default=None, max_length=200)
    base_unit: str
    category: Literal['food', 'medicine', 'household', 'unknown'] = 'unknown'
    tags: list[str] = Field(default_factory=list, max_length=30)
    source: str = Field(min_length=1, max_length=200, pattern=r'\S')

    @field_validator('base_unit')
    @classmethod
    def unit(cls, value):
        if value not in UNIT_CANONICAL:
            raise ValueError('Unsupported base unit')
        return UNIT_CANONICAL[value]

    @field_validator('tags')
    @classmethod
    def bounded_tags(cls, values):
        if any(not v.strip() or len(v) > 80 for v in values):
            raise ValueError('Invalid product tag')
        return values


class ProductLink(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    operation_id: UUID
    expected_inventory_version: int = Field(ge=1, strict=True)
    product_id: UUID | None  # Explicit null unlinks; omission is rejected.
    source: str = Field(min_length=1, max_length=200, pattern=r'\S')
