from fastapi import APIRouter, Request, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, extract, select
from datetime import datetime, timedelta, date
from typing import List

from app.db import get_db
from app.rbac import require_roles, ROLE_ADMIN, ROLE_ACCOUNTANT, ROLE_VIEWER
from app.models import Document, DocumentType, Case, Category, TransactionV1, CaseStatus # ✅ Import models ที่ถูกต้อง
from app.schemas.common import make_success_response
from app.schemas.dashboard import (
    DashboardResponse, DashboardData, SummaryData, 
    MonthlyData, ActivityData, TransactionItem
)
from app.core.settings import settings

router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=["Dashboard"],
)

@router.get("", response_model=DashboardResponse)
async def get_full_dashboard(
    request: Request, 
    year: int = Query(default=datetime.now().year),
    db: Session = Depends(get_db)
):
    # 1. Check Permissions
    _, auth_error = require_roles(db, request, [ROLE_ADMIN, ROLE_ACCOUNTANT, ROLE_VIEWER])
    if auth_error:
        return auth_error

    # 2. Mock Data (ถ้าเปิดใช้ใน .env)
    if settings.USE_MOCK_DATA:
        # ... (Mock Data เดิม) ...
        return make_success_response({
             "summary": {"expenses": 34567, "income": 45000, "balance": 10433},
             "monthlyStats": [], # (ละไว้ฐานที่เข้าใจ)
             "activityStats": [],
             "latestTransactions": []
        })

    # 3. Real Data Query (เปลี่ยนมาใช้ Document PV ตาม Chatbot)
    
    # กำหนดช่วงเวลา (ทั้งปี)
    # หมายเหตุ: Document.created_at คือวันที่เอกสารออก (วันที่อนุมัติจ่ายจริง)
    
    # ------------------------------------------------------------------
    # A. Summary (Total for the selected year)
    # ------------------------------------------------------------------
    
    # Expense Sum: ต้องใช้ DocumentType.PV เท่านั้น (เหมือน Chatbot)
    expense_sum = db.query(func.sum(Document.amount))\
        .join(Case, Document.case_id == Case.id)\
        .filter(
            Document.doc_type == DocumentType.PV,
            Case.status == CaseStatus.APPROVED, # ✅✅ Approved Only
            extract('year', Document.created_at) == year
        ).scalar() or 0.0

    # Income (ถ้า RV ผูกกับ Case ก็ต้องทำเหมือนกัน)
    # สมมติ RV ก็ต้อง Approved
    income_sum = db.query(func.sum(Document.amount))\
        .join(Case, Document.case_id == Case.id)\
        .filter(
            Document.doc_type == DocumentType.RV,
            Case.status == CaseStatus.APPROVED, # ✅✅ Approved Only
            extract('year', Document.created_at) == year
        ).scalar() or 0.0
    
    balance = float(income_sum) - float(expense_sum)

    # =========================================================
    # B. Monthly Stats (Graph)
    # =========================================================
    monthly_query = db.query(
        extract('month', Document.created_at).label('month'),
        func.sum(Document.amount).label('total')
    ).join(Case, Document.case_id == Case.id)\
     .filter(
        Document.doc_type == DocumentType.PV,
        Case.status == CaseStatus.APPROVED, # ✅✅ Approved Only
        extract('year', Document.created_at) == year
    ).group_by(extract('month', Document.created_at)).all()
    
    # ... (Mapping Logic เหมือนเดิม) ...
    monthly_stats = []
    expense_map = {int(m): float(total) for m, total in monthly_query}
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for i, m_name in enumerate(months):
        monthly_stats.append(MonthlyData(name=m_name, value=expense_map.get(i+1, 0.0)))

    # =========================================================
    # C. Activity Stats (Pie Chart)
    # =========================================================
    activities = db.query(Category.name_th, func.sum(Document.amount))\
        .join(Case, Document.case_id == Case.id)\
        .join(Category, Case.category_id == Category.id)\
        .filter(
            Document.doc_type == DocumentType.PV,
            Case.status == CaseStatus.APPROVED, # ✅✅ Approved Only
            extract('year', Document.created_at) == year
        ).group_by(Category.name_th).all()
        
    # ... (Color & List Logic เหมือนเดิม) ...
    activity_stats = []
    colors = ["#8884d8", "#82ca9d", "#ffc658", "#ff8042", "#0088fe", "#00C49F"]
    for i, (cat_name, val) in enumerate(activities):
        activity_stats.append(ActivityData(name=cat_name, value=float(val), fill=colors[i % len(colors)]))

    # =========================================================
    # D. Latest Transactions
    # =========================================================
    latest_docs = db.query(Document)\
        .join(Case, Document.case_id == Case.id)\
        .filter(
            Case.status == CaseStatus.APPROVED, # ✅✅ Approved Only
            extract('year', Document.created_at) == year
        ).order_by(Document.created_at.desc()).limit(5).all()
    
    # ... (Transform Logic เหมือนเดิม) ...
    tx_list = []
    for doc in latest_docs:
        # Safe access
        cat_name = doc.case.category.name_th if (doc.case and doc.case.category) else "-"
        initial = doc.case.category.name_en[0] if (doc.case and doc.case.category and doc.case.category.name_en) else "D"
        
        tx_list.append(TransactionItem(
            id=str(doc.id),
            initial=initial,
            name=f"{cat_name} ({doc.doc_type.value})",
            description=doc.doc_no,
            amount=float(doc.amount)
        ))

    return make_success_response({
        "summary": {"expenses": float(expense_sum), "income": float(income_sum), "balance": balance},
        "monthlyStats": monthly_stats,
        "activityStats": activity_stats,
        "latestTransactions": tx_list
    })