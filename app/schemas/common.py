from typing import Any, Optional
from pydantic import BaseModel


class ErrorObject(BaseModel):
    code: str
    message: str
    details: Optional[dict[str, Any]] = None


class ResponseEnvelope(BaseModel):
    success: bool
    data: Any | None
    error: Optional[ErrorObject] = None


def make_success_response(data: Any) -> dict[str, Any]:
    return {"success": True, "data": data, "error": None}


def make_error_response(code: str, message: str, details: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    return {
        "success": False,
        "data": None,
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
    }
