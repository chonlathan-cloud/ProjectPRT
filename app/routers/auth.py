from fastapi import APIRouter
from fastapi.responses import JSONResponse
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from app.core.settings import settings
from app.core.security import create_access_token
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
    try:
        id_info = id_token.verify_oauth2_token(
            payload.id_token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
        )
        if id_info.get("aud") != settings.GOOGLE_CLIENT_ID:
            raise ValueError("Invalid audience")
    except Exception as exc:
        return JSONResponse(
            status_code=401,
            content=make_error_response(
                code="UNAUTHORIZED",
                message="Invalid Google ID token",
                details={"reason": str(exc)},
            ),
        )

    user_id = id_info.get("sub")
    email = id_info.get("email")
    name = id_info.get("name") or email

    access_token = create_access_token(sub=user_id, email=email, name=name)

    data = GoogleAuthData(
        access_token=access_token,
        user=GoogleUser(
            user_id=user_id,
            email=email,
            name=name,
        ),
    )
    return make_success_response(data.model_dump())
