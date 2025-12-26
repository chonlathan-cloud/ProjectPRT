from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from app.models import DocumentType

class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    case_id: UUID
    doc_type: DocumentType
    doc_no: str
    amount: float
    pdf_uri: str | None
    created_by: str
    created_at: datetime
