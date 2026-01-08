# app/routers/dashboard.py
from fastapi import APIRouter, Request, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, extract
from datetime import datetime, date

from app.db import get_db
from app.rbac import require_roles, ROLE_ADMIN, ROLE_ACCOUNTANT, ROLE_VIEWER
from app.models import Document, DocumentType, Case, Category, CaseStatus
from app.schemas.common import make_success_response
from app.schemas.dashboard import (
    DashboardResponse, MonthlyData, ActivityData, TransactionItem
)

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
    # 1. Permission Check
    _, auth_error = require_roles(db, request, [ROLE_ADMIN, ROLE_ACCOUNTANT, ROLE_VIEWER])
    if auth_error:
        return auth_error

    # ---------------------------------------------------------
    # Helper Filter: สร้างตัวแปรเก็บเงื่อนไขพื้นฐานไว้ใช้ซ้ำ
    # กรองเฉพาะปีที่เลือก และ ตัดเคสที่ยกเลิก/ปฏิเสธ/ดราฟทิ้ง (แล้วแต่ Business logic ว่าจะนับสถานะไหนบ้าง)
    # ในที่นี้สมมติว่านับเฉพาะที่ APPROVED หรือ PAID แล้ว หรืออย่างน้อยต้องไม่ Cancelled
    base_filter = [
        extract('year', Document.created_at) == year,
        Case.status.notin_([CaseStatus.DRAFT, CaseStatus.CANCELLED, CaseStatus.REJECTED]) # <--- สำคัญ!
    ]
    # ---------------------------------------------------------

    # A. Summary
    # ต้อง Join Case เพื่อเช็ค Status
    income_sum = db.query(func.sum(Document.amount))\
        .join(Case, Document.case_id == Case.id)\
        .filter(
            *base_filter,
            Document.doc_type == DocumentType.RV
        ).scalar() or 0.0

    expense_sum = db.query(func.sum(Document.amount))\
        .join(Case, Document.case_id == Case.id)\
        .filter(
            *base_filter,
            Document.doc_type == DocumentType.PV
        ).scalar() or 0.0

    balance = float(income_sum) - float(expense_sum)

    # B. Monthly Stats (PV Only)
    monthly_data = db.query(
        extract('month', Document.created_at).label('month'),
        func.sum(Document.amount).label('total')
    ).join(Case, Document.case_id == Case.id)\
     .filter(
        *base_filter,
        Document.doc_type == DocumentType.PV
    ).group_by('month').all()

    # ... (ส่วน Mapping เดือน เหมือนเดิม) ...
    months_map = {int(m): float(v) for m, v in monthly_data}
    months_name = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    monthly_stats = []
    for i, name in enumerate(months_name):
        val = months_map.get(i + 1, 0.0)
        monthly_stats.append(MonthlyData(name=name, value=val))

    # C. Activity Stats (Category)
    cat_data = db.query(
        Category.name_th,
        func.sum(Document.amount)
    ).join(Case, Document.case_id == Case.id)\
     .join(Category, Case.category_id == Category.id)\
     .filter(
        *base_filter,
        Document.doc_type == DocumentType.PV
     ).group_by(Category.name_th).all()

    # ... (ส่วนสีและ Loop เหมือนเดิม) ...
    colors = ["#8884d8", "#82ca9d", "#ffc658", "#ff8042", "#0088fe", "#00C49F"]
    activity_stats = []
    for i, (name, val) in enumerate(cat_data):
        activity_stats.append(ActivityData(
            name=name,
            value=float(val),
            fill=colors[i % len(colors)]
        ))

    # D. Latest Transactions
    latest_docs = db.query(Document, Case, Category)\
        .join(Case, Document.case_id == Case.id)\
        .join(Category, Case.category_id == Category.id)\
        .filter(*base_filter)\
        .order_by(desc(Document.created_at))\
        .limit(5).all()

    # ... (ส่วน Loop latest_transactions เหมือนเดิม) ...
    latest_transactions = []
    for doc, case, cat in latest_docs:
        initial_char = "P" if doc.doc_type == DocumentType.PV else "R"
        latest_transactions.append(TransactionItem(
            id=str(doc.id),
            initial=initial_char, 
            name=cat.name_th,
            description=f"{doc.doc_no} - {case.purpose}",
            amount=float(doc.amount)
        ))

    return make_success_response({
        "summary": {
            "expenses": float(expense_sum),
            "income": float(income_sum),
            "balance": balance
        },
        "monthlyStats": monthly_stats,
        "activityStats": activity_stats,
        "latestTransactions": latest_transactions
    })