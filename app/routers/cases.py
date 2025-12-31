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
from app.models import Category, Case, CaseStatus, FundingType, Document, DocCounter, Payment, PaymentType, DocumentType, AuditLog, Attachment
from app.schemas.case import CaseCreate, CaseResponse, CaseSubmit
from app.schemas.workflow import PaymentCreate, SettlementSubmit, WorkflowResponse
from app.schemas.adjustment import AdjustmentType, AdjustmentCreate, PaymentOut, VarianceResponse
from app.schemas.attachment import AttachmentOut
from app.schemas.files import SignedUrlResponse
from app.services.audit import log_audit_event
from app.config import settings
from app.services import gcs
from app.services import pdf

router = APIRouter(
    prefix="/api/v1/cases",
    tags=["Cases"]
)

# ... (ฟังก์ชัน generate_case_no, _generate_document_no, _calculate_variance_info, _ensure_case_visibility เหมือนเดิม)
def generate_case_no() -> str:
    today_str = datetime.now(timezone.utc).strftime("%y%m%d")
    unique_suffix = uuid.uuid4().hex[:6].upper()
    return f"CAS-{today_str}-{unique_suffix}"

def _generate_document_no(db: Session, doc_prefix_enum: DocumentType) -> str:
    doc_prefix = doc_prefix_enum.value
    current_ym = datetime.now(timezone.utc).strftime("%y%m")
    doc_counter = db.execute(
        select(DocCounter).filter_by(doc_prefix=doc_prefix, year_month=current_ym).with_for_update()
    ).scalar_one_or_none()

    if not doc_counter:
        doc_counter = DocCounter(doc_prefix=doc_prefix_enum, year_month=current_ym, last_number=0)
        db.add(doc_counter)
        db.flush()
    
    doc_counter.last_number += 1
    new_number = int(doc_counter.last_number)
    padded_number = f"{new_number:04d}"
    return f"{doc_prefix}-{current_ym}-{padded_number}"

async def _calculate_variance_info(db: Session, case_id: UUID) -> dict:
    cr_document = db.execute(select(Document).filter_by(case_id=case_id, doc_type=DocumentType.CR)).scalar_one_or_none()
    db_document = db.execute(select(Document).filter_by(case_id=case_id, doc_type=DocumentType.DB)).scalar_one_or_none()
    
    # Helper: Return default/zero if docs missing (for safety)
    if not cr_document or not db_document:
         return {
            "cr_amount": decimal.Decimal(0),
            "db_amount": decimal.Decimal(0),
            "variance": decimal.Decimal(0),
            "expected_adjustment_type": None,
            "expected_adjustment_amount": decimal.Decimal(0),
        }

    cr_amount = decimal.Decimal(cr_document.amount)
    db_amount = decimal.Decimal(db_document.amount)
    variance = db_amount - cr_amount

    expected_adjustment_type = None
    expected_adjustment_amount = decimal.Decimal("0.00")

    if variance < 0:
        expected_adjustment_type = AdjustmentType.REFUND
        expected_adjustment_amount = abs(variance)
    elif variance > 0:
        expected_adjustment_type = AdjustmentType.ADDITIONAL
        expected_adjustment_amount = variance

    return {
        "cr_amount": cr_amount,
        "db_amount": db_amount,
        "variance": variance,
        "expected_adjustment_type": expected_adjustment_type,
        "expected_adjustment_amount": expected_adjustment_amount,
    }

def _ensure_case_visibility(db_case: Case, current_user: UserInDB) -> None:
    can_see_all = any(role in current_user.roles for role in [
        Role.FINANCE, Role.ACCOUNTING, Role.ADMIN, Role.EXECUTIVE, Role.TREASURY
    ])
    if not can_see_all and db_case.requester_id != current_user.username:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this case.")

# ... (create_case เหมือนเดิม)
@router.post("/", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
async def create_case(
    payload: CaseCreate,
    current_user: Annotated[UserInDB, Depends(has_role([Role.REQUESTER]))],
    db: Session = Depends(get_db)
):
    category = db.execute(select(Category).filter_by(id=payload.category_id)).scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")
    if not category.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category is inactive.")

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
        created_by=current_user.username
    )

    db.add(db_case)
    db.flush()

    log_audit_event(db, "case", db_case.id, "create", current_user.username, payload.model_dump(mode="json"))
    db.commit()
    db.refresh(db_case)
    return CaseResponse.model_validate(db_case)


# --- 1. แก้ไข: Submit Case ให้สร้าง PS Document เลย ---
@router.post("/{case_id}/submit", response_model=WorkflowResponse)
async def submit_case(
    case_id: UUID,
    current_user: Annotated[UserInDB, Depends(has_role([Role.REQUESTER]))],
    db: Session = Depends(get_db)
):
    with db.begin(): # ใช้ Transaction
        db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
        if not db_case:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")

        if db_case.requester_id != current_user.username:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to submit this case.")

        if db_case.status != CaseStatus.DRAFT:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Only DRAFT cases can be submitted.")

        # --- A. สร้างเลข PS ทันที ---
        ps_doc_no = _generate_document_no(db, DocumentType.PS)
        
        # --- B. สร้าง Document Record ---
        # Note: pdf_uri เราใส่ placeholder ไปก่อน เพราะเดี๋ยว Frontend จะ Generate PDF เองแล้วส่งมาเก็บ (ถ้าต้องการ) 
        # หรือถ้าระบบหลังบ้านเจน ก็จะเป็นอีก Step
        db_document = Document(
            case_id=case_id,
            doc_type=DocumentType.PS,
            doc_no=ps_doc_no,
            amount=db_case.requested_amount,
            pdf_uri="generated_by_frontend", 
            created_by=current_user.username
        )
        db.add(db_document)

        # --- C. อัปเดตสถานะ ---
        old_status = db_case.status
        db_case.status = CaseStatus.SUBMITTED
        db_case.updated_by = current_user.username
        db_case.updated_at = datetime.now(timezone.utc)
        
        db.flush()

        log_audit_event(
            db, "case", db_case.id, "submit", current_user.username,
            {"old_status": old_status.value, "new_status": db_case.status.value, "ps_doc_no": ps_doc_no}
        )

        return WorkflowResponse(
            message=f"Case {db_case.case_no} submitted. PS Document {ps_doc_no} generated.",
            case_id=str(db_case.id),
            status=db_case.status.value,
            doc_no=ps_doc_no, # ส่งเลขเอกสารกลับไปให้ Frontend
            audit_details={"ps_doc_no": ps_doc_no}
        )

# --- 2. แก้ไข: Approve Case ไม่ต้องสร้างเลข PS ซ้ำ ---
@router.post("/{case_id}/ps/approve", response_model=WorkflowResponse)
async def ps_approve_case(
    case_id: UUID,
    current_user: Annotated[UserInDB, Depends(has_role([Role.FINANCE, Role.ADMIN]))],
    db: Session = Depends(get_db)
):
    with db.begin():
        db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
        if not db_case:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")

        if db_case.status != CaseStatus.SUBMITTED:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Case status must be SUBMITTED.")

        # หาเลข PS เดิมที่สร้างตอน Submit
        existing_ps_doc = db.execute(
            select(Document).filter_by(case_id=case_id, doc_type=DocumentType.PS)
        ).scalar_one_or_none()
        
        # ถ้าไม่มี (เช่น เคสเก่า) ค่อยสร้างใหม่ แต่ปกติควรมีแล้ว
        ps_doc_no = existing_ps_doc.doc_no if existing_ps_doc else _generate_document_no(db, DocumentType.PS)
        
        # Update status
        old_status = db_case.status
        db_case.status = CaseStatus.PS_APPROVED
        db_case.updated_by = current_user.username
        db_case.updated_at = datetime.now(timezone.utc)

        db.flush()

        log_audit_event(
            db, "case", db_case.id, "ps_approve", current_user.username,
            {"old_status": old_status.value, "new_status": db_case.status.value}
        )
        
        return WorkflowResponse(
            message=f"Case {db_case.case_no} PS approved.",
            case_id=str(db_case.id),
            status=db_case.status.value,
            doc_no=ps_doc_no,
            audit_details={}
        )

# ... (cr_issue_case, record_payment_for_case, submit_settlement_for_case, db_issue_case และอื่นๆ เหมือนเดิมได้เลยครับ)
@router.post("/{case_id}/cr/issue", response_model=WorkflowResponse)
async def cr_issue_case(
    case_id: UUID,
    current_user: Annotated[UserInDB, Depends(has_role([Role.ACCOUNTING, Role.ADMIN]))],
    db: Session = Depends(get_db)
):
    with db.begin():
        db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
        if not db_case: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
        if db_case.status != CaseStatus.PS_APPROVED:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Status must be PS_APPROVED.")
        
        if db.execute(select(Document).filter_by(case_id=case_id, doc_type=DocumentType.CR)).scalar_one_or_none():
             raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"CR already exists.")

        cr_doc_no = _generate_document_no(db, DocumentType.CR)
        # Placeholder PDF URI
        db_cr = Document(case_id=case_id, doc_type=DocumentType.CR, doc_no=cr_doc_no, amount=db_case.requested_amount, pdf_uri="generated_by_backend", created_by=current_user.username)
        db.add(db_cr)
        
        old_s = db_case.status
        db_case.status = CaseStatus.CR_ISSUED
        db.flush()
        log_audit_event(db, "case", case_id, "cr_issue", current_user.username, {"old": old_s.value, "new": db_case.status.value, "doc": cr_doc_no})
        
        return WorkflowResponse(message="CR Issued", case_id=str(case_id), status=db_case.status.value, doc_no=cr_doc_no)

@router.post("/{case_id}/payment", response_model=WorkflowResponse)
async def record_payment_for_case(
    case_id: UUID, payment_in: PaymentCreate,
    current_user: Annotated[UserInDB, Depends(has_role([Role.TREASURY, Role.ADMIN]))],
    db: Session = Depends(get_db)
):
    with db.begin():
        db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
        if not db_case: raise HTTPException(status_code=404, detail="Case not found")
        if db_case.status != CaseStatus.CR_ISSUED: raise HTTPException(status_code=409, detail="Must be CR_ISSUED")
        
        cr_doc = db.execute(select(Document).filter_by(case_id=case_id, doc_type=DocumentType.CR)).scalar_one_or_none()
        if not cr_doc: raise HTTPException(status_code=404, detail="CR doc missing")

        db_pay = Payment(case_id=case_id, type=PaymentType.DISBURSE, amount=cr_doc.amount, paid_by=current_user.username, paid_at=datetime.now(timezone.utc), reference_no=payment_in.reference_no)
        db.add(db_pay)
        
        db_case.status = CaseStatus.PAID
        db.flush()
        log_audit_event(db, "case", case_id, "payment", current_user.username, {"amount": float(cr_doc.amount)})
        return WorkflowResponse(message="Payment Recorded", case_id=str(case_id), status="PAID")

@router.post("/{case_id}/settlement/submit", response_model=WorkflowResponse)
async def submit_settlement_for_case(
    case_id: UUID, settlement_in: SettlementSubmit,
    current_user: Annotated[UserInDB, Depends(has_role([Role.REQUESTER]))],
    db: Session = Depends(get_db)
):
    with db.begin():
        db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
        if not db_case: raise HTTPException(404, "Case not found")
        if db_case.status != CaseStatus.PAID: raise HTTPException(409, "Must be PAID")
        if db_case.requester_id != current_user.username: raise HTTPException(403, "Not owner")

        db_case.status = CaseStatus.SETTLEMENT_SUBMITTED
        db.flush()
        # Log actual amount for DB issuance later
        log_audit_event(db, "case", case_id, "settlement_submit", current_user.username, {"actual_amount": float(settlement_in.actual_amount)})
        return WorkflowResponse(message="Settlement Submitted", case_id=str(case_id), status="SETTLEMENT_SUBMITTED")

@router.post("/{case_id}/db/issue", response_model=WorkflowResponse)
async def db_issue_case(
    case_id: UUID,
    current_user: Annotated[UserInDB, Depends(has_role([Role.ACCOUNTING, Role.ADMIN]))],
    db: Session = Depends(get_db)
):
    with db.begin():
        db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
        if not db_case: raise HTTPException(404, "Case not found")
        if db_case.status != CaseStatus.SETTLEMENT_SUBMITTED: raise HTTPException(409, "Must be SETTLEMENT_SUBMITTED")
        
        if db.execute(select(Document).filter_by(case_id=case_id, doc_type=DocumentType.DB)).scalar_one_or_none():
             raise HTTPException(409, "DB already exists")

        # Get actual amount from audit log (simplified)
        log = db.execute(select(AuditLog).filter_by(entity_id=case_id, action="settlement_submit").order_by(AuditLog.performed_at.desc())).scalar_one_or_none()
        actual_amount = decimal.Decimal(log.details_json["actual_amount"]) if log else db_case.requested_amount

        db_doc_no = _generate_document_no(db, DocumentType.DB)
        db_doc = Document(case_id=case_id, doc_type=DocumentType.DB, doc_no=db_doc_no, amount=actual_amount, pdf_uri="generated_by_backend", created_by=current_user.username)
        db.add(db_doc)

        db_case.status = CaseStatus.CLOSED # Close case after DB
        db.flush()
        log_audit_event(db, "case", case_id, "db_issue", current_user.username, {"doc": db_doc_no})
        return WorkflowResponse(message="DB Issued & Closed", case_id=str(case_id), status="CLOSED", doc_no=db_doc_no)

# ... (list_cases, list_attachments, etc. ใช้ของเดิมได้)
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