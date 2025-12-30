import uuid
import datetime
import enum
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Numeric, UniqueConstraint, Text
from sqlalchemy.dialects.postgresql import UUID, ENUM, JSONB
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()

# --- Enums ---
class CategoryType(enum.Enum):
    # spec: categories.type
    EXPENSE = "EXPENSE"
    REVENUE = "REVENUE"
    ASSET = "ASSET" # Added for future use

class FundingType(enum.Enum):
    # spec: cases.funding_type
    OPERATING = "OPERATING"
    GOV_BUDGET = "GOV_BUDGET"

class CaseStatus(enum.Enum):
    # spec: cases.status
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    PS_APPROVED = "PS_APPROVED"
    PS_REJECTED = "PS_REJECTED"
    CR_ISSUED = "CR_ISSUED"
    PAID = "PAID"
    SETTLEMENT_SUBMITTED = "SETTLEMENT_SUBMITTED"
    DB_ISSUED = "DB_ISSUED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"

class DocumentType(enum.Enum):
    # spec: documents.doc_type, doc_counters.doc_prefix
    PS = "PS"
    CR = "CR"
    DB = "DB"

class PaymentType(enum.Enum):
    # spec: payments.type
    DISBURSE = "DISBURSE"
    REFUND = "REFUND"
    ADDITIONAL = "ADDITIONAL"

class AttachmentType(enum.Enum):
    # spec: attachments.type
    QUOTE = "QUOTE"
    RECEIPT = "RECEIPT"
    OTHER = "OTHER"

# --- Models ---

class Category(Base):
    # spec: categories table
    __tablename__ = 'categories'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4) # spec: id (PK, UUID)
    name_th = Column(String, unique=True, nullable=False) # spec: name_th (VARCHAR, UNIQUE, NOT NULL)
    type = Column(ENUM(CategoryType, name='category_type', create_type=False), nullable=False) # spec: type (ENUM 'EXPENSE', 'REVENUE', NOT NULL)
    account_code = Column(String, unique=True, nullable=False) # spec: account_code (VARCHAR, UNIQUE, NOT NULL)
    is_active = Column(Boolean, default=True, nullable=False) # spec: is_active (BOOLEAN, DEFAULT TRUE, NOT NULL)
    created_by = Column(String, nullable=False) # spec: created_by (VARCHAR, NOT NULL)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False) # spec: created_at (TIMESTAMP WITH TIME ZONE, DEFAULT NOW(), NOT NULL)
    updated_by = Column(String, nullable=True) # spec: updated_by (VARCHAR)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True) # spec: updated_at (TIMESTAMP WITH TIME ZONE)

    cases = relationship("Case", back_populates="category")

    def __repr__(self):
        return f"<Category(name_th='{self.name_th}', type='{self.type.value}', account_code='{self.account_code}')>"

class Case(Base):
    # spec: cases table
    __tablename__ = 'cases'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4) # spec: id (PK, UUID)
    case_no = Column(String, unique=True, nullable=False) # spec: case_no (VARCHAR, UNIQUE, NOT NULL)
    category_id = Column(UUID(as_uuid=True), ForeignKey('categories.id', ondelete='RESTRICT'), nullable=False) # spec: category_id (FK to categories.id, UUID, NOT NULL)
    account_code = Column(String, nullable=False) # spec: account_code (VARCHAR, NOT NULL) -- Denormalized from category for immutability
    requester_id = Column(String, nullable=False) # spec: requester_id (VARCHAR, NOT NULL)
    department_id = Column(String, nullable=True) # spec: department_id (VARCHAR)
    cost_center_id = Column(String, nullable=True) # spec: cost_center_id (VARCHAR)
    funding_type = Column(ENUM(FundingType, name='funding_type', create_type=False), default=FundingType.OPERATING, nullable=False) # spec: funding_type (ENUM 'OPERATING', 'GOV_BUDGET', DEFAULT 'OPERATING', NOT NULL)
    requested_amount = Column(Numeric(18, 2), nullable=False) # spec: requested_amount (NUMERIC(18, 2), NOT NULL)
    purpose = Column(Text, nullable=False) # plan.md: purpose (TEXT, NOT NULL) for audit-friendly descriptions
    status = Column(ENUM(CaseStatus, name='case_status', create_type=False), nullable=False) # spec: status (ENUM 'DRAFT', ..., 'CANCELLED', NOT NULL)
    created_by = Column(String, nullable=False) # spec: created_by (VARCHAR, NOT NULL)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False) # spec: created_at (TIMESTAMP WITH TIME ZONE, DEFAULT NOW(), NOT NULL)
    updated_by = Column(String, nullable=True) # spec: updated_by (VARCHAR)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True) # spec: updated_at (TIMESTAMP WITH TIME ZONE)

    category = relationship("Category", back_populates="cases")
    documents = relationship("Document", back_populates="case")
    payments = relationship("Payment", back_populates="case")
    attachments = relationship("Attachment", back_populates="case")

    def __repr__(self):
        return f"<Case(case_no='{self.case_no}', status='{self.status.value}')>"

class Document(Base):
    # spec: documents table
    __tablename__ = 'documents'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4) # spec: id (PK, UUID)
    case_id = Column(UUID(as_uuid=True), ForeignKey('cases.id', ondelete='RESTRICT'), nullable=False) # spec: case_id (FK to cases.id, UUID, NOT NULL)
    doc_type = Column(ENUM(DocumentType, name='document_type', create_type=False), nullable=False) # spec: doc_type (ENUM 'PS', 'CR', 'DB', NOT NULL)
    doc_no = Column(String, unique=True, nullable=False) # spec: doc_no (VARCHAR, UNIQUE, NOT NULL)
    amount = Column(Numeric(18, 2), nullable=False) # spec: amount (NUMERIC(18, 2), NOT NULL)
    pdf_uri = Column(String, nullable=False) # spec: pdf_uri (VARCHAR, NOT NULL) -- GCS URI
    created_by = Column(String, nullable=False) # spec: created_by (VARCHAR, NOT NULL)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False) # spec: created_at (TIMESTAMP WITH TIME ZONE, DEFAULT NOW(), NOT NULL)
    updated_by = Column(String, nullable=True) # spec: updated_by (VARCHAR)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True) # spec: updated_at (TIMESTAMP WITH TIME ZONE)

    __table_args__ = (
        UniqueConstraint('case_id', 'doc_type', name='uq_case_id_doc_type'), # spec: UNIQUE(case_id, doc_type)
    )

    case = relationship("Case", back_populates="documents")

    def __repr__(self):
        return f"<Document(doc_no='{self.doc_no}', doc_type='{self.doc_type.value}', case_id='{self.case_id}')>"

class Payment(Base):
    # spec: payments table
    __tablename__ = 'payments'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4) # spec: id (PK, UUID)
    case_id = Column(UUID(as_uuid=True), ForeignKey('cases.id', ondelete='RESTRICT'), nullable=False) # spec: case_id (FK to cases.id, UUID, NOT NULL)
    type = Column(ENUM(PaymentType, name='payment_type', create_type=False), nullable=False) # spec: type (ENUM 'DISBURSE', 'REFUND', 'ADDITIONAL', NOT NULL)
    amount = Column(Numeric(18, 2), nullable=False) # spec: amount (NUMERIC(18, 2), NOT NULL)
    paid_by = Column(String, nullable=False) # spec: paid_by (VARCHAR, NOT NULL)
    paid_at = Column(DateTime(timezone=True), nullable=False) # spec: paid_at (TIMESTAMP WITH TIME ZONE, NOT NULL)
    reference_no = Column(String, nullable=True) # spec: reference_no (VARCHAR)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False) # spec: created_at (TIMESTAMP WITH TIME ZONE, DEFAULT NOW(), NOT NULL)

    case = relationship("Case", back_populates="payments")

    def __repr__(self):
        return f"<Payment(type='{self.type.value}', amount='{self.amount}', case_id='{self.case_id}')>"

class Attachment(Base):
    # spec: attachments table
    __tablename__ = 'attachments'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4) # spec: id (PK, UUID)
    case_id = Column(UUID(as_uuid=True), ForeignKey('cases.id', ondelete='RESTRICT'), nullable=False) # spec: case_id (FK to cases.id, UUID, NOT NULL)
    type = Column(ENUM(AttachmentType, name='attachment_type', create_type=False), nullable=False) # spec: type (ENUM 'QUOTE', 'RECEIPT', 'OTHER', NOT NULL)
    gcs_uri = Column(String, nullable=False) # spec: gcs_uri (VARCHAR, NOT NULL)
    uploaded_by = Column(String, nullable=False) # spec: uploaded_by (VARCHAR, NOT NULL)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False) # spec: uploaded_at (TIMESTAMP WITH TIME ZONE, DEFAULT NOW(), NOT NULL)

    case = relationship("Case", back_populates="attachments")

    def __repr__(self):
        return f"<Attachment(type='{self.type.value}', gcs_uri='{self.gcs_uri}', case_id='{self.case_id}')>"

class AuditLog(Base):
    # spec: audit_logs table
    __tablename__ = 'audit_logs'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4) # spec: id (PK, UUID)
    entity_type = Column(String, nullable=False) # spec: entity_type (VARCHAR, NOT NULL)
    entity_id = Column(UUID(as_uuid=True), nullable=False) # spec: entity_id (UUID, NOT NULL)
    action = Column(String, nullable=False) # spec: action (VARCHAR, NOT NULL)
    performed_by = Column(String, nullable=False) # spec: performed_by (VARCHAR, NOT NULL)
    performed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False) # spec: performed_at (TIMESTAMP WITH TIME ZONE, DEFAULT NOW(), NOT NULL)
    details_json = Column(JSONB, nullable=True) # spec: details_json (JSONB)

    def __repr__(self):
        return f"<AuditLog(entity_type='{self.entity_type}', action='{self.action}', performed_by='{self.performed_by}')>"

class DocCounter(Base):
    # spec: doc_counters table
    __tablename__ = 'doc_counters'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4) # spec: id (PK, UUID)
    doc_prefix = Column(ENUM(DocumentType, name='doc_prefix_type', create_type=False), nullable=False) # spec: doc_prefix (ENUM 'PS', 'CR', 'DB', NOT NULL)
    year_month = Column(String(4), nullable=False) # spec: year_month (VARCHAR(4), NOT NULL) -- Format 'YYMM'
    last_number = Column(Numeric, default=0, nullable=False) # spec: last_number (INTEGER, DEFAULT 0, NOT NULL)

    __table_args__ = (
        UniqueConstraint('doc_prefix', 'year_month', name='uq_doc_prefix_year_month'), # spec: UNIQUE(doc_prefix, year_month)
    )

    def __repr__(self):
        return f"<DocCounter(doc_prefix='{self.doc_prefix.value}', year_month='{self.year_month}', last_number='{self.last_number}')>"


class TransactionV1(Base):
    __tablename__ = "transactions_v1"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(String, nullable=False)  # "income" or "expense"
    category = Column(String, nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)
    occurred_at = Column(Date, nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by = Column(String, nullable=False)


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    google_sub = Column(String, nullable=True, unique=True)
    # บังคับ Email.แทน
    email = Column(String, nullable=True, unique=True)
    name = Column(String, nullable=True)
    # เพิ่มช่องเก็บรหัสผ่าน (hashed)
    hashed_password = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")


class UserRole(Base):
    __tablename__ = "user_roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False)  # admin, accountant, requester, viewer
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="roles")

    __table_args__ = (
        UniqueConstraint("user_id", "role", name="uq_user_role"),
    )
