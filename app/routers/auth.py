from fastapi import APIRouter

from app.core.settings import settings
from fastapi.responses import JSONResponse

from app.schemas.common import make_success_response, make_error_response
from app.schemas.auth import (
    GoogleAuthRequest,
    GoogleAuthData,
    GoogleUser,
    GoogleAuthResponse,
)

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Auth"],
)


@router.post("/google", response_model=GoogleAuthResponse)
async def auth_google(payload: GoogleAuthRequest):
    if not settings.USE_MOCK_DATA:
        return JSONResponse(
            status_code=501,
            content=make_error_response(
                code="NOT_IMPLEMENTED",
                message="Mock data disabled for auth endpoint",
                details={},
            ),
        )

    data = GoogleAuthData(
        access_token="mock_jwt_token",
        user=GoogleUser(
            user_id="usr_mock_1",
            email="mock@example.com",
            name="Mock User",
        ),
    )
    return make_success_response(data.model_dump())
