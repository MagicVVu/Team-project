"""P8.3: typed, read-only extensions to the deployed backend planning envelope."""
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal
from pydantic import AwareDatetime, ConfigDict, Field, model_validator
from p0.schemas import Model
from p1.schemas import Unit
from p3.schemas import Query
from v1.schemas import PlanningSnapshot


class Basis(Model):
    # Exact keys: backend compares set(basis) as well as every value.
    protocol_version: Literal["planning-revalidation-1"]
    snapshot_id: str = Field(min_length=1)
    event_watermark: str = Field(min_length=1)
    shopping_version: int = Field(strict=True, ge=1)
    inventory_versions: dict[str, Annotated[int, Field(strict=True, ge=1)]]
    facts_versions: dict[str, Annotated[int, Field(strict=True, ge=0)]]
    product_versions: dict[str, Annotated[int, Field(strict=True, ge=1)]]
    risk_rules: dict[str, Any]

    @model_validator(mode="after")
    def versions(self):
        for mapping, minimum in ((self.inventory_versions, 1), (self.facts_versions, 0), (self.product_versions, 1)):
            if any(not key or type(value) is not int or value < minimum for key, value in mapping.items()):
                raise ValueError("Invalid basis versions")
        return self


class AggregateBatch(Model):
    batch_id: str
    version: int = Field(strict=True, ge=1)
    quantity: Decimal = Field(ge=0, le=1_000_000_000)
    unit: Unit
    base_quantity: Decimal | None
    location: str | None
    label_expiry: date | None
    opened_at: date | None
    status: Literal["ACTIVE", "FINISHED", "REVERSED", "DISCARDED"]
    expired: bool
    expiry_known: bool
    facts_version: int = Field(strict=True, ge=0)
    stock_verification: dict[str, Any] | None
    mapping_status: Literal["household_attested"]


class Product(Model):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)
    product_id: str
    item_key: str
    name: str
    specification: str | None
    base_unit: Unit
    category: str
    version: int = Field(strict=True, ge=1)
    identity_status: Literal["household_attested"]
    tag_source: Literal["household_attested"]
    platform_rule_review_status: str
    batches: list[AggregateBatch] = Field(max_length=1000)
    quantity_complete: bool
    total_quantity: Decimal | None = Field(ge=0)
    nonexpired_active_quantity: Decimal | None = Field(ge=0)
    usable_quantity: None
    consumption_coverage_days: None
    version_token: str = Field(min_length=1)


class Provenance(Model):
    model_config = ConfigDict(extra="allow", allow_inf_nan=False)
    schema_version: Literal["backend-planning-provenance-1"]
    pending_state: Literal["none", "association_unknown", "linked_complete", "shopping_list_missing"]
    pending_count: int = Field(strict=True, ge=0, le=10000)
    product_aggregates_v1: list[Product] = Field(max_length=1000)
    revalidation_basis: Basis
    events: dict[str, dict[str, Any]] = Field(max_length=20000)
    ledger_coverage: str
    risk_rules: dict[str, Any]


class BackendSnapshot(PlanningSnapshot):
    provenance: Provenance


class ProductPlanning(Model):
    product: Product
    as_of: AwareDatetime
    window_start: date
    window_end_exclusive: date
    recorded_consumption_quantity: Decimal | None
    recorded_consumption_event_ids: list[str]
    pending_quantity: Decimal | None
    # The current backend deliberately provides no product-wide coverage,
    # preferences, reviewed usability or stock-verification policy.
    forecast_status: Literal["unavailable"] = "unavailable"
    remaining_days: None = None
    reference_date: None = None
    suggested_quantity: None = None
    reason_codes: list[str]


class PlanningContext(Model):
    protocol_version: Literal["p83-planning-adapter-1"] = "p83-planning-adapter-1"
    pending_state: Literal["none", "association_unknown", "linked_complete", "shopping_list_missing"]
    pending_count: int
    pending_complete: bool
    ledger_coverage: str
    history_complete_means: Literal["stored_events_only_not_daily_coverage"] = "stored_events_only_not_daily_coverage"
    automatic_planning_commit: Literal[False] = False
    manual_plan_only: Literal[True] = True
    revalidation_basis: Basis


class RevalidationDiagnostic(Model):
    model_config = ConfigDict(extra="allow")
    protocol_version: Literal["planning-revalidation-1"]
    status: Literal["stale", "blocked"]
    mismatches: list[str]
    blockers: list[str]
    current_basis: Basis
    inventory_written: Literal[False]
    shopping_written: Literal[False]
    automatic_planning_commit: Literal[False]


class RevalidationRequest(Model):
    original_basis: Basis
    query: Query
    diagnostic: RevalidationDiagnostic | None = None


class PlanningReview(Model):
    status: Literal["stale", "blocked"]
    mismatches: list[str]
    blockers: list[str]
    original_basis: Basis
    current_basis: Basis
    regenerated: Literal[True] = True
    automatic_planning_commit: Literal[False] = False
