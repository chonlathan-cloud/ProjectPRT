from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_
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

def get_expense_analytics_tool(db: Session, start_date: str = None, end_date: str = None, category_name: str = None):
    """
    วิเคราะห์ยอดใช้จ่ายจริง (จาก PV)
    Args:
        start_date (str): YYYY-MM-DD
        end_date (str): YYYY-MM-DD
        category_name (str): คำค้นหาหมวดหมู่ เช่น "ค่าเดินทาง", "อุปกรณ์"
    """
    query = select(func.sum(Document.amount)).join(Case).join(Category)
    query = query.filter(Document.doc_type == DocumentType.PV) # เฉพาะรายจ่ายจริง

    if start_date:
        query = query.filter(Document.created_at >= datetime.strptime(start_date, "%Y-%m-%d"))
    if end_date:
        query = query.filter(Document.created_at <= datetime.strptime(end_date, "%Y-%m-%d"))
    
    if category_name:
        query = query.filter(Category.name_th.ilike(f"%{category_name}%"))

    total = db.execute(query).scalar() or 0.0
    
    # ดึงรายละเอียดหมวดหมู่มาด้วย (ถ้ามีการกรองวัน)
    breakdown_text = ""
    if category_name:
        breakdown_text = f" (เฉพาะหมวดที่มีคำว่า '{category_name}')"
    
    return {
        "total_expense": float(total),
        "period": f"{start_date} to {end_date}",
        "note": f"ยอดรวมจากเอกสาร PV{breakdown_text}"
    }