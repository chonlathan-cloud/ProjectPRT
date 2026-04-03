import uuid
from sqlalchemy import create_engine, text

# ⚠️ แก้รหัสผ่าน DB ตรงนี้ให้ถูกต้อง
DB_PASSWORD = "Pao_122546"  # <--- แก้รหัสผ่านให้ตรงกับของคุณ

# URL เชื่อมต่อไปยัง Cloud SQL Proxy
DB_URL = f"postgresql://prt_app:{DB_PASSWORD}@127.0.0.1:6543/prt"

def seed_user():
    try:
        engine = create_engine(DB_URL)
        with engine.connect() as conn:
            print("🚀 Connecting to Cloud Database...")

            # 1. สร้าง Admin User (ถ้ายังไม่มี)
            user_id = "104514501856260067222" # ID ที่คุณใช้ใน Token (admin_google_id_123)
            # หรือถ้าคุณใช้ 'admin_google_id_123' ใน token ให้แก้ตรงนี้ให้ตรงกัน
            # เช็คจาก token เก่า: "sub": "admin_google_id_123"
            # ผมแนะนำให้ใช้ ID นี้ให้ตรงกับ Token ที่เรา Generate กัน:
            sub_id = "admin_google_id_123" 

            print(f"Adding user: {sub_id}...")

            # Insert User
            conn.execute(text(f"""
                INSERT INTO users (id, google_sub, email, name, created_at)
                VALUES ('{uuid.uuid4()}', '{sub_id}', 'admin@test.com', 'Admin', NOW())
                ON CONFLICT (google_sub) DO NOTHING;
            """))

            # ดึง ID จริงออกมา
            result = conn.execute(text(f"SELECT id FROM users WHERE google_sub = '{sub_id}'"))
            real_user_id = result.scalar()

            # 2. ยัดเยียดบทบาท Admin ให้ (Insert Role)
            print(f"Assigning ADMIN role to user ID: {real_user_id}")
            conn.execute(text(f"""
                INSERT INTO user_roles (id, user_id, role, created_at)
                VALUES ('{uuid.uuid4()}', '{real_user_id}', 'admin', NOW())
                ON CONFLICT DO NOTHING;
            """))

            # แถม role อื่นๆ ให้ด้วยเพื่อความชัวร์ในการเทส
            for role in ['accounting', 'finance', 'viewer']:
                conn.execute(text(f"""
                    INSERT INTO user_roles (id, user_id, role, created_at)
                    VALUES ('{uuid.uuid4()}', '{real_user_id}', '{role}', NOW())
                    ON CONFLICT DO NOTHING;
                """))

            conn.commit()
            print("✅ SUCCESS! Admin user created on Cloud SQL.")

    except Exception as e:
        print(f"❌ Error: {e}")
        print("Tip: เช็ครหัสผ่าน DB และแน่ใจว่าเปิด cloud-sql-proxy อยู่")

if __name__ == "__main__":
    seed_user()