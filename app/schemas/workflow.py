from typing import Optional
from pydantic import BaseModel, Field


class PaymentCreate(BaseModel):
    reference_no: Optional[str] = None


class SettlementSubmit(BaseModel):
    actual_amount: float = Field(..., gt=0)


class WorkflowResponse(BaseModel):
    message: str
    case_id: str
    status: str
    doc_no: Optional[str] = None
    audit_details: Optional[dict] = None
