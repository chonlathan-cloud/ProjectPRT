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
    all_case_ids = set(payload.linked_case_ids)
    all_case_ids.add(payload.main_case_id)
    
    cases = db.execute(select(Case).filter(Case.id.in_(all_case_ids))).scalars().all()
    
    if len(cases) != len(all_case_ids):
        raise HTTPException(404, "Some cases not found.")
    
    total_amount = 0
    for c in cases:
        if c.status not in [CaseStatus.PAID, CaseStatus.APPROVED]:
             raise HTTPException(400, f"Case {c.case_no} is in {c.status.value}. Must be PAID or APPROVED.")
        total_amount += c.requested_amount

    jv_no = _generate_document_no(db, DocumentType.JV)
    
    # [CHANGE] PDF URI เป็น client-render
    jv_doc = Document(
        case_id=payload.main_case_id, 
        doc_type=DocumentType.JV,
        doc_no=jv_no,
        amount=total_amount,
        pdf_uri="client-render", # <--- เปลี่ยนตรงนี้
        created_by=current_user.username
    )
    db.add(jv_doc)
    db.flush()
    
    for c in cases:
        line = JVLineItem(
            jv_document_id=jv_doc.id,
            ref_case_id=c.id,
            amount=c.requested_amount
        )
        db.add(line)
        c.status = CaseStatus.CLOSED
        c.updated_by = current_user.username
        c.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(jv_doc)
    
    return DocumentResponse.model_validate(jv_doc)