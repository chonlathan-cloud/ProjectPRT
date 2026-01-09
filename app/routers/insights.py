from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, or_
from typing import Optional, List
from datetime import datetime

from app.db import get_db
from app.models import Case, User, CaseStatus
from app.schemas.common import ResponseEnvelope, make_success_response
# คุณอาจต้องสร้าง Schema นี้เพิ่มใน app/schemas/insights.py หรือใส่ไว้ในไฟล์นี้ชั่วคราวก็ได้
from pydantic import BaseModel

router = APIRouter()

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

@router.get("/", response_model=ResponseEnvelope[InsightsResponse])
def get_insights_data(
    username: Optional[str] = Query(None, alias="user_id"),
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    # 1. Base Query
    query = db.query(Case)

    # 2. Filter by Date (Month/Year)
    if year:
        # ถ้าส่งปีมา กรองตามปี (ใช้ created_at หรือ date field ของคุณ)
        # สมมติใช้ created_at
        query = query.filter(extract('year', Case.created_at) == year)
    
    if month:
        query = query.filter(extract('month', Case.created_at) == month)

    # 3. Filter by User (Username)
    if username:
        # Join กับ User table เพื่อหาจาก username
        query = query.join(User, Case.requester_id == User.id).filter(User.name == username) # หรือ User.username แล้วแต่ Model จริง

    # ดึงข้อมูลทั้งหมดที่ผ่าน Filter มาก่อน
    all_cases = query.all()

    # --- Calculation Logic ---
    summary = SummaryStats()
    transactions = []

    # Status Groups definition
    PENDING_STATUSES = [CaseStatus.SUBMITTED]
    APPROVED_STATUSES = [CaseStatus.APPROVED, CaseStatus.PAID, CaseStatus.CLOSED]

    for case in all_cases:
        amount = case.requested_amount or 0.0
        
        # 1. Normal (Total) - นับทุกใบที่ Query เจอ
        summary.normal_count += 1
        summary.normal_amount += amount

        # 2. Pending (Submitted)
        if case.status in PENDING_STATUSES:
            summary.pending_count += 1
            summary.pending_amount += amount

        # 3. Approved (Approved + Paid + Closed)
        if case.status in APPROVED_STATUSES:
            summary.approved_count += 1
            summary.approved_amount += amount

        # Prepare Transaction List
        transactions.append(TransactionItem(
            id=str(case.id),
            doc_no=case.case_no or "-", # หรือ case.doc_no ถ้ามี
            date=case.created_at.strftime("%d/%m/%Y"),
            creator_id=str(case.requester_id), # เดี๋ยว Frontend เอาไป Map ชื่ออีกที
            user_code=str(case.requester_id)[0:6], # Mock User Code from ID prefix
            purpose=case.purpose or "",
            amount=amount,
            status=case.status.value
        ))

    return make_success_response(
        InsightsResponse(summary=summary, transactions=transactions)
    )