from datetime import datetime, timezone
from typing import Optional, List, Annotated
from uuid import UUID
import uuid
import decimal

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from app.db import get_db
from app.deps import Role, has_role, get_current_user, UserInDB
from app.models import (
    Category, Case, CaseStatus, FundingType, Document, DocCounter, 
    Payment, PaymentType, DocumentType, AuditLog, Attachment, CategoryType
)
from app.schemas.case import CaseCreate, CaseResponse, CaseSubmit
from app.schemas.workflow import WorkflowResponse
from app.services.audit import log_audit_event
# from app.services import pdf # (Comment ไว้ก่อน เดี๋ยวเรามาทำ PDF Gen กันทีหลัง)

router = APIRouter(
    prefix="/api/v1/cases",
    tags=["Cases"]
)

# --- Helper Functions ---

def generate_case_no() -> str:
    """Generate Case Number (e.g., CAS-251231-A1B2C3)"""
    today_str = datetime.now(timezone.utc).strftime("%y%m%d")
    unique_suffix = uuid.uuid4().hex[:6].upper()
    return f"CAS-{today_str}-{unique_suffix}"

def _generate_document_no(db: Session, doc_prefix_enum: DocumentType) -> str:
    """
    Generate Running Document Number (e.g., PV-2512-0001)
    Locks the counter row to prevent race conditions.
    """
    doc_prefix = doc_prefix_enum.value
    current_ym = datetime.now(timezone.utc).strftime("%y%m")
    
    # Select for update to lock the row
    doc_counter = db.execute(
        select(DocCounter).filter_by(doc_prefix=doc_prefix_enum, year_month=current_ym).with_for_update()
    ).scalar_one_or_none()

    if not doc_counter:
        doc_counter = DocCounter(doc_prefix=doc_prefix_enum, year_month=current_ym, last_number=0)
        db.add(doc_counter)
        db.flush()
    
    doc_counter.last_number += 1
    new_number = int(doc_counter.last_number)
    return f"{doc_prefix}-{current_ym}-{new_number:04d}"

def _ensure_case_visibility(db_case: Case, current_user: UserInDB) -> None:
    can_see_all = any(role in current_user.roles for role in [
        Role.FINANCE, Role.ACCOUNTING, Role.ADMIN, Role.EXECUTIVE, Role.TREASURY
    ])
    if not can_see_all and db_case.requester_id != current_user.username:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this case.")

# --- Core Endpoints ---

@router.post("/", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
async def create_case(
    payload: CaseCreate,
    current_user: Annotated[UserInDB, Depends(has_role([Role.REQUESTER]))],
    db: Session = Depends(get_db)
):
    # 1. Validate Category
    category = db.execute(select(Category).filter_by(id=payload.category_id)).scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")
    if not category.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category is inactive.")

    # 2. Validate Deposit Account for Revenue/Asset
    if category.type in [CategoryType.REVENUE, CategoryType.ASSET]:
        if not payload.deposit_account_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Deposit account (deposit_account_id) is required for Revenue or Asset cases."
            )
        # Verify deposit account exists
        deposit_acc = db.execute(select(Category).filter_by(id=payload.deposit_account_id)).scalar_one_or_none()
        if not deposit_acc:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deposit account not found.")

    account_code = category.account_code
    case_no = generate_case_no()
    
    while db.execute(select(Case).filter_by(case_no=case_no)).scalar_one_or_none():
        case_no = generate_case_no()

    db_case = Case(
        case_no=case_no,
        category_id=payload.category_id,
        account_code=account_code,
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
    db.flush()
    log_audit_event(db, "case", db_case.id, "create", current_user.username, payload.model_dump(mode="json"))
    db.commit()
    db.refresh(db_case)
    return CaseResponse.model_validate(db_case)


@router.post("/{case_id}/submit", response_model=WorkflowResponse)
async def submit_case(
    case_id: UUID,
    current_user: Annotated[UserInDB, Depends(has_role([Role.REQUESTER]))],
    db: Session = Depends(get_db)
):
    db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
    if not db_case: raise HTTPException(404, "Case not found.")
    if db_case.requester_id != current_user.username: raise HTTPException(403, "Not authorized.")
    if db_case.status != CaseStatus.DRAFT: raise HTTPException(409, "Only DRAFT cases can be submitted.")

    old_status = db_case.status
    db_case.status = CaseStatus.SUBMITTED
    db_case.updated_by = current_user.username
    db_case.updated_at = datetime.now(timezone.utc)
    
    db.flush()
    log_audit_event(db, "case", db_case.id, "submit", current_user.username, {"old": old_status.value, "new": db_case.status.value})
    db.commit()

    return WorkflowResponse(message=f"Case {db_case.case_no} submitted.", case_id=str(db_case.id), status=db_case.status.value)


@router.post("/{case_id}/approve", response_model=WorkflowResponse)
async def approve_case(
    case_id: UUID,
    current_user: Annotated[UserInDB, Depends(has_role([Role.FINANCE, Role.ADMIN, Role.ACCOUNTING]))],
    db: Session = Depends(get_db)
):
    """
    Unified Approval Endpoint:
    - If Expense: Generate PV -> Status APPROVED
    - If Revenue: Generate RV -> Status CLOSED (Assuming money received)
    """
    db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
    if not db_case: raise HTTPException(404, "Case not found")
    
    # Check Status
    if db_case.status != CaseStatus.SUBMITTED:
        raise HTTPException(409, f"Case must be SUBMITTED to approve. Current: {db_case.status.value}")

    # Determine Logic based on Category Type
    category = db.execute(select(Category).filter_by(id=db_case.category_id)).scalar_one()
    
    doc_type = None
    new_status = None
    doc_no = None

    if category.type == CategoryType.EXPENSE:
        # --- EXPENSE FLOW: Generate PV ---
        doc_type = DocumentType.PV
        new_status = CaseStatus.APPROVED
        
    elif category.type in [CategoryType.REVENUE, CategoryType.ASSET]:
        # --- REVENUE FLOW: Generate RV ---
        # For Revenue, "Approving" means we acknowledge receipt/booking.
        doc_type = DocumentType.RV
        new_status = CaseStatus.CLOSED # Revenue cases close immediately upon booking? Or PAID? Let's use CLOSED for simplicity.
    
    else:
        raise HTTPException(400, f"Unknown category type: {category.type}")

    # --- Generate Document ---
    doc_no = _generate_document_no(db, doc_type)
    
    # Check if doc already exists (Idempotency check)
    existing_doc = db.execute(select(Document).filter_by(case_id=case_id, doc_type=doc_type)).scalar_one_or_none()
    if existing_doc:
        raise HTTPException(409, f"{doc_type.value} Document already exists for this case.")

    db_doc = Document(
        case_id=case_id,
        doc_type=doc_type,
        doc_no=doc_no,
        amount=db_case.requested_amount,
        pdf_uri="pending_generation", # Placeholder for now
        created_by=current_user.username
    )
    db.add(db_doc)

    # --- Update Case ---
    old_status = db_case.status
    db_case.status = new_status
    db_case.updated_by = current_user.username
    db_case.updated_at = datetime.now(timezone.utc)

    db.flush()
    log_audit_event(
        db, "case", case_id, "approve", current_user.username, 
        {"old_status": old_status.value, "new_status": new_status.value, "doc_type": doc_type.value, "doc_no": doc_no}
    )
    
    db.commit()

    return WorkflowResponse(
        message=f"Case Approved. {doc_type.value} {doc_no} Generated.",
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
    """
    For PV Cases: Mark as PAID (Money transferred).
    """
    db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
    if not db_case: raise HTTPException(404, "Case not found")
    
    if db_case.status != CaseStatus.APPROVED:
        raise HTTPException(409, "Case must be APPROVED (PV Issued) to pay.")

    # Record Payment (Optional: Add Payment record logic here if needed, for now just Status)
    # db_payment = Payment(...) 

    db_case.status = CaseStatus.PAID
    db_case.updated_by = current_user.username
    db_case.updated_at = datetime.now(timezone.utc)
    
    db.commit()
    return WorkflowResponse(message="Case marked as PAID.", case_id=str(case_id), status="PAID")


@router.post("/{case_id}/close", response_model=WorkflowResponse)
async def close_case(
    case_id: UUID,
    current_user: Annotated[UserInDB, Depends(has_role([Role.REQUESTER, Role.ADMIN]))],
    db: Session = Depends(get_db)
):
    """
    Requester Closes the case after uploading receipt.
    Condition: is_receipt_uploaded must be True.
    """
    db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
    if not db_case: raise HTTPException(404, "Case not found")

    if db_case.status != CaseStatus.PAID:
        raise HTTPException(409, "Case must be PAID to close.")
    
    if db_case.requester_id != current_user.username and Role.ADMIN not in current_user.roles:
        raise HTTPException(403, "Not authorized.")

    # [Task 3.5 Check]
    if not db_case.is_receipt_uploaded:
        raise HTTPException(400, "Cannot close case: Receipt not uploaded yet.")

    db_case.status = CaseStatus.CLOSED
    db_case.updated_by = current_user.username
    db_case.updated_at = datetime.now(timezone.utc)
    
    db.commit()
    return WorkflowResponse(message="Case CLOSED successfully.", case_id=str(case_id), status="CLOSED")


# --- Read Endpoints ---

@router.get("/", response_model=List[CaseResponse])
async def read_cases(
    current_user: Annotated[UserInDB, Depends(get_current_user)],
    db: Session = Depends(get_db),
    status: Optional[CaseStatus] = None
):
    query = select(Case)
    conditions = []
    
    # Roles that can see ALL cases
    can_see_all = any(role in current_user.roles for role in [
        Role.FINANCE, Role.ACCOUNTING, Role.ADMIN, Role.EXECUTIVE, Role.TREASURY
    ])
    
    if not can_see_all: 
        conditions.append(Case.requester_id == current_user.username)
    
    if status: 
        conditions.append(Case.status == status)
    
    if conditions: 
        query = query.where(and_(*conditions))
    
    query = query.order_by(Case.created_at.desc())
    return [CaseResponse.model_validate(c) for c in db.execute(query).scalars().all()]

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