from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, or_, text
from app.models import Document, DocumentType, Case, Category, Attachment, CaseStatus
import json

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
        .join(Case, Document.case_id == Case.id) # เปลี่ยนเป็น Inner Join เพื่อความชัวร์เรื่อง Status
        .join(Category, Case.category_id == Category.id)
        .filter(Case.status.in_([
            CaseStatus.APPROVED, 
            CaseStatus.PAID, 
            CaseStatus.CLOSED
        ])) # ✅✅✅ all status ที่ผ่านการอนุมัติแล้ว
    )

    # 2. Filter Transaction Type (กรองประเภทเอกสาร)
    if transaction_type == "EXPENSE":
        base_query = base_query.filter(Document.doc_type == DocumentType.PV)
        type_label = "รายจ่าย (PV)"
    elif transaction_type == "REVENUE":
        base_query = base_query.filter(Document.doc_type == DocumentType.RV)
        type_label = "รายรับ (RV)"
    else:
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
        base_query = base_query.filter(Category.name_th.ilike(f"%{category_name}%"))

    # ... (ส่วน Calculate Total & List เหมือนเดิม) ...
    total_query = select(func.sum(Document.amount)).select_from(base_query.subquery())
    total = db.execute(total_query).scalar() or 0.0

    items_query = base_query.order_by(Document.created_at.desc()).limit(5)
    items = db.execute(items_query).scalars().all()

    doc_list = []
    for doc in items:
        # doc.case มีแน่นอนเพราะ join แล้ว
        cat_name = doc.case.category.name_th if doc.case.category else "-"
        prefix = "+" if doc.doc_type == DocumentType.RV else "-"
        doc_list.append(f"{prefix} {doc.doc_no}: {doc.amount:,.2f} บาท ({cat_name})")

    if not doc_list and total > 0:
        doc_list.append("(มีรายการเพิ่มเติม...)")

    return {
        "transaction_type": transaction_type,
        "total_amount": float(total),
        "period": f"{start_date or 'N/A'} to {end_date or 'N/A'}",
        "breakdown": doc_list,
        "note": f"ยอดรวม{type_label} (สถานะ Approved เท่านั้น)"
    }

def search_cases_with_details_tool(db: Session, category_keyword: str = None, requester_name: str = None, status: str = None):
    """
    ค้นหาข้อมูล Case แบบละเอียด (รองรับการถามว่า 'ค่าอาหารมีอะไรบ้าง')
    """
    sql = """
        SELECT 
            d.doc_no,
            c.created_at,
            c.requested_amount,
            c.purpose,
            u.name as requester_name,
            cat.name_th as category_name
        FROM cases c
        JOIN categories cat ON c.category_id = cat.id
        LEFT JOIN documents d ON c.id = d.case_id
        LEFT JOIN users u ON c.requester_id = u.email -- หรือ u.google_sub ตามโครงสร้าง
        WHERE 1=1
    """
    params = {}
    
    if category_keyword:
        sql += " AND cat.name_th ILIKE :cat_kw"
        params["cat_kw"] = f"%{category_keyword}%"
        
    if requester_name:
        sql += " AND u.name ILIKE :req_name"
        params["req_name"] = f"%{requester_name}%"

    if status == 'APPROVED':
        sql += " AND c.status IN ('APPROVED', 'PAID', 'CLOSED')" # รวมสถานะที่ผ่านแล้ว
        
    sql += " ORDER BY c.created_at DESC LIMIT 10"
    
    results = db.execute(text(sql), params).fetchall()
    
    if not results:
        return "ไม่พบข้อมูลรายการครับ"
        
    # Format ข้อมูลกลับไปให้ AI อ่านง่ายๆ
    output_list = []
    for r in results:
        doc_str = r.doc_no if r.doc_no else "รอออกเลข"
        date_str = r.created_at.strftime("%d/%m/%Y")
        output_list.append(f"- {doc_str} | {date_str} | {r.requested_amount:,.2f} บาท | โดย: {r.requester_name} | รายการ: {r.purpose}")
        
    return "\n".join(output_list)