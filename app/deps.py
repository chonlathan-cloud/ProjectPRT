import enum
from typing import Annotated, List

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db import get_db
from app.core.security import decode_access_token
from app.models import User, UserRole  # ต้องมี Models นี้ใน app/models.py

# Role Enum
class Role(str, enum.Enum):
    REQUESTER = "requester"
    FINANCE = "finance"
    ACCOUNTING = "accounting"
    TREASURY = "treasury"
    ADMIN = "admin"
    EXECUTIVE = "executive"

# OAuth2 Scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# User Model for Dependency Injection
class UserInDB:
    def __init__(self, username: str, roles: List[Role], id: str = None):
        self.id = id
        self.username = username
        self.roles = roles

# --- Real Implementation: Validate JWT & Fetch from DB ---
async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db)
) -> UserInDB:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # 1. Decode JWT Token
    try:
        payload = decode_access_token(token)
        google_sub: str = payload.get("sub")
        if google_sub is None:
            raise credentials_exception
    except Exception:
        raise credentials_exception

    # 2. Fetch User from DB
    user = db.execute(select(User).filter_by(google_sub=google_sub)).scalar_one_or_none()
    if user is None:
        raise credentials_exception

    # 3. Fetch Roles from DB
    user_roles = db.execute(select(UserRole.role).filter_by(user_id=user.id)).scalars().all()
    
    # Convert string roles from DB to Enum
    roles_enum = []
    for r in user_roles:
        try:
            roles_enum.append(Role(r))
        except ValueError:
            pass # Ignore invalid roles in DB

    return UserInDB(username=user.google_sub, roles=roles_enum, id=str(user.id))


def has_role(required_roles: List[Role]):
    def role_checker(current_user: Annotated[UserInDB, Depends(get_current_user)]):
        # Check if user has ANY of the required roles
        if not any(role in current_user.roles for role in required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": "Insufficient permissions",
                    "required_roles": [r.value for r in required_roles]
                }
            )
        return current_user
    return role_checker