from pydantic import BaseModel
from typing import List


class RolesUpdateRequest(BaseModel):
    roles: List[str]
