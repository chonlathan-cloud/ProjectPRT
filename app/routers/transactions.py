from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

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


@router.post(
    "",
    response_model=TransactionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_transaction(
    request: Request,
    payload: TransactionCreateRequest,
):
    unauthorized_response = _require_auth(request)
    if unauthorized_response:
        return unauthorized_response

    data = TransactionCreateData(
        transaction_id="tx_mock_0001",
        status="created",
    )
    return make_success_response(data.model_dump())
