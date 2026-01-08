import vertexai
from vertexai.generative_models import GenerativeModel, Tool, FunctionDeclaration, Part
from sqlalchemy.orm import Session
from datetime import datetime
from app.core.settings import settings
from app.services.chat_tools import search_documents_tool, get_expense_analytics_tool

# Initialize (ควรทำที่ startup event แต่ใส่ตรงนี้เพื่อให้เห็นภาพรวม)
# ตรวจสอบว่า GOOGLE_CLOUD_PROJECT ใน .env ถูกต้อง
try:
    vertexai.init(project=settings.GOOGLE_CLOUD_PROJECT, location="asia-southeast1")
except Exception as e:
    print(f"Vertex AI Init Warning: {e}")

# --- Tool Declarations ---
search_tool = FunctionDeclaration(
    name="search_documents",
    description="Search for file attachments by filename keyword.",
    parameters={
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "Search term e.g. 'invoice', 'slip'"}
        },
        "required": ["keyword"]
    }
)

analytics_tool = FunctionDeclaration(
    name="get_expense_analytics",
    description="Calculate total expenses (PV) with optional filters.",
    parameters={
        "type": "object",
        "properties": {
            "start_date": {"type": "string", "description": "Start date YYYY-MM-DD"},
            "end_date": {"type": "string", "description": "End date YYYY-MM-DD"},
            "category_name": {"type": "string", "description": "Category name filter e.g. 'Travel', 'Food'"}
        }
    }
)

prt_tools = Tool(function_declarations=[search_tool, analytics_tool])

class PRTChatAgent:
    def __init__(self):
        self.model = GenerativeModel(
            "gemini-2.5-flash-001",
            tools=[prt_tools]
        )

    def chat(self, user_message: str, db: Session, user_name: str = "User"):
        # Context ปัจจุบัน
        today = datetime.now().strftime("%Y-%m-%d")
        
        system_prompt = f"""
        You are PRT Financial Assistant. 
        Current Date: {today}.
        User: {user_name}.
        
        Rules:
        1. When asked about 'this month', calculate the start and end dates of the current month based on Today.
        2. When asked about 'last quarter', calculate dates accordingly.
        3. Only use provided tools for data.
        4. Answer in Thai naturally.
        """

        chat = self.model.start_chat()
        
        # ส่ง System Prompt ไปพร้อมข้อความแรก (หรือตั้งตอน init model ก็ได้)
        full_prompt = f"{system_prompt}\n\nUser Question: {user_message}"
        response = chat.send_message(full_prompt)

        # Function Calling Loop
        if response.candidates[0].content.parts[0].function_call:
            func_call = response.candidates[0].content.parts[0].function_call
            func_name = func_call.name
            func_args = func_call.args
            
            print(f"🤖 AI Calling Tool: {func_name} with {func_args}")

            api_result = None
            if func_name == "search_documents":
                api_result = search_documents_tool(db, keyword=func_args.get("keyword"))
            elif func_name == "get_expense_analytics":
                api_result = get_expense_analytics_tool(
                    db, 
                    start_date=func_args.get("start_date"),
                    end_date=func_args.get("end_date"),
                    category_name=func_args.get("category_name")
                )

            # ส่งผลลัพธ์กลับไปให้ Gemini
            response = chat.send_message(
                Part.from_function_response(
                    name=func_name,
                    response={"result": api_result}
                )
            )

        return response.text