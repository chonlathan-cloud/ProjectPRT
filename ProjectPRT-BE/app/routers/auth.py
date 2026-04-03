from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from sqlalchemy.orm import Session
from typing import Annotated
import uuid

from app.core.hashing import Hasher
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
    UserSignupRequest,
    UserLoginRequest,
    UserAuthResponse,   
)
from app.deps import get_current_user, UserInDB

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Auth"],
)


# --- 1. SIGN UP ENDPOINT ---
@router.post("/signup", response_model=UserAuthResponse)
async def signup(payload: UserSignupRequest, db: Session = Depends(get_db)):
    # เช็คว่า Email ซ้ำไหม
    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user:
        return JSONResponse(
            status_code=400,
            content=make_error_response(
                code="DUPLICATE_EMAIL",
                message="Email already registered"
            )
        )

    # สร้าง User ใหม่ พร้อม Hash Password
    new_user = User(
        id=uuid.uuid4(),
        email=payload.email,
        name=payload.name,
        position=payload.position,
        hashed_password=Hasher.get_password_hash(payload.password),
        # google_sub เป็น None
    )
    db.add(new_user)
    db.flush()

    # Default Role (ให้เป็น Requester ไปก่อน)
    db.add(UserRole(user_id=new_user.id, role=ROLE_REQUESTER))
    
    db.commit()
    db.refresh(new_user)

    # Auto-login: สร้าง Token ส่งกลับไปเลย
    access_token = create_access_token(sub=str(new_user.id), email=new_user.email, name=new_user.name)
    
    data = GoogleAuthData(
        access_token=access_token,
        user=GoogleUser(user_id=str(new_user.id), email=new_user.email, name=new_user.name, position=new_user.position)
    )
    return make_success_response(data.model_dump())

# --- 2. LOGIN ENDPOINT ---
@router.post("/login", response_model=UserAuthResponse)
async def login(payload: UserLoginRequest, db: Session = Depends(get_db)):
    # หา User จาก Email
    user = db.query(User).filter(User.email == payload.email).first()
    
    # เช็ค Password
    if not user or not user.hashed_password or not Hasher.verify_password(payload.password, user.hashed_password):
        return JSONResponse(
            status_code=401,
            content=make_error_response(
                code="UNAUTHORIZED",
                message="Invalid email or password"
            )
        )
    if hasattr(user, "is_active") and not user.is_active:
        return JSONResponse(
            status_code=403,
            content=make_error_response(
                code="FORBIDDEN",
                message="User is disabled"
            )
        )

    # สร้าง Token
    access_token = create_access_token(sub=str(user.id), email=user.email, name=user.name)

    data = GoogleAuthData(
        access_token=access_token,
        user=GoogleUser(user_id=str(user.id), email=user.email, name=user.name, position=user.position)
    )
    return make_success_response(data.model_dump())


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
        if hasattr(db_user, "is_active") and not db_user.is_active:
            return JSONResponse(
                status_code=403,
                content=make_error_response(
                    code="FORBIDDEN",
                    message="User is disabled"
                )
            )
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

@router.get("/me")
async def get_my_info(current_user: Annotated[UserInDB, Depends(get_current_user)]):
    """
    Get current user info and roles from token/database.
    """
    return make_success_response({
        "username": current_user.username,
        "roles": current_user.roles  # ระบบจะดึงจาก DB ล่าสุดผ่าน get_current_user
    })
