from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models import AttachmentType # Import from app.models


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    case_id: UUID
    type: AttachmentType
    gcs_uri: str
    uploaded_by: str
    uploaded_at: datetime
