from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict
from app.models import FundingType, CaseStatus

class CaseCreate(BaseModel):
    category_id: UUID
    requested_amount: float = Field(..., gt=0)
    purpose: str = Field(..., min_length=1)
    department_id: Optional[str] = None
    cost_center_id: Optional[str] = None
    funding_type: FundingType = FundingType.OPERATING
    
    # [NEW] สำหรับระบุบัญชีรับเงิน (กรณี Revenue/Refund)
    deposit_account_id: Optional[UUID] = None 

class CaseSubmit(BaseModel):
    pass

class CaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    case_no: str
    category_id: UUID
    account_code: str
    requester_id: str
    department_id: Optional[str] = None
    cost_center_id: Optional[str] = None
    funding_type: FundingType
    requested_amount: float
    purpose: str
    status: CaseStatus
    
    # [NEW] Fields
    deposit_account_id: Optional[UUID] = None
    is_receipt_uploaded: bool

    created_by: str
    created_at: datetime
    updated_by: Optional[str] = None
    updated_at: Optional[datetime] = None