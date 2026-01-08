import vertexai
from vertexai.generative_models import GenerativeModel, Tool, FunctionDeclaration, Part
from sqlalchemy.orm import Session
from datetime import datetime
import logging
from app.services.chat_tools import (
    search_documents_tool, 
    get_financial_analytics_tool, 
    search_cases_with_details_tool # <--- ✅ Import Tool ใหม่ที่เพิ่งสร้าง
)
from app.core.settings import settings

# ตั้งค่า Logger
logger = logging.getLogger(__name__)

# --- 1. Init Vertex AI ---
try:
    vertexai.init(project=settings.GOOGLE_CLOUD_PROJECT, location="asia-southeast1")
except Exception as e:
    logger.error(f"Vertex AI Init Error: {e}")

# --- 2. Tool Definitions ---

# Tool 1: ค้นหาไฟล์ (เดิม)
search_doc_decl = FunctionDeclaration(
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

# Tool 2: ดูยอดรวม (เดิม)
analytics_decl = FunctionDeclaration(
    name="get_financial_analytics", 
    description="Get total financial summary (Income/Expense/Balance). Use this for aggregation questions like 'Total expense this month'.",
    parameters={
        "type": "object",
        "properties": {
            "start_date": {"type": "string", "description": "Start date YYYY-MM-DD"},
            "end_date": {"type": "string", "description": "End date YYYY-MM-DD"},
            "category_name": {"type": "string", "description": "Category filter e.g. 'Sales', 'Travel'"},
            "transaction_type": {
                "type": "string", 
                "enum": ["EXPENSE", "REVENUE", "ALL"],
                "description": "Type of transaction."
            }
        },
        "required": ["transaction_type"] 
    }
)

# Tool 3: ค้นหารายการละเอียด (✅ เพิ่มใหม่)
case_details_decl = FunctionDeclaration(
    name="search_cases_with_details",
    description="Search for specific expense/revenue lists/items. Use this when user asks for 'list of items', 'details of expenses', 'who requested what', or specific category breakdowns.",
    parameters={
        "type": "object",
        "properties": {
            "category_keyword": {"type": "string", "description": "Keyword for category e.g. 'Food', 'Travel', 'Equipment'"},
            "requester_name": {"type": "string", "description": "Name of the requester to filter"},
            "status": {"type": "string", "description": "Filter by status e.g. 'APPROVED'"}
        },
    }
)

# รวม Tools ทั้งหมด
prt_tools = Tool(function_declarations=[search_doc_decl, analytics_decl, case_details_decl])

# --- 3. Chat Agent Class ---
class PRTChatAgent:
    def __init__(self):
        # ใช้ Model Flash ที่เร็วและประหยัด
        self.model = GenerativeModel(
            "gemini-2.5-flash",
            tools=[prt_tools]
        )

    def chat(self, user_message: str, db: Session, user_name: str = "User"):
        # Context เวลาปัจจุบัน
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        
        # ✅ System Prompt ที่ปรับปรุงใหม่
        system_prompt = f"""
        You are 'PRT FinBot', an expert financial assistant.
        
        --- CONTEXT ---
        * User: {user_name}
        * Today: {today_str}
        
        --- TOOL USAGE GUIDELINES ---
        1. **Summary Questions:** If asked for "Total", "Sum", "Overview", use `get_financial_analytics`.
        2. **List/Detail Questions:** If asked for "List", "What are they?", "Show details", "Who spent what?", use `search_cases_with_details`.
        3. **File Questions:** If asked for "File", "PDF", "Receipt", use `search_documents`.
        
        --- RESPONSE RULES ---
        1. **Be Fact-Based:** Only answer based on the Tool Output. Do not hallucinate numbers.
        2. **Show References:** When listing items, always show [Doc No] and [Amount] clearly.
           Example: "- PV-6601-001: 500 บาท (ค่าอาหาร) โดย คุณสมชาย"
        3. **Thai Language:** Always answer in polite Thai.
        """

        # เริ่ม Chat
        chat = self.model.start_chat()
        full_msg = f"{system_prompt}\n\nUser Question: {user_message}"
        
        try:
            response = chat.send_message(full_msg)
            
            # --- Function Calling Loop ---
            if response.candidates[0].content.parts[0].function_call:
                func_call = response.candidates[0].content.parts[0].function_call
                func_name = func_call.name
                func_args = func_call.args
                
                logger.info(f"🤖 AI Calling: {func_name} with {func_args}")
                
                api_result = None
                try:
                    # 1. Search Documents
                    if func_name == "search_documents":
                        api_result = search_documents_tool(db, keyword=func_args.get("keyword"))
                    
                    # 2. Analytics (ยอดรวม)
                    elif func_name == "get_financial_analytics":
                        api_result = get_financial_analytics_tool(
                            db, 
                            start_date=func_args.get("start_date"),
                            end_date=func_args.get("end_date"),
                            category_name=func_args.get("category_name"),
                            transaction_type=func_args.get("transaction_type", "EXPENSE")
                        )
                    
                    # 3. Case Details (✅ รายการละเอียด)
                    elif func_name == "search_cases_with_details":
                        api_result = search_cases_with_details_tool(
                            db,
                            category_keyword=func_args.get("category_keyword"),
                            requester_name=func_args.get("requester_name"),
                            status=func_args.get("status")
                        )

                except Exception as tool_err:
                    logger.error(f"Tool Error: {tool_err}")
                    api_result = {"error": "เกิดข้อผิดพลาดในการดึงข้อมูลจากฐานข้อมูล"}

                # ส่งผลลัพธ์กลับไปให้ AI สรุปเป็นภาษาคน
                response = chat.send_message(
                    Part.from_function_response(
                        name=func_name,
                        response={"result": api_result}
                    )
                )

            return response.text

        except Exception as e:
            logger.error(f"Gemini Chat Error: {e}")
            return "ขออภัยครับ ระบบ AI ขัดข้องชั่วคราว"