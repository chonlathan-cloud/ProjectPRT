from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, or_
from app.models import Document, DocumentType, Case, Category, Attachment

def search_documents_tool(db: Session, keyword: str):
    """
    ค้นหาไฟล์เอกสาร (Attachments) จากชื่อไฟล์หรือ URI
    """
    results = db.execute(
        select(Attachment)
        .filter(Attachment.gcs_uri.ilike(f"%{keyword}%"))
        .limit(5)
    ).scalars().all()

    if not results:
        return "ไม่พบเอกสารที่ค้นหาครับ"

    output = []
    for file in results:
        # ในอนาคตอาจเปลี่ยนเป็น Signed URL
        output.append(f"- ไฟล์: {file.gcs_uri.split('/')[-1]} (ID: {file.id})")

    return "\n".join(output)


def get_financial_analytics_tool(
    db: Session, 
    start_date: str = None, 
    end_date: str = None, 
    category_name: str = None,
    transaction_type: str = "EXPENSE" # ✅ เพิ่ม Parameter นี้ (EXPENSE | REVENUE | ALL)
):
    """
    วิเคราะห์ข้อมูลการเงิน (รองรับทั้ง รายรับ-RV และ รายจ่าย-PV)
    """
    
    # 1. Base Query: ใช้ Outer Join เพื่อความปลอดภัย (เผื่อบาง Doc ไม่มี Case)
    base_query = (
        select(Document)
        .outerjoin(Case, Document.case_id == Case.id)
        .outerjoin(Category, Case.category_id == Category.id)
    )

    # 2. Filter Transaction Type (กรองประเภทเอกสาร)
    if transaction_type == "EXPENSE":
        base_query = base_query.filter(Document.doc_type == DocumentType.PV)
        type_label = "รายจ่าย (PV)"
    elif transaction_type == "REVENUE":
        base_query = base_query.filter(Document.doc_type == DocumentType.RV)
        type_label = "รายรับ (RV)"
    else:
        # กรณี ALL หรืออื่นๆ (เอาทั้งคู่)
        base_query = base_query.filter(or_(
            Document.doc_type == DocumentType.PV, 
            Document.doc_type == DocumentType.RV
        ))
        type_label = "รายรับ-รายจ่าย"

    # 3. Apply Date & Category Filters
    if start_date:
        try:
            s_date = datetime.strptime(start_date, "%Y-%m-%d")
            base_query = base_query.filter(Document.created_at >= s_date)
        except ValueError: pass

    if end_date:
        try:
            e_date = datetime.strptime(end_date, "%Y-%m-%d")
            e_date = e_date.replace(hour=23, minute=59, second=59)
            base_query = base_query.filter(Document.created_at <= e_date)
        except ValueError: pass

    if category_name:
        # ค้นหาจากชื่อ Category (เช่น "ค่าเดินทาง", "รายได้จากการขาย")
        base_query = base_query.filter(Category.name_th.ilike(f"%{category_name}%"))

    # 4. Calculate Total
    total_query = select(func.sum(Document.amount)).select_from(base_query.subquery())
    total = db.execute(total_query).scalar() or 0.0

    # 5. Get List Items
    items_query = base_query.order_by(Document.created_at.desc()).limit(5)
    items = db.execute(items_query).scalars().all()

    doc_list = []
    for doc in items:
        # Safe Access Category Name
        cat_name = "-"
        if doc.case and doc.case.category:
            cat_name = doc.case.category.name_th
        
        # ใส่สัญลักษณ์ +/- หรือระบุประเภทให้ชัดเจน
        prefix = "+" if doc.doc_type == DocumentType.RV else "-"
        doc_list.append(f"{prefix} {doc.doc_no}: {doc.amount:,.2f} บาท ({cat_name})")

    if not doc_list and total > 0:
        doc_list.append("(มีรายการย่อยมากกว่านี้ แต่แสดงได้สูงสุด 5 รายการ)")

    return {
        "transaction_type": transaction_type,
        "total_amount": float(total),
        "period": f"{start_date or 'N/A'} to {end_date or 'N/A'}",
        "breakdown": doc_list,
        "note": f"ยอดรวม{type_label} ตามเอกสารที่อนุมัติแล้ว"
    }