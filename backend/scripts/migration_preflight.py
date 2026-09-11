"""
SAFE READ-ONLY MONGODB MIGRATION PREFLIGHT SCRIPT
Reuses the project's existing configuration and Motor/PyMongo async drivers.
DOES NOT WRITE, MODIFY, DROP, OR MIGRATE ANY DATA.
NO SECRETS OR PASSWORDS EXPOSED.
"""
import asyncio
from typing import Dict, Any, List
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings


async def run_preflight() -> Dict[str, Any]:
    # 1. Verify project config
    db_name = settings.MONGODB_DB_NAME
    raw_url = settings.MONGODB_URL
    
    # Safe display string for connection (sanitize credentials if present)
    safe_host = "local MongoDB (localhost:27017)" if "localhost" in raw_url or "127.0.0.1" in raw_url else "configured host"

    # 2. Connect using project driver
    client = AsyncIOMotorClient(raw_url, serverSelectionTimeoutMS=4000)
    db = client[db_name]

    # 3. Connectivity check (read-only ping)
    ping_ok = False
    try:
        ping_res = await client.admin.command("ping")
        ping_ok = bool(ping_res.get("ok"))
    except Exception as e:
        print(f"[PREFLIGHT ERROR] Database unreachable: {e}")
        return {"readiness": "FAIL", "reason": f"Connection failed: {e}"}

    # 4. List collections
    collections: List[str] = sorted(await db.list_collection_names())
    
    collection_stats = {}
    total_docs = 0

    for col_name in collections:
        col = db[col_name]
        count = await col.count_documents({})
        total_docs += count

        # Inspect indexes safely
        indexes = []
        try:
            cursor = col.list_indexes()
            async for idx in cursor:
                idx_info = {
                    "name": idx.get("name"),
                    "keys": list(idx.get("key", {}).items()),
                    "unique": idx.get("unique", False),
                    "sparse": idx.get("sparse", False),
                    "expireAfterSeconds": idx.get("expireAfterSeconds"),
                }
                indexes.append(idx_info)
        except Exception:
            pass

        collection_stats[col_name] = {
            "count": count,
            "indexes": indexes,
        }

    client.close()

    # 5. Format preflight output
    print("\nLOCAL MONGODB PREFLIGHT")
    print("=======================")
    print(f"\nDatabase: {db_name}")
    print(f"Connection: {safe_host}\n")
    print("Collections:")

    for col_name in collections:
        stats = collection_stats[col_name]
        print(f"  {col_name}: {stats['count']} document(s)")
        if stats["indexes"]:
            idx_names = [i["name"] for i in stats["indexes"]]
            print(f"    - Indexes ({len(stats['indexes'])}): {', '.join(idx_names)}")

    print(f"\nTotal documents: {total_docs}")

    # Determine readiness
    is_ready = ping_ok and db_name == "resilience_db" and len(collections) > 0
    readiness_str = "PASS" if is_ready else "FAIL"

    print("\nMigration readiness:")
    print(readiness_str)

    return {
        "database": db_name,
        "connection": safe_host,
        "collections": collection_stats,
        "total_documents": total_docs,
        "readiness": readiness_str,
    }


if __name__ == "__main__":
    asyncio.run(run_preflight())
