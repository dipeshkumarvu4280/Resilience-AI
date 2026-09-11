import asyncio
import json
from bson import json_util
from app.db.mongodb import get_database, close_mongo_connection

async def main():
    db = get_database()
    
    # 1. Print all plans for SIT-WURURZ4T
    print("=== COORDINATION PLANS FOR SIT-WURURZ4T ===")
    plans = await db.coordination_plans.find({"situation_id": "SIT-WURURZ4T"}).sort("version", 1).to_list(50)
    for p in plans:
        print(f"Plan v{p.get('version')} ({p.get('plan_id')}): status={p.get('status')} | priority={p.get('assessed_priority')}")
        allocs = p.get("recommended_allocations", [])
        print(f"  Allocations ({len(allocs)}):")
        for a in allocs:
            print(f"    - Type: {a.get('resource_type')} | Required: {a.get('quantity_required')} {a.get('unit')} | Matched: {a.get('matched_resource_id')} ({a.get('matched_resource_name')}) | Allocated: {a.get('allocated_quantity')} | Available: {a.get('available_in_inventory')}")
        if p.get("diff_summary"):
            print(f"  Diff Summary: {json.dumps(p.get('diff_summary'), indent=4)}")

    # 2. Print all resources in MongoDB
    print("\n=== ALL RESOURCES IN MONGO DB ===")
    resources = await db.resources.find().to_list(100)
    print(f"Found {len(resources)} resources in MongoDB:")
    for r in resources:
        print(f"ID: {r.get('resource_id')} | Name: {r.get('name')} | Type: {r.get('resource_type')} | Category: {r.get('category')} | QtyAvail: {r.get('quantity_available')} / {r.get('quantity_total')} {r.get('unit')} | Status: {r.get('status')} | Condition: {r.get('condition')}")

    # 3. Print assessed needs for SIT-WURURZ4T
    sit = await db.situations.find_one({"situation_id": "SIT-WURURZ4T"})
    if sit:
        print(f"\n=== SITUATION: {sit.get('situation_id')} ===")
        print(f"Title: {sit.get('title')} | Type: {sit.get('emergency_type')} | Severity: {sit.get('severity_level')}")
        print(f"Report IDs: {sit.get('report_ids')}")
        for r_id in sit.get("report_ids", []):
            rep = await db.citizen_reports.find_one({"report_id": r_id})
            need = await db.needs_assessments.find_one({"report_id": r_id})
            print(f"  Report {r_id}: type={rep.get('emergency_type') if rep else 'N/A'}")
            if need:
                print(f"    Needs: {need.get('need_items')}")

    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(main())
