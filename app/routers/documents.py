# app/routers/dashboard.py
from fastapi import APIRouter, Request, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, extract
from datetime import datetime, date

from app.db import get_db
from app.rbac import require_roles, ROLE_ADMIN, ROLE_ACCOUNTANT, ROLE_VIEWER
from app.models import Document, DocumentType, Case, Category, CaseStatus, JVLineItem, Attachment, AttachmentType
from app.services.doc_numbers import generate_document_no
from app.services import gcs
from app.schemas.common import make_success_response
from app.schemas.document import JVCreate, DocumentResponse
from app.schemas.dashboard import (
    DashboardResponse, MonthlyData, ActivityData, TransactionItem
)

router = APIRouter(
    prefix="/api/v1/documents",
    tags=["documents"],
)

@router.get("", response_model=DashboardResponse)
async def get_full_dashboard(
    request: Request, 
    year: int = Query(default=datetime.now().year),
    db: Session = Depends(get_db)
):
    # 1. Permission Check
    _, auth_error = require_roles(db, request, [ROLE_ADMIN, ROLE_ACCOUNTANT, ROLE_VIEWER])
    if auth_error:
        return auth_error

    # ---------------------------------------------------------
    # Helper Filter: สร้างตัวแปรเก็บเงื่อนไขพื้นฐานไว้ใช้ซ้ำ
    # กรองเฉพาะปีที่เลือก และ ตัดเคสที่ยกเลิก/ปฏิเสธ/ดราฟทิ้ง (แล้วแต่ Business logic ว่าจะนับสถานะไหนบ้าง)
    # ในที่นี้สมมติว่านับเฉพาะที่ APPROVED หรือ PAID แล้ว หรืออย่างน้อยต้องไม่ Cancelled
    base_filter = [
        extract('year', Document.created_at) == year,
        Case.status.notin_([CaseStatus.DRAFT, CaseStatus.CANCELLED, CaseStatus.REJECTED]) # <--- สำคัญ!
    ]
    # ---------------------------------------------------------

    # A. Summary
    # ต้อง Join Case เพื่อเช็ค Status
    income_sum = db.query(func.sum(Document.amount))\
        .join(Case, Document.case_id == Case.id)\
        .filter(
            *base_filter,
            Document.doc_type == DocumentType.RV
        ).scalar() or 0.0

    expense_sum = db.query(func.sum(Document.amount))\
        .join(Case, Document.case_id == Case.id)\
        .filter(
            *base_filter,
            Document.doc_type == DocumentType.PV
        ).scalar() or 0.0

    balance = float(income_sum) - float(expense_sum)

    # B. Monthly Stats (PV Only)
    monthly_data = db.query(
        extract('month', Document.created_at).label('month'),
        func.sum(Document.amount).label('total')
    ).join(Case, Document.case_id == Case.id)\
     .filter(
        *base_filter,
        Document.doc_type == DocumentType.PV
    ).group_by('month').all()

    # ... (ส่วน Mapping เดือน เหมือนเดิม) ...
    months_map = {int(m): float(v) for m, v in monthly_data}
    months_name = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    monthly_stats = []
    for i, name in enumerate(months_name):
        val = months_map.get(i + 1, 0.0)
        monthly_stats.append(MonthlyData(name=name, value=val))

    # C. Activity Stats (Category)
    cat_data = db.query(
        Category.name_th,
        func.sum(Document.amount)
    ).join(Case, Document.case_id == Case.id)\
     .join(Category, Case.category_id == Category.id)\
     .filter(
        *base_filter,
        Document.doc_type == DocumentType.PV
     ).group_by(Category.name_th).all()

    # ... (ส่วนสีและ Loop เหมือนเดิม) ...
    colors = ["#8884d8", "#82ca9d", "#ffc658", "#ff8042", "#0088fe", "#00C49F"]
    activity_stats = []
    for i, (name, val) in enumerate(cat_data):
        activity_stats.append(ActivityData(
            name=name,
            value=float(val),
            fill=colors[i % len(colors)]
        ))

    # D. Latest Transactions
    latest_docs = db.query(Document, Case, Category)\
        .join(Case, Document.case_id == Case.id)\
        .join(Category, Case.category_id == Category.id)\
        .filter(*base_filter)\
        .order_by(desc(Document.created_at))\
        .limit(5).all()

    # ... (ส่วน Loop latest_transactions เหมือนเดิม) ...
    case_ids = [case.id for _, case, _ in latest_docs]
    receipt_map = {}
    if case_ids:
        receipt_rows = db.query(Attachment.case_id, Attachment.gcs_uri, Attachment.uploaded_at)\
            .filter(
                Attachment.type == AttachmentType.RECEIPT,
                Attachment.case_id.in_(case_ids)
            )\
            .order_by(Attachment.case_id, desc(Attachment.uploaded_at))\
            .all()
        for case_id, gcs_uri, _uploaded_at in receipt_rows:
            if case_id not in receipt_map:
                receipt_map[case_id] = gcs_uri

    latest_transactions = []
    for doc, case, cat in latest_docs:
        initial_char = "P" if doc.doc_type == DocumentType.PV else "R"
        gcs_uri = receipt_map.get(case.id)
        receipt_url = gcs.generate_signed_download_url(gcs_uri) if gcs_uri else None
        latest_transactions.append(TransactionItem(
            id=str(doc.id),
            initial=initial_char, 
            name=cat.name_th,
            description=f"{doc.doc_no} - {case.purpose}",
            amount=float(doc.amount),
            receipt_url=receipt_url
        ))

    return make_success_response({
        "summary": {
            "expenses": float(expense_sum),
            "income": float(income_sum),
            "balance": balance
        },
        "monthlyStats": monthly_stats,
        "activityStats": activity_stats,
        "latestTransactions": latest_transactions
    })

@router.post("/jv", response_model=DocumentResponse)
async def create_jv(
    payload: JVCreate,
    db: Session = Depends(get_db)
):
    """
    สร้าง JV โดยการรวม Case (PV/RV) หลายๆ ใบเข้าด้วยกัน
    """
    # 1. ตรวจสอบ Case หลัก
    main_case = db.query(Case).filter(Case.id == payload.main_case_id).first()
    if not main_case:
        raise HTTPException(404, "Main case not found")

    # 2. คำนวณยอดรวมจากทุก Case ที่เลือกรวมกัน
    total_amount = main_case.requested_amount
    all_case_ids = [payload.main_case_id] + payload.linked_case_ids
    
    # วนลูปเช็ค Case อื่นๆ และรวมยอด
    for linked_id in payload.linked_case_ids:
        c = db.query(Case).filter(Case.id == linked_id).first()
        if c:
            total_amount += c.requested_amount
    
    # 3. สร้างเอกสาร JV (ใช้เลข Running ใหม่)
    # (สมมติฟังก์ชัน _generate_document_no มีอยู่แล้วในไฟล์นี้ หรือ import มา)
    jv_no = generate_document_no(db, DocumentType.JV)
    
    jv_doc = Document(
        case_id=main_case.id, # JV ผูกกับ Case หลัก
        doc_type=DocumentType.JV,
        doc_no=jv_no,
        amount=total_amount,
        pdf_uri="pending-jv",
        created_by="system" 
    )
    db.add(jv_doc)
    db.flush()

    # 4. สร้าง JV Line Items (Link กลับไปหา Case เดิม)
    for cid in all_case_ids:
        c = db.query(Case).filter(Case.id == cid).first()
        line = JVLineItem(
            jv_document_id=jv_doc.id,
            ref_case_id=cid,
            amount=c.requested_amount
        )
        db.add(line)
        
        # Option: ปิด Case เดิมเพื่อไม่ให้เอาไปใช้ซ้ำ
        c.status = CaseStatus.CLOSED
        
    db.commit()
    db.refresh(jv_doc)
    return jv_doc
