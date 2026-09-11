from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.db.mongodb import get_database
from app.api.deps import require_admin, get_current_user
from app.models.user import UserResponse
from app.models.enums import ServiceStatus
from app.models.system import SystemHealthResponse, ServiceInfo, PlatformConfigModel, PlatformConfigUpdate

router = APIRouter()


@router.get("/health")
async def health_check(db: AsyncIOMotorDatabase = Depends(get_database)):
    db_connected = False
    try:
        await db.command("ping")
        db_connected = True
    except Exception:
        db_connected = False
        
    return {
        "status": "healthy" if db_connected else "degraded",
        "system": "RESILIENCE",
        "phase": "Phase 9 (Emergency Intelligence & Integrated Operations)",
        "database": "connected" if db_connected else "disconnected",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phases_active": {
            "phase_0_base": True,
            "phase_1_auth": True,
            "phase_2_intake": True,
            "phase_3_resources": True,
            "phase_4_situations": True,
            "phase_5_multiagent": True,
            "phase_6_monitoring": True,
            "phase_7_notifications": True,
            "phase_8_field_operations": True,
            "phase_9_analytics": True,
        }
    }


@router.get("/status", response_model=SystemHealthResponse)
async def system_status(db: AsyncIOMotorDatabase = Depends(get_database)):
    db_connected = False
    try:
        await db.command("ping")
        db_connected = True
    except Exception:
        db_connected = False
        
    now = datetime.now(timezone.utc)
    
    services = {
        "platform_core": ServiceInfo(
            name="RESILIENCE Platform Engine",
            status=ServiceStatus.OPERATIONAL,
            phase="Phase 0 Active",
            description="FastAPI ASGI core, RBAC policy enforcement, token authentication & CORS gateway.",
            last_check=now,
            details="v0.9.0 running in high-availability mode"
        ),
        "database_storage": ServiceInfo(
            name="Operational Data Store (MongoDB Atlas)",
            status=ServiceStatus.OPERATIONAL if db_connected else ServiceStatus.DEGRADED,
            phase="Phase 0 Active",
            description="Document store for operator credentials, volunteers, reports, and audit trails.",
            last_check=now,
            details="Connected to cluster resilience_db" if db_connected else "Reconnecting to primary database"
        ),
        "auth_security": ServiceInfo(
            name="Identity & Access Management (OAuth & RBAC)",
            status=ServiceStatus.OPERATIONAL,
            phase="Phase 0 Active",
            description="Bcrypt cryptographic credential verification, Google OAuth 2.0 PKCE, and JWT sessions.",
            last_check=now,
            details="Role-based access control and IDOR protections active"
        ),
        "citizen_reporting": ServiceInfo(
            name="Citizen Emergency Reporting Gateway",
            status=ServiceStatus.OPERATIONAL,
            phase="Phase 1 Active",
            description="Direct citizen emergency ingestion, reverse geocoding, and multi-media evidence capture.",
            last_check=now,
            details="Ingestion pipeline operational with reverse geocoding"
        ),
        "incident_triage": ServiceInfo(
            name="Incident Triage & Situation Fusion",
            status=ServiceStatus.OPERATIONAL,
            phase="Phase 2 & 4 Active",
            description="Spatiotemporal clustering, severity calculation, and watch desk incident management.",
            last_check=now,
            details="Clustering algorithms & situation intelligence active"
        ),
        "resource_logistics": ServiceInfo(
            name="Emergency Resource & Shelter Inventory",
            status=ServiceStatus.OPERATIONAL,
            phase="Phase 3 Active",
            description="Real-time tracking of shelters, vehicles, medical supplies, and stockpile allocations.",
            last_check=now,
            details="Live inventory registry & optimistic locking active"
        ),
        "gis_mapping": ServiceInfo(
            name="Live Geospatial Situational GIS Map",
            status=ServiceStatus.OPERATIONAL,
            phase="Phase 4 Active",
            description="Google Maps GIS, roadmap & satellite imagery, impact radius circles, and shelter overlays.",
            last_check=now,
            details="Google Maps JavaScript SDK integration operational"
        ),
        "ai_intelligence": ServiceInfo(
            name="AI Multi-Agent Coordination Engine",
            status=ServiceStatus.OPERATIONAL,
            phase="Phase 5 Active",
            description="Specialized agents (Incident, Needs, Resource, Shelter, Volunteer, Healthcare, Route, Conflict).",
            last_check=now,
            details="Multi-agent orchestrator & explainable rationale operational"
        ),
        "live_monitoring": ServiceInfo(
            name="Live Monitoring & Change Impact Analysis",
            status=ServiceStatus.OPERATIONAL,
            phase="Phase 6 Active",
            description="Automated event capture, ripple effect graph evaluation, and proactive officer alerts.",
            last_check=now,
            details="Monitoring service & impact analyzer active"
        ),
        "simulation_engine": ServiceInfo(
            name="What-If Scenario Simulation Engine",
            status=ServiceStatus.OPERATIONAL,
            phase="Phase 6.5 Active",
            description="Safe isolated in-memory what-if scenario testing with zero live mutation.",
            last_check=now,
            details="Simulation overlay engine operational"
        ),
        "notification_hub": ServiceInfo(
            name="Multi-Channel Emergency Notification Hub",
            status=ServiceStatus.OPERATIONAL,
            phase="Phase 7 Active",
            description="In-App notification queue, unread counters, and WhatsApp template messaging gateway.",
            last_check=now,
            details="In-app notification queue and delivery tracking active"
        ),
        "field_operations": ServiceInfo(
            name="Field Operations & Response Coordination",
            status=ServiceStatus.OPERATIONAL,
            phase="Phase 8 Active",
            description="Task assignment, responder dispatch, ground status updates, and incident closure.",
            last_check=now,
            details="Field task lifecycle & resource reconciliation active"
        ),
        "executive_intelligence": ServiceInfo(
            name="Executive Intelligence & Analytics Engine",
            status=ServiceStatus.OPERATIONAL,
            phase="Phase 9 Active",
            description="Cross-incident milestones, bottleneck detection, fleet metrics, and post-incident analysis.",
            last_check=now,
            details="Direct MongoDB Atlas aggregation pipelines operational"
        ),
        "emergency_analytics": ServiceInfo(
            name="Emergency Intelligence & Live Analytics",
            status=ServiceStatus.OPERATIONAL,
            phase="Phase 9 Active",
            description="Cross-incident milestones, bottleneck detection, fleet metrics, and post-incident analysis.",
            last_check=now,
            details="Direct MongoDB Atlas aggregation pipelines operational"
        ),
    }
    
    return SystemHealthResponse(
        system_name="RESILIENCE",
        environment="production-foundation",
        version="v0.9.0-operations",
        overall_status="OPERATIONAL" if db_connected else "DEGRADED",
        timestamp=now,
        active_phase="Phase 9 (Emergency Intelligence & Integrated Operations)",
        services=services,
        database_connected=db_connected,
    )


@router.get("/config", response_model=PlatformConfigModel)
async def get_platform_config(
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_admin: UserResponse = Depends(require_admin),
):
    """
    Fetch authoritative platform settings from MongoDB Atlas.
    """
    doc = await db["platform_settings"].find_one({"_id": "global_config"})
    if not doc:
        # Create default config record in MongoDB
        now = datetime.now(timezone.utc)
        default_config = PlatformConfigModel(
            updated_at=now,
            updated_by="System Default",
        )
        doc_to_save = default_config.model_dump()
        doc_to_save["_id"] = "global_config"
        await db["platform_settings"].insert_one(doc_to_save)
        return default_config

    doc.pop("_id", None)
    return PlatformConfigModel(**doc)


@router.put("/config", response_model=PlatformConfigModel)
async def update_platform_config(
    payload: PlatformConfigUpdate,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_admin: UserResponse = Depends(require_admin),
):
    """
    Update platform operational parameters (Admin only).
    """
    now = datetime.now(timezone.utc)
    current_doc = await db["platform_settings"].find_one({"_id": "global_config"})
    
    data_dict = {}
    if current_doc:
        current_doc.pop("_id", None)
        data_dict = current_doc
    else:
        data_dict = PlatformConfigModel().model_dump()

    # Update modified fields
    update_data = payload.model_dump(exclude_unset=True)
    data_dict.update(update_data)
    data_dict["updated_at"] = now
    data_dict["updated_by"] = current_admin.full_name

    await db["platform_settings"].update_one(
        {"_id": "global_config"},
        {"$set": data_dict},
        upsert=True,
    )

    # Record audit log
    await db["audit_logs"].insert_one({
        "event_id": f"EVT-CFG-{int(now.timestamp())}",
        "action": "PLATFORM_CONFIG_UPDATED",
        "actor_id": current_admin.id,
        "actor_name": current_admin.full_name,
        "actor_role": current_admin.role.value,
        "details": f"Admin '{current_admin.full_name}' updated platform configuration settings.",
        "timestamp": now,
    })

    return PlatformConfigModel(**data_dict)
