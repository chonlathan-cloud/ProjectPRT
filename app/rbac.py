from typing import List, Tuple

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.security import get_current_user_identity_from_header
from app.models import User, UserRole
from app.schemas.common import make_error_response

ROLE_ADMIN = "admin"
ROLE_ACCOUNTANT = "accounting"
ROLE_REQUESTER = "requester"
ROLE_VIEWER = "viewer"
ALL_ROLES = {ROLE_ADMIN, ROLE_ACCOUNTANT, ROLE_REQUESTER, ROLE_VIEWER}


def get_current_user(db: Session, request: Request) -> Tuple[User | None, JSONResponse | None]:
    try:
        identity = get_current_user_identity_from_header(request.headers.get("authorization"))
    except Exception:
        return None, JSONResponse(
            status_code=401,
            content=make_error_response(
                code="UNAUTHORIZED",
                message="Invalid or expired token",
                details={},
            ),
        )
    try:
        user = db.query(User).filter(User.id == identity).first()
    except Exception:
        user = None
        
    if not user:
        return None, JSONResponse(
            status_code=401,
            content=make_error_response(
                code="UNAUTHORIZED",
                message="User not found",
                details={},
            ),
        )
    return user, None


def get_current_roles(db: Session, user_id) -> List[str]:
    return [ur.role for ur in db.query(UserRole).filter(UserRole.user_id == user_id).all()]


def require_roles(db: Session, request: Request, allowed_roles: List[str]):
    user, auth_error = get_current_user(db, request)
    if auth_error:
        return None, auth_error
    if allowed_roles:
        roles = get_current_roles(db, user.id)
        if not set(roles).intersection(set(allowed_roles)):
            return None, JSONResponse(
                status_code=403,
                content=make_error_response(
                    code="FORBIDDEN",
                    message="Insufficient permissions",
                    details={"required_roles": allowed_roles},
                ),
            )
    return user, None
