import asyncio
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

async def cleanup_synthetic_timeline():
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]

    print("=" * 60)
    print("RESILIENCE AUDIT TIMELINE NARROW SYNTHETIC CLEANUP")
    print(f"Target Database: {settings.MONGODB_DB_NAME}")
    print("=" * 60)

    # 1. Fetch user 9999999002
    officer = await db["users"].find_one({"phone": "9999999002"})
    if not officer:
        print("[ERROR] Officer 9999999002 not found in users collection!")
        client.close()
        return

    officer_id = str(officer["_id"])
    officer_name = officer.get("full_name", "Dipesh Kumar")
    print(f"[FOUND] Officer Account: ID={officer_id}, Name='{officer_name}', Phone={officer['phone']}")

    # 2. Identify duplicate and synthetic events in citizen_reports
    reports_cursor = db["citizen_reports"].find({"timeline.actor_id": officer_id})
    reports = await reports_cursor.to_list(length=100)
    print(f"[FOUND] {len(reports)} report(s) containing events by officer {officer_id}")

    duplicate_event_ids = ["EVT-TLLY6BW4", "EVT-8R5FTRPQ"]

    for r in reports:
        report_id = r["report_id"]
        old_timeline = r.get("timeline", [])
        new_timeline = []
        modified_events = 0
        removed_events = 0

        for ev in old_timeline:
            ev_id = ev.get("event_id")
            if ev_id in duplicate_event_ids:
                removed_events += 1
                print(f"  [REMOVING DUPLICATE] Report {report_id}: EventID={ev_id} ({ev.get('event_type')}) at {ev.get('timestamp')}")
                continue

            # Update synthetic bootstrap name to real officer name
            if ev.get("actor_id") == officer_id and (ev.get("actor_name") == "Officer Marcus Vance" or "Marcus Vance" in ev.get("details", "")):
                ev["actor_name"] = officer_name
                ev["details"] = ev.get("details", "").replace("Officer Marcus Vance", officer_name).replace("Marcus Vance", officer_name)
                modified_events += 1
                print(f"  [UPDATING PROVEN SYNTHETIC ACTOR] EventID={ev_id}: set actor_name='{officer_name}'")

            new_timeline.append(ev)

        # Update report document
        update_doc = {"timeline": new_timeline}
        if r.get("acknowledged_by") == "Officer Marcus Vance":
            update_doc["acknowledged_by"] = officer_name
            print(f"  [UPDATING ACKNOWLEDGED_BY] Report {report_id}: set acknowledged_by='{officer_name}'")

        await db["citizen_reports"].update_one(
            {"report_id": report_id},
            {"$set": update_doc}
        )
        print(f"[UPDATED REPORT] {report_id}: removed {removed_events} duplicate(s), updated {modified_events} event(s).")

    # 3. Clean audit_logs collection
    # Remove ONLY the exact proven duplicate IDs
    del_res = await db["audit_logs"].delete_many({"event_id": {"$in": duplicate_event_ids}})
    print(f"[AUDIT_LOGS] Deleted {del_res.deleted_count} duplicate records ({duplicate_event_ids})")

    # Update proven synthetic actor names in audit_logs
    audit_cursor = db["audit_logs"].find({"actor_id": officer_id, "actor_name": "Officer Marcus Vance"})
    async for a in audit_cursor:
        cleaned_details = a.get("details", "").replace("Officer Marcus Vance", officer_name).replace("Marcus Vance", officer_name)
        await db["audit_logs"].update_one(
            {"_id": a["_id"]},
            {
                "$set": {
                    "actor_name": officer_name,
                    "details": cleaned_details,
                }
            }
        )
        print(f"  [UPDATED AUDIT LOG] EventID={a.get('event_id')}: set actor_name='{officer_name}'")

    print("\nCleanup completed successfully without dropping any database or deleting real data.")
    client.close()

if __name__ == "__main__":
    asyncio.run(cleanup_synthetic_timeline())
