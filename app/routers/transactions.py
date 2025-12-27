from datetime import datetime

from fastapi import APIRouter, Request, status, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.security import get_current_user_identity_from_header
from app.core.settings import settings
from app.db import get_db
from app.models import TransactionV1
from app.schemas.common import make_error_response, make_success_response
from app.schemas.transactions import (
    TransactionCreateRequest,
    TransactionCreateData,
    TransactionCreateResponse,
)

router = APIRouter(
    prefix="/api/v1/transactions",
    tags=["Transactions"],
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


@router.post(
    "",
    response_model=TransactionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_transaction(
    request: Request,
    payload: TransactionCreateRequest,
    db: Session = Depends(get_db),
):
    identity, unauthorized_response = _authenticate(request)
    if unauthorized_response:
        return unauthorized_response

    if settings.USE_MOCK_DATA:
        data = TransactionCreateData(
            transaction_id="tx_mock_0001",
            status="created",
        )
        return make_success_response(data.model_dump())

    if payload.type not in {"income", "expense"}:
        return JSONResponse(
            status_code=400,
            content=make_error_response(
                code="VALIDATION_ERROR",
                message="Invalid transaction type",
                details={"type": payload.type},
            ),
        )

    try:
        occurred_date = datetime.strptime(payload.occurred_at, "%Y-%m-%d").date()
    except Exception:
        return JSONResponse(
            status_code=400,
            content=make_error_response(
                code="VALIDATION_ERROR",
                message="Invalid occurred_at format, expected YYYY-MM-DD",
                details={"occurred_at": payload.occurred_at},
            ),
        )

    try:
        db_tx = TransactionV1(
            type=payload.type,
            category=payload.category,
            amount=payload.amount,
            occurred_at=occurred_date,
            note=payload.note,
            created_by=identity,
        )
        db.add(db_tx)
        db.commit()
        db.refresh(db_tx)
    except Exception:
        db.rollback()
        return JSONResponse(
            status_code=500,
            content=make_error_response(
                code="INTERNAL_ERROR",
                message="Failed to create transaction",
                details={},
            ),
        )

    data = TransactionCreateData(
        transaction_id=str(db_tx.id),
        status="created",
    )
    return make_success_response(data.model_dump())
