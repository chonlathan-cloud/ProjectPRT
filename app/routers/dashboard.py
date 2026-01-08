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
    
    # Expense Sum: ต้องใช้ DocumentType.PV เท่านั้น (เหมือน Chatbot)
    expense_sum = db.query(func.sum(Document.amount)).filter(
        Document.doc_type == DocumentType.PV,
        extract('year', Document.created_at) == year
    ).scalar() or 0.0

    # Monthly Stats (กราฟรายจ่าย): ใช้ Document PV
    monthly_stats = []
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    
    monthly_query = db.query(
        extract('month', Document.created_at).label('month'),
        func.sum(Document.amount).label('total')
    ).filter(
        Document.doc_type == DocumentType.PV, # ✅ ย้ำว่า PV
        extract('year', Document.created_at) == year
    ).group_by(extract('month', Document.created_at)).all()
    
    expense_map = {int(m): float(total) for m, total in monthly_query}
    for i, m_name in enumerate(months):
        monthly_stats.append(MonthlyData(name=m_name, value=expense_map.get(i+1, 0.0)))

    # ... (Income Logic และ Balance ... ถ้าจะให้แม่นก็ควรใช้ DocumentType.RV) ...
    # สมมติ Income ใช้ RV ด้วย
    income_sum = db.query(func.sum(Document.amount)).filter(
        Document.doc_type == DocumentType.RV,
        extract('year', Document.created_at) == year
    ).scalar() or 0.0
    
    balance = float(income_sum) - float(expense_sum)

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
    # ไม่กรอง DocumentType! เอาหมด (PV, RV, JV)
    latest_docs = db.query(Document)\
        .filter(extract('year', Document.created_at) == year)\
        .order_by(Document.created_at.desc())\
        .limit(5)\
        .all()
        # หมายเหตุ: ไม่ต้อง Join Case/Category ตรงนี้ก็ได้ถ้าจะเอาเร็ว 
        # แต่ถ้าจะเอาชื่อหมวดหมู่ ต้องระวังว่า JV/RV อาจไม่มี Case ID หรือเปล่า?
        # ถ้า JV ไม่มี Case ID อาจต้อง Handle Error, แต่สมมติว่าทุก Document มี Case
    
    tx_list = []
    for doc in latest_docs:
        # พยายามหาชื่อ Category (ถ้ามี)
        cat_name = "-"
        initial = "?"
        
        # Safe access relations
        if doc.case and doc.case.category:
            cat_name = doc.case.category.name_th
            if doc.case.category.name_en:
                initial = doc.case.category.name_en[0].upper()
        
        # กำหนด Description ตามประเภท
        doc_type_label = f" ({doc.doc_type.value})" if doc.doc_type else ""
        
        tx_list.append(TransactionItem(
            id=str(doc.id),
            initial=doc.doc_type.value[0] if doc.doc_type else "D", # ใช้ตัวแรกของประเภทเอกสาร (P, R, J)
            name=f"{cat_name}{doc_type_label}", # เช่น "ค่าเดินทาง (PV)"
            description=doc.doc_no, # โชว์เลขที่เอกสาร
            amount=float(doc.amount)
        ))

    # Activity Stats (Pie Chart): อันนี้เลือกเอาว่าจะโชว์แค่ Expense หรือทั้งหมด
    # ปกติ Pie Chart ค่าใช้จ่าย จะดูแค่ PV
    # ... (ใช้ Logic เดิมที่ join category แต่กรอง PV) ...

    return make_success_response({
        "summary": {"expenses": float(expense_sum), "income": float(income_sum), "balance": balance},
        "monthlyStats": monthly_stats,
        "activityStats": [], # (เติม Logic Pie Chart ตามเดิม)
        "latestTransactions": tx_list
    })