from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from app.core.settings import settings
from app.deps import Role, has_role

# Import Routers
from app.routers.categories import router as categories_router
from app.routers.cases import router as cases_router
from app.routers.files import router as files_router
from app.routers.documents import router as documents_router
from app.routers.dashboard import router as dashboard_router
from app.routers.transactions import router as transactions_router
from app.routers.auth import router as auth_router
from app.routers.admin import router as admin_router
from app.routers.chat import router as chat_router
from app.routers import insights  # ✅ ตรวจสอบว่าไฟล์ app/routers/insights.py มีอยู่จริง

app = FastAPI(
    title="PRT Software Accounting API",
    description="Backend for PRT Software Accounting System",
    version="0.1.0",
)

# --- CORS Configuration ---
# อนุญาตให้ Frontend โทรหา Backend ได้
origins = [
    "http://localhost:3000",
    "https://frontend-app-886029565568.asia-southeast1.run.app", # Frontend URL
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS if hasattr(settings, "CORS_ALLOW_ORIGINS") else origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 🚀 Register Routers with /api/v1 Prefix ---
# นี่คือส่วนสำคัญที่ทำให้ Frontend เจอ Backend
API_PREFIX = "/api/v1"

app.include_router(auth_router, prefix=f"{API_PREFIX}/auth", tags=["Auth"])
app.include_router(cases_router, prefix=f"{API_PREFIX}/cases", tags=["Cases"])
app.include_router(categories_router, prefix=f"{API_PREFIX}/categories", tags=["Categories"])
app.include_router(dashboard_router, prefix=f"{API_PREFIX}/dashboard", tags=["Dashboard"])
app.include_router(insights.router, prefix=f"{API_PREFIX}/insights", tags=["Insights"]) # ✅ Insights
app.include_router(transactions_router, prefix=f"{API_PREFIX}/transactions", tags=["Transactions"])
app.include_router(files_router, prefix=f"{API_PREFIX}/files", tags=["Files"])
app.include_router(documents_router, prefix=f"{API_PREFIX}/documents", tags=["Documents"])
app.include_router(chat_router, prefix=f"{API_PREFIX}/chat", tags=["Chat AI"])
app.include_router(admin_router, prefix=f"{API_PREFIX}/admin", tags=["Admin"])

# --- Health & Debug Routes ---
@app.get("/healthz", tags=["Health Check"])
async def health_check():
    return {"status": "ok"}

@app.get("/", tags=["Health Check"])
async def root():
    return {"message": "PRT Software Accounting API is running"}