import requests
import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.security import create_access_token
from app.settings import settings
from app.models import User, UserRole

# Config
BASE_URL = "http://127.0.0.1:8000"
DB_URL = settings.DATABASE_URL
ADMIN_SUB = "admin_google_id_123"
REQ_SUB = "requester_google_id_456"

# Setup DB Connection
engine = create_engine(DB_URL)
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

def setup_users():
    print("🔄 Setting up test users in DB...")
    # Clear existing test users
    try:
        db.execute(text(f"DELETE FROM user_roles WHERE user_id IN (SELECT id FROM users WHERE google_sub IN ('{ADMIN_SUB}', '{REQ_SUB}'))"))
        db.execute(text(f"DELETE FROM users WHERE google_sub IN ('{ADMIN_SUB}', '{REQ_SUB}')"))
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"⚠️ Clean up warning (first run?): {e}")

    # 1. Create Admin User
    admin = User(
        id=uuid.uuid4(),
        google_sub=ADMIN_SUB,
        email="admin@test.com",
        name="Admin Test",
        created_at=datetime.now(timezone.utc)
    )
    db.add(admin)
    db.add(UserRole(id=uuid.uuid4(), user_id=admin.id, role="admin"))

    # 2. Create Requester User (Default)
    requester = User(
        id=uuid.uuid4(),
        google_sub=REQ_SUB,
        email="req@test.com",
        name="Requester Test",
        created_at=datetime.now(timezone.utc)
    )
    db.add(requester)
    db.add(UserRole(id=uuid.uuid4(), user_id=requester.id, role="requester"))
    
    db.commit()
    print("✅ Users Created: Admin & Requester")
    return admin, requester

def run_test():
    admin, requester = setup_users()

    # Generate Tokens
    token_admin = create_access_token(sub=ADMIN_SUB, email="admin@test.com", name="Admin")
    token_req = create_access_token(sub=REQ_SUB, email="req@test.com", name="Requester")

    headers_admin = {"Authorization": f"Bearer {token_admin}"}
    headers_req = {"Authorization": f"Bearer {token_req}"}

    print("\n--- 🧪 Start Testing ---")

    # 1. Check Admin Roles via /me
    print("\n1️⃣  Admin checking GET /api/v1/auth/me")
    r = requests.get(f"{BASE_URL}/api/v1/auth/me", headers=headers_admin)
    print(f"   Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()['data']
        print(f"   Roles: {data['roles']}")
        if "admin" in data['roles']:
            print("   ✅ Pass: Admin has 'admin' role")
        else:
            print("   ❌ Fail: Admin missing role")

    # 2. Check Requester Roles BEFORE update
    print("\n2️⃣  Requester checking GET /api/v1/auth/me (Before Update)")
    r = requests.get(f"{BASE_URL}/api/v1/auth/me", headers=headers_req)
    if r.status_code == 200:
        roles = r.json()['data']['roles']
        print(f"   Current Roles: {roles}")
        if "accountant" not in roles:
            print("   ✅ Pass: Not yet an accountant")
        else:
            print("   ❌ Fail: Already has accountant role?")

    # 3. Requester tries to create Transaction (Should Fail)
    print("\n3️⃣  Requester calling POST /api/v1/transactions (Expect 403)")
    payload = {
        "type": "expense",
        "category": "Travel",
        "amount": 100.0,
        "occurred_at": "2025-02-06",
        "note": "Test transaction"
    }
    r = requests.post(f"{BASE_URL}/api/v1/transactions", json=payload, headers=headers_req)
    print(f"   Status: {r.status_code}")

    # 4. Admin assigns 'accounting' role to Requester
    print("\n4️⃣  Admin assigning 'accounting' role to Requester")
    role_payload = {"roles": ["requester", "accounting"]}
    r = requests.post(f"{BASE_URL}/api/v1/admin/users/{requester.id}/roles", json=role_payload, headers=headers_admin)
    print(f"   Status: {r.status_code}")

    # 5. Check Requester Roles AFTER update (Crucial Step!)
    print("\n5️⃣  Requester checking GET /api/v1/auth/me (After Update)")
    r = requests.get(f"{BASE_URL}/api/v1/auth/me", headers=headers_req)
    if r.status_code == 200:
        roles = r.json()['data']['roles']
        print(f"   New Roles: {roles}")
        if "accounting" in roles:
            print("   ✅ Pass: Role 'accounting' found in DB")
        else:
            print("   ❌ Fail: Role not updated in DB response")

    # 6. Requester (now Accountant) tries Transaction again
    print("\n6️⃣  Requester (now Accountant) calling POST /api/v1/transactions")
    r = requests.post(f"{BASE_URL}/api/v1/transactions", json=payload, headers=headers_req)
    print(f"   Status: {r.status_code} (Expected 201)")
    if r.status_code == 201:
        print(f"   ✅ SUCCESS: Transaction Created ID: {r.json()['data']['transaction_id']}")
    else:
        print(f"   ❌ Failed: {r.text}")

if __name__ == "__main__":
    run_test()