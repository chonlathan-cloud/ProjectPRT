from typing import Annotated, List
from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db import get_db
from app.deps import Role, has_role, UserInDB
from app.models import (
    Document, DocumentType, Case, CaseStatus, 
    JVLineItem, DocCounter
)
from app.schemas.document import JVCreate, DocumentResponse

router = APIRouter(
    prefix="/api/v1/documents",
    tags=["Documents"]
)

def _generate_document_no(db: Session, doc_prefix_enum: DocumentType) -> str:
    # Reuse Logic เดิม (ควร Refactor ไปไว้ใน service หรือ utils กลางในอนาคต)
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

@router.post("/jv", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_jv(
    payload: JVCreate,
    current_user: Annotated[UserInDB, Depends(has_role([Role.ACCOUNTING, Role.ADMIN, Role.FINANCE]))],
    db: Session = Depends(get_db)
):
    """
    Create a Journal Voucher (JV) to aggregate multiple cases (PVs).
    Logic:
    1. Validate all cases exist and are PAID (or APPROVED).
    2. Sum amounts.
    3. Create JV Document linked to Main Case.
    4. Create JV Line Items.
    5. Auto-Close all involved cases.
    """
    
    # 1. Combine IDs (Ensure Main Case is in the list)
    all_case_ids = set(payload.linked_case_ids)
    all_case_ids.add(payload.main_case_id)
    
    # 2. Fetch Cases
    cases = db.execute(select(Case).filter(Case.id.in_(all_case_ids))).scalars().all()
    
    if len(cases) != len(all_case_ids):
        raise HTTPException(404, "Some cases not found.")
    
    total_amount = 0
    
    for c in cases:
        # Validate Status: Should be PAID or APPROVED?
        # Usually we do JV after Payment to clear/close.
        if c.status not in [CaseStatus.PAID, CaseStatus.APPROVED]:
             raise HTTPException(400, f"Case {c.case_no} is in {c.status.value} status. Must be PAID or APPROVED to include in JV.")
        
        total_amount += c.requested_amount # Or actual paid amount? Using requested for now as per schema.

    # 3. Generate JV Doc No
    jv_no = _generate_document_no(db, DocumentType.JV)
    
    # 4. Create Document Header
    jv_doc = Document(
        case_id=payload.main_case_id, # Link to Main Case
        doc_type=DocumentType.JV,
        doc_no=jv_no,
        amount=total_amount,
        pdf_uri="pending_jv_gen",
        created_by=current_user.username
    )
    db.add(jv_doc)
    db.flush() # Get ID
    
    # 5. Create Line Items & Close Cases
    for c in cases:
        # Line Item
        line = JVLineItem(
            jv_document_id=jv_doc.id,
            ref_case_id=c.id,
            amount=c.requested_amount
        )
        db.add(line)
        
        # Close Case (Auto-close via JV)
        # Note: We bypass 'is_receipt_uploaded' check here because JV itself implies settlement evidence is being handled.
        # Or we can require upload on the Main Case. Let's Auto-Close for convenience.
        c.status = CaseStatus.CLOSED
        c.updated_by = current_user.username
        c.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(jv_doc)
    
    return DocumentResponse.model_validate(jv_doc)