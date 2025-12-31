from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db import get_db
from app.deps import Role, get_current_user, UserInDB
from app.models import Case, Attachment, AttachmentType
from app.schemas.files import SignedUrlCreate, SignedUrlPurpose, SignedUrlResponse
from app.config import settings
from app.services import gcs
from app.services.audit import log_audit_event

router = APIRouter(
    prefix="/api/v1/files",
    tags=["Files"]
)

@router.post("/signed-url", response_model=SignedUrlResponse)
async def get_signed_url(
    signed_url_in: SignedUrlCreate,
    current_user: Annotated[UserInDB, Depends(get_current_user)],
    db: Session = Depends(get_db)
):
    db_case = db.execute(select(Case).filter_by(id=signed_url_in.case_id)).scalar_one_or_none()
    if not db_case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")

    # Check case ownership for UPLOAD purpose
    if signed_url_in.purpose == SignedUrlPurpose.UPLOAD:
        if db_case.requester_id != current_user.username:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to upload attachments to this case.")
        if not signed_url_in.attachment_type:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="attachment_type is required for UPLOAD purpose.")
        if not signed_url_in.content_type:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="content_type is required for UPLOAD purpose.")

        # Create a new attachments row FIRST to generate attachment_id
        new_attachment_id = uuid.uuid4()
        object_name = f"{settings.GCS_BASE_PATH}/cases/{db_case.id}/attachments/{new_attachment_id}/{signed_url_in.filename}"
        gcs_uri = f"gs://{settings.GCS_BUCKET_NAME}/{object_name}"

        db_attachment = Attachment(
            id=new_attachment_id,
            case_id=db_case.id,
            type=signed_url_in.attachment_type, # Use the enum value
            gcs_uri=gcs_uri,
            uploaded_by=current_user.username,
            uploaded_at=datetime.now(timezone.utc)
        )
        db.add(db_attachment)
        db.flush() # Flush to make sure attachment_id is available if needed

        signed_url = gcs.generate_signed_upload_url(
            object_name=object_name,
            content_type=signed_url_in.content_type
        )

        log_audit_event(
            db,
            entity_type="attachment",
            entity_id=db_attachment.id,
            action="attachment_upload_url_created",
            performed_by=current_user.username,
            details_json={
                "case_id": str(db_case.id),
                "filename": signed_url_in.filename,
                "content_type": signed_url_in.content_type,
                "gcs_uri": gcs_uri,
                "expires_in_seconds": settings.SIGNED_URL_EXPIRATION_SECONDS
            }
        )
        db.commit()

        return SignedUrlResponse(
            attachment_id=new_attachment_id,
            gcs_uri=gcs_uri,
            signed_url=signed_url,
            method="PUT",
            expires_in=settings.SIGNED_URL_EXPIRATION_SECONDS
        )

    elif signed_url_in.purpose == SignedUrlPurpose.DOWNLOAD:
        if not signed_url_in.attachment_type: # For DOWNLOAD, attachment_type is optional but we need a way to identify the attachment.
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="attachment_type or attachment_id is required for DOWNLOAD purpose.")

        # Retrieve the attachment based on case_id and attachment_type (or id if provided)
        attachment_query = select(Attachment).filter_by(case_id=db_case.id)

        # Assuming for download, we need attachment_id to pinpoint the file
        if signed_url_in.attachment_type: # If type is provided, find the latest one.
            attachment = db.execute(attachment_query.filter_by(type=signed_url_in.attachment_type).order_by(Attachment.uploaded_at.desc())).scalar_one_or_none()
        elif signed_url_in.attachment_id: # If ID is provided
            attachment = db.execute(attachment_query.filter_by(id=signed_url_in.attachment_id)).scalar_one_or_none()
        else:
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Either attachment_type or attachment_id must be provided for DOWNLOAD purpose.")

        if not attachment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found.")

        # Visibility check for download
        can_see_all = any(role in current_user.roles for role in [
            Role.FINANCE, Role.ACCOUNTING, Role.ADMIN, Role.EXECUTIVE, Role.TREASURY
        ])
        if not can_see_all and db_case.requester_id != current_user.username:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to download this attachment.")

        # Extract object_name from gcs_uri
        # gcs_uri format: gs://<bucket>/<object_name>
        object_name_start_index = len(f"gs://{settings.GCS_BUCKET_NAME}/")
        object_name = attachment.gcs_uri[object_name_start_index:]

        signed_url = gcs.generate_signed_download_url(object_name=object_name)

        log_audit_event(
            db,
            entity_type="attachment",
            entity_id=attachment.id,
            action="attachment_download_url_created",
            performed_by=current_user.username,
            details_json={
                "case_id": str(db_case.id),
                "attachment_id": str(attachment.id),
                "filename": signed_url_in.filename, # filename from request, not stored in DB
                "gcs_uri": attachment.gcs_uri,
                "expires_in_seconds": settings.SIGNED_URL_EXPIRATION_SECONDS
            }
        )
        db.commit()

        return SignedUrlResponse(
            signed_url=signed_url,
            method="GET",
            expires_in=settings.SIGNED_URL_EXPIRATION_SECONDS
        )
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid purpose specified.")
