from datetime import datetime, timezone
from typing import Optional, List, Annotated
from uuid import UUID
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from app.db import get_db
from app.deps import Role, has_role, get_current_user, UserInDB
from app.models import (
    Category, Case, CaseStatus, Document, DocCounter, 
    DocumentType, CategoryType, User)
from app.schemas.workflow import WorkflowResponse
from app.schemas.case import CaseCreate, CaseResponse
from app.services.audit import log_audit_event
from pydantic import BaseModel

router = APIRouter(
    prefix="/api/v1/cases",
    tags=["Cases"]
)

# ✅ Model พิเศษสำหรับหน้า Admin/Dashboard
class CaseAdminView(BaseModel):
    id: UUID
    case_no: str
    doc_no: Optional[str] = None
    requester_name: str
    description: str
    requested_amount: float
    created_at: datetime
    status: str
    department: Optional[str] = None

    class Config:
        from_attributes = True

# --- Helper Functions ---
def generate_case_no() -> str:
    today_str = datetime.now(timezone.utc).strftime("%y%m%d")
    unique_suffix = uuid.uuid4().hex[:6].upper()
    return f"CAS-{today_str}-{unique_suffix}"

def _generate_document_no(db: Session, doc_prefix_enum: DocumentType) -> str:
    current_ym = datetime.now(timezone.utc).strftime("%y%m")
    doc_counter = db.execute(
        select(DocCounter).filter_by(doc_prefix=doc_prefix_enum, year_month=current_ym).with_for_update()
    ).scalar_one_or_none()

    if not doc_counter:
        doc_counter = DocCounter(doc_prefix=doc_prefix_enum, year_month=current_ym, last_number=0)
        db.add(doc_counter)
        db.flush()
    
    doc_counter.last_number += 1
    new_number = int(doc_counter.last_number)
    return f"{doc_prefix_enum.value}-{current_ym}-{new_number:04d}"

def _ensure_case_visibility(db_case: Case, current_user: UserInDB) -> None:
    can_see_all = any(role in current_user.roles for role in [
        Role.FINANCE, Role.ACCOUNTING, Role.ADMIN, Role.EXECUTIVE, Role.TREASURY
    ])
    if not can_see_all and db_case.requester_id != current_user.username:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this case.")

# --- Endpoints ---

@router.post("/", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
async def create_case(
    payload: CaseCreate,
    current_user: Annotated[UserInDB, Depends(has_role([Role.REQUESTER]))],
    db: Session = Depends(get_db)
):
    category = db.execute(select(Category).filter_by(id=payload.category_id)).scalar_one_or_none()
    if not category: raise HTTPException(404, "Category not found.")
    if not category.is_active: raise HTTPException(400, "Category is inactive.")

    if category.type in [CategoryType.REVENUE, CategoryType.ASSET]:
        if not payload.deposit_account_id:
            raise HTTPException(400, "Deposit account is required for Revenue/Asset cases.")

    case_no = generate_case_no()
    db_case = Case(
        case_no=case_no,
        category_id=payload.category_id,
        account_code=category.account_code,
        requester_id=current_user.username,
        department_id=payload.department_id,
        cost_center_id=payload.cost_center_id,
        funding_type=payload.funding_type,
        requested_amount=payload.requested_amount,
        purpose=payload.purpose,
        status=CaseStatus.DRAFT,
        deposit_account_id=payload.deposit_account_id,
        is_receipt_uploaded=False, 
        created_by=current_user.username
    )
    db.add(db_case)
    db.commit()
    db.refresh(db_case)
    log_audit_event(db, "case", db_case.id, "create", current_user.username, payload.model_dump(mode="json"))
    return CaseResponse.model_validate(db_case)

@router.post("/{case_id}/submit", response_model=WorkflowResponse)
async def submit_case(
    case_id: UUID,
    current_user: Annotated[UserInDB, Depends(has_role([Role.REQUESTER]))],
    db: Session = Depends(get_db)
):
    # ✅ แก้ไข 1: ลบ with db.begin() ออก เพื่อแก้ Error 500 (Transaction ซ้อน)
    db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
    if not db_case: raise HTTPException(404, "Case not found.")
    
    if db_case.requester_id != current_user.username: raise HTTPException(403, "Not authorized.")
    if db_case.status != CaseStatus.DRAFT: raise HTTPException(409, "Only DRAFT cases can be submitted.")

    # --- Gen Document No ---
    category = db.execute(select(Category).filter_by(id=db_case.category_id)).scalar_one()
    
    # ✅ แก้ไข 2: เพิ่ม Logic สำหรับ JV (ถ้าไม่ใช่ Expense/Revenue ให้เป็น JV)
    if category.type == CategoryType.EXPENSE:
        doc_type = DocumentType.PV
    elif category.type == CategoryType.REVENUE:
        doc_type = DocumentType.RV
    else:
        doc_type = DocumentType.JV  # ครอบคลุม ASSET และอื่นๆ

    # ตรวจสอบว่ามีเอกสารเดิมไหม
    existing_doc = db.execute(select(Document).filter_by(case_id=case_id)).scalar_one_or_none()
    
    if not existing_doc:
        doc_no = _generate_document_no(db, doc_type)
        new_doc = Document(
            case_id=case_id,
            doc_type=doc_type,
            doc_no=doc_no,
            amount=db_case.requested_amount,
            pdf_uri="pending-approval", 
            created_by=current_user.username
        )
        db.add(new_doc)
        db.flush() # สำคัญ: flush เพื่อให้ new_doc เข้า session
    else:
        doc_no = existing_doc.doc_no

    old_status = db_case.status
    db_case.status = CaseStatus.SUBMITTED
    db_case.updated_by = current_user.username
    db_case.updated_at = datetime.now(timezone.utc)
    
    log_audit_event(
        db, "case", db_case.id, "submit_and_gen_no", current_user.username, 
        {"old": old_status.value, "new": db_case.status.value, "doc_no": doc_no}
    )

    # ✅ แก้ไข 3: Commit ปิดท้าย
    db.commit() 
    db.refresh(db_case)

    return WorkflowResponse(
        message=f"Submitted. Generated {doc_no}", 
        case_id=str(db_case.id), 
        status=db_case.status.value,
        doc_no=doc_no
    )

@router.post("/{case_id}/approve", response_model=WorkflowResponse)
async def approve_case(
    case_id: UUID,
    current_user: Annotated[UserInDB, Depends(has_role([Role.FINANCE, Role.ADMIN, Role.ACCOUNTING]))],
    db: Session = Depends(get_db)
):
    db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
    if not db_case: raise HTTPException(404, "Case not found")
    
    if db_case.status != CaseStatus.SUBMITTED:
        raise HTTPException(409, f"Case must be SUBMITTED to approve.")

    category = db.execute(select(Category).filter_by(id=db_case.category_id)).scalar_one()
    # ถ้าเป็น Expense -> Approved (รอจ่ายเงิน), ถ้าเป็น Revenue/Asset -> Closed (จบงานเลย)
    new_status = CaseStatus.APPROVED if category.type == CategoryType.EXPENSE else CaseStatus.CLOSED

    doc = db.execute(select(Document).filter_by(case_id=case_id)).scalar_one_or_none()
    doc_no = doc.doc_no if doc else "N/A"

    old_status = db_case.status
    db_case.status = new_status
    db_case.updated_by = current_user.username
    db_case.updated_at = datetime.now(timezone.utc)

    db.commit()
    log_audit_event(
        db, "case", case_id, "approve", current_user.username, 
        {"old_status": old_status.value, "new_status": new_status.value, "doc_no": doc_no}
    )

    return WorkflowResponse(
        message=f"Case Approved ({doc_no})",
        case_id=str(case_id),
        status=new_status.value,
        doc_no=doc_no
    )

@router.post("/{case_id}/pay", response_model=WorkflowResponse)
async def mark_paid(
    case_id: UUID,
    current_user: Annotated[UserInDB, Depends(has_role([Role.TREASURY, Role.ADMIN]))],
    db: Session = Depends(get_db)
):
    db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
    if not db_case: raise HTTPException(404, "Case not found")
    if db_case.status != CaseStatus.APPROVED: raise HTTPException(409, "Case must be APPROVED to pay.")

    db_case.status = CaseStatus.PAID
    db_case.updated_by = current_user.username
    db_case.updated_at = datetime.now(timezone.utc)
    db.commit()
    return WorkflowResponse(message="Case marked as PAID.", case_id=str(case_id), status="PAID")

@router.get("/", response_model=List[CaseAdminView])
async def read_cases(
    current_user: Annotated[UserInDB, Depends(get_current_user)],
    db: Session = Depends(get_db),
    status: Optional[CaseStatus] = None
):
    query = (
        select(
            Case.id,
            Case.case_no,
            Case.purpose.label("description"),
            Case.requested_amount,
            Case.created_at,
            Case.status,
            Case.department_id.label("department"),
            Document.doc_no,
            User.name.label("requester_name")
        )
        .outerjoin(Document, Case.id == Document.case_id)
        .outerjoin(User, Case.requester_id == User.email)
    )

    can_see_all = any(role in current_user.roles for role in [Role.FINANCE, Role.ACCOUNTING, Role.ADMIN, Role.EXECUTIVE, Role.TREASURY])
    if not can_see_all: 
        query = query.where(Case.requester_id == current_user.username)
    
    if status: 
        query = query.where(Case.status == status)
    
    query = query.order_by(Case.created_at.desc())
    
    results = db.execute(query).all()
    
    mapped_results = []
    for row in results:
        mapped_results.append(CaseAdminView(
            id=row.id,
            case_no=row.case_no,
            doc_no=row.doc_no if row.doc_no else "-",
            requester_name=row.requester_name if row.requester_name else "Unknown",
            description=row.description,
            requested_amount=float(row.requested_amount),
            created_at=row.created_at,
            status=row.status.value,
            department=row.department
        ))
        
    return mapped_results

@router.get("/{case_id}", response_model=CaseResponse)
async def read_case(
    case_id: UUID,
    current_user: Annotated[UserInDB, Depends(get_current_user)],
    db: Session = Depends(get_db)
):
    db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
    if not db_case: raise HTTPException(404, "Not Found")
    _ensure_case_visibility(db_case, current_user)
    return CaseResponse.model_validate(db_case)