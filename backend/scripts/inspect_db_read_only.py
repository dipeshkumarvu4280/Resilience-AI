import asyncio
import json
from datetime import datetime
from bson import json_util
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

async def inspect():
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    
    print("=" * 60)
    print(f"DATABASE: {settings.MONGODB_DB_NAME} at {settings.MONGODB_URL}")
    collections = await db.list_collection_names()
    print("COLLECTIONS:", collections)
    print("=" * 60)
    
    # 1. Inspect USERS
    print("\n--- USERS COLLECTION ---")
    users_cursor = db["users"].find({})
    users = await users_cursor.to_list(length=100)
    print(f"Total users: {len(users)}")
    for u in users:
        print(f"  User ID: {u.get('_id')} | Phone: {u.get('phone')} | Name: {u.get('full_name')} | Role: {u.get('role')} | Badge: {u.get('badge_number')} | Email: {u.get('email')} | Created: {u.get('created_at')} (type: {type(u.get('created_at')).__name__})")

    # 2. Inspect CITIZEN REPORTS
    print("\n--- CITIZEN REPORTS COLLECTION ---")
    reports_cursor = db["citizen_reports"].find({})
    reports = await reports_cursor.to_list(length=100)
    print(f"Total reports: {len(reports)}")
    for r in reports:
        print(f"\nReport ID: {r.get('report_id')} | Emergency: {r.get('emergency_type')} | Status: {r.get('status')} | Priority: {r.get('priority')}")
        print(f"  Citizen: {r.get('citizen_name')} ({r.get('citizen_phone')})")
        print(f"  Created At: {r.get('created_at')} (type: {type(r.get('created_at')).__name__}) | Updated At: {r.get('updated_at')}")
        print(f"  Acknowledged By: {r.get('acknowledged_by')} | Acknowledged At: {r.get('acknowledged_at')}")
        
        print(f"  Notes ({len(r.get('notes', []))}):")
        for n in r.get("notes", []):
            print(f"    - NoteID: {n.get('note_id')} | Author: {n.get('author_name')} ({n.get('author_id')}) | Role: {n.get('author_role')} | Created: {n.get('created_at')} (type: {type(n.get('created_at')).__name__}) | Note: {n.get('note')}")
        
        print(f"  Timeline ({len(r.get('timeline', []))}):")
        for idx, t in enumerate(r.get("timeline", [])):
            ts = t.get('timestamp')
            print(f"    [{idx}] EventID: {t.get('event_id')} | Type: {t.get('event_type')} | Actor: '{t.get('actor_name')}' (ID: {t.get('actor_id')}, Role: {t.get('actor_role')}) | Details: {t.get('details')} | Timestamp: {ts} (type: {type(ts).__name__})")

    # 3. Inspect AUDIT LOGS
    print("\n--- AUDIT LOGS COLLECTION ---")
    if "audit_logs" in collections:
        audit_cursor = db["audit_logs"].find({})
        audits = await audit_cursor.to_list(length=100)
        print(f"Total audit logs: {len(audits)}")
        for a in audits:
            print(f"  Audit ID: {a.get('_id')} | EventID: {a.get('event_id')} | Report: {a.get('report_id')} | Action: {a.get('action')} | Actor: '{a.get('actor_name')}' (ID: {a.get('actor_id')}, Role: {a.get('actor_role')}) | Details: {a.get('details')} | Timestamp: {a.get('timestamp')} (type: {type(a.get('timestamp')).__name__})")
    else:
        print("audit_logs collection does not exist.")

    # 4. Search for any other occurrences of Marcus, Vance, EOC-408, Dipesh across all collections
    print("\n--- TEXT MATCH SEARCH ACROSS ALL COLLECTIONS ---")
    for coll_name in collections:
        coll = db[coll_name]
        for term in ["Marcus", "Vance", "EOC-408", "EOC-WATCH", "Dipesh"]:
            count = await coll.count_documents({
                "$or": [
                    {"full_name": {"$regex": term, "$options": "i"}},
                    {"actor_name": {"$regex": term, "$options": "i"}},
                    {"badge_number": {"$regex": term, "$options": "i"}},
                    {"details": {"$regex": term, "$options": "i"}},
                    {"timeline.actor_name": {"$regex": term, "$options": "i"}},
                    {"timeline.details": {"$regex": term, "$options": "i"}},
                    {"notes.author_name": {"$regex": term, "$options": "i"}},
                ]
            })
            if count > 0:
                print(f"  Collection '{coll_name}' has {count} documents matching '{term}'")

    client.close()

if __name__ == "__main__":
    asyncio.run(inspect())
