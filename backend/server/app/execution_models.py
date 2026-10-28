"""Additive execution ledger; legacy task and draft states remain unchanged."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DraftOperation(Base):
    __tablename__ = "draft_operations"
    __table_args__ = (
        CheckConstraint("draft_revision >= 1 AND task_revision >= 1", name="ck_operation_revisions"),
        CheckConstraint("action IN ('ADD','MOVE','PLAN_ADD','CONSUME','OPEN','DISCARD')", name="ck_operation_action"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    draft_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("ai_drafts.id", ondelete="RESTRICT"), unique=True, nullable=False)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    household_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("households.id", ondelete="RESTRICT"), nullable=False, index=True)
    draft_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    task_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    command_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    receipt_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    committed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DraftDecision(Base):
    __tablename__ = "draft_decisions"
    __table_args__ = (
        CheckConstraint("draft_revision >= 1 AND task_revision >= 1", name="ck_decision_revisions"),
        CheckConstraint("(status = 'committed' AND operation_id IS NOT NULL) OR (status = 'cancelled' AND operation_id IS NULL)", name="ck_decision_status"),
    )
    draft_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("ai_drafts.id", ondelete="RESTRICT"), primary_key=True)
    draft_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    task_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    operation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("draft_operations.id", ondelete="RESTRICT"), unique=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class BusinessEvent(Base):
    """One durable semantic event per committed action; only Consumed is consumption."""
    __tablename__ = "business_events"
    __table_args__ = (
        CheckConstraint("event_type IN ('StockAdded','StockMoved','PlanAdded','Consumed','Opened','Discarded','Created','Adjusted','Purchased','Edited','Corrected','ProductLinked','Counted','Archived')", name="ck_business_event_type"),
        CheckConstraint("(event_type IN ('StockMoved','Opened') AND quantity IS NULL) OR (event_type IN ('StockAdded','PlanAdded','Consumed','Discarded') AND quantity IS NOT NULL AND quantity > 0 AND quantity <= 1000000000) OR (event_type IN ('Created','Adjusted','Purchased','Edited','Corrected','ProductLinked','Counted','Archived') AND (quantity IS NULL OR (quantity >= 0 AND quantity <= 1000000000)))", name="ck_business_event_quantity"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    operation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("draft_operations.id", ondelete="RESTRICT"), unique=True, nullable=True)
    request_id: Mapped[UUID | None] = mapped_column(Uuid(), ForeignKey('mutation_receipts.operation_id', ondelete='RESTRICT'), unique=True)
    related_event_id: Mapped[UUID | None] = mapped_column(Uuid(), ForeignKey('business_events.id', ondelete='RESTRICT'))
    product_id: Mapped[UUID | None] = mapped_column(Uuid(), ForeignKey('products.id', ondelete='RESTRICT'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    household_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("households.id", ondelete="RESTRICT"), nullable=False, index=True)
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    inventory_item_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("inventory_items.id", ondelete="RESTRICT"))
    shopping_item_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("shopping_list_items.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(16, 6))
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    before_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    after_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
