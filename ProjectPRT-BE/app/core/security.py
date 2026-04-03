from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import jwt

from app.core.settings import settings


def create_access_token(sub: str, email: str, name: str) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": sub,
        "email": email,
        "name": name,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


def get_current_user_identity_from_header(authorization_header: str | None) -> str:
    if not authorization_header or not authorization_header.lower().startswith("bearer "):
        raise ValueError("Missing Authorization header")
    token = authorization_header.split(" ", 1)[1].strip()
    payload = decode_access_token(token)
    identity = payload.get("sub") or payload.get("email")
    if not identity:
        raise ValueError("Token missing identity")
    return identity
