from typing import Optional, List, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from app.db import get_db
from app.deps import Role, has_role,UserInDB
from app.models import Category, CategoryType, AuditLog
from app.schemas.category import CategoryCreate, CategoryUpdate, CategoryResponse
from app.services.audit import log_audit_event

router = APIRouter(
    prefix="/api/v1/categories",
    tags=["Categories"]
)

@router.get("/", response_model=List[CategoryResponse])
async def read_categories(
    type: Optional[CategoryType] = None,
    active: bool = True,
    db: Session = Depends(get_db)
):
    query = select(Category)
    conditions = [Category.is_active == active]

    if type:
        conditions.append(Category.type == type)

    query = query.where(and_(*conditions)).order_by(Category.name_th.asc())
    categories = db.execute(query).scalars().all()
    return [CategoryResponse.model_validate(cat) for cat in categories]

@router.post("/", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    category_in: CategoryCreate,
    current_user: Annotated[UserInDB, Depends(has_role([Role.ACCOUNTING, Role.ADMIN]))],
    db: Session = Depends(get_db)
):
    # Check for unique name_th
    existing_name = db.execute(select(Category).filter_by(name_th=category_in.name_th)).scalar_one_or_none()
    if existing_name:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category with this name_th already exists.")

    # Check for unique account_code
    existing_code = db.execute(select(Category).filter_by(account_code=category_in.account_code)).scalar_one_or_none()
    if existing_code:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category with this account_code already exists.")

    db_category = Category(
        **category_in.model_dump(),
        is_active=True,  # Default to true as per requirements
        created_by=current_user.username
    )
    db.add(db_category)
    db.flush() # Flush to get the ID for audit logging

    log_audit_event(
        db,
        entity_type="category",
        entity_id=db_category.id,
        action="create",
        performed_by=current_user.username,
        details_json=category_in.model_dump()
    )

    db.commit()
    db.refresh(db_category)
    return CategoryResponse.model_validate(db_category)

@router.patch("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: UUID,
    category_in: CategoryUpdate,
    current_user: Annotated[UserInDB, Depends(has_role([Role.ACCOUNTING, Role.ADMIN]))],
    db: Session = Depends(get_db)
):
    db_category = db.execute(select(Category).filter_by(id=category_id)).scalar_one_or_none()
    if not db_category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")

    old_data = CategoryResponse.model_validate(db_category).model_dump(mode='json')

    update_data = category_in.model_dump(exclude_unset=True)

    # Check for name_th conflict if name_th is being updated
    if "name_th" in update_data and update_data["name_th"] != db_category.name_th:
        existing_name = db.execute(select(Category).filter(
            Category.name_th == update_data["name_th"],
            Category.id != category_id
        )).scalar_one_or_none()
        if existing_name:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category with this name_th already exists.")

    # Check for account_code conflict if account_code is being updated
    if "account_code" in update_data and update_data["account_code"] != db_category.account_code:
        existing_code = db.execute(select(Category).filter(
            Category.account_code == update_data["account_code"],
            Category.id != category_id
        )).scalar_one_or_none()
        if existing_code:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category with this account_code already exists.")

    for key, value in update_data.items():
        setattr(db_category, key, value)

    db_category.updated_by = current_user.username

    action = "update"
    if "is_active" in update_data and update_data["is_active"] is False and old_data["is_active"] is True:
        action = "deactivate"

    db.flush()
    new_data = CategoryResponse.model_validate(db_category).model_dump(mode='json')

    log_audit_event(
        db,
        entity_type="category",
        entity_id=db_category.id,
        action=action,
        performed_by=current_user.username,
        details_json={"old": old_data, "new": new_data}
    )

    db.commit()
    db.refresh(db_category)
    return CategoryResponse.model_validate(db_category)
