from datetime import datetime, timezone
from typing import Optional, List, Annotated
from uuid import UUID
import uuid
import decimal # Import decimal for precise financial calculations

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from app.db import get_db
from app.deps import Role, has_role, get_current_user, UserInDB
from app.models import Category, Case, CaseStatus, FundingType, Document, DocCounter, Payment, PaymentType, DocumentType, AuditLog
from app.schemas.case import CaseCreate, CaseResponse, CaseSubmit
from app.schemas.workflow import PaymentCreate, SettlementSubmit, WorkflowResponse
from app.schemas.adjustment import AdjustmentType, AdjustmentCreate, PaymentOut, VarianceResponse # New imports
from app.services.audit import log_audit_event

router = APIRouter(
    prefix="/api/cases",
    tags=["Cases"]
)

def generate_case_no() -> str:
    """
    Generates a unique, human-readable case number.
    Format: CAS-YYMMDD-XXXXXX (last 6 chars of a UUID hex for uniqueness)
    """
    today_str = datetime.now(timezone.utc).strftime("%y%m%d")
    unique_suffix = uuid.uuid4().hex[:6].upper()
    return f"CAS-{today_str}-{unique_suffix}"

def _generate_document_no(db: Session, doc_prefix_enum: DocumentType) -> str:
    """
    Generates a unique document number for a given document type prefix.
    The number is atomically incremented using the doc_counters table.
    Format: <PREFIX>-YYMM-#### (e.g., PS-2312-0001)
    """
    doc_prefix = doc_prefix_enum.value # e.g., 'PS', 'CR', 'DB'
    current_ym = datetime.now(timezone.utc).strftime("%y%m")

    # Retrieve and increment the counter in a transactional manner
    # Using FOR UPDATE to lock the row during update
    doc_counter = db.execute(
        select(DocCounter).filter_by(doc_prefix=doc_prefix, year_month=current_ym).with_for_update()
    ).scalar_one_or_none()

    if not doc_counter:
        doc_counter = DocCounter(doc_prefix=doc_prefix_enum, year_month=current_ym, last_number=0)
        db.add(doc_counter)
        db.flush() # Ensure it's in the session to be updated
    
    doc_counter.last_number += 1
    new_number = int(doc_counter.last_number)
    
    # Pad with leading zeros to 4 digits
    padded_number = f"{new_number:04d}"

    doc_no = f"{doc_prefix}-{current_ym}-{padded_number}"
    return doc_no


async def _calculate_variance_info(
    db: Session,
    case_id: UUID,
) -> dict:
    """
    Helper function to calculate variance and expected adjustment details.
    """
    cr_document = db.execute(
        select(Document).filter_by(case_id=case_id, doc_type=DocumentType.CR)
    ).scalar_one_or_none()
    db_document = db.execute(
        select(Document).filter_by(case_id=case_id, doc_type=DocumentType.DB)
    ).scalar_one_or_none()

    if not cr_document or not db_document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CR or DB document not found for this case.")

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

# --- Inserted helper for case visibility rules ---
def _ensure_case_visibility(
    db_case: Case,
    current_user: UserInDB,
) -> None:
    """
    Enforce case visibility rules:
    - Non-privileged users (requester-only) can only access their own cases.
    - Privileged roles can access all cases.
    """
    can_see_all = any(role in current_user.roles for role in [
        Role.FINANCE, Role.ACCOUNTING, Role.ADMIN, Role.EXECUTIVE, Role.TREASURY
    ])

    if not can_see_all and db_case.requester_id != current_user.username:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this case.")


@router.post("/", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
async def create_case(
    payload: CaseCreate,
    current_user: Annotated[str, Depends(get_current_user)],
    db: Session = Depends(get_db)
):
    # Validate category exists and is active
    category = db.execute(select(Category).filter_by(id=payload.category_id)).scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")
    if not category.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category is inactive.")

    # Denormalize account_code from category
    account_code = category.account_code

    # Generate unique case_no
    case_no = generate_case_no()
    # Ensure case_no is unique (though UUID suffix makes collisions highly unlikely)
    while db.execute(select(Case).filter_by(case_no=case_no)).scalar_one_or_none():
        case_no = generate_case_no()

    db_case = Case(
        case_no=case_no,
        category_id=payload.category_id,
        account_code=account_code, # Denormalized
        requester_id=current_user.username,
        department_id=payload.department_id,
        cost_center_id=payload.cost_center_id,
        funding_type=payload.funding_type,
        requested_amount=payload.requested_amount,
        purpose=payload.purpose,
        status=CaseStatus.DRAFT, # Initial status
        created_by=current_user.username
    )

    db.add(db_case)
    db.flush() # Flush to get the ID for audit logging

    log_audit_event(
        db,
        entity_type="case",
        entity_id=db_case.id,
        action="create",
        performed_by=current_user.username,
        details_json=payload.model_dump(mode="json") # JSON-serializable payload
    )

    db.commit()
    db.refresh(db_case)
    return CaseResponse.model_validate(db_case)


@router.post("/{case_id}/submit", response_model=CaseResponse)
async def submit_case(
    case_id: UUID,
    # case_submit: CaseSubmit, # Not strictly needed if body is empty
    current_user: Annotated[UserInDB, Depends(has_role([Role.REQUESTER]))],
    db: Session = Depends(get_db)
):
    db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
    if not db_case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")

    # Visibility rule: requester can submit ONLY their own case
    if db_case.requester_id != current_user.username:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to submit this case.")

    # Allowed transition: DRAFT -> SUBMITTED only
    if db_case.status != CaseStatus.DRAFT:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Case cannot be submitted from status {db_case.status.value}. Only DRAFT cases can be submitted.")

    old_status = db_case.status
    db_case.status = CaseStatus.SUBMITTED
    db_case.updated_by = current_user.username
    db_case.updated_at = datetime.now(timezone.utc)

    db.flush()

    log_audit_event(
        db,
        entity_type="case",
        entity_id=db_case.id,
        action="submit",
        performed_by=current_user.username,
        details_json={
            "old_status": old_status.value,
            "new_status": db_case.status.value
        } # JSON-serializable
    )

    db.commit()
    db.refresh(db_case)
    return CaseResponse.model_validate(db_case)


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

        # Precondition: case.status == SUBMITTED
        if db_case.status != CaseStatus.SUBMITTED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Case status must be SUBMITTED to approve PS, but is {db_case.status.value}."
            )

        # Check if PS document already exists for this case
        existing_ps_doc = db.execute(
            select(Document).filter_by(case_id=case_id, doc_type=DocumentType.PS)
        ).scalar_one_or_none()
        if existing_ps_doc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"PS document already exists for case {case_id}."
            )

        # Generate doc_no using doc_counters
        ps_doc_no = _generate_document_no(db, DocumentType.PS)

        # Create documents row (doc_type=PS, amount=case.requested_amount, created_by=current_user.username)
        db_ps_document = Document(
            case_id=case_id,
            doc_type=DocumentType.PS,
            doc_no=ps_doc_no,
            amount=db_case.requested_amount,
            pdf_uri="placeholder_ps_uri", # Placeholder for now
            created_by=current_user.username
        )
        db.add(db_ps_document)

        # Update case.status=PS_APPROVED
        old_status = db_case.status
        db_case.status = CaseStatus.PS_APPROVED
        db_case.updated_by = current_user.username
        db_case.updated_at = datetime.now(timezone.utc)

        db.flush() # Flush to ensure all changes are registered before audit log

        # Audit action="ps_approve" with old/new status + ps_doc_no
        log_audit_event(
            db,
            entity_type="case",
            entity_id=db_case.id,
            action="ps_approve",
            performed_by=current_user.username,
            details_json={
                "old_status": old_status.value,
                "new_status": db_case.status.value,
                "ps_doc_no": ps_doc_no
            }
        )
        db.refresh(db_case)
        return WorkflowResponse(
            message=f"Case {db_case.case_no} PS approved and status set to {db_case.status.value}.",
            case_id=str(db_case.id),
            status=db_case.status.value,
            doc_no=ps_doc_no,
            audit_details={"new_status": db_case.status.value, "ps_doc_no": ps_doc_no}
        )


@router.post("/{case_id}/cr/issue", response_model=WorkflowResponse)
async def cr_issue_case(
    case_id: UUID,
    current_user: Annotated[UserInDB, Depends(has_role([Role.ACCOUNTING, Role.ADMIN]))],
    db: Session = Depends(get_db)
):
    with db.begin():
        db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
        if not db_case:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")

        # Precondition: case.status == PS_APPROVED
        if db_case.status != CaseStatus.PS_APPROVED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Case status must be PS_APPROVED to issue CR, but is {db_case.status.value}."
            )

        # Check if CR document already exists for this case
        existing_cr_doc = db.execute(
            select(Document).filter_by(case_id=case_id, doc_type=DocumentType.CR)
        ).scalar_one_or_none()
        if existing_cr_doc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"CR document already exists for case {case_id}."
            )

        # Generate CR doc_no via doc_counters
        cr_doc_no = _generate_document_no(db, DocumentType.CR)

        # Create documents row (doc_type=CR, amount=case.requested_amount)
        db_cr_document = Document(
            case_id=case_id,
            doc_type=DocumentType.CR,
            doc_no=cr_doc_no,
            amount=db_case.requested_amount,
            pdf_uri="placeholder_cr_uri", # Placeholder for now
            created_by=current_user.username
        )
        db.add(db_cr_document)

        # Update case.status=CR_ISSUED
        old_status = db_case.status
        db_case.status = CaseStatus.CR_ISSUED
        db_case.updated_by = current_user.username
        db_case.updated_at = datetime.now(timezone.utc)

        db.flush() # Flush to ensure all changes are registered before audit log

        # Audit action="cr_issue" with old/new status + cr_doc_no
        log_audit_event(
            db,
            entity_type="case",
            entity_id=db_case.id,
            action="cr_issue",
            performed_by=current_user.username,
            details_json={
                "old_status": old_status.value,
                "new_status": db_case.status.value,
                "cr_doc_no": cr_doc_no
            }
        )
        db.refresh(db_case)
        return WorkflowResponse(
            message=f"Case {db_case.case_no} CR issued and status set to {db_case.status.value}.",
            case_id=str(db_case.id),
            status=db_case.status.value,
            doc_no=cr_doc_no,
            audit_details={"new_status": db_case.status.value, "cr_doc_no": cr_doc_no}
        )


@router.post("/{case_id}/payment", response_model=WorkflowResponse)
async def record_payment_for_case(
    case_id: UUID,
    payment_in: PaymentCreate,
    current_user: Annotated[UserInDB, Depends(has_role([Role.TREASURY, Role.ADMIN]))],
    db: Session = Depends(get_db)
):
    with db.begin():
        db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
        if not db_case:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")

        # Precondition: case.status == CR_ISSUED
        if db_case.status != CaseStatus.CR_ISSUED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Case status must be CR_ISSUED to record payment, but is {db_case.status.value}."
            )

        # Find CR document for the case
        cr_document = db.execute(
            select(Document).filter_by(case_id=case_id, doc_type=DocumentType.CR)
        ).scalar_one_or_none()
        if not cr_document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"CR document not found for case {case_id}. Cannot record payment."
            )

        # Check if payment already exists for this case
        existing_payment = db.execute(
            select(Payment).filter_by(case_id=case_id, type=PaymentType.DISBURSE)
        ).scalar_one_or_none()
        if existing_payment:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Payment already recorded for case {case_id}."
            )

        # Insert payments row
        db_payment = Payment(
            case_id=case_id,
            type=PaymentType.DISBURSE,
            amount=cr_document.amount,
            paid_by=current_user.username,
            paid_at=datetime.now(timezone.utc),
            reference_no=payment_in.reference_no
        )
        db.add(db_payment)

        # Update case.status=PAID
        old_status = db_case.status
        db_case.status = CaseStatus.PAID
        db_case.updated_by = current_user.username
        db_case.updated_at = datetime.now(timezone.utc)

        db.flush() # Flush to ensure all changes are registered before audit log

        # Audit action="payment_disburse"
        log_audit_event(
            db,
            entity_type="case",
            entity_id=db_case.id,
            action="payment_disburse",
            performed_by=current_user.username,
            details_json={
                "old_status": old_status.value,
                "new_status": db_case.status.value,
                "payment_amount": float(db_payment.amount), # Ensure JSON-serializable
                "reference_no": db_payment.reference_no
            }
        )
        db.refresh(db_case)
        return WorkflowResponse(
            message=f"Case {db_case.case_no} payment recorded and status set to {db_case.status.value}.",
            case_id=str(db_case.id),
            status=db_case.status.value,
            audit_details={"new_status": db_case.status.value, "payment_amount": float(db_payment.amount)}
        )


@router.post("/{case_id}/settlement/submit", response_model=WorkflowResponse)
async def submit_settlement_for_case(
    case_id: UUID,
    settlement_in: SettlementSubmit,
    current_user: Annotated[UserInDB, Depends(has_role([Role.REQUESTER]))],
    db: Session = Depends(get_db)
):
    with db.begin():
        db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
        if not db_case:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")

        # Precondition: case.status == PAID
        if db_case.status != CaseStatus.PAID:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Case status must be PAID to submit settlement, but is {db_case.status.value}."
            )

        # Must own the case
        if db_case.requester_id != current_user.username:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to submit settlement for this case.")

        # Update case.status=SETTLEMENT_SUBMITTED
        old_status = db_case.status
        db_case.status = CaseStatus.SETTLEMENT_SUBMITTED
        db_case.updated_by = current_user.username
        db_case.updated_at = datetime.now(timezone.utc)

        db.flush() # Flush to ensure all changes are registered before audit log

        # Audit action="settlement_submit" with actual_amount
        log_audit_event(
            db,
            entity_type="case",
            entity_id=db_case.id,
            action="settlement_submit",
            performed_by=current_user.username,
            details_json={
                "old_status": old_status.value,
                "new_status": db_case.status.value,
                "actual_amount": float(settlement_in.actual_amount) # Store in audit log
            }
        )
        db.refresh(db_case)
        return WorkflowResponse(
            message=f"Case {db_case.case_no} settlement submitted and status set to {db_case.status.value}.",
            case_id=str(db_case.id),
            status=db_case.status.value,
            audit_details={"new_status": db_case.status.value, "actual_amount": float(settlement_in.actual_amount)}
        )


@router.post("/{case_id}/db/issue", response_model=WorkflowResponse)
async def db_issue_case(
    case_id: UUID,
    current_user: Annotated[UserInDB, Depends(has_role([Role.ACCOUNTING, Role.ADMIN]))],
    db: Session = Depends(get_db)
):
    with db.begin():
        db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
        if not db_case:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")

        # Precondition: case.status == SETTLEMENT_SUBMITTED
        if db_case.status != CaseStatus.SETTLEMENT_SUBMITTED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Case status must be SETTLEMENT_SUBMITTED to issue DB, but is {db_case.status.value}."
            )

        # Check if DB document already exists for this case
        existing_db_doc = db.execute(
            select(Document).filter_by(case_id=case_id, doc_type=DocumentType.DB)
        ).scalar_one_or_none()
        if existing_db_doc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"DB document already exists for case {case_id}."
            )

        # Retrieve actual_amount from the latest settlement_submit audit log
        settlement_audit_log = db.execute(
            select(AuditLog)
            .filter_by(entity_type="case", entity_id=case_id, action="settlement_submit")
            .order_by(AuditLog.performed_at.desc())
        ).scalar_one_or_none()

        if not settlement_audit_log or "actual_amount" not in settlement_audit_log.details_json:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Settlement actual_amount not found in audit logs. Settlement might not have been submitted."
            )
        actual_amount = decimal.Decimal(settlement_audit_log.details_json["actual_amount"])

        # Find CR document amount
        cr_document = db.execute(
            select(Document).filter_by(case_id=case_id, doc_type=DocumentType.CR)
        ).scalar_one_or_none()
        if not cr_document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"CR document not found for case {case_id}."
            )
        cr_amount = decimal.Decimal(cr_document.amount)

        # Generate DB doc_no via doc_counters
        db_doc_no = _generate_document_no(db, DocumentType.DB)

        # Create documents row (doc_type=DB, amount=actual_amount)
        db_db_document = Document(
            case_id=case_id,
            doc_type=DocumentType.DB,
            doc_no=db_doc_no,
            amount=actual_amount,
            pdf_uri="placeholder_db_uri", # Placeholder for now
            created_by=current_user.username
        )
        db.add(db_db_document)

        # Update case.status=DB_ISSUED then CLOSED
        old_status = db_case.status
        db_case.status = CaseStatus.DB_ISSUED
        db_case.updated_by = current_user.username
        db_case.updated_at = datetime.now(timezone.utc)
        
        # Immediate transition to CLOSED as per requirements
        db.flush() # Flush so the change is available for the next update in the same transaction
        db_case.status = CaseStatus.CLOSED

        variance = actual_amount - cr_amount

        db.flush() # Flush to ensure all changes are registered before audit log

        # Audit action="db_issue"
        log_audit_event(
            db,
            entity_type="case",
            entity_id=db_case.id,
            action="db_issue",
            performed_by=current_user.username,
            details_json={
                "old_status": old_status.value,
                "new_status": db_case.status.value,
                "db_doc_no": db_doc_no,
                "actual_amount": float(actual_amount), # Ensure JSON-serializable
                "cr_amount": float(cr_amount), # Ensure JSON-serializable
                "variance": float(variance) # Ensure JSON-serializable
            }
        )
        db.refresh(db_case)
        return WorkflowResponse(
            message=f"Case {db_case.case_no} DB issued and status set to {db_case.status.value}.",
            case_id=str(db_case.id),
            status=db_case.status.value,
            doc_no=db_doc_no,
            audit_details={
                "new_status": db_case.status.value,
                "db_doc_no": db_doc_no,
                "actual_amount": float(actual_amount),
                "cr_amount": float(cr_amount),
                "variance": float(variance)
            }
        )


@router.get("/", response_model=List[CaseResponse])
async def read_cases(
    current_user: Annotated[UserInDB, Depends(get_current_user)],
    db: Session = Depends(get_db),
    status: Optional[CaseStatus] = None
):
    query = select(Case)
    conditions = []

    # Determine if the current user has any non-requester special roles
    can_see_all = any(role in current_user.roles for role in [
        Role.FINANCE, Role.ACCOUNTING, Role.ADMIN, Role.EXECUTIVE, Role.TREASURY
    ])

    # Visibility rules
    if not can_see_all:
        # If the user is only a REQUESTER (or has no special roles), they can only see their own cases
        conditions.append(Case.requester_id == current_user.username)

    if status:
        conditions.append(Case.status == status)

    if conditions:
        query = query.where(and_(*conditions))

    query = query.order_by(Case.created_at.desc())
    cases = db.execute(query).scalars().all()
    return [CaseResponse.model_validate(case) for case in cases]


@router.get("/{case_id}", response_model=CaseResponse)
async def read_case(
    case_id: UUID,
    current_user: Annotated[UserInDB, Depends(get_current_user)],
    db: Session = Depends(get_db)
):
    db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
    if not db_case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")

    # Determine if the current user has any non-requester special roles
    can_see_all = any(role in current_user.roles for role in [
        Role.FINANCE, Role.ACCOUNTING, Role.ADMIN, Role.EXECUTIVE, Role.TREASURY
    ])

    # Visibility rules
    if not can_see_all:
        # If the user is only a REQUESTER (or has no special roles), they can only see their own cases
        if db_case.requester_id != current_user.username:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this case.")

    return CaseResponse.model_validate(db_case)

# --- Inserted variance endpoint ---

@router.get("/{case_id}/variance", response_model=VarianceResponse)
async def get_case_variance(
    case_id: UUID,
    current_user: Annotated[UserInDB, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    # Ensure the case exists
    db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
    if not db_case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")

    # Visibility rule
    _ensure_case_visibility(db_case, current_user)

    # Compute variance info (requires both CR and DB documents)
    info = await _calculate_variance_info(db, case_id)

    # Fetch recorded adjustments (payments of type REFUND/ADDITIONAL)
    adjustments = db.execute(
        select(Payment)
        .filter_by(case_id=case_id)
        .where(Payment.type.in_([PaymentType.REFUND, PaymentType.ADDITIONAL]))
        .order_by(Payment.paid_at.asc())
    ).scalars().all()

    return VarianceResponse(
        case_id=case_id,
        cr_amount=info["cr_amount"],
        db_amount=info["db_amount"],
        variance=info["variance"],
        expected_adjustment_type=info["expected_adjustment_type"],
        expected_adjustment_amount=info["expected_adjustment_amount"],
        adjustments_recorded=[PaymentOut.model_validate(p) for p in adjustments],
    )

# --- Under/Over Adjustment endpoint ---
@router.post("/{case_id}/adjustments", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
async def create_case_adjustment(
    case_id: UUID,
    adjustment_in: AdjustmentCreate,
    current_user: Annotated[UserInDB, Depends(has_role([Role.TREASURY, Role.ADMIN]))],
    db: Session = Depends(get_db),
):
    """
    Record an under/over adjustment after DB is issued.
    - If DB < CR => expected REFUND
    - If DB > CR => expected ADDITIONAL
    Adjustment is recorded as a Payment row with type REFUND or ADDITIONAL.
    """
    with db.begin():
        db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
        if not db_case:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")

        # Must have reached the end of the workflow (DB issued & case closed in this implementation)
        if db_case.status != CaseStatus.CLOSED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Case must be CLOSED to record adjustment, but is {db_case.status.value}."
            )

        # Compute expected adjustment type/amount from CR and DB
        info = await _calculate_variance_info(db, case_id)
        expected_type = info["expected_adjustment_type"]
        expected_amount = info["expected_adjustment_amount"]

        if expected_type is None or expected_amount == decimal.Decimal("0.00"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No adjustment is required for this case."
            )

        # Validate requested adjustment type matches expectation
        if adjustment_in.type != expected_type:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Invalid adjustment type. Expected {expected_type.value}."
            )

        # Sum existing adjustments recorded (same type)
        existing_adjustments = db.execute(
            select(Payment)
            .filter_by(case_id=case_id)
            .where(Payment.type.in_([PaymentType.REFUND, PaymentType.ADDITIONAL]))
        ).scalars().all()

        existing_total = decimal.Decimal("0.00")
        for p in existing_adjustments:
            if p.type.value == expected_type.value:
                existing_total += decimal.Decimal(p.amount)

        remaining = expected_amount - existing_total
        if remaining <= decimal.Decimal("0.00"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Adjustment has already been fully recorded for this case."
            )

        # Enforce exact match to remaining (audit-friendly, avoids partial states)
        if decimal.Decimal(adjustment_in.amount) != remaining:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Adjustment amount must equal the remaining expected amount: {str(remaining)}"
            )

        payment_type = PaymentType.REFUND if adjustment_in.type == AdjustmentType.REFUND else PaymentType.ADDITIONAL

        db_payment = Payment(
            case_id=case_id,
            type=payment_type,
            amount=adjustment_in.amount,
            paid_by=current_user.username,
            paid_at=datetime.now(timezone.utc),
            reference_no=adjustment_in.reference_no,
        )
        db.add(db_payment)
        db.flush()

        log_audit_event(
            db,
            entity_type="case",
            entity_id=db_case.id,
            action="adjustment_record",
            performed_by=current_user.username,
            details_json={
                "type": adjustment_in.type.value,
                "amount": float(adjustment_in.amount),
                "reference_no": adjustment_in.reference_no,
                "expected_amount": float(expected_amount),
            },
        )

        return PaymentOut.model_validate(db_payment)
