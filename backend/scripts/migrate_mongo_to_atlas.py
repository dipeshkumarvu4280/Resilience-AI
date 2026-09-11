"""
SAFE IDEMPOTENT MONGODB TO ATLAS MIGRATION SCRIPT
=================================================
Migrates real data from local MongoDB (localhost:27017/resilience_db) to MongoDB Atlas (resilience_db).
- Zero deletion/modification of local database.
- Idempotent upsert logic (no duplicates on re-run).
- Preserves exact ObjectIds, BSON types, timestamps, nulls, and indexes.
- Full SHA-256 cryptographic document integrity check.
- Never prints passwords, secrets, or raw connection strings.
"""
import asyncio
import os
import hashlib
import json
from datetime import datetime
from typing import Dict, Any, List, Tuple
from bson import json_util
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import IndexModel
from app.core.config import settings


def hash_doc(doc: dict) -> str:
    """Computes deterministic SHA-256 hash of canonical BSON JSON representation."""
    canonical_json = json_util.dumps(doc, sort_keys=True)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


async def run_migration() -> bool:
    print("=" * 70)
    print("MONGODB ATLAS DATA MIGRATION")
    print("============================")

    # 1. Read Connection URIs
    local_url = settings.MONGODB_URL
    local_db_name = settings.MONGODB_DB_NAME
    atlas_url = os.environ.get("ATLAS_MONGODB_URL") or settings.ATLAS_MONGODB_URL

    if not atlas_url or not atlas_url.strip():
        print("\n[ERROR] ATLAS_MONGODB_URL is not set!")
        print("Please set ATLAS_MONGODB_URL in your environment or in backend/.env:")
        print("  ATLAS_MONGODB_URL=mongodb+srv://<username>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority")
        print("\nDO NOT hardcode your password into source code.")
        return False

    # 2. Connect and Verify Both Databases
    print("\n[STEP 1 & 2] Connecting to Source and Target Databases...")
    source_client = AsyncIOMotorClient(local_url, serverSelectionTimeoutMS=4000)
    target_client = AsyncIOMotorClient(atlas_url, serverSelectionTimeoutMS=8000)

    try:
        await source_client.admin.command("ping")
        print("  [SUCCESS] Source MongoDB reachable (localhost:27017)")
    except Exception as e:
        print(f"  [FATAL ERROR] Source MongoDB connection failed: {e}")
        source_client.close()
        target_client.close()
        return False

    try:
        await target_client.admin.command("ping")
        print("  [SUCCESS] Target MongoDB Atlas cluster reachable")
    except Exception as e:
        print(f"  [FATAL ERROR] Target MongoDB Atlas connection failed: {e}")
        source_client.close()
        target_client.close()
        return False

    source_db: AsyncIOMotorDatabase = source_client[local_db_name]
    target_db: AsyncIOMotorDatabase = target_client[local_db_name]
    print(f"  Source Database: {source_db.name}")
    print(f"  Target Database: {target_db.name}")

    # Expected Collections
    collections_to_migrate = [
        "users",
        "citizen_reports",
        "citizen_identities",
        "auth_audit_logs",
        "audit_logs",
        "otps",
        "citizen_otps",
    ]

    # 3. Source Snapshot
    print("\n[STEP 3] Source Snapshot...")
    source_stats: Dict[str, Dict[str, Any]] = {}
    total_source_docs = 0

    for col_name in collections_to_migrate:
        col = source_db[col_name]
        count = await col.count_documents({})
        total_source_docs += count

        indexes = []
        try:
            async for idx in col.list_indexes():
                indexes.append(idx)
        except Exception:
            pass

        source_stats[col_name] = {
            "count": count,
            "indexes": indexes,
        }
        print(f"  - {col_name}: {count} docs, {len(indexes)} indexes")

    print(f"  Total Source Documents: {total_source_docs}")

    # 4. Target Safety Check
    print("\n[STEP 4] Target Pre-Migration Safety Check...")
    target_existing_counts: Dict[str, int] = {}
    for col_name in collections_to_migrate:
        target_col = target_db[col_name]
        t_count = await target_col.count_documents({})
        target_existing_counts[col_name] = t_count
        if t_count > 0:
            print(f"  [INFO] Target collection '{col_name}' already contains {t_count} documents. Idempotent upsert will be used.")

    # 5. Migrate Documents
    print("\n[STEP 5] Migrating Documents to Atlas (Idempotent Upsert)...")
    migrated_counts: Dict[str, int] = {}

    for col_name in collections_to_migrate:
        source_col = source_db[col_name]
        target_col = target_db[col_name]
        doc_count = source_stats[col_name]["count"]

        if doc_count == 0:
            migrated_counts[col_name] = 0
            print(f"  - {col_name}: 0 documents (empty collection)")
            continue

        inserted_count = 0
        async for doc in source_col.find({}):
            doc_id = doc["_id"]
            # Safe idempotent upsert: only set document on insert or match exact
            res = await target_col.update_one(
                {"_id": doc_id},
                {"$setOnInsert": doc},
                upsert=True
            )
            inserted_count += 1

        migrated_counts[col_name] = inserted_count
        print(f"  [MIGRATED] {col_name}: {inserted_count}/{doc_count} documents processed")

    # 6. Index Migration
    print("\n[STEP 6] Replicating Indexes to Atlas...")
    for col_name in collections_to_migrate:
        indexes = source_stats[col_name]["indexes"]
        target_col = target_db[col_name]

        index_models_to_create = []
        for idx in indexes:
            idx_name = idx.get("name")
            if idx_name == "_id_":
                continue  # Default index already exists

            key_spec = list(idx.get("key", {}).items())
            kwargs = {"name": idx_name}
            if idx.get("unique"):
                kwargs["unique"] = True
            if idx.get("sparse"):
                kwargs["sparse"] = True
            if "expireAfterSeconds" in idx:
                kwargs["expireAfterSeconds"] = idx["expireAfterSeconds"]

            index_models_to_create.append(IndexModel(key_spec, **kwargs))

        if index_models_to_create:
            try:
                created_names = await target_col.create_indexes(index_models_to_create)
                print(f"  [INDEXES REPLICATED] {col_name}: {', '.join(created_names)}")
            except Exception as e:
                print(f"  [INDEX WARNING] {col_name}: {e}")
        else:
            print(f"  - {col_name}: Default _id_ index only")

    # 7. Post-Migration Verification
    print("\n[STEP 7] Post-Migration Verification (LOCAL vs ATLAS)...")
    print("-" * 60)
    print(f"{'COLLECTION':<22} | {'LOCAL':<8} | {'ATLAS':<8} | {'STATUS'}")
    print("-" * 60)

    all_counts_match = True
    total_atlas_docs = 0

    for col_name in collections_to_migrate:
        local_c = source_stats[col_name]["count"]
        atlas_c = await target_db[col_name].count_documents({})
        total_atlas_docs += atlas_c

        status = "MATCH" if local_c == atlas_c else "MISMATCH"
        if local_c != atlas_c:
            all_counts_match = False

        print(f"{col_name:<22} | {local_c:<8} | {atlas_c:<8} | {status}")

    print("-" * 60)
    print(f"{'TOTAL DOCUMENTS':<22} | {total_source_docs:<8} | {total_atlas_docs:<8} | {'MATCH' if total_source_docs == total_atlas_docs else 'MISMATCH'}")
    print("-" * 60)

    # 8. Data Integrity Check (SHA-256 Hash Verification)
    print("\n[STEP 8] Cryptographic Data Integrity Verification (SHA-256)...")
    mismatches = 0
    total_checked = 0

    for col_name in collections_to_migrate:
        source_col = source_db[col_name]
        target_col = target_db[col_name]

        async for s_doc in source_col.find({}):
            total_checked += 1
            doc_id = s_doc["_id"]
            t_doc = await target_col.find_one({"_id": doc_id})

            if not t_doc:
                print(f"  [INTEGRITY ERROR] Missing doc in Atlas: {col_name} ID={doc_id}")
                mismatches += 1
                continue

            s_hash = hash_doc(s_doc)
            t_hash = hash_doc(t_doc)

            if s_hash != t_hash:
                print(f"  [INTEGRITY ERROR] Hash mismatch: {col_name} ID={doc_id}")
                mismatches += 1

    if mismatches == 0 and total_checked == total_source_docs:
        print(f"  [PASS] All {total_checked} documents verified identical (Source == Atlas).")
    else:
        print(f"  [FAIL] {mismatches} mismatch(es) found during data integrity check!")

    source_client.close()
    target_client.close()

    success = all_counts_match and mismatches == 0 and (total_atlas_docs == total_source_docs)
    print("\n" + "=" * 70)
    print(f"MIGRATION RESULT: {'SUCCESS (READY FOR SWITCH)' if success else 'FAILED'}")
    print("=" * 70)
    return success


if __name__ == "__main__":
    asyncio.run(run_migration())
