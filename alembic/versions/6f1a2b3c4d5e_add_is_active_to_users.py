"""add is_active to users

Revision ID: 6f1a2b3c4d5e
Revises: 521b4999a17c
Create Date: 2026-01-16 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6f1a2b3c4d5e"
down_revision: Union[str, Sequence[str], None] = "521b4999a17c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "is_active")
