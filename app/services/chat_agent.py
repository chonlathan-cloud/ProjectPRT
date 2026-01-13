# app/services/chat_agent.py
import vertexai
from vertexai.generative_models import GenerativeModel, Tool, FunctionDeclaration, Part
from sqlalchemy.orm import Session
from app.core.settings import settings
from app.services.chat_tools import (
    search_document_by_no_tool,
    get_financial_analytics_tool,
    check_workflow_status_tool,
    get_policy_info_tool,
    get_monthly_comparison_tool
)
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# --- Tool Definitions ---

# 1. Search Specific Document
search_doc_decl = FunctionDeclaration(
    name="search_document_by_no",
    description="Find a specific document by its number (PV-xxxx, RV-xxxx) to get status, amount, and download link.",
    parameters={
        "type": "object",
        "properties": {
            "doc_no": {"type": "string", "description": "Document number e.g. PV-6702-001"}
        },
        "required": ["doc_no"]
    }
)

# 2. Financial Analytics
analytics_decl = FunctionDeclaration(
    name="get_financial_analytics",
    description="Calculate total income or expense for a specific period. EXCLUDES JV/Journal Vouchers.",
    parameters={
        "type": "object",
        "properties": {
            "start_date": {"type": "string", "description": "YYYY-MM-DD"},
            "end_date": {"type": "string", "description": "YYYY-MM-DD"},
            "transaction_type": {"type": "string", "enum": ["EXPENSE", "REVENUE"], "description": "Default is EXPENSE"}
        },
        "required": ["transaction_type"]
    }
)

# 3. Workflow Status
workflow_decl = FunctionDeclaration(
    name="check_workflow_status",
    description="Check who is currently holding the task or why it is delayed.",
    parameters={
        "type": "object",
        "properties": {
            "doc_or_case_no": {"type": "string", "description": "Case or Doc number"}
        },
        "required": ["doc_or_case_no"]
    }
)

# 4. Policy Info
policy_decl = FunctionDeclaration(
    name="get_policy_info",
    description="Answer questions about rules, regulations, limits, or how-to (e.g., taxi limit, meal allowance).",
    parameters={
        "type": "object",
        "properties": {
            "query_topic": {"type": "string", "description": "Topic of the policy question"}
        },
        "required": ["query_topic"]
    }
)

# 5. Monthly Insight
insight_decl = FunctionDeclaration(
    name="get_monthly_comparison",
    description="Compare this month's expense with last month.",
    parameters={"type": "object", "properties": {}}
)

prt_tools = Tool(function_declarations=[
    search_doc_decl, analytics_decl, workflow_decl, policy_decl, insight_decl
])

class PRTChatAgent:
    def __init__(self):
        vertexai.init(project=settings.GOOGLE_CLOUD_PROJECT, location="asia-southeast1")
        self.model = GenerativeModel("gemini-2.5-flash", tools=[prt_tools])

    def chat(self, user_message: str, db: Session, user_name: str):
        # System Prompt ขั้นเทพ
        system_instruction = f"""
        You are PRT FinBot.
        Context: User={user_name}, Date={datetime.now().strftime('%Y-%m-%d')}
        
        RULES:
        1. **Strictly exclude JV (Journal Voucher)** from any "Spending", "Expense", or "Income" calculation unless explicitly asked.
        2. If user asks for specific document details, use `search_document_by_no` and provide the **download link** if available.
        3. If user asks about rules/limits (e.g. taxi, food), use `get_policy_info`.
        4. Answer in **Thai**.
        """

        chat = self.model.start_chat()
        
        # ส่ง Prompt + Message
        response = chat.send_message(f"{system_instruction}\n\nUser: {user_message}")

        # Handle Function Calling
        if response.candidates[0].content.parts[0].function_call:
            func = response.candidates[0].content.parts[0].function_call
            fname = func.name
            args = func.args
            
            logger.info(f"Tool Call: {fname} with {args}")
            
            result = None
            try:
                if fname == "search_document_by_no":
                    result = search_document_by_no_tool(db, args["doc_no"])
                elif fname == "get_financial_analytics":
                    result = get_financial_analytics_tool(db, args.get("start_date"), args.get("end_date"), args.get("transaction_type"))
                elif fname == "check_workflow_status":
                    result = check_workflow_status_tool(db, args["doc_or_case_no"])
                elif fname == "get_policy_info":
                    result = get_policy_info_tool(args["query_topic"])
                elif fname == "get_monthly_comparison":
                    result = get_monthly_comparison_tool(db)
            except Exception as e:
                result = f"Error executing tool: {e}"

            # ส่งผลกลับ AI
            response = chat.send_message(
                Part.from_function_response(name=fname, response={"result": result})
            )
            
        return response.text