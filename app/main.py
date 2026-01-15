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
from app.routers import insights  # ✅ ต้อง import module นี้
from app.routers.profit_loss import router as profit_loss_router

app = FastAPI(
    title="PRT Software Accounting API",
    description="Backend for PRT Software Accounting System",
    version="0.1.0",
)

# --- CORS Configuration ---
origins = [
    "http://localhost:3000",
    "https://frontend-app-886029565568.asia-southeast1.run.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS if hasattr(settings, "CORS_ALLOW_ORIGINS") else origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Register Routers (แบบไม่มี Prefix ที่นี่ เพราะไปใส่ในไฟล์ลูกแทน) ---
app.include_router(categories_router)
app.include_router(cases_router)
app.include_router(files_router)
app.include_router(documents_router)
app.include_router(dashboard_router)
app.include_router(transactions_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(chat_router)
app.include_router(insights.router) # ✅ เพิ่ม insights เข้าไป
app.include_router(profit_loss_router)

# --- Health Checks ---
@app.get("/healthz", tags=["Health Check"])
async def health_check():
    return {"status": "ok"}

@app.get("/", tags=["Health Check"])
async def root():
    return {"message": "PRT Software Accounting API is running"}

# --- RBAC Demo Routes ---
@app.get("/admin-only", tags=["RBAC Demo"], dependencies=[Depends(has_role([Role.ADMIN]))])
async def admin_only_route():
    return {"message": "Welcome, Admin!"}

@app.get("/finance-or-admin", tags=["RBAC Demo"], dependencies=[Depends(has_role([Role.FINANCE, Role.ADMIN]))])
async def finance_or_admin_route():
    return {"message": "Welcome, Finance or Admin!"}

@app.get("/requester-info", tags=["RBAC Demo"], dependencies=[Depends(has_role([Role.REQUESTER]))])
async def requester_info_route():
    return {"message": "Welcome, Requester! Here is some info."}
