from datetime import datetime, timezone
from typing import Optional, List, Annotated
from uuid import UUID
import uuid

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.services.doc_numbers import generate_document_no

from app.db import get_db
from app.deps import Role, has_role, get_current_user, UserInDB
from app.models import (
    Category,
    Case,
    CaseStatus,
    Document,
    DocumentType,
    CategoryType,
    User,
    Attachment,
    AttachmentType,
)
from app.schemas.workflow import WorkflowResponse
from app.schemas.case import CaseCreate, CaseResponse
from app.schemas.files import FileUploadResponse
from app.services.audit import log_audit_event
from app.services import gcs
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
    current_user: Annotated[UserInDB, Depends(get_current_user)],
    db: Session = Depends(get_db)
):
    category = db.execute(select(Category).filter_by(id=payload.category_id)).scalar_one_or_none()
    if not category:
        raise HTTPException(404, "Category not found.")
    if not category.is_active:
        raise HTTPException(400, "Category is inactive.")

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

@router.post("/{case_id}/upload-receipt", response_model=FileUploadResponse)
async def upload_receipt(
    case_id: UUID,
    current_user: Annotated[UserInDB, Depends(get_current_user)],
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
    if not db_case:
        raise HTTPException(status_code=404, detail="Case not found")

    doc = db.execute(select(Document).filter_by(case_id=case_id)).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=400, detail="Document not generated yet.")

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    destination_blob_name = f"{doc.doc_no}/{timestamp}_{file.filename}"
    file_content = await file.read()
    gcs_uri = gcs.upload_bytes(
        destination_blob_name,
        file_content,
        content_type=file.content_type or "application/octet-stream"
    )

    attachment = Attachment(
        case_id=case_id,
        type=AttachmentType.RECEIPT,
        gcs_uri=destination_blob_name,
        uploaded_by=current_user.username
    )
    db.add(attachment)
    db_case.is_receipt_uploaded = True
    db.commit()
    db.refresh(attachment)

    return FileUploadResponse(
        id=attachment.id,
        case_id=case_id,
        file_name=file.filename,
        url=gcs_uri,
        type=attachment.type
    )

@router.post("/{case_id}/submit", response_model=WorkflowResponse)
async def submit_case(
    case_id: UUID,
    current_user: Annotated[UserInDB, Depends(get_current_user)],
    db: Session = Depends(get_db)
):
    db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
    if not db_case:
        raise HTTPException(404, "Case not found.")

    if db_case.requester_id != current_user.username:
        raise HTTPException(403, "Not authorized.")
    if db_case.status != CaseStatus.DRAFT:
        raise HTTPException(409, "Only DRAFT cases can be submitted.")

    # --- Gen Document No ---
    category = db.execute(select(Category).filter_by(id=db_case.category_id)).scalar_one()

    if category.type == CategoryType.EXPENSE:
        doc_type = DocumentType.PV
    elif category.type == CategoryType.REVENUE:
        doc_type = DocumentType.RV
    else:
        doc_type = DocumentType.JV  # ครอบคลุม ASSET และอื่นๆ

    existing_doc = db.execute(select(Document).filter_by(case_id=case_id)).scalar_one_or_none()

    if not existing_doc:
        doc_no = generate_document_no(db, doc_type)
        new_doc = Document(
            case_id=case_id,
            doc_type=doc_type,
            doc_no=doc_no,
            amount=db_case.requested_amount,
            pdf_uri="pending-approval",
            created_by=current_user.username
        )
        db.add(new_doc)
        db.flush()
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
    if not db_case:
        raise HTTPException(404, "Case not found")

    if db_case.status != CaseStatus.SUBMITTED:
        raise HTTPException(409, "Case must be SUBMITTED to approve.")

    category = db.execute(select(Category).filter_by(id=db_case.category_id)).scalar_one()
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
    if not db_case:
        raise HTTPException(404, "Case not found")
    if db_case.status != CaseStatus.APPROVED:
        raise HTTPException(409, "Case must be APPROVED to pay.")

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

    can_see_all = any(role in current_user.roles for role in [
        Role.FINANCE, Role.ACCOUNTING, Role.ADMIN, Role.EXECUTIVE, Role.TREASURY
    ])
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

@router.get("/search-by-doc", response_model=List[CaseAdminView])
async def search_cases(
    doc_no: str = Query(..., min_length=3),
    db: Session = Depends(get_db)
):
    """
    ค้นหา Case จากเลขที่เอกสาร (PV-xxxx, RV-xxxx)
    """
    results = db.query(Case).join(Document).filter(
        Document.doc_no.ilike(f"%{doc_no}%")
    ).all()

    mapped_results = []
    for row in results:
        doc = db.query(Document).filter(Document.case_id == row.id).first()
        mapped_results.append(CaseAdminView(
            id=row.id,
            case_no=row.case_no,
            doc_no=doc.doc_no if doc else "-",
            requester_name=row.requester_id,
            description=row.purpose,
            requested_amount=float(row.requested_amount),
            created_at=row.created_at,
            status=row.status.value,
            department=row.department_id
        ))
    return mapped_results

@router.get("/{case_id}", response_model=CaseResponse)
async def read_case(
    case_id: UUID,
    current_user: Annotated[UserInDB, Depends(get_current_user)],
    db: Session = Depends(get_db)
):
    db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
    if not db_case:
        raise HTTPException(404, "Not Found")
    _ensure_case_visibility(db_case, current_user)
    return CaseResponse.model_validate(db_case)
