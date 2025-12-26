from pydantic import BaseModel, EmailStr
from app.schemas.common import ResponseEnvelope


class GoogleAuthRequest(BaseModel):
    id_token: str


class GoogleUser(BaseModel):
    user_id: str
    email: EmailStr
    name: str


class GoogleAuthData(BaseModel):
    access_token: str
    user: GoogleUser


class GoogleAuthResponse(ResponseEnvelope):
    data: GoogleAuthData
