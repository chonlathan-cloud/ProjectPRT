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
# Import new enums and models
from app.models import (
    Category, Case, CaseStatus, FundingType, Document, DocCounter, 
    Payment, PaymentType, DocumentType, AuditLog, Attachment, CategoryType
)
from app.schemas.case import CaseCreate, CaseResponse, CaseSubmit
from app.schemas.workflow import WorkflowResponse
from app.services.audit import log_audit_event
from app.config import settings
from app.services import gcs
from app.services import pdf

router = APIRouter(
    prefix="/api/v1/cases",
    tags=["Cases"]
)

# ... Helper Functions ...
def generate_case_no() -> str:
    today_str = datetime.now(timezone.utc).strftime("%y%m%d")
    unique_suffix = uuid.uuid4().hex[:6].upper()
    return f"CAS-{today_str}-{unique_suffix}"

def _generate_document_no(db: Session, doc_prefix_enum: DocumentType) -> str:
    doc_prefix = doc_prefix_enum.value
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
    return f"{doc_prefix}-{current_ym}-{new_number:04d}"

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
    # 1. Validate Category
    category = db.execute(select(Category).filter_by(id=payload.category_id)).scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")
    if not category.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category is inactive.")

    # 2. [Refactor] Validate Deposit Account for Revenue/Asset
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
        
        # Optional: Check if deposit account is actually an ASSET type? (Rules might vary, keeping flexible for now)

    account_code = category.account_code
    case_no = generate_case_no()
    
    # Ensure uniqueness
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
        
        # New Fields
        deposit_account_id=payload.deposit_account_id,
        is_receipt_uploaded=False, # Default

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
    if not db_case:
        raise HTTPException(status_code=404, detail="Case not found.")

    if db_case.requester_id != current_user.username:
        raise HTTPException(status_code=403, detail="Not authorized to submit this case.")

    if db_case.status != CaseStatus.DRAFT:
        raise HTTPException(status_code=409, detail=f"Only DRAFT cases can be submitted.")

    # Note: For Voucher System, we DO NOT generate PV here. PV is generated at Approval.
    # Just update status.
    
    old_status = db_case.status
    db_case.status = CaseStatus.SUBMITTED
    db_case.updated_by = current_user.username
    db_case.updated_at = datetime.now(timezone.utc)
    
    db.flush()

    log_audit_event(
        db, "case", db_case.id, "submit", current_user.username,
        {"old_status": old_status.value, "new_status": db_case.status.value}
    )

    db.commit()

    return WorkflowResponse(
        message=f"Case {db_case.case_no} submitted for approval.",
        case_id=str(db_case.id),
        status=db_case.status.value
    )

# --- Deprecated / Needs Update Endpoints ---
# IMPORTANT: The following endpoints need to be updated for PV/RV/JV flow later (Task 3.4, 3.6).
# For now, I've updated Enum references to avoid crashes, but logic needs full refactor.

@router.post("/{case_id}/approve", response_model=WorkflowResponse) # Renamed from ps/approve for generic use
async def approve_case(
    case_id: UUID,
    current_user: Annotated[UserInDB, Depends(has_role([Role.FINANCE, Role.ADMIN]))],
    db: Session = Depends(get_db)
):
    db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
    if not db_case: raise HTTPException(404, "Case not found")
    if db_case.status != CaseStatus.SUBMITTED: raise HTTPException(409, "Must be SUBMITTED")

    # [TODO Task 3.4] Logic to generate PV here
    pv_doc_no = _generate_document_no(db, DocumentType.PV)
    
    # Mocking PV creation for now to prevent crash
    # Real implementation needs PDF generation logic
    db_doc = Document(
        case_id=case_id, doc_type=DocumentType.PV, doc_no=pv_doc_no, 
        amount=db_case.requested_amount, pdf_uri="pending_gen", created_by=current_user.username
    )
    db.add(db_doc)

    old_s = db_case.status
    db_case.status = CaseStatus.APPROVED # New Status
    db.flush()
    log_audit_event(db, "case", case_id, "approve", current_user.username, {"old": old_s.value, "new": db_case.status.value})
    
    db.commit()
    return WorkflowResponse(message="Case Approved (PV Generated)", case_id=str(case_id), status="APPROVED", doc_no=pv_doc_no)

@router.get("/", response_model=List[CaseResponse])
async def read_cases(
    current_user: Annotated[UserInDB, Depends(get_current_user)],
    db: Session = Depends(get_db),
    status: Optional[CaseStatus] = None
):
    query = select(Case)
    conditions = []
    can_see_all = any(role in current_user.roles for role in [Role.FINANCE, Role.ACCOUNTING, Role.ADMIN, Role.EXECUTIVE, Role.TREASURY])
    if not can_see_all: conditions.append(Case.requester_id == current_user.username)
    if status: conditions.append(Case.status == status)
    if conditions: query = query.where(and_(*conditions))
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