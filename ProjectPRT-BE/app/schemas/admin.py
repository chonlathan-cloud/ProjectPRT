from pydantic import BaseModel
from typing import List, Optional


class RolesUpdateRequest(BaseModel):
    roles: List[str]


class UserUpdateRequest(BaseModel):
    name: Optional[str] = None
    position: Optional[str] = None
