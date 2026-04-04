import uuid
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.core.settings import settings
from app.constants.revenue_income_types import REVENUE_INCOME_TYPES

# --- CONFIGURATION ---
# ถ้า Run บนเครื่อง local และต่อ Cloud SQL Proxy ใช้ localhost
# ถ้าใช้ env file ให้ดึงจาก settings (ต้องแน่ใจว่าค่าถูกต้อง)
DB_URL = settings.DATABASE_URL

def seed_categories_full():
    print(f"🚀 Connecting to database...")
    engine = create_engine(DB_URL)

    # รายการบัญชีปี 2566 (Full List)
    # Format: (name_th, account_code, type)
    categories = [
        # --- หมวด 1: สินทรัพย์ (ASSET) ---
        ("เงินสดในมือ (Cash in hands)", "101011", "ASSET"),
        ("เงินทดรองจ่าย (Petty Cash)", "101012", "ASSET"),
        ("บัญชีเงินฝาก-งบอุดหนุน (017-1-38327-3)", "102011", "ASSET"),
        ("บัญชีเงินฝาก-นอกงบบริจาค (017-0-22753-7)", "102012", "ASSET"),
        ("บัญชีเงินฝาก-นอกงบคงคลัง (ใบเสร็จรับเงิน ร.ร.พระปริยัติ)", "102013", "ASSET"),
        ("ลูกหนี้การค้า", "10300", "ASSET"),
        ("สินทรัพย์อื่นๆ", "10400", "ASSET"),

        # --- หมวด 4: รายได้ (REVENUE) เดิม ---
        ("เงินอุดหนุนโรงเรียนพระปริยัติธรรมฯ", "401011", "REVENUE"),
        ("เงินอุดหนุนโรงเรียนพระปริยัติธรรมฯ ธรรม-บาลี", "401012", "REVENUE"),
        ("อุดหนุนสมทบ โควิด", "401013", "REVENUE"),
        ("แม่กองธรรมสนามหลวง นักธรรมดีเด่น", "401021", "REVENUE"),
        ("รายได้จากการบริจาค", "401022", "REVENUE"),
        ("รายได้อื่น ๆ", "401023", "REVENUE"),
        ("รายได้จากดอกเบี้ย", "401024", "REVENUE"),

        # --- หมวด 5: ค่าใช้จ่าย (EXPENSE) ---
        ("เงินตอบแทนครู", "501014", "EXPENSE"),
        ("พัฒนาฝึกอบรม", "501024", "EXPENSE"),
        ("ภัตตาหาร", "501033", "EXPENSE"),
        ("ค่าพาหนะ", "501043", "EXPENSE"),
        ("อุปกรณ์การเรียน", "501051", "EXPENSE"),
        ("ค่าจ้างเหมา", "501064", "EXPENSE"),
        ("ค่าซ่อมบำรุง", "501071", "EXPENSE"),
        ("ค่าใช้จ่ายพื้นฐาน", "501083", "EXPENSE"),
        ("เงินประกันสังคม", "501094", "EXPENSE"),
        ("ค่าจัดกิจกรรมพัฒนาผู้เรียน", "501102", "EXPENSE"),
        ("ค่าตอบแทนครูพิเศษ", "501114", "EXPENSE"),
        ("ค่าตอบแทนครูบาลี(เสริม)", "501124", "EXPENSE"),
        ("ค่าวัสดุ-ครุภัณฑ์", "501131", "EXPENSE"),
        ("อื่น ๆ งบประมาณ", "501141", "EXPENSE"),
        ("อื่น ๆ วิชาการ", "501152", "EXPENSE"),
        ("อื่น ๆ จัดการทั่วไป", "501163", "EXPENSE"),
        ("ค่าตอบแทนครูและนักเรียนการแข่งขันทักษะ", "501172", "EXPENSE"),
        ("ค่าหนังสือเรียน", "501182", "EXPENSE"),
        ("ค่าตอบแทนสนับสนุนครูบนดอย", "501194", "EXPENSE"),
        ("ค่าธรรมเนียมการโอน", "501203", "EXPENSE"),
        ("เงินสำรองค่าใช้จ่ายล่วงหน้า", "509", "EXPENSE"),
    ]
    categories.extend((name, code, "REVENUE") for code, name in REVENUE_INCOME_TYPES)

    try:
        with engine.connect() as conn:
            print(f"📦 Upserting {len(categories)} categories...")
            
            for name, code, cat_type in categories:
                # ใช้ UPSERT: ถ้ามี Code นี้อยู่แล้ว ให้ Update ชื่อและประเภท (ป้องกัน Error Duplicate)
                sql = text("""
                    INSERT INTO categories (id, name_th, account_code, type, is_active, created_by, created_at)
                    VALUES (:id, :name, :code, :type, TRUE, 'system_seed', NOW())
                    ON CONFLICT (account_code) DO UPDATE 
                    SET name_th = EXCLUDED.name_th, 
                        type = EXCLUDED.type,
                        is_active = TRUE;
                """)
                
                conn.execute(sql, {
                    "id": uuid.uuid4(),
                    "name": name,
                    "code": code,
                    "type": cat_type
                })
                
            conn.commit()
            print("✅ Success! Categories seeded/updated successfully.")
    except OperationalError as exc:
        raise RuntimeError(
            "Database connection failed. ตรวจสอบค่า DATABASE_URL ใน .env และให้แน่ใจว่า PostgreSQL/Cloud SQL Proxy "
            "กำลังรันอยู่ที่ host/port ตาม URL นั้น"
        ) from exc

if __name__ == "__main__":
    seed_categories_full()
