from pydantic import BaseModel
from typing import List, Optional
from app.schemas.common import ResponseEnvelope

class SummaryData(BaseModel):
    expenses: float
    income: float
    balance: float

class MonthlyData(BaseModel):
    name: str
    value: float
    highlight: bool = False

class ActivityData(BaseModel):
    name: str
    value: float
    fill: str

class TransactionItem(BaseModel):
    id: str
    initial: str
    name: str
    description: str
    amount: float

class DashboardData(BaseModel):
    summary: SummaryData
    monthlyStats: List[MonthlyData]
    activityStats: List[ActivityData]
    latestTransactions: List[TransactionItem]

class DashboardResponse(ResponseEnvelope):
    data: DashboardData
