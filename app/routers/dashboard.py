from fastapi import APIRouter, Request, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, extract, select
from datetime import datetime, timedelta, date
from typing import List

from app.db import get_db
from app.rbac import require_roles, ROLE_ADMIN, ROLE_ACCOUNTANT, ROLE_VIEWER
from app.models import Document, DocumentType, Case, Category, TransactionV1 # ✅ Import models ที่ถูกต้อง
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
    
    # 1. Income (รายรับ): ยังคงใช้ TransactionV1 หรือถ้ามี RV (Receipt Voucher) ควรใช้ DocumentType.RV
    # เบื้องต้นคงไว้แบบเดิมก่อน หรือถ้าจะให้แม่นยำควรเช็คระบบรายรับอีกที
    income_sum = db.execute(
        select(func.sum(Document.amount))
        .filter(Document.doc_type == DocumentType.RV) # <--- ใช้ RV
        .filter(extract('year', Document.created_at) == year)
    ).scalar() or 0.0
    
    # 2. Expenses (รายจ่าย): ✅ แก้มาใช้ Document PV (เหมือน Chatbot)
    expense_sum = db.query(func.sum(Document.amount)).filter(
        Document.doc_type == DocumentType.PV, # เฉพาะใบสำคัญจ่าย
        extract('year', Document.created_at) == year
    ).scalar() or 0
    
    balance = float(income_sum) - float(expense_sum)

    # ------------------------------------------------------------------
    # B. Monthly Stats (Expenses รายเดือน จาก PV)
    # ------------------------------------------------------------------
    monthly_stats = []
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    
    # ดึงข้อมูลรายจ่ายแยกรายเดือน (Group by Month)
    # ใช้ SQL Group by เพื่อประสิทธิภาพที่ดีกว่า Loop
    monthly_query = db.query(
        extract('month', Document.created_at).label('month'),
        func.sum(Document.amount).label('total')
    ).filter(
        Document.doc_type == DocumentType.PV,
        extract('year', Document.created_at) == year
    ).group_by(extract('month', Document.created_at)).all()
    
    # แปลงผลลัพธ์เป็น Dictionary เพื่อ Map กับชื่อเดือน
    expense_map = {int(m): float(total) for m, total in monthly_query}

    for i, m_name in enumerate(months):
        val = expense_map.get(i + 1, 0.0) # เดือนเริ่มที่ 1
        monthly_stats.append(MonthlyData(name=m_name, value=val))

    # ------------------------------------------------------------------
    # C. Activity Stats (Expenses grouped by Category)
    # ------------------------------------------------------------------
    # ต้อง Join: Document -> Case -> Category
    activities = db.query(
        Category.name_th, 
        func.sum(Document.amount)
    ).join(Case, Document.case_id == Case.id)\
     .join(Category, Case.category_id == Category.id)\
     .filter(
        Document.doc_type == DocumentType.PV,
        extract('year', Document.created_at) == year
    ).group_by(Category.name_th).all()
    
    colors = ["#8884d8", "#82ca9d", "#ffc658", "#ff8042", "#0088fe", "#00C49F"]
    activity_stats = []
    for i, (cat_name, val) in enumerate(activities):
        activity_stats.append(ActivityData(
            name=cat_name, 
            value=float(val), 
            fill=colors[i % len(colors)]
        ))

    # ------------------------------------------------------------------
    # D. Latest Transactions (List of PV Documents)
    # ------------------------------------------------------------------
    latest_docs = db.query(Document, Category.name_th, Category.name_en)\
        .join(Case, Document.case_id == Case.id)\
        .join(Category, Case.category_id == Category.id)\
        .filter(
            Document.doc_type == DocumentType.PV,
            extract('year', Document.created_at) == year
        ).order_by(Document.created_at.desc()).limit(7).all()
    
    tx_list = []
    for doc, cat_th, cat_en in latest_docs:
        tx_list.append(TransactionItem(
            id=str(doc.id),
            initial=cat_en[0].upper() if cat_en else "E",
            name=cat_th, # ชื่อหมวดหมู่
            description=f"{doc.doc_no} (PV)", # เลขที่เอกสาร
            amount=float(doc.amount)
        ))

    return make_success_response({
        "summary": {"expenses": float(expense_sum), "income": float(income_sum), "balance": balance},
        "monthlyStats": monthly_stats,
        "activityStats": activity_stats,
        "latestTransactions": tx_list
    })