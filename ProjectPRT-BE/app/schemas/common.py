from typing import Any, Optional, TypeVar, Generic
from pydantic import BaseModel

# ✅ 1. เพิ่ม TypeVar
T = TypeVar("T")

class ErrorObject(BaseModel):
    code: str
    message: str
    details: Optional[dict[str, Any]] = None

# ✅ 2. สืบทอดจาก Generic[T] และแก้ type ของ data เป็น Optional[T]
class ResponseEnvelope(BaseModel, Generic[T]):
    success: bool
    data: Optional[T] = None
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