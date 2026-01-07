from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import get_db
from app.deps import get_current_user, UserInDB
from app.services.chat_agent import PRTChatAgent

router = APIRouter(prefix="/api/v1/chat", tags=["Chat"])

class ChatRequest(BaseModel):
    message: str

# Instantiate Agent (Singleton)
agent = PRTChatAgent()

@router.post("")
async def chat_endpoint(
    payload: ChatRequest,
    current_user: UserInDB = Depends(get_current_user), # ✅ Security Check
    db: Session = Depends(get_db)
):
    try:
        reply = agent.chat(payload.message, db, user_name=current_user.username)
        return {"reply": reply}
    except Exception as e:
        print(f"Chat Error: {e}")
        # กรณี Vertex AI Error (เช่น Quota เต็ม หรือ Config ผิด)
        return {"reply": "ขออภัยครับ ระบบ AI ขัดข้องชั่วคราว (หรือยังไม่ได้ตั้งค่า Vertex AI)"}