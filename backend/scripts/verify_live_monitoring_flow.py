import asyncio
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from app.models.enums import MonitoringEventType, EventSourceType
from app.services.monitoring.monitoring_service import MonitoringService

async def main():
    db_name = getattr(settings, 'MONGODB_DB_NAME', None) or getattr(settings, 'DATABASE_NAME', None) or getattr(settings, 'MONGODB_DATABASE', 'resilience_ai')
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[db_name]

    print("--- 1. PRE-CHECK ATLAS DATABASE COUNTS ---")
    pre_events = await db["monitoring_events"].count_documents({})
    pre_impacts = await db["change_impacts"].count_documents({})
    print(f"Pre-check: monitoring_events={pre_events}, change_impacts={pre_impacts}")

    print("\n--- 2. EXECUTE AUTHENTIC OPERATIONAL MUTATION ---")
    # Record real operational change: Resource stock adjustment on actual existing resource RES-AST-M96X37CP
    res = await db["resources"].find_one({"resource_id": "RES-AST-M96X37CP"})
    if not res:
        print("Resource RES-AST-M96X37CP not found!")
        client.close()
        return

    prev_qty = float(res.get("quantity_available", 70.0))
    new_qty = 65.0 if prev_qty != 65.0 else 70.0
    
    # Update resource in DB
    await db["resources"].update_one(
        {"resource_id": "RES-AST-M96X37CP"},
        {"$set": {"quantity_available": new_qty, "updated_at": datetime.now(timezone.utc)}}
    )

    # Invoke MonitoringService.record_change_event
    actor = {"id": "OFF-VERIFY", "full_name": "Emergency Officer Duty Desk", "role": "RESOURCE_MANAGER"}
    event = await MonitoringService.record_change_event(
        event_type=MonitoringEventType.RESOURCE_QUANTITY_CHANGED,
        source_type=EventSourceType.RESOURCE_INVENTORY,
        source_id="RES-AST-M96X37CP",
        previous_state={
            "name": res.get("name"),
            "resource_type": res.get("resource_type"),
            "quantity_available": prev_qty,
            "quantity_total": res.get("quantity_total"),
            "status": res.get("status"),
        },
        new_state={
            "name": res.get("name"),
            "resource_type": res.get("resource_type"),
            "quantity_available": new_qty,
            "quantity_total": res.get("quantity_total"),
            "status": "PARTIALLY_AVAILABLE" if new_qty < float(res.get("quantity_total", 100.0)) else "AVAILABLE",
        },
        actor=actor,
        db=db,
    )

    print(f"Generated Event: ID={event.event_id if event else None}, Type={event.event_type if event else None}, Status={event.status if event else None}")

    print("\n--- 3. VERIFY MONGO ATLAS PERSISTENCE ---")
    post_events = await db["monitoring_events"].count_documents({})
    post_impacts = await db["change_impacts"].count_documents({})
    print(f"Post-check: monitoring_events={post_events}, change_impacts={post_impacts}")

    event_doc = await db["monitoring_events"].find_one({"source_id": "RES-AST-M96X37CP"}, sort=[("detected_at", -1)])
    if event_doc:
        print("Authoritative Event in Atlas:")
        print(f"  Event ID: {event_doc.get('event_id')}")
        print(f"  Type: {event_doc.get('event_type')}")
        print(f"  Source Type: {event_doc.get('source_type')}")
        print(f"  Source ID: {event_doc.get('source_id')}")
        print(f"  Changed Fields: {event_doc.get('changed_fields')}")
        print(f"  Impact Level: {event_doc.get('impact_level')}")
        print(f"  Is Simulation: {event_doc.get('is_simulation')}")

    print("\n--- 4. QUERY LIVE MONITORING STATS & EVENTS ENDPOINTS VIA SERVICE ---")
    stats = await MonitoringService.get_monitoring_stats(db=db)
    print("Telemetry Stats Summary:")
    print(f"  Total Events: {stats.total_events}")
    print(f"  Active Alerts: {stats.active_alerts}")
    print(f"  Critical Impacts: {stats.critical_impacts}")
    print(f"  High Impacts: {stats.high_impacts}")
    print(f"  Domain Breakdown: {stats.domain_breakdown}")

    events_res = await MonitoringService.get_monitoring_events(page=1, limit=10, db=db)
    print(f"\nLive Events List: Total Count = {events_res.total_count}")
    for item in events_res.items:
        print(f"  - [{item.event_id}] {item.event_type} on {item.source_type}:{item.source_id} (Impact: {item.impact_level})")

    # Restore resource back to original quantity
    await db["resources"].update_one(
        {"resource_id": "RES-AST-M96X37CP"},
        {"$set": {"quantity_available": prev_qty, "updated_at": datetime.now(timezone.utc)}}
    )
    print(f"\nReversible restoration completed. Restored quantity_available={prev_qty}")

    client.close()

if __name__ == "__main__":
    asyncio.run(main())
