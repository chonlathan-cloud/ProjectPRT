from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, extract, or_
from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session, selectinload


from app.db import get_db
from app.models import Case, User, CaseStatus, Document
from app.schemas.common import ResponseEnvelope, make_success_response
# คุณอาจต้องสร้าง Schema นี้เพิ่มใน app/schemas/insights.py หรือใส่ไว้ในไฟล์นี้ชั่วคราวก็ได้
from pydantic import BaseModel

router = APIRouter(
    prefix="/api/v1/insights",
    tags=["Insights"]
)
# --- Response Schemas ---
class SummaryStats(BaseModel):
    normal_count: int = 0
    normal_amount: float = 0.0
    pending_count: int = 0
    pending_amount: float = 0.0
    approved_count: int = 0
    approved_amount: float = 0.0

class TransactionItem(BaseModel):
    id: str
    doc_no: str
    date: str
    creator_id: str  # จะคืนค่าเป็น Username หรือ User ID ก็ได้ แต่ Frontend ใช้โชว์ชื่อ
    user_code: str
    purpose: str
    amount: float
    status: str

class InsightsResponse(BaseModel):
    summary: SummaryStats
    transactions: List[TransactionItem]

# response schema wrapper
class InsightsResponseEnvelope(ResponseEnvelope):
    data: InsightsResponse

@router.get("/", response_model=InsightsResponseEnvelope)
def get_insights_data(
    username: Optional[str] = Query(None, alias="user_id"),
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    # 1. Base Query
    query = db.qurey(Case,Document.doc_no).opterjoin(Document, Case.id == Document.case_id)

    # 2. Filter by Date (Month/Year)
    if year:
        query = query.filter(extract('year', Case.created_at) == year)
    
    if month:
        query = query.filter(extract('month', Case.created_at) == month)

    # 3. Filter by User (Username)
    if username:
        query = query.join(User, Case.requester_id == User.id).filter(User.name == username)

    VALID_STATUSES = [CaseStatus.SUBMITTED, CaseStatus.APPROVED, CaseStatus.PAID, CaseStatus.CLOSED]
    query = query.filter(Case.status.in_(VALID_STATUSES))
    result = query.all()

    # --- Calculation Logic ---
    summary = SummaryStats()
    transactions = []

    for case, doc_no in result:
        amount = float(case.requested_amount or 0.0)
        
        # 1. Normal (Total)
        summary.normal_count += 1
        summary.normal_amount += amount

        # 2. Pending (Submitted)

        summary.pending_count += 1
        summary.pending_amount += amount

        # 3. Approved (Approved + Paid + Closed)
        real_doc_no = doc_no if doc_no else "-"
        # Prepare Transaction List
        transactions.append(TransactionItem(
            id=str(case.id),
            doc_no=real_doc_no,
            date=case.created_at.strftime("%d/%m/%Y"),
            creator_id=str(case.requester_id),
            user_code=str(case.requester_id)[0:6],
            purpose=case.purpose or "",
            amount=amount, # ✅ ใช้ค่าที่แปลงแล้ว
            status=case.status.value
        ))

    return make_success_response(
        InsightsResponse(summary=summary, transactions=transactions)
    )