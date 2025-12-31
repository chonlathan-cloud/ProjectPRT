from datetime import datetime, timezone
from typing import List, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db import get_db
from app.deps import get_current_user, UserInDB
from app.models import Document, Case, DocumentType # Import DocumentType
from app.schemas.document import DocumentOut
from app.schemas.files import SignedUrlResponse
from app.services.audit import log_audit_event
from app.config import settings
from app.services import gcs
from app.routers.cases import _ensure_case_visibility # Reusing the helper from cases router


router = APIRouter(
    prefix="/api/v1/cases/{case_id}/documents",
    tags=["Documents"]
)

@router.get("", response_model=List[DocumentOut])
async def list_documents_for_case(
    case_id: UUID,
    current_user: Annotated[UserInDB, Depends(get_current_user)],
    db: Session = Depends(get_db)
):
    db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
    if not db_case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")

    _ensure_case_visibility(db_case, current_user)

    # Order by doc_type (PS, CR, DB) and then created_at
    documents = db.execute(
        select(Document)
        .filter_by(case_id=case_id)
        .order_by(Document.created_at.asc())
    ).scalars().all()

    return [DocumentOut.model_validate(doc) for doc in documents]


@router.get("/{doc_type}/download-url", response_model=SignedUrlResponse)
async def get_document_download_url(
    case_id: UUID,
    doc_type: DocumentType, # Use DocumentType enum for validation
    current_user: Annotated[UserInDB, Depends(get_current_user)],
    db: Session = Depends(get_db)
):
    db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
    if not db_case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")

    _ensure_case_visibility(db_case, current_user)

    db_document = db.execute(
        select(Document)
        .filter_by(case_id=case_id, doc_type=doc_type)
    ).scalar_one_or_none()

    if not db_document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{doc_type.value} document not found for case {case_id}.")

    if not db_document.pdf_uri or db_document.pdf_uri.startswith("placeholder_"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"PDF URI for {doc_type.value} document not found or is a placeholder.")

    # Extract object_name from pdf_uri
    # Assuming pdf_uri format is gs://<bucket_name>/<object_name>
    uri_prefix = f"gs://{settings.GCS_BUCKET_NAME}/"
    if not db_document.pdf_uri.startswith(uri_prefix):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid PDF URI format.")

    object_name = db_document.pdf_uri[len(uri_prefix):]

    signed_url = gcs.generate_signed_download_url(object_name=object_name)

    log_audit_event(
        db,
        entity_type="document",
        entity_id=db_document.id,
        action="download_url_generated",
        performed_by=current_user.username,
        details_json={
            "case_id": str(db_case.id),
            "doc_type": doc_type.value,
            "doc_no": db_document.doc_no,
            "pdf_uri": db_document.pdf_uri,
            "expires_in_seconds": settings.SIGNED_URL_EXPIRATION_SECONDS
        }
    )
    db.commit()

    return SignedUrlResponse(
        signed_url=signed_url,
        method="GET",
        expires_in=settings.SIGNED_URL_EXPIRATION_SECONDS
    )