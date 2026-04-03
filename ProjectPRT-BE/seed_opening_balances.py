import uuid
from datetime import date
from sqlalchemy import create_engine, text
from app.settings import settings

DB_URL = settings.DATABASE_URL

def seed_opening_balances():
    print(f"🚀 Connecting to database for Opening Balances...")
    engine = create_engine(DB_URL)

    # --- ✏️ แก้ไขตัวเลขจริงตรงนี้เมื่อพร้อมครับ ---
    # วันที่ยอดยกมา (เช่น 1 ม.ค. 2566 หรือ วันเริ่มระบบ)
    AS_OF_DATE = date(2023, 1, 1) 
    
    OPENING_BALANCES = [
        # (Account Code, Amount)
        ("101011", 0.00),  # เงินสดในมือ
        ("101012", 0.00),  # เงินทดรองจ่าย
        ("102011", 0.00),  # เงินฝาก-งบอุดหนุน
        ("102012", 0.00),  # เงินฝาก-นอกงบบริจาค
        ("102013", 0.00),  # เงินฝาก-นอกงบคงคลัง
        ("10300", 0.00), # ลูกหนี้การค้า (จากหมายเหตุที่คุณให้มา)
        ("10400", 0.00),   # สินทรัพย์อื่นๆ
    ]

    with engine.connect() as conn:
        print(f"💰 Recording Opening Balances as of {AS_OF_DATE}...")
        
        for code, amount in OPENING_BALANCES:
            # 1. หาชื่อหมวดหมู่เพื่อมาใส่ใน note
            result = conn.execute(text("SELECT name_th FROM categories WHERE account_code = :code"), {"code": code})
            cat_name = result.scalar()
            
            if not cat_name:
                print(f"⚠️ Warning: Account code {code} not found in categories. Skipping.")
                continue

            # 2. สร้าง Transaction ประเภท 'opening_balance'
            # เราใช้ table transactions_v1 (หรือ table ที่เก็บการเคลื่อนไหว)
            # ในที่นี้สมมติว่าเป็น transactions_v1 ถ้าโครงสร้างเปลี่ยนให้แก้ตรงนี้
            sql = text("""
                INSERT INTO transactions_v1 (id, type, category, amount, occurred_at, note, created_by, created_at)
                VALUES (:id, 'opening_balance', :category, :amount, :occurred_at, :note, 'system_seed', NOW())
            """)
            
            conn.execute(sql, {
                "id": uuid.uuid4(),
                "category": cat_name, # เก็บชื่อ category (Flat) ตาม design ปัจจุบัน
                "amount": amount,
                "occurred_at": AS_OF_DATE,
                "note": f"ยอดยกมาปี 2566 - {code}"
            })
            
        conn.commit()
        print("✅ Success! Opening balances recorded.")

if __name__ == "__main__":
    seed_opening_balances()