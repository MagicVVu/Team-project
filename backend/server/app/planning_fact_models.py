"""User-attested planning facts and durable, scoped write receipts."""
from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InventoryPlanningFacts(Base):
    __tablename__ = "inventory_planning_facts"
    __table_args__ = (CheckConstraint("version >= 1", name="ck_planning_facts_version"),)

    inventory_item_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey("inventory_items.id", ondelete="CASCADE"), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    facts_json: Mapped[dict] = mapped_column(JSON, nullable=False)


class PlanningFactWrite(Base):
    __tablename__ = "planning_fact_writes"

    operation_id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    inventory_item_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey("inventory_items.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    household_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
