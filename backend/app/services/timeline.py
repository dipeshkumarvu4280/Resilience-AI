import secrets
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.models.enums import ReportStatus, TimelineEventType, UserRole
from app.models.officer import TimelineEvent


def generate_event_id() -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    suffix = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"EVT-{suffix}"


# Valid state transitions according to Phase 2 operational rules:
# RECEIVED -> ACKNOWLEDGED
# ACKNOWLEDGED -> UNDER_ASSESSMENT
# UNDER_ASSESSMENT -> ACTION_REQUIRED
# ACTION_REQUIRED -> RESOLVED
ALLOWED_STATUS_TRANSITIONS: Dict[ReportStatus, List[ReportStatus]] = {
    ReportStatus.RECEIVED: [ReportStatus.ACKNOWLEDGED, ReportStatus.REJECTED],
    ReportStatus.ACKNOWLEDGED: [ReportStatus.UNDER_ASSESSMENT, ReportStatus.RECEIVED, ReportStatus.REJECTED],
    ReportStatus.UNDER_ASSESSMENT: [ReportStatus.ACTION_REQUIRED, ReportStatus.ACKNOWLEDGED, ReportStatus.REJECTED],
    ReportStatus.ACTION_REQUIRED: [ReportStatus.RESOLVED, ReportStatus.UNDER_ASSESSMENT, ReportStatus.REJECTED],
    ReportStatus.RESOLVED: [ReportStatus.UNDER_ASSESSMENT, ReportStatus.ACTION_REQUIRED],
    ReportStatus.REJECTED: [],
    # Aliases
    ReportStatus.VERIFIED: [ReportStatus.ACKNOWLEDGED, ReportStatus.UNDER_ASSESSMENT, ReportStatus.REJECTED],
    ReportStatus.IN_PROGRESS: [ReportStatus.ACTION_REQUIRED, ReportStatus.RESOLVED, ReportStatus.REJECTED],
    ReportStatus.SUBMITTED: [ReportStatus.ACKNOWLEDGED, ReportStatus.REJECTED],
    ReportStatus.PENDING: [ReportStatus.ACKNOWLEDGED, ReportStatus.REJECTED],
}


def validate_status_transition(current_status: ReportStatus, target_status: ReportStatus) -> bool:
    if current_status == target_status:
        return True
    allowed = ALLOWED_STATUS_TRANSITIONS.get(current_status, [])
    return target_status in allowed


async def record_timeline_event(
    db: AsyncIOMotorDatabase,
    report_id: str,
    event_type: TimelineEventType,
    details: str,
    actor_id: Optional[str] = None,
    actor_name: Optional[str] = None,
    actor_role: Optional[UserRole] = None,
    previous_value: Optional[str] = None,
    new_value: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> TimelineEvent:
    event_id = generate_event_id()
    now = datetime.now(timezone.utc)

    event_doc: Dict[str, Any] = {
        "event_id": event_id,
        "event_type": event_type.value,
        "actor_id": actor_id,
        "actor_name": actor_name,
        "actor_role": actor_role.value if actor_role else None,
        "details": details,
        "previous_value": previous_value,
        "new_value": new_value,
        "timestamp": now,
    }
    if metadata:
        event_doc["metadata"] = metadata

    # Append to report document's timeline array
    await db["citizen_reports"].update_one(
        {"report_id": report_id},
        {
            "$push": {"timeline": event_doc},
            "$set": {"updated_at": now},
        }
    )

    # Also record in centralized audit_logs and timeline_events collection for traceability
    audit_doc = {
        "event_id": event_id,
        "report_id": report_id,
        "entity_id": report_id,
        "entity_type": "CITIZEN_REPORT",
        "action": event_type.value,
        "actor_id": actor_id,
        "actor_name": actor_name,
        "actor_role": actor_role.value if actor_role else None,
        "details": details,
        "previous_value": previous_value,
        "new_value": new_value,
        "metadata": metadata or {},
        "timestamp": now,
    }
    await db["audit_logs"].insert_one(audit_doc)
    await db["timeline_events"].insert_one({
        "event_id": event_id,
        "report_id": report_id,
        "event_type": event_type.value,
        "actor_id": actor_id,
        "actor_name": actor_name,
        "actor_role": actor_role.value if actor_role else None,
        "details": details,
        "metadata": metadata or {},
        "timestamp": now,
    })

    return TimelineEvent(
        event_id=event_id,
        event_type=event_type,
        actor_id=actor_id,
        actor_name=actor_name,
        actor_role=actor_role.value if actor_role else None,
        details=details,
        previous_value=previous_value,
        new_value=new_value,
        timestamp=now,
    )
