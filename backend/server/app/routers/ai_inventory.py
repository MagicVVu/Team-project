"""Internal-only, read-only endpoints for the AI P1 RemoteInventoryReader.

The service token authenticates the calling *service*, not the identity headers.
We also check that the user is active and a member of the claimed household,
and filter each resource by that household. Token configured via Compose env.
"""
from __future__ import annotations

import os
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import HouseholdMember, InventoryItem, User
from app.planning_fact_models import InventoryPlanningFacts
from app.services.ai_inventory import IncompatibleInventory, to_p1_batch

router = APIRouter(prefix="/internal/v1/inventory", tags=["Internal AI Inventory"])


def with_risk_facts(item, profile):
    batch = to_p1_batch(item)
    if profile is not None and (profile.facts_json or {}).get("risk_facts"):
        from app.services.planning_facts import identity, risk_fields
        saved = profile.facts_json["risk_facts"]
        if saved["inventory_identity"] == identity(item, "risk_facts"):
            batch.update(risk_fields(item, {"risk_facts": saved["value"]}))
    return batch


def _authorize(
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_household_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> UUID:
    expected = os.environ.get("BACKEND_TOOL_TOKEN", "")
    if not expected or not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid tool authorization")
    received = authorization[7:]
    if not received or not secrets.compare_digest(received, expected):
        raise HTTPException(status_code=401, detail="Invalid tool authorization")
    try:
        user_id = UUID(x_user_id or "")
        household_id = UUID(x_household_id or "")
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="Inventory scope not found") from None
    authorized = db.scalar(
        select(HouseholdMember.user_id)
        .join(User, HouseholdMember.user_id == User.id)
        .where(
            HouseholdMember.user_id == user_id,
            HouseholdMember.household_id == household_id,
            User.is_active.is_(True),
        )
    )
    if authorized is None:
        raise HTTPException(status_code=404, detail="Inventory scope not found")
    return household_id


@router.get("/search")
def search_batches(
    name: str | None = Query(default=None, max_length=200),
    household_id: UUID = Depends(_authorize),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(InventoryItem).where(InventoryItem.household_id == household_id)
    if name is not None:
        value = name.strip()
        if not value:
            raise HTTPException(status_code=422, detail="name cannot be blank")
        # SQLAlchemy autoescape prevents '%' and '_' from acting as LIKE wildcards.
        stmt = stmt.where(func.lower(InventoryItem.name).contains(value.lower(), autoescape=True))
    # A deterministic full result is required; fail rather than silently truncate.
    rows = db.scalars(stmt.order_by(InventoryItem.created_at.asc(), InventoryItem.id.asc()).limit(1001)).all()
    if len(rows) > 1000:
        raise HTTPException(status_code=409, detail="Too many batches for P1 tool; narrow inventory query")
    try:
        profiles = {p.inventory_item_id: p for p in db.scalars(select(InventoryPlanningFacts)
            .where(InventoryPlanningFacts.inventory_item_id.in_([row.id for row in rows]))).all()}
        batches = [with_risk_facts(row, profiles.get(row.id)) for row in rows]
    except IncompatibleInventory as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    return {"data": {"batches": batches}}


@router.get("/batches/{batch_id}")
def get_batch(
    batch_id: UUID,
    household_id: UUID = Depends(_authorize),
    db: Session = Depends(get_db),
) -> dict:
    item = db.scalar(select(InventoryItem).where(
        InventoryItem.id == batch_id,
        InventoryItem.household_id == household_id,
    ))
    if item is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    try:
        batch = with_risk_facts(item, db.get(InventoryPlanningFacts, item.id))
    except IncompatibleInventory as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    return {"data": {"batch": batch}}
