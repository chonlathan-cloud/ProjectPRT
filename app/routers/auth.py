from fastapi import APIRouter

from app.schemas.common import make_success_response
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
    data = GoogleAuthData(
        access_token="mock_jwt_token",
        user=GoogleUser(
            user_id="usr_mock_1",
            email="mock@example.com",
            name="Mock User",
        ),
    )
    return make_success_response(data.model_dump())
