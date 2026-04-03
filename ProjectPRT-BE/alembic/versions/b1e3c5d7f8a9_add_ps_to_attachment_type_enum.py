"""add PS to attachment_type enum

Revision ID: b1e3c5d7f8a9
Revises: 8b7c6d5e4f3a
Create Date: 2026-02-04

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b1e3c5d7f8a9"
down_revision: Union[str, Sequence[str], None] = "8b7c6d5e4f3a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE attachment_type ADD VALUE IF NOT EXISTS 'PS'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values safely.
    pass
