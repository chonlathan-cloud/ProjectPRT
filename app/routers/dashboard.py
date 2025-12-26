from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.schemas.common import make_error_response, make_success_response
from app.schemas.dashboard import SummaryData, MonthlyItem, SummaryResponse, MonthlyResponse

router = APIRouter(
    prefix="/api/v1/dashboard",
    tags=["Dashboard"],
)


def _require_auth(request: Request):
    if not request.headers.get("authorization"):
        return JSONResponse(
            status_code=401,
            content=make_error_response(
                code="UNAUTHORIZED",
                message="Missing Authorization header",
                details={},
            ),
        )
    return None


@router.get("/summary", response_model=SummaryResponse)
async def get_dashboard_summary(request: Request):
    unauthorized_response = _require_auth(request)
    if unauthorized_response:
        return unauthorized_response

    data = SummaryData(
        total_income=45000,
        total_expense=34567,
        balance=10433,
    )
    return make_success_response(data.model_dump())


@router.get("/monthly", response_model=MonthlyResponse)
async def get_dashboard_monthly(request: Request):
    unauthorized_response = _require_auth(request)
    if unauthorized_response:
        return unauthorized_response

    monthly_data = [
        MonthlyItem(month="2024-09", income=8000, expense=7200),
        MonthlyItem(month="2024-10", income=8500, expense=7300),
        MonthlyItem(month="2024-11", income=7600, expense=6400),
        MonthlyItem(month="2024-12", income=9000, expense=7800),
        MonthlyItem(month="2025-01", income=8800, expense=7100),
        MonthlyItem(month="2025-02", income=9100, expense=6767),
    ]
    return make_success_response([item.model_dump() for item in monthly_data])
