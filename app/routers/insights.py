from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, extract, or_
from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session, selectinload
from uuid import UUID


from app.db import get_db
from app.models import Case, CaseStatus, Document, Category, CategoryType
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
    requester_id: Optional[str] = Query(None, alias="user_id"),
    category_id: Optional[UUID] = Query(None),
    category_type: Optional[CategoryType] = Query(None),
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    # 1. Base Query (โหลด documents มาด้วย เพื่อรวม doc_no ทั้งหมด)
    query = db.query(Case).options(selectinload(Case.documents))

    # 2. Filter by Date (Month/Year)
    if year:
        query = query.filter(extract("year", Case.created_at) == year)
    if month:
        query = query.filter(extract("month", Case.created_at) == month)

    # 3. Filter by User (Requester ID)
    if requester_id:
        query = query.filter(Case.requester_id == requester_id)

    # 4. Filter by Category
    if category_id:
        query = query.filter(Case.category_id == category_id)
    
    # Filter by Category Type
    if category_type:
        query = query.join(Category, Case.category_id == Category.id).filter(Category.type == category_type)

    # 4. Status definitions
    NORMAL_STATUSES = [
        CaseStatus.DRAFT,
        CaseStatus.SUBMITTED,
        CaseStatus.APPROVED,
        CaseStatus.PAID,
        CaseStatus.CLOSED,
    ]
    PENDING_STATUSES = [CaseStatus.SUBMITTED]
    APPROVED_STATUSES = [CaseStatus.APPROVED, CaseStatus.PAID, CaseStatus.CLOSED]

    # 5. Apply normal-status filter
    query = query.filter(Case.status.in_(NORMAL_STATUSES))

    results = query.all()

    # --- Calculation Logic ---
    summary = SummaryStats()
    transactions = []

    for case in results:
        amount = float(case.requested_amount or 0.0)

        # 1) Normal (Total)
        summary.normal_count += 1
        summary.normal_amount += amount

        # 2) Pending (Submitted)
        if case.status in PENDING_STATUSES:
            summary.pending_count += 1
            summary.pending_amount += amount

        # 3) Approved (Approved + Paid + Closed)
        if case.status in APPROVED_STATUSES:
            summary.approved_count += 1
            summary.approved_amount += amount

        # รวมเลขเอกสารทั้งหมด
        doc_numbers = [doc.doc_no for doc in case.documents if doc.doc_no]
        doc_no = ", ".join(doc_numbers) if doc_numbers else "-"

        transactions.append(TransactionItem(
            id=str(case.id),
            doc_no=doc_no,
            date=case.created_at.strftime("%d/%m/%Y"),
            creator_id=str(case.requester_id),
            user_code=str(case.requester_id)[0:6],
            purpose=case.purpose or "",
            amount=amount,
            status=case.status.value
        ))

    return make_success_response(
        InsightsResponse(summary=summary, transactions=transactions)
    )
