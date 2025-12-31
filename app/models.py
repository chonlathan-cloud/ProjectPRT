import uuid
import datetime
import enum
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Numeric, UniqueConstraint, Text
from sqlalchemy.dialects.postgresql import UUID, ENUM, JSONB
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

Base = declarative_base()

# --- Enums (Refactored) ---
class CategoryType(enum.Enum):
    EXPENSE = "EXPENSE"
    REVENUE = "REVENUE"
    ASSET = "ASSET"

class FundingType(enum.Enum):
    OPERATING = "OPERATING"
    GOV_BUDGET = "GOV_BUDGET"

class CaseStatus(enum.Enum):
    # Flow ใหม่สำหรับ Voucher System
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"   # แทน PS_APPROVED (ใช้รวมทั้ง PV approved และ RV recorded)
    REJECTED = "REJECTED"
    PAID = "PAID"           # จ่ายเงินแล้ว (สำหรับ PV)
    CLOSED = "CLOSED"       # ปิดงานสมบูรณ์
    CANCELLED = "CANCELLED"

class DocumentType(enum.Enum):
    # Voucher Types
    PV = "PV"  # Payment Voucher
    RV = "RV"  # Receive Voucher
    JV = "JV"  # Journal Voucher

class PaymentType(enum.Enum):
    DISBURSE = "DISBURSE"
    REFUND = "REFUND"
    ADDITIONAL = "ADDITIONAL"

class AttachmentType(enum.Enum):
    QUOTE = "QUOTE"
    RECEIPT = "RECEIPT"
    OTHER = "OTHER"

# --- Models ---

class Category(Base):
    __tablename__ = 'categories'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name_th = Column(String, unique=True, nullable=False)
    type = Column(ENUM(CategoryType, name='category_type', create_type=False), nullable=False)
    account_code = Column(String, unique=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_by = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    cases = relationship("Case", foreign_keys="[Case.category_id]", back_populates="category")

    def __repr__(self):
        return f"<Category(name_th='{self.name_th}', type='{self.type.value}', account_code='{self.account_code}')>"

class Case(Base):
    __tablename__ = 'cases'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_no = Column(String, unique=True, nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey('categories.id', ondelete='RESTRICT'), nullable=False)
    account_code = Column(String, nullable=False)
    requester_id = Column(String, nullable=False)
    department_id = Column(String, nullable=True)
    cost_center_id = Column(String, nullable=True)
    funding_type = Column(ENUM(FundingType, name='funding_type', create_type=False), default=FundingType.OPERATING, nullable=False)
    requested_amount = Column(Numeric(18, 2), nullable=False)
    purpose = Column(Text, nullable=False)
    
    # Update Enum here
    status = Column(ENUM(CaseStatus, name='case_status', create_type=False), nullable=False)
    
    # --- New Columns for Voucher System ---
    deposit_account_id = Column(UUID(as_uuid=True), ForeignKey('categories.id', ondelete='RESTRICT'), nullable=True) # สำหรับ RV
    is_receipt_uploaded = Column(Boolean, default=False, nullable=False) # สำหรับ PV (check ใบเสร็จ)

    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_by = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Relationships
    category = relationship("Category", foreign_keys=[category_id], back_populates="cases")
    deposit_account = relationship("Category", foreign_keys=[deposit_account_id]) # New relationship
    
    documents = relationship("Document", back_populates="case")
    payments = relationship("Payment", back_populates="case")
    attachments = relationship("Attachment", back_populates="case")
    
    # Link to JV Line Items
    jv_line_items = relationship("JVLineItem", back_populates="ref_case")

    def __repr__(self):
        return f"<Case(case_no='{self.case_no}', status='{self.status.value}')>"

class Document(Base):
    __tablename__ = 'documents'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey('cases.id', ondelete='RESTRICT'), nullable=False)
    
    # Update Enum here
    doc_type = Column(ENUM(DocumentType, name='document_type', create_type=False), nullable=False)
    
    doc_no = Column(String, unique=True, nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)
    pdf_uri = Column(String, nullable=False)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_by = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Note: UniqueConstraint might need review if 1 case can have multiple PVs (Scenario 1 Over Budget)
    # But for now, we keep it per spec v3 (1 Case = 1 PV), additional amount uses NEW Case.
    __table_args__ = (
        UniqueConstraint('case_id', 'doc_type', name='uq_case_id_doc_type'),
    )

    case = relationship("Case", back_populates="documents")
    # Link to JV Lines if this document is a JV
    jv_lines = relationship("JVLineItem", back_populates="jv_document")

    def __repr__(self):
        return f"<Document(doc_no='{self.doc_no}', doc_type='{self.doc_type.value}', case_id='{self.case_id}')>"

# --- New Model for JV ---
class JVLineItem(Base):
    __tablename__ = 'jv_line_items'

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    jv_document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id', ondelete='CASCADE'), nullable=False)
    ref_case_id = Column(UUID(as_uuid=True), ForeignKey('cases.id', ondelete='RESTRICT'), nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)

    jv_document = relationship("Document", back_populates="jv_lines")
    ref_case = relationship("Case", back_populates="jv_line_items")

# ... (Models อื่นๆ: Payment, Attachment, AuditLog, DocCounter, User, TransactionV1 คงเดิม) ...
class Payment(Base):
    __tablename__ = 'payments'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey('cases.id', ondelete='RESTRICT'), nullable=False)
    type = Column(ENUM(PaymentType, name='payment_type', create_type=False), nullable=False)
    amount = Column(Numeric(18, 2), nullable=False)
    paid_by = Column(String, nullable=False)
    paid_at = Column(DateTime(timezone=True), nullable=False)
    reference_no = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    case = relationship("Case", back_populates="payments")

class Attachment(Base):
    __tablename__ = 'attachments'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id = Column(UUID(as_uuid=True), ForeignKey('cases.id', ondelete='RESTRICT'), nullable=False)
    type = Column(ENUM(AttachmentType, name='attachment_type', create_type=False), nullable=False)
    gcs_uri = Column(String, nullable=False)
    uploaded_by = Column(String, nullable=False)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    case = relationship("Case", back_populates="attachments")

class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type = Column(String, nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    action = Column(String, nullable=False)
    performed_by = Column(String, nullable=False)
    performed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    details_json = Column(JSONB, nullable=True)

class DocCounter(Base):
    __tablename__ = 'doc_counters'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doc_prefix = Column(ENUM(DocumentType, name='doc_prefix_type', create_type=False), nullable=False)
    year_month = Column(String(4), nullable=False)
    last_number = Column(Numeric, default=0, nullable=False)
    __table_args__ = (UniqueConstraint('doc_prefix', 'year_month', name='uq_doc_prefix_year_month'),)

class TransactionV1(Base):
    __tablename__ = "transactions_v1"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(String, nullable=False)
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
    email = Column(String, nullable=True, unique=True)
    name = Column(String, nullable=True)
    hashed_password = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")

class UserRole(Base):
    __tablename__ = "user_roles"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    user = relationship("User", back_populates="roles")
    __table_args__ = (UniqueConstraint("user_id", "role", name="uq_user_role"),)