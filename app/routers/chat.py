# app/routers/chat.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import logging

from app.db import get_db
from app.deps import get_current_user
from app.services.chat_agent import PRTChatAgent

router = APIRouter(
    prefix="/api/v1/chat",
    tags=["Chat"]
)

class ChatRequest(BaseModel):
    message: str

# 2. สร้าง Global Instance ของ Agent ไว้ข้างนอก
# (เพื่อให้โหลด Model แค่ครั้งเดียวตอน Start Server ไม่ใช่โหลดใหม่ทุกครั้งที่ User พิมพ์)
chat_agent = PRTChatAgent()

@router.post("")
async def chat_endpoint(
    payload: ChatRequest,
    current_user = Depends(get_current_user), # บังคับ Login
    db: Session = Depends(get_db)
):
    try:
        # 3. เตรียมชื่อ User (ถ้าไม่มีชื่อ ให้ใช้อีเมลแทน)
        user_name = current_user.name if current_user.name else current_user.email

        # 4. เรียกใช้ฟังก์ชัน chat() โดยส่ง db และ user_name เข้าไปตามโครงสร้างใหม่
        reply = chat_agent.chat(
            user_message=payload.message,
            db=db,
            user_name=user_name
        )
        
        return {"reply": reply}

    except Exception as e:
        logging.error(f"Chat Endpoint Error: {e}")
        return {"reply": "ขออภัยครับ ระบบขัดข้องชั่วคราว (กรุณาติดต่อ Admin)"}