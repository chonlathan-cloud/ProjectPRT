from datetime import datetime
from typing import Optional, List
from uuid import UUID
from decimal import Decimal

from pydantic import BaseModel, ConfigDict
from app.models import DocumentType

class JVCreate(BaseModel):
    main_case_id: UUID  # Case หลักที่จะให้ JV นี้ไปเกาะอยู่ (เช่น Case แรกที่เปิด)
    linked_case_ids: List[UUID] # Case อื่นๆ ที่จะเอามารวม (รวม Main Case ด้วยก็ได้ หรือไม่ก็ได้ ระบบจะจัดการให้)
    description: str = "Adjustment / Closing Entry"

class JVLineItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    ref_case_id: UUID
    amount: float

class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    case_id: UUID
    doc_type: DocumentType
    doc_no: str
    amount: float
    pdf_uri: str
    created_by: str
    created_at: datetime
    
    # Optional: แสดง JV Lines ถ้ามี
    jv_lines: List[JVLineItemResponse] = []