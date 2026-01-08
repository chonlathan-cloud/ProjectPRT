import sys
from sqlalchemy import create_engine, text
from app.settings import settings

# ใช้ Database URL จาก settings (ตรวจสอบให้แน่ใจว่าเป็น DB ที่ถูกต้อง: Dev/Prod)
# ถ้าจะรันบนเครื่อง Local ที่ต่อ Cloud SQL Proxy ให้ override ค่านี้
# DB_URL = "postgresql://prt_app:PASSWORD@127.0.0.1:6543/prt" 
DB_URL = settings.DATABASE_URL

def cleanup_legacy_system():
    print(f"🔥 Starting Legacy Data Cleanup (PS, CR, DB)...")
    print(f"Target Database: {DB_URL}")
    
    confirm = input("Are you sure you want to DELETE data? (type 'yes' to confirm): ")
    if confirm != "yes":
        print("Aborted.")
        return

    engine = create_engine(DB_URL)

    with engine.connect() as conn:
        trans = conn.begin() # เริ่ม Transaction (ถ้าพังจะ Rollback อัตโนมัติ)
        try:
            # ---------------------------------------------------------
            # 1. ลบเอกสารเก่า (Documents)
            # ---------------------------------------------------------
            print("1️⃣  Deleting Legacy Documents (PS, CR, DB)...")
            
            # แปลง Enum เป็น Text เพื่อเช็คค่า (รองรับกรณี Migration ยังไม่รัน หรือรันไปแล้ว)
            delete_docs_sql = text("""
                DELETE FROM documents 
                WHERE doc_type::text IN ('PS', 'CR', 'DB');
            """)
            result_docs = conn.execute(delete_docs_sql)
            print(f"   -> Deleted {result_docs.rowcount} documents.")

            # ---------------------------------------------------------
            # 2. ลบตัวนับเลขเอกสารเก่า (Doc Counters)
            # ---------------------------------------------------------
            print("2️⃣  Deleting Legacy Counters (PS, CR, DB)...")
            
            delete_counters_sql = text("""
                DELETE FROM doc_counters 
                WHERE doc_prefix::text IN ('PS', 'CR', 'DB');
            """)
            result_counters = conn.execute(delete_counters_sql)
            print(f"   -> Deleted {result_counters.rowcount} counters.")

            # ---------------------------------------------------------
            # 3. Reset สถานะ Case (Sanitize Cases)
            # ---------------------------------------------------------
            # เคสที่ค้างอยู่ในสถานะเก่า ต้องถูกตบกลับเป็น DRAFT เพื่อเริ่ม Flow ใหม่แบบ PV/RV
            print("3️⃣  Resetting Legacy Case Statuses to DRAFT...")
            
            # สถานะเก่าที่เราจะล้าง
            legacy_statuses = [
                'PS_APPROVED', 
                'PS_REJECTED', 
                'CR_ISSUED', 
                'DB_ISSUED', 
                'SETTLEMENT_SUBMITTED'
            ]
            
            # สร้าง string สำหรับ query (format: 'STAT1', 'STAT2')
            status_list_str = ", ".join([f"'{s}'" for s in legacy_statuses])
            
            reset_cases_sql = text(f"""
                UPDATE cases 
                SET status = 'DRAFT', 
                    updated_at = NOW(),
                    updated_by = 'system_cleanup'
                WHERE status::text IN ({status_list_str});
            """)
            result_cases = conn.execute(reset_cases_sql)
            print(f"   -> Reset {result_cases.rowcount} cases to DRAFT.")

            # ---------------------------------------------------------
            # 4. (Optional) ลบ Payments ที่เกิดจากระบบเก่า
            # ---------------------------------------------------------
            # ถ้าต้องการลบประวัติการจ่ายเงินเก่าด้วย (เพราะมันผูกกับ CR ที่ลบไปแล้ว)
            print("4️⃣  Cleaning up orphaned Payments...")
            # ลบ Payment ที่ case_id อยู่ในสถานะ DRAFT (ซึ่งเราเพิ่ง reset ไป)
            # หรือจะลบทั้งหมดที่เป็น type เก่าก็ได้ แต่วิธีนี้ปลอดภัยกว่า
            delete_payments_sql = text("""
                DELETE FROM payments 
                WHERE case_id IN (
                    SELECT id FROM cases WHERE status::text = 'DRAFT'
                );
            """)
            result_payments = conn.execute(delete_payments_sql)
            print(f"   -> Deleted {result_payments.rowcount} payments.")

            trans.commit()
            print("✅ CLEANUP SUCCESSFUL! The database is now free of legacy artifacts.")
            
        except Exception as e:
            trans.rollback()
            print(f"❌ Error during cleanup: {e}")
            print("🔄 Rolled back all changes.")

if __name__ == "__main__":
    cleanup_legacy_system()