"""Persist read-only AI messages, continuation state, and unconfirmed drafts.

Revision ID: 20261014_0005
Revises: 20261014_0004

No inventory, shopping list, user, or previous migration data is altered.
"""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = '20261014_0005'
down_revision: str | None = '20261014_0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('ai_tasks',
        sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column('user_id', sa.Uuid(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('household_id', sa.Uuid(as_uuid=True), sa.ForeignKey('households.id', ondelete='CASCADE'), nullable=False),
        sa.Column('request_id', sa.String(100), nullable=False),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('original_text', sa.Text(), nullable=False),
        sa.Column('household_timezone', sa.String(64), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('processing_nonce', sa.String(36), nullable=True),
        sa.Column('lease_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('result_json', sa.JSON(), nullable=True),
        sa.Column('context_json', sa.JSON(), nullable=True),
        sa.Column('revision', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', 'household_id', 'request_id', name='uq_ai_task_request'),
        sa.CheckConstraint('revision >= 1', name='ck_ai_task_revision'),
        sa.CheckConstraint("status IN ('processing','needs_clarification','needs_confirmation','answered','unsupported','error')", name='ck_ai_task_status'),
    )
    op.create_index('ix_ai_tasks_home_user', 'ai_tasks', ['household_id', 'user_id'])
    op.create_table('ai_drafts',
        sa.Column('id', sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column('task_id', sa.Uuid(as_uuid=True), sa.ForeignKey('ai_tasks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Uuid(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('household_id', sa.Uuid(as_uuid=True), sa.ForeignKey('households.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(16), nullable=False, server_default=sa.text("'pending'")),
        sa.Column('revision', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('command_json', sa.JSON(), nullable=False),
        sa.Column('preview_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('task_id', name='uq_ai_drafts_task'),
        sa.CheckConstraint("status IN ('pending','superseded')", name='ck_ai_drafts_status'),
        sa.CheckConstraint('revision >= 1', name='ck_ai_drafts_revision'),
    )
    op.create_index('ix_ai_drafts_home_user', 'ai_drafts', ['household_id', 'user_id'])


def downgrade() -> None:
    """Do not run on production: deletes persisted AI tasks and drafts."""
    op.drop_index('ix_ai_drafts_home_user', table_name='ai_drafts')
    op.drop_table('ai_drafts')
    op.drop_index('ix_ai_tasks_home_user', table_name='ai_tasks')
    op.drop_table('ai_tasks')
