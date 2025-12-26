from pydantic import BaseModel
from typing import List
from app.schemas.common import ResponseEnvelope


class SummaryData(BaseModel):
    total_income: float
    total_expense: float
    balance: float


class SummaryResponse(ResponseEnvelope):
    data: SummaryData


class MonthlyItem(BaseModel):
    month: str
    income: float
    expense: float


class MonthlyResponse(ResponseEnvelope):
    data: List[MonthlyItem]
