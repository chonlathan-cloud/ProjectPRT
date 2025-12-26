from pydantic import BaseModel
from typing import Optional
from app.schemas.common import ResponseEnvelope


class TransactionCreateRequest(BaseModel):
    type: str
    category: str
    amount: float
    occurred_at: str
    note: Optional[str] = None


class TransactionCreateData(BaseModel):
    transaction_id: str
    status: str


class TransactionCreateResponse(ResponseEnvelope):
    data: TransactionCreateData
