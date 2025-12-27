from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from sqlalchemy.orm import Session
import uuid

from app.core.settings import settings
from app.core.security import create_access_token
from app.db import get_db
from app.models import User, UserRole
from app.rbac import ROLE_REQUESTER, ROLE_ADMIN
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
async def auth_google(payload: GoogleAuthRequest, db: Session = Depends(get_db)):
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

    # Upsert user
    db_user = db.query(User).filter(User.google_sub == user_id).first()
    is_first_user = db.query(User).count() == 0
    make_admin = False
    if is_first_user:
        make_admin = True
    if settings.BOOTSTRAP_ADMIN_SUB and settings.BOOTSTRAP_ADMIN_SUB == user_id:
        make_admin = True

    if not db_user:
        db_user = User(
            id=uuid.uuid4(),
            google_sub=user_id,
            email=email,
            name=name,
        )
        db.add(db_user)
        db.flush()
        default_role = UserRole(user_id=db_user.id, role=ROLE_ADMIN if make_admin else ROLE_REQUESTER)
        db.add(default_role)
    else:
        db_user.email = email
        db_user.name = name
        if make_admin:
            has_admin = db.query(UserRole).filter(UserRole.user_id == db_user.id, UserRole.role == ROLE_ADMIN).first()
            if not has_admin:
                db.add(UserRole(user_id=db_user.id, role=ROLE_ADMIN))
    db.commit()
    db.refresh(db_user)

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
