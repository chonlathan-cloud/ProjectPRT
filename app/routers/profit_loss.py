from datetime import datetime, timezone
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db import get_db
from app.models import Case, CaseStatus, Category, CategoryType
from app.schemas.common import ResponseEnvelope, make_success_response

router = APIRouter(
    prefix="/api/v1/profit-loss",
    tags=["ProfitLoss"]
)


class ProfitLossEntry(BaseModel):
    label: str
    value: float = 0.0
    isHeader: bool = False
    isSubHeader: bool = False
    isTotal: bool = False


class ProfitLossEnvelope(ResponseEnvelope[Dict[str, List[ProfitLossEntry]]]):
    data: Dict[str, List[ProfitLossEntry]]


TEMPLATES = {
    "งบดำเนินการ": [
        {"label": "รายได้จากการดำเนินงาน", "isHeader": True},
        {"label": "รายได้จากเงินงบประมาณ (ก)", "isSubHeader": True},
        {"label": "เงินอุดหนุนโรงเรียนพระปริยัติธรรมฯ", "code": "401011"},
        {"label": "เงินอุดหนุนโรงเรียนพระปริยัติธรรมฯ ธรรม-บาลี", "code": "401012"},
        {"label": "อุดหนุนสมทบ โควิด", "code": "401013"},
        {"label": "รายได้จากแหล่งอื่น (ข)", "isSubHeader": True},
        {"label": "แม่กองธรรมสนามหลวง นักธรรมดีเด่น", "code": "401021"},
        {"label": "รายได้จากการบริจาค", "code": "401022"},
        {"label": "รายได้อื่นๆ", "code": "401023"},
        {"label": "รายได้จากดอกเบี้ย", "code": "401024"},
        {"label": "รวมรายได้ (ก)+(ข)", "isTotal": True},
        {"label": "ค่าใช้จ่ายจากการดำเนินงาน", "isHeader": True},
        {"label": "ค่าธรรมเนียมการโอน", "code": "501203"},
        {"label": "รวมค่าใช้จ่ายจากการดำเนินงาน", "isTotal": True},
        {"label": "เงินสำรองค่าใช้จ่ายล่วงหน้า", "code": "509"},
        {"label": "คงเหลือสุทธิ", "isTotal": True},
        {"label": "สรุปผลการดำเนินงาน", "isHeader": True},
        {"label": "รายได้ (สูง) กว่ารายจ่าย ณ. วันที่ 30 ก.ย. 64", "isTotal": True},
    ],
    "งบนอก": [
        {"label": "รายได้จากการดำเนินงาน", "isHeader": True},
        {"label": "รายได้จากแหล่งอื่น", "isSubHeader": True},
        {"label": "รายได้จากการบริจาค", "code": "401022"},
        {"label": "รายได้อื่นๆ", "code": "401023"},
        {"label": "รายได้จากดอกเบี้ย", "code": "401024"},
        {"label": "รวมรายได้", "isTotal": True},
        {"label": "ค่าใช้จ่ายจากการดำเนินงาน", "isHeader": True},
        {"label": "รวมค่าใช้จ่ายจากการดำเนินงาน", "isTotal": True},
        {"label": "คงเหลือสุทธิ", "isTotal": True},
        {"label": "สรุปผลการดำเนินงาน", "isHeader": True},
        {"label": "รายได้ (สูง) กว่ารายจ่าย ณ. วันที่ 30 ก.ย. 64", "isTotal": True},
        {"label": "หมายเหตุ : ไม่มี", "isSubHeader": True},
    ],
    "งบอุดหนุน": [
        {"label": "รายได้จากการดำเนินงาน ต.ค 63 - ก.ย 64", "isHeader": True},
        {"label": "รายได้จากเงินงบประมาณ (ก)", "isSubHeader": True},
        {"label": "เงินอุดหนุนโรงเรียนพระปริยัติธรรมฯ", "code": "401011"},
        {"label": "เงินอุดหนุนโรงเรียนพระปริยัติธรรมฯ ธรรม-บาลี", "code": "401012"},
        {"label": "อุดหนุนสมทบ โควิด", "code": "401013"},
        {"label": "รายได้จากแหล่งอื่น (ข)", "isSubHeader": True},
        {"label": "ไม่มีรายการ", "isSubHeader": True},
        {"label": "รวมรายได้ (ก)+(ข)", "isTotal": True},
        {"label": "ค่าใช้จ่ายจากการดำเนินงาน ต.ค 63 - ก.ย 64", "isHeader": True},
        {"label": "อื่น ๆ ค่าธรรมเนียมธนาคาร", "code": "501203"},
        {"label": "ส่วนต่างรายงานจำนวนเต็มบาท", "code": "509"},
        {"label": "รวมค่าใช้จ่ายจากการดำเนินงาน", "isTotal": True},
        {"label": "คงเหลือสุทธิ", "isTotal": True},
        {"label": "สรุปผลการดำเนินงาน", "isHeader": True},
        {"label": "รายได้ (สูง) กว่ารายจ่าย ณ. วันที่ 30 ก.ย. 64", "isTotal": True},
        {"label": "หมายเหตุ : ไม่มี", "isSubHeader": True},
    ],
}


def _to_fiscal_year_range(year_be: int) -> tuple[datetime, datetime]:
    year_ce = year_be - 543
    if year_ce < 1900:
        raise HTTPException(status_code=400, detail="Invalid year value.")
    start_dt = datetime(year_ce - 1, 10, 1, tzinfo=timezone.utc)
    end_dt = datetime(year_ce, 10, 1, tzinfo=timezone.utc)
    return start_dt, end_dt


def _get_totals_by_account_code(
    db: Session,
    start_dt: datetime,
    end_dt: datetime
) -> Dict[str, float]:
    results = db.execute(
        select(
            Category.account_code,
            func.coalesce(func.sum(Case.requested_amount), 0)
        )
        .join(Category, Case.category_id == Category.id)
        .where(
            Case.status.in_([CaseStatus.APPROVED, CaseStatus.CLOSED]),
            Case.created_at >= start_dt,
            Case.created_at < end_dt,
            Category.type.in_([CategoryType.EXPENSE, CategoryType.REVENUE])
        )
        .group_by(Category.account_code)
    ).all()

    totals: Dict[str, float] = {}
    for account_code, total in results:
        totals[str(account_code)] = float(total or 0)
    return totals


def _build_sheet(template_rows: List[dict], totals: Dict[str, float]) -> List[ProfitLossEntry]:
    built_rows: List[ProfitLossEntry] = []
    for row in template_rows:
        code = row.get("code")
        value = totals.get(code, 0.0) if code else 0.0
        built_rows.append(ProfitLossEntry(
            label=row["label"],
            value=float(value),
            isHeader=row.get("isHeader", False),
            isSubHeader=row.get("isSubHeader", False),
            isTotal=row.get("isTotal", False),
        ))
    return built_rows


@router.get("", response_model=ProfitLossEnvelope)
def get_profit_loss_data(
    year: int = Query(..., description="B.E. year (e.g., 2565)"),
    db: Session = Depends(get_db)
):
    start_dt, end_dt = _to_fiscal_year_range(year)
    totals = _get_totals_by_account_code(db, start_dt, end_dt)

    payload: Dict[str, List[ProfitLossEntry]] = {}
    for sheet_name, rows in TEMPLATES.items():
        payload[sheet_name] = _build_sheet(rows, totals)

    return make_success_response(payload)
