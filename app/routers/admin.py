from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User, UserRole
from app.rbac import ROLE_ADMIN, ALL_ROLES, require_roles
from app.schemas.common import make_success_response, make_error_response
from app.schemas.admin import RolesUpdateRequest

router = APIRouter(
    prefix="/api/v1",
    tags=["Admin"],
)


@router.get("/admin/users")
async def list_users(request: Request, db: Session = Depends(get_db)):
    _, auth_error = require_roles(db, request, [ROLE_ADMIN])
    if auth_error:
        return auth_error

    users = db.query(User).all()
    results = []
    for user in users:
        roles = [ur.role for ur in db.query(UserRole).filter(UserRole.user_id == user.id).all()]
        results.append(
            {
                "user_id": str(user.id),
                "google_sub": user.google_sub,
                "email": user.email,
                "name": user.name,
                "roles": roles,
            }
        )
    return make_success_response(results)


@router.post("/admin/users/{user_id}/roles")
async def update_user_roles(user_id: str, payload: RolesUpdateRequest, request: Request, db: Session = Depends(get_db)):
    _, auth_error = require_roles(db, request, [ROLE_ADMIN])
    if auth_error:
        return auth_error

    invalid_roles = [r for r in payload.roles if r not in ALL_ROLES]
    if invalid_roles:
        return JSONResponse(
            status_code=400,
            content=make_error_response(
                code="VALIDATION_ERROR",
                message="Invalid roles",
                details={"invalid_roles": invalid_roles},
            ),
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return JSONResponse(
            status_code=404,
            content=make_error_response(
                code="NOT_FOUND",
                message="User not found",
                details={},
            ),
        )

    db.query(UserRole).filter(UserRole.user_id == user.id).delete()
    db.flush()
    for role in payload.roles:
        db.add(UserRole(user_id=user.id, role=role))
    db.commit()

    roles = [ur.role for ur in db.query(UserRole).filter(UserRole.user_id == user.id).all()]
    return make_success_response(
        {
            "user_id": str(user.id),
            "google_sub": user.google_sub,
            "email": user.email,
            "name": user.name,
            "roles": roles,
        }
    )


@router.get("/me")
async def get_me(request: Request, db: Session = Depends(get_db)):
    user, auth_error = require_roles(db, request, [])  # just auth
    if auth_error:
        return auth_error
    roles = [ur.role for ur in db.query(UserRole).filter(UserRole.user_id == user.id).all()]
    return make_success_response(
        {
            "user_id": str(user.id),
            "google_sub": user.google_sub,
            "email": user.email,
            "name": user.name,
            "roles": roles,
        }
    )
