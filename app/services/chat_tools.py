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
    """
    # ❌ ของเดิม (สาเหตุ Error)
    # query = select(func.sum(Document.amount)).join(Case).join(Category)

    # ✅ ของใหม่ (ระบุชัดเจนว่า join ผ่าน category_id)
    query = (
        select(func.sum(Document.amount))
        .join(Case, Document.case_id == Case.id) # Join Case ก่อน (กันเหนียว)
        .join(Category, Case.category_id == Category.id) # <--- ระบุเงื่อนไขตรงนี้ชัดๆ
    )
    
    # [NEW] เพิ่ม Query เพื่อดึง 5 รายการล่าสุดที่เกี่ยวข้อง
    detail_query = (
        select(Document.id, Document.doc_no, Document.amount, Document.created_at, Category.name_th)
        .join(Case, Document.case_id == Case.id)
        .join(Category, Case.category_id == Category.id)
        .filter(Document.doc_type == DocumentType.PV)
    )

    query = query.filter(Document.doc_type == DocumentType.PV) # เฉพาะรายจ่ายจริง

    recent_docs = db.execute(detail_query.order_by(Document.created_at.desc()).limit(5)).all()
    
    #แปลงข้อมูลเป็น list ของ string
    doc_list = []
    for doc in recent_docs:
        doc_list.append(f"- {doc.doc_no}: {doc.amount:,.2f} บาท ({doc.name_th})")
    if start_date:
        # แปลง string เป็น date เพื่อความชัวร์ (บางทีมาแค่ YYYY-MM-DD)
        try:
            s_date = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(Document.created_at >= s_date)
        except ValueError:
            pass # หรือ handle error ตามเหมาะสม

    if end_date:
        try:
            e_date = datetime.strptime(end_date, "%Y-%m-%d")
            # ควรปรับเวลาให้ครอบคลุมถึงสิ้นวัน (23:59:59) ถ้าจำเป็น
            query = query.filter(Document.created_at <= e_date)
        except ValueError:
            pass

    if category_name:
        query = query.filter(Category.name_th.ilike(f"%{category_name}%"))

    # ... (ส่วน return เหมือนเดิม) ...
    total = db.execute(query).scalar() or 0.0
    
    breakdown_text = ""
    if category_name:
        breakdown_text = f" (เฉพาะหมวดที่มีคำว่า '{category_name}')"
    
    return {
        "total_expense": float(total),
        "period": f"{start_date} to {end_date}",
        "breakdown": doc_list,
        "note": f"ยอดรวมจากเอกสาร PV"
    }