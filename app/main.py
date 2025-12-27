from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from app.core.settings import settings
from app.deps import Role, has_role
from app.routers.categories import router as categories_router
from app.routers.cases import router as cases_router
from app.routers.files import router as files_router
from app.routers.documents import router as documents_router
from app.routers.dashboard import router as dashboard_router
from app.routers.transactions import router as transactions_router
from app.routers.auth import router as auth_router
from app.routers.admin import router as admin_router

app = FastAPI(
    title="PRT Software Accounting API",
    description="Backend for PRT Software Accounting System, Phase 2: Backend Skeleton + RBAC Foundation",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(categories_router)
app.include_router(cases_router)
app.include_router(files_router)
app.include_router(documents_router)
app.include_router(dashboard_router)
app.include_router(transactions_router)
app.include_router(auth_router)
app.include_router(admin_router)

@app.get("/healthz", tags=["Health Check"])
async def health_check():
    return {"status": "ok"}

@app.get("/admin-only", tags=["RBAC Demo"], dependencies=[Depends(has_role([Role.ADMIN]))])
async def admin_only_route():
    return {"message": "Welcome, Admin!"}

@app.get("/finance-or-admin", tags=["RBAC Demo"], dependencies=[Depends(has_role([Role.FINANCE, Role.ADMIN]))])
async def finance_or_admin_route():
    return {"message": "Welcome, Finance or Admin!"}

@app.get("/requester-info", tags=["RBAC Demo"], dependencies=[Depends(has_role([Role.REQUESTER]))])
async def requester_info_route():
    return {"message": "Welcome, Requester! Here is some info."}
