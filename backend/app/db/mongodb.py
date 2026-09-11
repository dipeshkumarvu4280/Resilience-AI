import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, IndexModel
from app.core.config import settings

logger = logging.getLogger("resilience.db")


class DatabaseManager:
    client: Optional[AsyncIOMotorClient] = None
    db: Optional[AsyncIOMotorDatabase] = None


db_manager = DatabaseManager()


async def connect_to_mongo():
    logger.info(f"Connecting to MongoDB at {settings.MONGODB_URL}...")
    try:
        db_manager.client = AsyncIOMotorClient(
            settings.MONGODB_URL,
            serverSelectionTimeoutMS=3000,
            maxPoolSize=20,
            minPoolSize=5
        )
        db_manager.db = db_manager.client[settings.MONGODB_DB_NAME]
        
        # Ping the server
        await db_manager.client.admin.command('ping')
        logger.info("Connected to MongoDB successfully.")
        
        # Initialize indexes
        await init_db_indexes()
    except Exception as e:
        logger.warning(f"MongoDB connection warning: {e}. Note: In-memory fallback will be active if needed.")


async def close_mongo_connection():
    logger.info("Closing MongoDB connection...")
    if db_manager.client:
        db_manager.client.close()
        logger.info("MongoDB connection closed.")


async def init_db_indexes():
    if db_manager.db is None:
        return
    try:
        users_col = db_manager.db["users"]
        await users_col.create_indexes([
            IndexModel([("phone", ASCENDING)], unique=True, name="idx_users_phone_unique"),
            IndexModel([("email", ASCENDING)], sparse=True, name="idx_users_email"),
            IndexModel([("google_sub", ASCENDING)], sparse=True, name="idx_users_google_sub"),
            IndexModel([("role", ASCENDING)], name="idx_users_role"),
        ])
        
        otps_col = db_manager.db["otps"]
        await otps_col.create_indexes([
            IndexModel([("phone", ASCENDING)], name="idx_otps_phone"),
            IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0, name="idx_otps_ttl"),
        ])

        audit_col = db_manager.db["auth_audit_logs"]
        await audit_col.create_indexes([
            IndexModel([("phone", ASCENDING)], name="idx_audit_phone"),
            IndexModel([("timestamp", ASCENDING)], name="idx_audit_timestamp"),
        ])

        # Phase 1: Citizen Emergency Reporting Indexes
        citizen_identities_col = db_manager.db["citizen_identities"]
        await citizen_identities_col.create_indexes([
            IndexModel([("phone", ASCENDING)], unique=True, name="idx_citizen_phone_unique"),
            IndexModel([("citizen_id", ASCENDING)], unique=True, name="idx_citizen_id_unique"),
        ])

        citizen_reports_col = db_manager.db["citizen_reports"]
        await citizen_reports_col.create_indexes([
            IndexModel([("report_id", ASCENDING)], unique=True, name="idx_reports_id_unique"),
            IndexModel([("citizen_phone", ASCENDING)], name="idx_reports_phone"),
            IndexModel([("status", ASCENDING)], name="idx_reports_status"),
            IndexModel([("emergency_type", ASCENDING)], name="idx_reports_type"),
            IndexModel([("created_at", ASCENDING)], name="idx_reports_created_at"),
        ])

        citizen_otps_col = db_manager.db["citizen_otps"]
        await citizen_otps_col.create_indexes([
            IndexModel([("phone", ASCENDING)], name="idx_citizen_otps_phone"),
            IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0, name="idx_citizen_otps_ttl"),
        ])

        # Phase 3: Emergency Resource Coordination Indexes
        resources_col = db_manager.db["resources"]
        await resources_col.create_indexes([
            IndexModel([("resource_id", ASCENDING)], unique=True, name="idx_resources_id_unique"),
            IndexModel([("resource_type", ASCENDING)], name="idx_resources_type"),
            IndexModel([("status", ASCENDING)], name="idx_resources_status"),
            IndexModel([("location.zone_or_district", ASCENDING)], name="idx_resources_zone"),
            IndexModel([("location.city", ASCENDING)], name="idx_resources_city"),
            IndexModel([("created_at", ASCENDING)], name="idx_resources_created_at"),
        ])

        needs_col = db_manager.db["needs_assessments"]
        await needs_col.create_indexes([
            IndexModel([("report_id", ASCENDING)], unique=True, name="idx_needs_report_unique"),
            IndexModel([("assessed_at", ASCENDING)], name="idx_needs_assessed_at"),
        ])

        alloc_col = db_manager.db["resource_allocations"]
        await alloc_col.create_indexes([
            IndexModel([("allocation_id", ASCENDING)], unique=True, name="idx_alloc_id_unique"),
            IndexModel([("report_id", ASCENDING)], name="idx_alloc_report_id"),
            IndexModel([("resource_id", ASCENDING)], name="idx_alloc_resource_id"),
            IndexModel([("status", ASCENDING)], name="idx_alloc_status"),
            IndexModel([("created_at", ASCENDING)], name="idx_alloc_created_at"),
        ])

        # Phase 4: Situation Intelligence & Clustering Indexes
        situations_col = db_manager.db["situations"]
        await situations_col.create_indexes([
            IndexModel([("situation_id", ASCENDING)], unique=True, name="idx_situations_id_unique"),
            IndexModel([("cluster_id", ASCENDING)], name="idx_situations_cluster_id"),
            IndexModel([("primary_report_id", ASCENDING)], name="idx_situations_primary_report"),
            IndexModel([("report_ids", ASCENDING)], name="idx_situations_report_ids"),
            IndexModel([("emergency_type", ASCENDING)], name="idx_situations_emergency_type"),
            IndexModel([("severity_level", ASCENDING)], name="idx_situations_severity_level"),
            IndexModel([("status", ASCENDING)], name="idx_situations_status"),
            IndexModel([("created_at", ASCENDING)], name="idx_situations_created_at"),
            IndexModel([("updated_at", ASCENDING)], name="idx_situations_updated_at"),
        ])

        # Phase 5: Multi-Agent Coordination & Central Orchestrator Indexes
        coord_col = db_manager.db["coordination_plans"]
        await coord_col.create_indexes([
            IndexModel([("plan_id", ASCENDING)], unique=True, name="idx_coordination_plans_id_unique"),
            IndexModel([("situation_id", ASCENDING)], name="idx_coordination_plans_situation"),
            IndexModel([("status", ASCENDING)], name="idx_coordination_plans_status"),
            IndexModel([("generated_at", ASCENDING)], name="idx_coordination_plans_generated_at"),
            IndexModel(
                [("situation_id", ASCENDING), ("state_fingerprint", ASCENDING)],
                unique=True,
                partialFilterExpression={"status": "PENDING_OFFICER_REVIEW", "state_fingerprint": {"$type": "string"}},
                name="idx_coordination_plans_pending_fingerprint",
            ),
        ])

        agent_runs_col = db_manager.db["ai_agent_runs"]
        await agent_runs_col.create_indexes([
            IndexModel([("run_id", ASCENDING)], unique=True, name="idx_agent_runs_id_unique"),
            IndexModel([("situation_id", ASCENDING)], name="idx_agent_runs_situation"),
            IndexModel([("agent_name", ASCENDING)], name="idx_agent_runs_name"),
            IndexModel([("state_fingerprint", ASCENDING)], name="idx_agent_runs_fingerprint"),
            IndexModel([("started_at", ASCENDING)], name="idx_agent_runs_started_at"),
        ])

        # Phase 6: Live Monitoring & Change Impact Analysis Indexes
        monitoring_events_col = db_manager.db["monitoring_events"]
        await monitoring_events_col.create_indexes([
            IndexModel([("event_id", ASCENDING)], unique=True, name="idx_monitoring_events_id_unique"),
            IndexModel([("event_fingerprint", ASCENDING)], name="idx_monitoring_events_fingerprint"),
            IndexModel([("situation_id", ASCENDING)], name="idx_monitoring_events_situation"),
            IndexModel([("coordination_plan_id", ASCENDING)], name="idx_monitoring_events_plan"),
            IndexModel([("event_type", ASCENDING)], name="idx_monitoring_events_type"),
            IndexModel([("source_type", ASCENDING)], name="idx_monitoring_events_source"),
            IndexModel([("impact_level", ASCENDING)], name="idx_monitoring_events_impact"),
            IndexModel([("status", ASCENDING)], name="idx_monitoring_events_status"),
            IndexModel([("detected_at", ASCENDING)], name="idx_monitoring_events_detected_at"),
        ])

        change_impacts_col = db_manager.db["change_impacts"]
        await change_impacts_col.create_indexes([
            IndexModel([("impact_id", ASCENDING)], unique=True, name="idx_change_impacts_id_unique"),
            IndexModel([("event_id", ASCENDING)], name="idx_change_impacts_event"),
            IndexModel([("situation_id", ASCENDING)], name="idx_change_impacts_situation"),
            IndexModel([("coordination_plan_id", ASCENDING)], name="idx_change_impacts_plan"),
            IndexModel([("impact_level", ASCENDING)], name="idx_change_impacts_level"),
            IndexModel([("plan_status", ASCENDING)], name="idx_change_impacts_plan_status"),
            IndexModel([("analyzed_at", ASCENDING)], name="idx_change_impacts_analyzed_at"),
        ])

        # Phase 7: Event-Driven Notification & Preferences Indexes
        notifications_col = db_manager.db["notifications"]
        await notifications_col.create_indexes([
            IndexModel([("notification_id", ASCENDING)], unique=True, name="idx_notif_id_unique"),
            IndexModel([("fingerprint", ASCENDING)], unique=True, name="idx_notif_fingerprint_unique"),
            IndexModel([("recipients.user_id", ASCENDING)], name="idx_notif_recipient_user"),
            IndexModel([("created_at", ASCENDING)], name="idx_notif_created_at"),
            IndexModel([("severity", ASCENDING)], name="idx_notif_severity"),
            IndexModel([("category", ASCENDING)], name="idx_notif_category"),
        ])

        notif_prefs_col = db_manager.db["notification_preferences"]
        await notif_prefs_col.create_indexes([
            IndexModel([("user_id", ASCENDING)], unique=True, name="idx_notif_prefs_user_unique"),
            IndexModel([("preference_id", ASCENDING)], unique=True, name="idx_notif_prefs_id_unique"),
        ])

        logger.info("MongoDB indexes verified successfully.")
    except Exception as e:
        logger.error(f"Error creating database indexes: {e}")



def get_database() -> AsyncIOMotorDatabase:
    import asyncio
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if db_manager.client is not None and current_loop is not None:
        try:
            client_loop = db_manager.client.get_io_loop()
            if client_loop is not current_loop:
                db_manager.client = AsyncIOMotorClient(
                    settings.MONGODB_URL,
                    serverSelectionTimeoutMS=3000,
                    maxPoolSize=20,
                    minPoolSize=5,
                )
                db_manager.db = db_manager.client[settings.MONGODB_DB_NAME]
        except Exception:
            pass

    if db_manager.db is None:
        # Emergency reconnection if needed
        client = AsyncIOMotorClient(
            settings.MONGODB_URL,
            serverSelectionTimeoutMS=3000,
            maxPoolSize=20,
            minPoolSize=5,
        )
        db_manager.client = client
        db_manager.db = client[settings.MONGODB_DB_NAME]
    return db_manager.db
