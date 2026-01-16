from datetime import datetime, timezone
from typing import Annotated, Optional
from uuid import UUID
import uuid

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db import get_db
from app.deps import get_current_user, UserInDB
from app.models import Case, Attachment, AttachmentType, CaseStatus
from app.services import gcs
from app.schemas.files import FileUploadResponse, SignedUrlResponse

router = APIRouter(
    prefix="/api/v1/files",
    tags=["Files"]
)

@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(

    current_user: Annotated[UserInDB, Depends(get_current_user)],
    
    file: UploadFile = File(...),
    case_id: UUID = Form(...),
    attachment_type: AttachmentType = Form(...),
    db: Session = Depends(get_db)
):
    """
    Upload a file to GCS and link it to a Case.
    [NEW] Logic: If attachment_type is RECEIPT, update case.is_receipt_uploaded = True
    """
    # 1. Validate Case
    db_case = db.execute(select(Case).filter_by(id=case_id)).scalar_one_or_none()
    if not db_case:
        raise HTTPException(status_code=404, detail="Case not found")

    # 2. Upload to GCS
    # Generate unique filename: {case_id}/{timestamp}_{original_name}
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    destination_blob_name = f"{case_id}/{timestamp}_{file.filename}"
    
    # Read file content
    file_content = await file.read()
    
    # Upload
    public_url = gcs.upload_bytes(
        destination_blob_name, 
        file_content, 
        content_type=file.content_type
    )

    # 3. Save Attachment Record
    attachment = Attachment(
        case_id=case_id,
        type=attachment_type,
        gcs_uri=destination_blob_name, # Store path for flexibility
        uploaded_by=current_user.username
    )
    db.add(attachment)

    # 4. [NEW LOGIC] Update Case status if Receipt
    if attachment_type == AttachmentType.RECEIPT:
        db_case.is_receipt_uploaded = True
        # Optional: Log audit or check status (must be PAID to be meaningful, but we allow upload anytime)
    
    db.commit()
    db.refresh(attachment)

    return FileUploadResponse(
        id=attachment.id,
        case_id=case_id,
        file_name=file.filename,
        url=public_url,
        type=attachment_type
    )

@router.get("/{case_id}/list", response_model=list[FileUploadResponse])
async def list_files(
    case_id: UUID,
    current_user: Annotated[UserInDB, Depends(get_current_user)],
    db: Session = Depends(get_db)
):
    # Validate Case access rights here if strictly needed
    attachments = db.execute(select(Attachment).filter_by(case_id=case_id)).scalars().all()
    
    return [
        FileUploadResponse(
            id=a.id,
            case_id=a.case_id,
            file_name=a.gcs_uri.split('/')[-1],
            url=gcs.generate_download_url(a.gcs_uri),
            type=a.type
        ) for a in attachments
    ]
