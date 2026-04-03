from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, or_, text, desc
from app.models import Document, DocumentType, Case, Category, Attachment, CaseStatus, AuditLog, User
from app.services.gcs import generate_download_url
import json

MOCK_POLICY_DATA = """
1. ค่าอาหารและเครื่องดื่ม: เบิกได้ตามจริงไม่เกิน 500 บาท/คน/มื้อ ต้องมีใบเสร็จรับเงินฉบับจริง
2. ค่าเดินทาง (Taxi): เบิกได้ตามจริง ต้องแนบใบเสร็จ ถ้าไม่มีให้ใช้ใบรับรองแทนใบเสร็จ (แบบฟอร์ม บก.111)
3. ค่าที่พัก: ระดับ Manager เบิกได้ 2,500 บาท/คืน, Staff เบิกได้ 1,500 บาท/คืน
4. การอนุมัติ: ยอดเงินไม่เกิน 10,000 บาท อนุมัติโดย Manager, เกิน 10,000 บาท ต้องให้ Director อนุมัติ
5. เอกสาร JV (Journal Voucher): ใช้สำหรับปรับปรุงบัญชีเท่านั้น ห้ามนำมาเบิกเงินสด
"""

def search_document_by_no_tool(db: Session, doc_no: str):
    """ค้นหาเอกสารจากเลขที่ (เช่น PV-6701-001) พร้อมสร้างลิงก์เปิดไฟล์"""
    # 1. ค้นหา Document
    doc = db.query(Document).filter(Document.doc_no.ilike(f"%{doc_no}%")).first()
    
    if not doc:
        # ลองหาจาก Case No เผื่อ User พิมพ์ผิด
        case = db.query(Case).filter(Case.case_no.ilike(f"%{doc_no}%")).first()
        if not case:
            return f"ไม่พบเอกสารเลขที่ {doc_no} ในระบบครับ"
        # ถ้าเจอ Case ให้หา Document ที่ผูกอยู่
        doc = db.query(Document).filter(Document.case_id == case.id).first()
        if not doc:
            return f"พบ Case {case.case_no} แต่ยังไม่มีเลขที่เอกสาร (สถานะ: {case.status.value})"

    # 2. ถ้าถูก REJECTED ไม่ให้ใช้งานต่อ
    case_obj = db.query(Case).filter(Case.id == doc.case_id).first() if doc else None
    if case_obj and case_obj.status == CaseStatus.REJECTED:
        reason = case_obj.reject_reason or "ไม่ระบุเหตุผล"
        return f"รายการ {doc.doc_no} ถูกปฏิเสธแล้ว (เหตุผล: {reason})"

    # 3. สร้าง Signed URL ถ้ามีไฟล์
    file_link = "ไม่มีไฟล์แนบ"
    if doc.pdf_uri:
        try:
            # สมมติว่า pdf_uri เก็บ path เช่น "documents/pv-xxxx.pdf" หรือ "gs://bucket/..."
            object_name = doc.pdf_uri.replace(f"gs://project-prt-bucket/", "") # ปรับตาม GCS logic คุณ
            # เรียกใช้ฟังก์ชันจาก gcs.py
            file_link = generate_download_url(object_name)
        except Exception as e:
            file_link = f"(Error generating link: {str(e)})"

    return json.dumps({
        "doc_no": doc.doc_no,
        "type": doc.doc_type.value,
        "amount": float(doc.amount),
        "status": "Active", # Document มักจะ Active ถ้าไม่ถูก Cancel
        "file_url": file_link
    }, ensure_ascii=False)

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
    transaction_type: str = "EXPENSE"
):
    """
    คำนวณยอดเงิน รายรับ/รายจ่าย (ตัด JV ทิ้ง) พร้อมแจกแจงรายการประกอบ
    """
    
    # 1. สร้าง Base Query (เก็บเงื่อนไขไว้ใช้ซ้ำ)
    #    เราต้อง Join Case และ Category เพื่อดึงรายละเอียดมาแสดง
    base_query = db.query(Document, Case, Category).\
        join(Case, Document.case_id == Case.id).\
        join(Category, Case.category_id == Category.id)
    
    # Filter: Status (เอาเฉพาะที่จ่ายแล้วหรืออนุมัติแล้ว)
    base_query = base_query.filter(Case.status.in_([CaseStatus.APPROVED, CaseStatus.PAID, CaseStatus.CLOSED]))

    # Filter: JV Must Die (ห้ามรวม JV เด็ดขาด)
    base_query = base_query.filter(Document.doc_type != DocumentType.JV)

    # Filter: Transaction Type
    if transaction_type == "EXPENSE":
        base_query = base_query.filter(Document.doc_type == DocumentType.PV)
    elif transaction_type == "REVENUE":
        base_query = base_query.filter(Document.doc_type == DocumentType.RV)
    
    # Filter: Date
    if start_date:
        base_query = base_query.filter(Document.created_at >= datetime.strptime(start_date, "%Y-%m-%d"))
    if end_date:
        base_query = base_query.filter(Document.created_at <= datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59))

    # -------------------------------------------------------
    # 2. Execute Queries
    # -------------------------------------------------------
    
    # A. หาผลรวม (Sum)
    total = base_query.with_entities(func.sum(Document.amount)).scalar() or 0.0

    # B. ดึงรายการประกอบ (Details)
    #    ดึงมาสัก 20 รายการเพื่อไม่ให้ Chat รกเกินไป (ถ้าเกินค่อยบอกว่ามีต่อ)
    items = base_query.with_entities(
        Document.doc_no, 
        Document.amount, 
        Case.purpose, 
        Category.name_th,
        Document.created_at
    ).order_by(desc(Document.created_at)).limit(20).all()

    # -------------------------------------------------------
    # 3. Format Output
    # -------------------------------------------------------
    
    response = f"📊 สรุปยอด {transaction_type} (ไม่รวม JV): {total:,.2f} บาท\n"
    response += "-" * 30 + "\n"
    response += "รายการประกอบ (ล่าสุด):\n"
    
    if not items:
        response += "(ไม่พบรายการในช่วงเวลานี้)"
    else:
        for item in items:
            # Format: - PV-6701-001: 500.00 (ค่าอาหาร...)
            doc_no = item.doc_no
            amt = item.amount
            purpose = item.purpose[:30] + "..." if len(item.purpose) > 30 else item.purpose # ตัดคำถ้ายาวไป
            cat_name = item.name_th
            
            response += f"- {doc_no}: {amt:,.2f} บาท ({cat_name} - {purpose})\n"
    
    return response

def check_workflow_status_tool(db: Session, doc_or_case_no: str):
    """เช็คสถานะล่าสุดและคนที่รับผิดชอบอยู่"""
    # หา Case ID ก่อน
    case = db.query(Case).filter(
        or_(Case.case_no.ilike(f"%{doc_or_case_no}%"), 
            Case.documents.any(Document.doc_no.ilike(f"%{doc_or_case_no}%")))
    ).first()

    if not case:
        return "ไม่พบรายการครับ"

    # หา Audit Log ล่าสุด
    last_log = db.query(AuditLog).filter(
        AuditLog.entity_id == case.id
    ).order_by(desc(AuditLog.performed_at)).first()

    updated_by = last_log.performed_by if last_log else case.updated_by
    last_update = last_log.performed_at.strftime("%d/%m/%Y %H:%M") if last_log else "-"

    if case.status == CaseStatus.REJECTED:
        reason = case.reject_reason or "ไม่ระบุเหตุผล"
        return f"รายการ {case.case_no} ถูกปฏิเสธแล้ว (เหตุผล: {reason})"

    return f"""
    รายการ: {case.case_no}
    สถานะปัจจุบัน: {case.status.value}
    อัปเดตล่าสุดโดย: {updated_by}
    เมื่อ: {last_update}
    (หมายเหตุ: ถ้าสถานะเป็น SUBMITTED แสดงว่ารอหัวหน้าอนุมัติ)
    """

# Skill 4: Policy Expert (Mock)
def get_policy_info_tool(query_topic: str):
    """ค้นหากฎระเบียบ (Mock Data)"""
    # ในอนาคตใช้ Vector Search ตรงนี้
    return f"ข้อมูลกฎระเบียบที่เกี่ยวข้อง:\n{MOCK_POLICY_DATA}"

# Skill 5: Data Insight (เทียบเดือนก่อน)
def get_monthly_comparison_tool(db: Session):
    """เปรียบเทียบยอดจ่ายเดือนนี้ vs เดือนที่แล้ว"""
    today = datetime.now()
    this_month_start = today.replace(day=1, hour=0, minute=0, second=0)
    
    # เดือนที่แล้ว
    last_month_end = this_month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    def get_sum(start, end):
        return db.query(func.sum(Document.amount))\
            .join(Case, Document.case_id == Case.id)\
            .filter(Document.doc_type == DocumentType.PV)\
            .filter(Case.status.in_([CaseStatus.APPROVED, CaseStatus.PAID, CaseStatus.CLOSED]))\
            .filter(Document.created_at.between(start, end))\
            .scalar() or 0.0

    this_month_total = get_sum(this_month_start, today)
    last_month_total = get_sum(last_month_start, last_month_end)

    diff = this_month_total - last_month_total
    percent = (diff / last_month_total * 100) if last_month_total > 0 else 100.0

    return {
        "this_month": this_month_total,
        "last_month": last_month_total,
        "diff_percent": percent,
        "trend": "เพิ่มขึ้น" if diff > 0 else "ลดลง"
    }
