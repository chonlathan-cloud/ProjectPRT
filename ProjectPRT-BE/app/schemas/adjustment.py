from datetime import datetime
from typing import Optional, List
from uuid import UUID
import decimal
import enum

from pydantic import BaseModel, Field, ConfigDict

from app.models import PaymentType


class AdjustmentType(str, enum.Enum):
    # Mirror PaymentType values without subclassing the enum itself
    REFUND = PaymentType.REFUND.value
    ADDITIONAL = PaymentType.ADDITIONAL.value


class AdjustmentCreate(BaseModel):
    type: AdjustmentType
    amount: decimal.Decimal = Field(..., gt=0, decimal_places=2)
    reference_no: Optional[str] = None


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    case_id: UUID
    type: PaymentType
    amount: decimal.Decimal
    paid_by: str
    paid_at: datetime
    reference_no: Optional[str] = None


class VarianceResponse(BaseModel):
    case_id: UUID
    cr_amount: decimal.Decimal
    db_amount: decimal.Decimal
    variance: decimal.Decimal
    expected_adjustment_type: Optional[AdjustmentType] = None
    expected_adjustment_amount: decimal.Decimal
    adjustments_recorded: List[PaymentOut]
