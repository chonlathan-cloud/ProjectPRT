from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text # Import text here
from app.db import get_db
from app.deps import Role, has_role, get_current_user
from app.routers.categories import router as categories_router
from app.routers.cases import router as cases_router

app = FastAPI(
    title="PRT Software Accounting API",
    description="Backend for PRT Software Accounting System, Phase 2: Backend Skeleton + RBAC Foundation",
    version="0.1.0",
)

app.include_router(categories_router)
app.include_router(cases_router)

@app.get("/healthz", tags=["Health Check"])
async def health_check(db: Session = Depends(get_db)):
    try:
        # Try to execute a simple query to check database connectivity
        db.execute(text("SELECT 1")) # Use text("SELECT 1")
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Database connection failed: {e}")

@app.get("/admin-only", tags=["RBAC Demo"], dependencies=[Depends(has_role([Role.ADMIN]))])
async def admin_only_route():
    return {"message": "Welcome, Admin!"}

@app.get("/finance-or-admin", tags=["RBAC Demo"], dependencies=[Depends(has_role([Role.FINANCE, Role.ADMIN]))])
async def finance_or_admin_route():
    return {"message": "Welcome, Finance or Admin!"}

@app.get("/requester-info", tags=["RBAC Demo"], dependencies=[Depends(has_role([Role.REQUESTER]))])
async def requester_info_route():
    return {"message": "Welcome, Requester! Here is some info."}
