"""Durable notification delivery claims.

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("alter table notifications add column locked_by text, add column locked_at timestamptz")


def downgrade() -> None:
    op.execute("alter table notifications drop column locked_by, drop column locked_at")
