"""Conversation cursor and request receipts; business tasks remain in ai_tasks."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class ConversationBinding(Base):
    __tablename__ = "ai_conversation_bindings"
    user_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    household_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False)
    task_id: Mapped[UUID | None] = mapped_column(Uuid(), ForeignKey("ai_tasks.id", ondelete="SET NULL"))
    reference_json: Mapped[dict | None] = mapped_column(JSON)
    processing_nonce: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConversationTurn(Base):
    __tablename__ = "ai_conversation_turns"
    __table_args__ = (UniqueConstraint("user_id", "household_id", "request_id", name="uq_conversation_request"),)
    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    household_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey("households.id", ondelete="CASCADE"), nullable=False)
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    task_id: Mapped[UUID | None] = mapped_column(Uuid(), ForeignKey("ai_tasks.id", ondelete="SET NULL"))
    source_revision: Mapped[int | None] = mapped_column(Integer)
    binding_json: Mapped[dict | None] = mapped_column(JSON)
    resolution_json: Mapped[dict | None] = mapped_column(JSON)
    response_json: Mapped[dict | None] = mapped_column(JSON)
    phase: Mapped[str] = mapped_column(String(24), nullable=False, default="resolving")
    processing_nonce: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
