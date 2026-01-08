from fastapi import APIRouter, Request, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, extract, select, case as sql_case
from datetime import datetime
from typing import List, Optional

from app.db import get_db
from app.rbac import require_roles, ROLE_ADMIN, ROLE_ACCOUNTANT, ROLE_VIEWER, ROLE_EXECUTIVE
from app.models import (
    Document, DocumentType, 
    Case, CaseStatus, 
    Category, CategoryType, 
    User
)
from app.schemas.common import make_success_response
from app.schemas.dashboard import (
    DashboardResponse, 
    DashboardData, 
    MonthlyData, 
    ActivityData, 
    TransactionItem
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
    """
    ดึงข้อมูล Dashboard ภาพรวม (Summary, Graph, Pie Chart, Recent Docs)
    - กรองเฉพาะรายการที่อนุมัติแล้ว (Approved, Paid, Closed)
    - อ้างอิงยอดเงินจากเอกสาร (Document Table)
    """

    # 1. Permission Check
    # อนุญาต Admin, Accounting, Viewer, Executive
    _, auth_error = require_roles(db, request, [ROLE_ADMIN, ROLE_ACCOUNTANT, ROLE_VIEWER, ROLE_EXECUTIVE])
    if auth_error:
        # ถ้าไม่มีสิทธิ์ Return Error กลับไป
        return auth_error

    # 2. Define Constants
    # สถานะที่ถือว่าเงิน "ถูกใช้ไปแล้ว" หรือ "ได้รับแล้ว" จริงๆ
    VALID_STATUSES = [CaseStatus.APPROVED, CaseStatus.PAID, CaseStatus.CLOSED]

    # =========================================================
    # A. Summary Stats (Income, Expense, Balance)
    # =========================================================
    
    # 3.1 Calculate Total Expense (รายจ่าย = PV)
    stmt_expense = (
        select(func.sum(Document.amount))
        .join(Case, Document.case_id == Case.id)
        .where(
            Document.doc_type == DocumentType.PV,
            Case.status.in_(VALID_STATUSES),
            extract('year', Document.created_at) == year
        )
    )
    expense_sum = db.execute(stmt_expense).scalar() or 0.0

    # 3.2 Calculate Total Income (รายรับ = RV)
    stmt_income = (
        select(func.sum(Document.amount))
        .join(Case, Document.case_id == Case.id)
        .where(
            Document.doc_type == DocumentType.RV,
            Case.status.in_(VALID_STATUSES),
            extract('year', Document.created_at) == year
        )
    )
    income_sum = db.execute(stmt_income).scalar() or 0.0
    
    # 3.3 Balance
    balance = float(income_sum) - float(expense_sum)

    # =========================================================
    # B. Monthly Stats (Bar Graph)
    # =========================================================
    # แสดงแนวโน้มรายจ่าย (Expense) รายเดือน
    stmt_monthly = (
        select(
            extract('month', Document.created_at).label('month'),
            func.sum(Document.amount).label('total')
        )
        .join(Case, Document.case_id == Case.id)
        .where(
            Document.doc_type == DocumentType.PV, # ดูเฉพาะรายจ่าย
            Case.status.in_(VALID_STATUSES),
            extract('year', Document.created_at) == year
        )
        .group_by(extract('month', Document.created_at))
    )
    monthly_results = db.execute(stmt_monthly).all()
    
    # Mapping Data ให้ครบ 12 เดือน (กันเดือนที่ไม่มีข้อมูลหายไป)
    expense_map = {int(row.month): float(row.total) for row in monthly_results}
    months_list = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    
    monthly_stats = []
    for i, m_name in enumerate(months_list):
        # เดือนเริ่มที่ 1, index เริ่มที่ 0
        monthly_stats.append(MonthlyData(
            name=m_name, 
            value=expense_map.get(i+1, 0.0)
        ))

    # =========================================================
    # C. Activity Stats (Pie Chart) - By Category
    # =========================================================
    stmt_activity = (
        select(Category.name_th, func.sum(Document.amount))
        .join(Case, Document.case_id == Case.id)
        .join(Category, Case.category_id == Category.id)
        .where(
            Document.doc_type == DocumentType.PV, # เฉพาะรายจ่าย
            Case.status.in_(VALID_STATUSES),
            extract('year', Document.created_at) == year
        )
        .group_by(Category.name_th)
    )
    activity_results = db.execute(stmt_activity).all()
    
    activity_stats = []
    # Palette สีสำหรับ Pie Chart
    colors = ["#8884d8", "#82ca9d", "#ffc658", "#ff8042", "#0088fe", "#00C49F", "#FFBB28", "#FF8042"]
    
    for i, (cat_name, val) in enumerate(activity_results):
        activity_stats.append(ActivityData(
            name=cat_name, 
            value=float(val), 
            fill=colors[i % len(colors)] # วนสีถ้า Category เยอะกว่าสีที่มี
        ))

    # =========================================================
    # D. Latest Transactions (Table)
    # =========================================================
    stmt_latest = (
        select(Document, Case, Category, User)
        .join(Case, Document.case_id == Case.id)
        .outerjoin(Category, Case.category_id == Category.id) # Outer join กันพลาดถ้าไม่มี Category
        .outerjoin(User, Case.requester_id == User.email)    # Join User เพื่อเอาชื่อคนขอเบิก
        .where(
            Case.status.in_(VALID_STATUSES),
            extract('year', Document.created_at) == year
        )
        .order_by(Document.created_at.desc()) # ล่าสุดขึ้นก่อน
        .limit(5)
    )
    latest_docs = db.execute(stmt_latest).all()
    
    tx_list = []
    for row in latest_docs:
        doc = row.Document
        case_obj = row.Case
        category = row.Category
        user = row.User
        
        # จัดการ Null Safety
        cat_name = category.name_th if category else "General"
        initial = category.name_en[0].upper() if (category and category.name_en) else "D"
        requester_name = user.name if user else (case_obj.requester_id or "Unknown")

        tx_list.append(TransactionItem(
            id=str(doc.id),
            initial=initial,
            name=f"{cat_name} ({requester_name})", # แสดงชื่อหมวดหมู่ + ชื่อคนเบิก
            description=doc.doc_no,                # แสดงเลขที่เอกสาร PV-xxxx
            amount=float(doc.amount),
            date=doc.created_at.strftime("%Y-%m-%d") # เพิ่มวันที่ถ้า Frontend รองรับ
        ))

    # =========================================================
    # Return Response
    # =========================================================
    return make_success_response({
        "summary": {
            "expenses": float(expense_sum), 
            "income": float(income_sum), 
            "balance": balance
        },
        "monthlyStats": monthly_stats,
        "activityStats": activity_stats,
        "latestTransactions": tx_list
    })