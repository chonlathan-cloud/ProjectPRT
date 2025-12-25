from datetime import datetime, timezone
from typing import Optional, List, Annotated
from uuid import UUID
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_

from app.db import get_db
from app.deps import Role, has_role, get_current_user
from app.models import Category, Case, CaseStatus, FundingType
from app.schemas.case import CaseCreate, CaseResponse, CaseSubmit
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

@router.post("/", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
async def create_case(
    case_in: CaseCreate,
    current_user: Annotated[str, Depends(has_role([Role.REQUESTER]))],
    db: Session = Depends(get_db)
):
    # Validate category exists and is active
    category = db.execute(select(Category).filter_by(id=case_in.category_id)).scalar_one_or_none()
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
        category_id=case_in.category_id,
        account_code=account_code, # Denormalized
        requester_id=current_user,
        department_id=case_in.department_id,
        cost_center_id=case_in.cost_center_id,
        funding_type=case_in.funding_type,
        requested_amount=case_in.requested_amount,
        purpose=case_in.purpose,
        status=CaseStatus.DRAFT, # Initial status
        created_by=current_user
    )

    db.add(db_case)
    db.flush() # Flush to get the ID for audit logging

    log_audit_event(
        db,
        entity_type="case",
        entity_id=db_case.id,
        action="create",
        performed_by=current_user,
        details_json=case_in.model_dump(mode="json") # JSON-serializable payload
    )

    db.commit()
    db.refresh(db_case)
    return CaseResponse.model_validate(db_case)


@router.post("/{case_id}/submit", response_model=CaseResponse)
async def submit_case(
    case_id: UUID,
    # case_submit: CaseSubmit, # Not strictly needed if body is empty
    current_user: Annotated[str, Depends(has_role([Role.REQUESTER]))],
    db: Session = Depends(get_db)
):
    db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
    if not db_case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")

    # Visibility rule: requester can submit ONLY their own case
    if db_case.requester_id != current_user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to submit this case.")

    # Allowed transition: DRAFT -> SUBMITTED only
    if db_case.status != CaseStatus.DRAFT:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Case cannot be submitted from status {db_case.status.value}. Only DRAFT cases can be submitted.")

    old_status = db_case.status
    db_case.status = CaseStatus.SUBMITTED
    db_case.updated_by = current_user
    db_case.updated_at = datetime.now(timezone.utc)

    db.flush()

    log_audit_event(
        db,
        entity_type="case",
        entity_id=db_case.id,
        action="submit",
        performed_by=current_user,
        details_json={
            "old_status": old_status.value,
            "new_status": db_case.status.value
        } # JSON-serializable
    )

    db.commit()
    db.refresh(db_case)
    return CaseResponse.model_validate(db_case)


@router.get("/", response_model=List[CaseResponse])
async def read_cases(
    current_user: Annotated[str, Depends(get_current_user)],
    current_user_roles: Annotated[List[Role], Depends(has_role([]))],
    db: Session = Depends(get_db),
    status: Optional[CaseStatus] = None
):
    query = select(Case)
    conditions = []

    # Determine if the current user has any non-requester special roles
    can_see_all = any(role in current_user_roles for role in [
        Role.FINANCE, Role.ACCOUNTING, Role.ADMIN, Role.EXECUTIVE, Role.TREASURY
    ])

    # Visibility rules
    if not can_see_all:
        # If the user is only a REQUESTER (or has no special roles), they can only see their own cases
        conditions.append(Case.requester_id == current_user)

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
    current_user: Annotated[str, Depends(get_current_user)],
    current_user_roles: Annotated[List[Role], Depends(has_role([]))],
    db: Session = Depends(get_db)
):
    db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
    if not db_case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")

    # Determine if the current user has any non-requester special roles
    can_see_all = any(role in current_user_roles for role in [
        Role.FINANCE, Role.ACCOUNTING, Role.ADMIN, Role.EXECUTIVE, Role.TREASURY
    ])

    # Visibility rules
    if not can_see_all:
        # If the user is only a REQUESTER (or has no special roles), they can only see their own cases
        if db_case.requester_id != current_user:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this case.")

    return CaseResponse.model_validate(db_case)
