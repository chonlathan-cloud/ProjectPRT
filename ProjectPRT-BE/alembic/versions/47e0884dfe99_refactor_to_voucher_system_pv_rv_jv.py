"""refactor to voucher system PV RV JV

Revision ID: 47e0884dfe99
Revises: 33af957697a1
Create Date: 2025-02-07 ...

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '47e0884dfe99'
down_revision: Union[str, Sequence[str], None] = '33af957697a1' # ⚠️ เช็คว่าตรงกับไฟล์ของคุณ
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. จัดการ Document Type (PS -> PV)
    op.execute("ALTER TYPE document_type RENAME TO document_type_old")
    op.execute("CREATE TYPE document_type AS ENUM('PV', 'RV', 'JV')")
    op.execute("""
        ALTER TABLE documents 
        ALTER COLUMN doc_type TYPE document_type 
        USING (
            CASE doc_type::text
                WHEN 'PS' THEN 'PV'::document_type
                WHEN 'CR' THEN 'RV'::document_type
                WHEN 'DB' THEN 'JV'::document_type
                ELSE 'JV'::document_type
            END
        )
    """)
    op.execute("DROP TYPE document_type_old")

    # 2. จัดการ Counter (Prefix)
    op.execute("ALTER TYPE doc_prefix_type RENAME TO doc_prefix_type_old")
    op.execute("CREATE TYPE doc_prefix_type AS ENUM('PV', 'RV', 'JV')")
    op.execute("""
        ALTER TABLE doc_counters 
        ALTER COLUMN doc_prefix TYPE doc_prefix_type 
        USING (
            CASE doc_prefix::text
                WHEN 'PS' THEN 'PV'::doc_prefix_type
                WHEN 'CR' THEN 'RV'::doc_prefix_type
                WHEN 'DB' THEN 'JV'::doc_prefix_type
                ELSE 'JV'::doc_prefix_type
            END
        )
    """)
    op.execute("DROP TYPE doc_prefix_type_old")

    # 3. จัดการ Case Status
    op.execute("ALTER TYPE case_status RENAME TO case_status_old")
    op.execute("CREATE TYPE case_status AS ENUM('DRAFT', 'SUBMITTED', 'APPROVED', 'REJECTED', 'PAID', 'CLOSED', 'CANCELLED')")
    op.execute("""
        ALTER TABLE cases 
        ALTER COLUMN status TYPE case_status 
        USING (
            CASE status::text
                WHEN 'PS_APPROVED' THEN 'APPROVED'::case_status
                ELSE status::text::case_status
            END
        )
    """)
    op.execute("DROP TYPE case_status_old")

    # 4. เพิ่ม Column และ Table ใหม่
    op.add_column('cases', sa.Column('deposit_account_id', sa.UUID(), nullable=True))
    op.add_column('cases', sa.Column('is_receipt_uploaded', sa.Boolean(), server_default='false', nullable=False))
    op.create_foreign_key('fk_cases_deposit_account', 'cases', 'categories', ['deposit_account_id'], ['id'], ondelete='RESTRICT')

    op.create_table('jv_line_items',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('jv_document_id', sa.UUID(), nullable=False),
        sa.Column('ref_case_id', sa.UUID(), nullable=False),
        sa.Column('amount', sa.Numeric(18, 2), nullable=False),
        sa.ForeignKeyConstraint(['jv_document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['ref_case_id'], ['cases.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('jv_line_items')
    op.drop_constraint('fk_cases_deposit_account', 'cases', type_='foreignkey')
    op.drop_column('cases', 'is_receipt_uploaded')
    op.drop_column('cases', 'deposit_account_id')