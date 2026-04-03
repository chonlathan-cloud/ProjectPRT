"""add ASSET to category_type enum

Revision ID: da576ab2e532
Revises: 4d1c2ef7bb6f
Create Date: 2025-02-06 ...

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'da576ab2e532'
down_revision: Union[str, Sequence[str], None] = '7c9a1c3e2f4d' # ตรวจสอบให้แน่ใจว่า revision ก่อนหน้า (down_revision) ตรงกับไฟล์ล่าสุดของคุณ
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # สั่งให้ PostgreSQL เพิ่มค่า 'ASSET' เข้าไปใน Enum ที่ชื่อ 'category_type'
    # เราต้องใช้ commit_block() เพราะ PostgreSQL ห้ามรัน ALTER TYPE ใน transaction ปกติ
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE category_type ADD VALUE 'ASSET'")


def downgrade() -> None:
    # PostgreSQL ไม่รองรับการลบค่าออกจาก ENUM ง่ายๆ
    # ดังนั้นขาถอยหลัง (Downgrade) เราจะปล่อยผ่าน
    pass