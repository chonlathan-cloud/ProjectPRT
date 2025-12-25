from typing import Optional
from enum import Enum
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict

class CategoryType(str, Enum):
    EXPENSE = "EXPENSE"
    REVENUE = "REVENUE"

class CategoryBase(BaseModel):
    name_th: str = Field(..., max_length=100)
    account_code: str = Field(..., max_length=20)

class CategoryCreate(CategoryBase):
    type: CategoryType

class CategoryUpdate(BaseModel):
    name_th: Optional[str] = Field(None, max_length=100)
    account_code: Optional[str] = Field(None, max_length=20)
    type: Optional[CategoryType] = None
    is_active: Optional[bool] = None

class CategoryInDBBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name_th: str
    type: CategoryType
    account_code: str
    is_active: bool

class CategoryResponse(CategoryInDBBase):
    pass
