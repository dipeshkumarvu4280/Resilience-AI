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


async def safe_create_indexes_for_collection(col, index_models: list[IndexModel]):
    """
    Safely and idempotently creates or reconciles indexes on a MongoDB collection.
    - If index already exists with matching specifications, create_indexes is a no-op.
    - If an index with the same name or key spec exists with conflicting options (e.g. stale
      partialFilterExpression from earlier code version), catches IndexKeySpecsConflict /
      IndexOptionsConflict, drops ONLY the conflicting stale index, and recreates it with
      the current target specification.
    - Zero document modification or deletion.
    """
    for index_model in index_models:
        idx_name = index_model.document.get("name")
        try:
            await col.create_indexes([index_model])
        except Exception as e:
            err_msg = str(e)
            if (
                "IndexKeySpecsConflict" in err_msg
                or "IndexOptionsConflict" in err_msg
                or "already exists with different options" in err_msg
                or "conflicting" in err_msg.lower()
                or "code 85" in err_msg
                or "code 86" in err_msg
            ):
                logger.warning(
                    f"Index spec conflict detected for index '{idx_name}' on collection '{col.name}': {e}. "
                    f"Reconciling: safely dropping stale index and recreating with current target definition."
                )
                try:
                    existing_info = await col.index_information()
                    # Drop by name if it matches
                    if idx_name and idx_name in existing_info:
                        await col.drop_index(idx_name)
                        logger.info(f"Dropped stale index '{idx_name}' from '{col.name}'.")
                    else:
                        # Drop by key spec match
                        target_key = index_model.document.get("key")
                        target_key_list = list(target_key.items()) if hasattr(target_key, "items") else list(target_key)
                        for existing_name, info in existing_info.items():
                            if existing_name == "_id_":
                                continue
                            if info.get("key") == target_key_list:
                                await col.drop_index(existing_name)
                                logger.info(f"Dropped conflicting index '{existing_name}' from '{col.name}'.")
                    # Recreate with clean target specification
                    await col.create_indexes([index_model])
                    logger.info(f"Successfully reconciled and recreated index '{idx_name}' on '{col.name}'.")
                except Exception as reconcile_err:
                    logger.error(f"Failed to reconcile index '{idx_name}' on '{col.name}': {reconcile_err}")
            else:
                logger.warning(f"Warning creating index '{idx_name}' on '{col.name}': {e}")


async def init_db_indexes():
    if db_manager.db is None:
        return
    try:
        # Phase 0: Authentication & Core Users
        await safe_create_indexes_for_collection(db_manager.db["users"], [
            IndexModel([("phone", ASCENDING)], unique=True, name="idx_users_phone_unique"),
            IndexModel([("email", ASCENDING)], sparse=True, name="idx_users_email"),
            IndexModel([("google_sub", ASCENDING)], sparse=True, name="idx_users_google_sub"),
            IndexModel([("role", ASCENDING)], name="idx_users_role"),
        ])
        
        await safe_create_indexes_for_collection(db_manager.db["otps"], [
            IndexModel([("phone", ASCENDING)], name="idx_otps_phone"),
            IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0, name="idx_otps_ttl"),
        ])

        await safe_create_indexes_for_collection(db_manager.db["auth_audit_logs"], [
            IndexModel([("phone", ASCENDING)], name="idx_audit_phone"),
            IndexModel([("timestamp", ASCENDING)], name="idx_audit_timestamp"),
        ])

        # Phase 1: Citizen Emergency Reporting Indexes
        await safe_create_indexes_for_collection(db_manager.db["citizen_identities"], [
            IndexModel([("phone", ASCENDING)], unique=True, name="idx_citizen_phone_unique"),
            IndexModel([("citizen_id", ASCENDING)], unique=True, name="idx_citizen_id_unique"),
        ])

        await safe_create_indexes_for_collection(db_manager.db["citizen_reports"], [
            IndexModel([("report_id", ASCENDING)], unique=True, name="idx_reports_id_unique"),
            IndexModel([("citizen_phone", ASCENDING)], name="idx_reports_phone"),
            IndexModel([("status", ASCENDING)], name="idx_reports_status"),
            IndexModel([("emergency_type", ASCENDING)], name="idx_reports_type"),
            IndexModel([("created_at", ASCENDING)], name="idx_reports_created_at"),
        ])

        await safe_create_indexes_for_collection(db_manager.db["citizen_otps"], [
            IndexModel([("phone", ASCENDING)], name="idx_citizen_otps_phone"),
            IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0, name="idx_citizen_otps_ttl"),
        ])

        # Phase 3: Emergency Resource Coordination Indexes
        await safe_create_indexes_for_collection(db_manager.db["resources"], [
            IndexModel([("resource_id", ASCENDING)], unique=True, name="idx_resources_id_unique"),
            IndexModel([("resource_type", ASCENDING)], name="idx_resources_type"),
            IndexModel([("status", ASCENDING)], name="idx_resources_status"),
            IndexModel([("location.zone_or_district", ASCENDING)], name="idx_resources_zone"),
            IndexModel([("location.city", ASCENDING)], name="idx_resources_city"),
            IndexModel([("created_at", ASCENDING)], name="idx_resources_created_at"),
        ])

        await safe_create_indexes_for_collection(db_manager.db["needs_assessments"], [
            IndexModel([("report_id", ASCENDING)], unique=True, name="idx_needs_report_unique"),
            IndexModel([("assessed_at", ASCENDING)], name="idx_needs_assessed_at"),
        ])

        await safe_create_indexes_for_collection(db_manager.db["resource_allocations"], [
            IndexModel([("allocation_id", ASCENDING)], unique=True, name="idx_alloc_id_unique"),
            IndexModel([("report_id", ASCENDING)], name="idx_alloc_report_id"),
            IndexModel([("resource_id", ASCENDING)], name="idx_alloc_resource_id"),
            IndexModel([("status", ASCENDING)], name="idx_alloc_status"),
            IndexModel([("created_at", ASCENDING)], name="idx_alloc_created_at"),
        ])

        # Phase 4: Situation Intelligence & Clustering Indexes
        await safe_create_indexes_for_collection(db_manager.db["situations"], [
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
        await safe_create_indexes_for_collection(db_manager.db["coordination_plans"], [
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

        await safe_create_indexes_for_collection(db_manager.db["ai_agent_runs"], [
            IndexModel([("run_id", ASCENDING)], unique=True, name="idx_agent_runs_id_unique"),
            IndexModel([("situation_id", ASCENDING)], name="idx_agent_runs_situation"),
            IndexModel([("agent_name", ASCENDING)], name="idx_agent_runs_name"),
            IndexModel([("state_fingerprint", ASCENDING)], name="idx_agent_runs_fingerprint"),
            IndexModel([("started_at", ASCENDING)], name="idx_agent_runs_started_at"),
        ])

        # Phase 6: Live Monitoring & Change Impact Analysis Indexes
        await safe_create_indexes_for_collection(db_manager.db["monitoring_events"], [
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

        await safe_create_indexes_for_collection(db_manager.db["change_impacts"], [
            IndexModel([("impact_id", ASCENDING)], unique=True, name="idx_change_impacts_id_unique"),
            IndexModel([("event_id", ASCENDING)], name="idx_change_impacts_event"),
            IndexModel([("situation_id", ASCENDING)], name="idx_change_impacts_situation"),
            IndexModel([("coordination_plan_id", ASCENDING)], name="idx_change_impacts_plan"),
            IndexModel([("impact_level", ASCENDING)], name="idx_change_impacts_level"),
            IndexModel([("plan_status", ASCENDING)], name="idx_change_impacts_plan_status"),
            IndexModel([("analyzed_at", ASCENDING)], name="idx_change_impacts_analyzed_at"),
        ])

        # Phase 7: Event-Driven Notification & Preferences Indexes
        await safe_create_indexes_for_collection(db_manager.db["notifications"], [
            IndexModel([("notification_id", ASCENDING)], unique=True, name="idx_notif_id_unique"),
            IndexModel([("fingerprint", ASCENDING)], unique=True, name="idx_notif_fingerprint_unique"),
            IndexModel([("recipients.user_id", ASCENDING)], name="idx_notif_recipient_user"),
            IndexModel([("created_at", ASCENDING)], name="idx_notif_created_at"),
            IndexModel([("severity", ASCENDING)], name="idx_notif_severity"),
            IndexModel([("category", ASCENDING)], name="idx_notif_category"),
        ])

        await safe_create_indexes_for_collection(db_manager.db["notification_preferences"], [
            IndexModel([("user_id", ASCENDING)], unique=True, name="idx_notif_prefs_user_unique"),
            IndexModel([("preference_id", ASCENDING)], unique=True, name="idx_notif_prefs_id_unique"),
        ])

        # Phase 8: Field Operations & Incident Closure Indexes
        await safe_create_indexes_for_collection(db_manager.db["response_tasks"], [
            IndexModel([("task_id", ASCENDING)], unique=True, name="idx_tasks_id_unique"),
            IndexModel([("situation_id", ASCENDING)], name="idx_tasks_situation"),
            IndexModel([("coordination_plan_id", ASCENDING)], name="idx_tasks_plan"),
            IndexModel([("status", ASCENDING)], name="idx_tasks_status"),
            IndexModel([("assigned_unit.unit_id", ASCENDING)], name="idx_tasks_assigned_unit"),
            IndexModel([("created_at", ASCENDING)], name="idx_tasks_created_at"),
        ])

        await safe_create_indexes_for_collection(db_manager.db["field_update_records"], [
            IndexModel([("update_id", ASCENDING)], unique=True, name="idx_field_updates_id_unique"),
            IndexModel([("task_id", ASCENDING)], name="idx_field_updates_task"),
            IndexModel([("reported_at", ASCENDING)], name="idx_field_updates_reported_at"),
        ])

        await safe_create_indexes_for_collection(db_manager.db["timeline_events"], [
            IndexModel([("event_id", ASCENDING)], unique=True, name="idx_timeline_event_id_unique"),
            IndexModel([("situation_id", ASCENDING)], name="idx_timeline_situation"),
            IndexModel([("timestamp", ASCENDING)], name="idx_timeline_timestamp"),
        ])

        logger.info("MongoDB indexes verified successfully.")
    except Exception as e:
        logger.error(f"Error initializing database indexes: {e}")



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
