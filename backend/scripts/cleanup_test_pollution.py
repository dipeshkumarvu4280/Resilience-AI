"""
Targeted surgical cleanup script for resilience_db.
Preserves genuine user-generated emergency complaint RES-ENFC4NT3 (Dipesh Kumar)
and genuine authorized operators while removing only test fixture records.
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

AUTHORIZED_OPERATOR_PHONES = {"9999999001", "9999999002", "9999999003"}
GENUINE_CITIZEN_PHONE = "9801338643"
GENUINE_REPORT_ID = "RES-ENFC4NT3"

async def run_cleanup():
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    
    print(f"Executing targeted cleanup on database: {settings.MONGODB_DB_NAME}")
    
    # 1. Audit before cleanup
    real_report = await db["citizen_reports"].find_one({"report_id": GENUINE_REPORT_ID})
    if not real_report:
        raise ValueError(f"FATAL: Genuine citizen report {GENUINE_REPORT_ID} not found! Aborting cleanup to prevent data loss.")
    
    print(f"CONFIRMED REAL REPORT TO PRESERVE: {real_report['report_id']} | {real_report['citizen_name']} | {real_report['citizen_phone']} | {real_report['emergency_type']}")
    
    # 2. Cleanup citizen_reports (delete test reports only)
    del_reports = await db["citizen_reports"].delete_many({"report_id": {"$ne": GENUINE_REPORT_ID}})
    print(f"  [citizen_reports] Removed {del_reports.deleted_count} test reports. Real report '{GENUINE_REPORT_ID}' preserved.")
    
    # 3. Cleanup citizen_identities (delete test citizens only)
    del_citizens = await db["citizen_identities"].delete_many({"phone": {"$ne": GENUINE_CITIZEN_PHONE}})
    print(f"  [citizen_identities] Removed {del_citizens.deleted_count} test citizen identities. Real citizen '{GENUINE_CITIZEN_PHONE}' preserved.")
    
    # 4. Cleanup citizen_otps
    del_c_otps = await db["citizen_otps"].delete_many({"phone": {"$ne": GENUINE_CITIZEN_PHONE}})
    print(f"  [citizen_otps] Removed {del_c_otps.deleted_count} test citizen OTPs.")
    
    # 5. Cleanup users (delete test fixture users only, keep authorized operators)
    del_users = await db["users"].delete_many({"phone": {"$nin": list(AUTHORIZED_OPERATOR_PHONES)}})
    print(f"  [users] Removed {del_users.deleted_count} test user accounts. Authorized operators preserved.")
    
    # 6. Cleanup test otps
    del_otps = await db["otps"].delete_many({"phone": {"$nin": list(AUTHORIZED_OPERATOR_PHONES)}})
    print(f"  [otps] Removed {del_otps.deleted_count} test operator OTPs.")
    
    # 7. Cleanup test auth audit logs
    del_logs = await db["auth_audit_logs"].delete_many({"phone": {"$nin": list(AUTHORIZED_OPERATOR_PHONES | {GENUINE_CITIZEN_PHONE})}})
    print(f"  [auth_audit_logs] Removed {del_logs.deleted_count} test audit logs.")
    
    # Verification
    final_reports = await db["citizen_reports"].find({}).to_list(length=100)
    final_users = await db["users"].find({}).to_list(length=100)
    final_citizens = await db["citizen_identities"].find({}).to_list(length=100)
    
    print("\n--- POST-CLEANUP AUDIT ---")
    print(f"citizen_reports count: {len(final_reports)}")
    for r in final_reports:
        print(f"  -> Report: {r['report_id']} | Citizen: {r['citizen_name']} | Phone: {r['citizen_phone']} | Type: {r['emergency_type']}")
    
    print(f"\nusers count: {len(final_users)}")
    for u in final_users:
        print(f"  -> User: {u['phone']} | {u['full_name']} | Role: {u['role']}")
        
    print(f"\ncitizen_identities count: {len(final_citizens)}")
    for c in final_citizens:
        print(f"  -> Citizen: {c['citizen_id']} | {c['name']} | Phone: {c['phone']}")
        
    assert len(final_reports) == 1
    assert final_reports[0]["report_id"] == GENUINE_REPORT_ID
    assert len(final_users) == 3
    assert len(final_citizens) == 1
    print("\nSUCCESS: All test data removed. Genuine report and authorized operators 100% verified.")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(run_cleanup())
