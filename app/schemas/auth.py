from pydantic import BaseModel, EmailStr, Field
from app.schemas.common import ResponseEnvelope


class GoogleAuthRequest(BaseModel):
    id_token: str


class GoogleUser(BaseModel):
    user_id: str
    email: EmailStr
    name: str
    position: str | None = None

class GoogleAuthData(BaseModel):
    access_token: str
    user: GoogleUser


class GoogleAuthResponse(ResponseEnvelope):
    data: GoogleAuthData

class UserSignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    name: str
    position: str | None = None

class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str

class UserAuthResponse(ResponseEnvelope):
    #ใช้ Structure เดี่ยวกับ GoogleAuthResponse
    data: GoogleAuthData