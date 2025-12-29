from fastapi import APIRouter, Request, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import datetime, timedelta, date
from typing import List

from app.db import get_db
from app.rbac import require_roles, ROLE_ADMIN, ROLE_ACCOUNTANT, ROLE_VIEWER
from app.models import TransactionV1
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

    # 2. Mock Data (ถ้าเปิดใช้)
    if settings.USE_MOCK_DATA:
        return make_success_response({
            "summary": {"expenses": 34567, "income": 45000, "balance": 10433},
            "monthlyStats": [
                {"name": "Jan", "value": 4000},
                {"name": "Feb", "value": 3000},
                {"name": "Mar", "value": 2000},
                {"name": "Apr", "value": 2780},
                {"name": "May", "value": 1890},
                {"name": "Jun", "value": 2390},
            ],
            "activityStats": [
                {"name": "Shopping", "value": 400, "fill": "#8884d8"},
                {"name": "Food", "value": 300, "fill": "#82ca9d"},
                {"name": "Rent", "value": 300, "fill": "#ffc658"},
            ],
            "latestTransactions": [
                {"id": "1", "initial": "S", "name": "Shopping", "description": "Buy clothes", "amount": 2500},
                {"id": "2", "initial": "F", "name": "Food", "description": "Dinner", "amount": 500},
            ]
        })

    # 3. Real Data Query (จาก TransactionV1)
    
    # A. Summary (Total for the selected year)
    start_date = date(year, 1, 1)
    end_date = date(year, 12, 31)
    
    income_sum = db.query(func.sum(TransactionV1.amount)).filter(
        TransactionV1.type == "income",
        TransactionV1.occurred_at >= start_date,
        TransactionV1.occurred_at <= end_date
    ).scalar() or 0
    
    expense_sum = db.query(func.sum(TransactionV1.amount)).filter(
        TransactionV1.type == "expense",
        TransactionV1.occurred_at >= start_date,
        TransactionV1.occurred_at <= end_date
    ).scalar() or 0
    
    balance = float(income_sum) - float(expense_sum)

    # B. Monthly Stats (Income vs Expense? หรือแค่ Expense ตามกราฟเดิม?)
    # สมมติกราฟโชว์ Expense รายเดือน
    monthly_stats = []
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for i, m_name in enumerate(months):
        m_start = date(year, i + 1, 1)
        if i == 11:
            m_end = date(year + 1, 1, 1)
        else:
            m_end = date(year, i + 2, 1)
            
        val = db.query(func.sum(TransactionV1.amount)).filter(
            TransactionV1.type == "expense", # โชว์รายจ่ายในกราฟ
            TransactionV1.occurred_at >= m_start,
            TransactionV1.occurred_at < m_end
        ).scalar() or 0
        
        monthly_stats.append(MonthlyData(name=m_name, value=float(val)))

    # C. Activity Stats (Expenses grouped by Category)
    activities = db.query(
        TransactionV1.category, func.sum(TransactionV1.amount)
    ).filter(
        TransactionV1.type == "expense",
        TransactionV1.occurred_at >= start_date,
        TransactionV1.occurred_at <= end_date
    ).group_by(TransactionV1.category).all()
    
    colors = ["#8884d8", "#82ca9d", "#ffc658", "#ff8042", "#0088fe", "#00C49F"]
    activity_stats = []
    for i, (cat, val) in enumerate(activities):
        activity_stats.append(ActivityData(
            name=cat, 
            value=float(val), 
            fill=colors[i % len(colors)]
        ))

    # D. Latest Transactions
    latest_txs = db.query(TransactionV1).order_by(
        TransactionV1.occurred_at.desc(), TransactionV1.created_at.desc()
        TransactionV1.occurred_at.desc(), 
        TransactionV1.created_at.desc()
    ).limit(10).all()
    
    tx_list = []
    for tx in latest_txs:
        tx_list.append(TransactionItem(
            id=str(tx.id),
            initial=tx.category[0].upper() if tx.category else "?",
            name=tx.category,
            description=tx.note or tx.occurred_at.strftime("%Y-%m-%d"),
            amount=float(tx.amount)
        ))

    return make_success_response({
        "summary": {"expenses": float(expense_sum), "income": float(income_sum), "balance": balance},
        "monthlyStats": monthly_stats,
        "activityStats": activity_stats,
        "latestTransactions": tx_list
    })