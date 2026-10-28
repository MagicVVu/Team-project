"""Household attestations identify products; they are never platform risk rules."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Product(Base):
    __tablename__ = 'products'
    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True, default=uuid4)
    household_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey('households.id', ondelete='RESTRICT'), index=True)
    name: Mapped[str] = mapped_column(String(80))
    specification: Mapped[str | None] = mapped_column(String(200))
    base_unit: Mapped[str] = mapped_column(String(30))
    category: Mapped[str] = mapped_column(String(20))
    tags_json: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(200))
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey('users.id', ondelete='RESTRICT'))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProductBatch(Base):
    __tablename__ = 'product_batches'
    inventory_item_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey('inventory_items.id', ondelete='RESTRICT'), primary_key=True)
    product_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey('products.id', ondelete='RESTRICT'), index=True)
    source: Mapped[str] = mapped_column(String(200))
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey('users.id', ondelete='RESTRICT'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MutationReceipt(Base):
    """Durable retries for existing CRUD operation IDs; not another draft executor."""
    __tablename__ = 'mutation_receipts'
    operation_id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    household_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey('households.id', ondelete='RESTRICT'), index=True)
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey('users.id', ondelete='RESTRICT'))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
