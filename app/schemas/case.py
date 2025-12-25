from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict
from app.models import FundingType, CaseStatus # Import enums from app.models


class CaseCreate(BaseModel):
    category_id: UUID
    requested_amount: float = Field(..., gt=0) # Greater than 0
    purpose: str = Field(..., min_length=1)
    department_id: Optional[str] = None
    cost_center_id: Optional[str] = None
    funding_type: FundingType = FundingType.OPERATING


class CaseSubmit(BaseModel):
    # No specific fields for submission, but a placeholder for clarity
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
    requested_amount: float # Changed from Numeric to float for Pydantic response
    purpose: str
    status: CaseStatus
    created_by: str
    created_at: datetime
    updated_by: Optional[str] = None
    updated_at: Optional[datetime] = None
