from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict

from app.models import AttachmentType # Import from app.models

class FileUploadResponse(BaseModel):
    id: UUID
    case_id: UUID
    file_name: str
    url: str
    type: AttachmentType

class SignedUrlPurpose(str, Enum):
    UPLOAD = "UPLOAD"
    DOWNLOAD = "DOWNLOAD"


class SignedUrlCreate(BaseModel):
    case_id: UUID
    filename: str = Field(..., min_length=1)
    content_type: Optional[str] = None # Required for UPLOAD, not for DOWNLOAD
    purpose: SignedUrlPurpose
    attachment_type: Optional[AttachmentType] = None # Required for UPLOAD if purpose=UPLOAD


class SignedUrlResponse(BaseModel):
    gcs_uri: Optional[str] = None
    attachment_id: Optional[UUID] = None # For UPLOAD
    signed_url: str
    method: str
    expires_in: int # Seconds
