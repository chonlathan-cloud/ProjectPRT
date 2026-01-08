import vertexai
from vertexai.generative_models import GenerativeModel, Tool, FunctionDeclaration, Part
from sqlalchemy.orm import Session
from datetime import datetime
import logging
from app.services.chat_tools import search_documents_tool, get_financial_analytics_tool, list_case_details_tool
from app.core.settings import settings
# ตั้งค่า Logger
logger = logging.getLogger(__name__)

# --- 1. Init Vertex AI ---
try:
    vertexai.init(project=settings.GOOGLE_CLOUD_PROJECT, location="asia-southeast1")
except Exception as e:
    logger.error(f"Vertex AI Init Error: {e}")

# --- 2. Tool Definitions ---
search_tool = FunctionDeclaration(
    name="search_documents",
    description="Search for file attachments/documents by filename keyword.",
    parameters={
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "Search term e.g. 'invoice', 'slip', 'receipt'"}
        },
        "required": ["keyword"]
    }
)

analytics_tool = FunctionDeclaration(
    name="get_financial_analytics", # เปลี่ยนชื่อให้สื่อความหมาย
    description="Get total financial amount (Income/Expense) from database documents (PV/RV).",
    parameters={
        "type": "object",
        "properties": {
            "start_date": {"type": "string", "description": "Start date YYYY-MM-DD"},
            "end_date": {"type": "string", "description": "End date YYYY-MM-DD"},
            "category_name": {"type": "string", "description": "Category filter e.g. 'Sales', 'Travel'"},
            "transaction_type": {
                "type": "string", 
                "enum": ["EXPENSE", "REVENUE", "ALL"],
                "description": "Type of transaction. Use 'REVENUE' for income/sales, 'EXPENSE' for costs/spending."
            }
        },
        # บังคับให้ AI ต้องคิดว่าจะดู Expense หรือ Revenue
        "required": ["transaction_type"] 
    }
)

prt_tools = Tool(function_declarations=[search_tool, analytics_tool])

# --- 3. Chat Agent Class ---
class PRTChatAgent:
    def __init__(self):
        # ✅ ใช้ 2.5-flash ซึ่งเสถียรและเร็วที่สุดตอนนี้
        self.model = GenerativeModel(
            "gemini-2.5-flash",
            tools=[prt_tools]
        )

    def chat(self, user_message: str, db: Session, user_name: str = "User"):
        # ✅ สร้าง Context เวลาปัจจุบัน
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        current_month = now.strftime("%B") # e.g. January
        current_year = now.year
        
        # ✅ System Prompt ฉบับสมบูรณ์ (รวมกฎข้อ 2 เรื่อง Breakdown)
        system_prompt = f"""
        You are 'PRT FinBot', an expert financial assistant for the Project PRT system.
        
        --- CURRENT CONTEXT ---
        * User: {user_name}
        * Today: {today_str} (Month: {current_month}, Year: {current_year})
        
        --- RULES ---
        1. **Zero/No Data:** If the tool returns 0.0, None, or empty list, DO NOT simply say "0". Instead, politely say "ไม่พบรายการในช่วงเวลานั้นครับ" or "ไม่มีข้อมูลในหมวดหมู่นี้ครับ".
        
        2. **Detail Breakdown:** If the tool provides a 'breakdown' list in the response, ALWAYS show it to the user clearly. 
           Example format:
           "ยอดรวมทั้งหมด 5,000 บาทครับ
            รายการล่าสุด:
            - PV-202401-001: 2,000 บาท (ค่าเดินทาง)
            - PV-202401-002: 3,000 บาท (ค่าที่พัก)"

        3. **Date Handling:** - If user asks for "this month", use {current_year}-{now.month:02d}-01 to {today_str}.
           - If user asks for "last year", use {current_year-1}-01-01 to {current_year-1}-12-31.

        4. **Language:** Answer in Thai (Natural & Professional).
        
        5. **Scope:** Only answer questions related to project finance, documents, and expenses.
        """

        # เริ่ม Chat Session
        chat = self.model.start_chat()
        
        
        # ส่ง Prompt + คำถาม User
        full_msg = f"{system_prompt}\n\nUser Question: {user_message}"
        
        try:
            response = chat.send_message(full_msg)
            
            # --- Function Calling Loop ---
            # เช็คว่า AI อยากเรียก Tool หรือไม่?
            if response.candidates[0].content.parts[0].function_call:
                func_call = response.candidates[0].content.parts[0].function_call
                func_name = func_call.name
                func_args = func_call.args
                
                logger.info(f"🤖 AI Calling: {func_name} with {func_args}")
                
                # Router เลือก Tool
                api_result = None
                try:
                    if func_name == "search_documents":
                        api_result = search_documents_tool(db, keyword=func_args.get("keyword"))
                    elif func_name == "get_financial_analytics":
                        api_result = get_financial_analytics_tool(
                            db, 
                            start_date=func_args.get("start_date"),
                            end_date=func_args.get("end_date"),
                            category_name=func_args.get("category_name"),
                            transaction_type=func_args.get("transaction_type", "EXPENSE") # Default เป็นรายจ่ายถ้า AI ลืมส่ง
                        )
                except Exception as tool_err:
                    logger.error(f"Tool Error: {tool_err}")
                    api_result = {"error": "เกิดข้อผิดพลาดในการดึงข้อมูลจากฐานข้อมูล"}

                # ส่งผลลัพธ์กลับไปให้ AI สรุป
                response = chat.send_message(
                    Part.from_function_response(
                        name=func_name,
                        response={"result": api_result}
                    )
                )

            return response.text

        except Exception as e:
            logger.error(f"Gemini Chat Error: {e}")
            return "ขออภัยครับ ระบบ AI ขัดข้องชั่วคราว กรุณาลองใหม่อีกครั้ง"