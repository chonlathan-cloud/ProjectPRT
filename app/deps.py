import enum
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

# spec: RBAC utilities with roles: Requester, Finance, Accounting, Treasury, Admin, Executive
class Role(str, enum.Enum):
    REQUESTER = "Requester"
    FINANCE = "Finance"
    ACCOUNTING = "Accounting"
    TREASURY = "Treasury"
    ADMIN = "Admin"
    EXECUTIVE = "Executive"

# Placeholder for OAuth2PasswordBearer. In a real application, this would point to a token endpoint.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Placeholder for User model. In a real app, this would be a Pydantic model for the User.
class UserInDB:
    def __init__(self, username: str, roles: list[Role]):
        self.username = username
        self.roles = roles

# This is a mock function. In a real application, this would validate the token
# and fetch the user from the database.
async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> UserInDB:
    # For now, let's just assume a valid token for 'admin' user with 'Admin' role.
    # This part needs to be replaced with actual token validation and user retrieval.
    if token == "fake-admin-token":
        return UserInDB(username="admin_user", roles=[Role.ADMIN])
    elif token == "fake-requester-token":
        return UserInDB(username="requester_user", roles=[Role.REQUESTER])
    elif token == "fake-finance-token":
        return UserInDB(username="finance_user", roles=[Role.FINANCE])
    elif token == "fake-accounting-token":
        return UserInDB(username="accounting_user", roles=[Role.ACCOUNTING])
    elif token == "fake-treasury-token":
        return UserInDB(username="treasury_user", roles=[Role.TREASURY])
    elif token == "fake-executive-token":
        return UserInDB(username="executive_user", roles=[Role.EXECUTIVE])
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")

def has_role(required_roles: list[Role]):
    def role_checker(current_user: Annotated[UserInDB, Depends(get_current_user)]):
        if not any(role in current_user.roles for role in required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User does not have the required role. Required: {', '.join([r.value for r in required_roles])}"
            )
        return current_user
    return role_checker
