"""add reject_reason and rejected_at to cases

Revision ID: 8b7c6d5e4f3a
Revises: 6f1a2b3c4d5e
Create Date: 2026-01-19 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8b7c6d5e4f3a"
down_revision: Union[str, Sequence[str], None] = "6f1a2b3c4d5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("reject_reason", sa.Text(), nullable=True))
    op.add_column("cases", sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("cases", "rejected_at")
    op.drop_column("cases", "reject_reason")
