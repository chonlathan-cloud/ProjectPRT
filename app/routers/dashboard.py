from datetime import date

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import get_current_user_identity_from_header
from app.db import get_db
from app.models import TransactionV1
from app.schemas.common import make_error_response, make_success_response
from app.schemas.dashboard import SummaryData, MonthlyItem, SummaryResponse, MonthlyResponse
from app.core.settings import settings

router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=["Dashboard"],
)


def _authenticate(request: Request):
    try:
        identity = get_current_user_identity_from_header(request.headers.get("authorization"))
        return identity, None
    except Exception:
        return None, JSONResponse(
            status_code=401,
            content=make_error_response(
                code="UNAUTHORIZED",
                message="Invalid or expired token",
                details={},
            ),
        )


@router.get("/summary", response_model=SummaryResponse)
async def get_dashboard_summary(request: Request, db: Session = Depends(get_db)):
    _, unauthorized_response = _authenticate(request)
    if unauthorized_response:
        return unauthorized_response

    if settings.USE_MOCK_DATA:
        data = SummaryData(
            total_income=45000,
            total_expense=34567,
            balance=10433,
        )
        return make_success_response(data.model_dump())

    try:
        income_sum = db.query(func.coalesce(func.sum(TransactionV1.amount), 0)).filter(TransactionV1.type == "income").scalar()
        expense_sum = db.query(func.coalesce(func.sum(TransactionV1.amount), 0)).filter(TransactionV1.type == "expense").scalar()
        income = float(income_sum or 0)
        expense = float(expense_sum or 0)
        balance = income - expense
        data = SummaryData(total_income=income, total_expense=expense, balance=balance)
        return make_success_response(data.model_dump())
    except Exception:
        return JSONResponse(
            status_code=500,
            content=make_error_response(
                code="INTERNAL_ERROR",
                message="Failed to compute summary",
                details={},
            ),
        )


@router.get("/monthly", response_model=MonthlyResponse)
async def get_dashboard_monthly(request: Request, db: Session = Depends(get_db)):
    _, unauthorized_response = _authenticate(request)
    if unauthorized_response:
        return unauthorized_response

    if settings.USE_MOCK_DATA:
        monthly_data = [
            MonthlyItem(month="2024-09", income=8000, expense=7200),
            MonthlyItem(month="2024-10", income=8500, expense=7300),
            MonthlyItem(month="2024-11", income=7600, expense=6400),
            MonthlyItem(month="2024-12", income=9000, expense=7800),
            MonthlyItem(month="2025-01", income=8800, expense=7100),
            MonthlyItem(month="2025-02", income=9100, expense=6767),
        ]
        return make_success_response([item.model_dump() for item in monthly_data])

    try:
        today = date.today()

        def month_start(base_date: date, offset_months: int) -> date:
            total_months = base_date.year * 12 + base_date.month - 1 + offset_months
            year = total_months // 12
            month = total_months % 12 + 1
            return date(year, month, 1)

        results = []
        for offset in range(-5, 1):  # last 6 months including current
            start = month_start(today, offset)
            next_start = month_start(today, offset + 1)

            income_sum = (
                db.query(func.coalesce(func.sum(TransactionV1.amount), 0))
                .filter(TransactionV1.type == "income")
                .filter(TransactionV1.occurred_at >= start)
                .filter(TransactionV1.occurred_at < next_start)
                .scalar()
            )
            expense_sum = (
                db.query(func.coalesce(func.sum(TransactionV1.amount), 0))
                .filter(TransactionV1.type == "expense")
                .filter(TransactionV1.occurred_at >= start)
                .filter(TransactionV1.occurred_at < next_start)
                .scalar()
            )
            results.append(
                MonthlyItem(
                    month=start.strftime("%Y-%m"),
                    income=float(income_sum or 0),
                    expense=float(expense_sum or 0),
                )
            )

        return make_success_response([item.model_dump() for item in results])
    except Exception:
        return JSONResponse(
            status_code=500,
            content=make_error_response(
                code="INTERNAL_ERROR",
                message="Failed to compute monthly data",
                details={},
            ),
        )
