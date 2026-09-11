import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from pymongo.database import Database
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.enums import (
    SensorType,
    SensorStatus,
    SensorReadingSource,
    SensorAlertStatus,
    SeverityLevel,
    MonitoringEventType,
    EventSourceType,
    EventStatus,
    ImpactLevel,
    TimelineEventType,
    UserRole,
    SensorReportingState,
    SensorHealthState,
)
from app.models.sensor import (
    generate_sensor_id,
    generate_reading_id,
    generate_sensor_alert_id,
    SensorCreate,
    SensorUpdate,
    SensorLocation,
    SensorCoverage,
    SensorReadingCreate,
    SensorReading,
    SensorAlert,
    SensorResponse,
    PaginatedSensorsResponse,
    SensorStatsResponse,
    PaginatedReadingsResponse,
    PaginatedAlertsResponse,
    SensorHealthDetail,
    SensorHealthSummary,
    SensorHealthResponse,
)
from app.models.monitoring import MonitoringEvent
from app.services.timeline import record_timeline_event
from app.services.monitoring.monitoring_service import MonitoringService
from app.services.resource_matching import haversine_distance_km

logger = logging.getLogger("resilience.sensor_service")


class SensorService:
    """
    Core Sensor Management, Threshold Evaluation Engine, and Operational Integration Service.
    Enforces strict zero-dummy-data policy and state-aware threshold transition detection.
    """

    async def create_sensor(
        self,
        db: AsyncIOMotorDatabase,
        sensor_in: SensorCreate,
        actor: Dict[str, Any],
    ) -> SensorResponse:
        """
        Creates a new Sensor in DRAFT state. Zero readings or alerts are created automatically.
        """
        now = datetime.now(timezone.utc)
        sensor_id = generate_sensor_id()

        loc_dict = sensor_in.location.model_dump() if sensor_in.location else {
            "latitude": sensor_in.latitude,
            "longitude": sensor_in.longitude,
            "address": sensor_in.location_name,
        }
        cov_dict = sensor_in.coverage.model_dump() if sensor_in.coverage else {
            "radius_meters": 2000.0,
            "display_value": 2.0,
            "display_unit": "km",
        }

        sensor_doc: Dict[str, Any] = {
            "sensor_id": sensor_id,
            "name": sensor_in.name.strip(),
            "sensor_type": sensor_in.sensor_type.value,
            "status": SensorStatus.DRAFT.value,
            "location_name": sensor_in.location_name.strip(),
            "latitude": sensor_in.latitude,
            "longitude": sensor_in.longitude,
            "location": loc_dict,
            "coverage": cov_dict,
            "unit": sensor_in.unit or "units",
            "threshold": float(sensor_in.threshold),
            "linked_situation_id": sensor_in.linked_situation_id,
            "description": sensor_in.description,
            "current_reading": None,
            "previous_reading": None,
            "last_updated": None,
            "in_alert": False,
            "current_alert_id": None,
            "active_stream_session_id": None,
            "created_by": actor.get("id"),
            "created_by_name": actor.get("full_name"),
            "created_at": now,
            "updated_at": now,
        }

        await db["sensors"].insert_one(sensor_doc)
        logger.info(f"Sensor {sensor_id} ({sensor_in.name}) created in DRAFT state by {actor.get('full_name')}.")

        return self._format_sensor_response(sensor_doc)

    async def update_sensor(
        self,
        db: AsyncIOMotorDatabase,
        sensor_id: str,
        sensor_in: SensorUpdate,
        actor: Dict[str, Any],
    ) -> SensorResponse:
        """
        Updates an existing sensor configuration including GPS coordinates and coverage radius.
        Audits all changes with strict zero dummy data validation.
        """
        clean_id = sensor_id.strip().upper()
        sensor = await db["sensors"].find_one({"sensor_id": clean_id})
        if not sensor:
            raise ValueError(f"Sensor {clean_id} not found.")

        now = datetime.now(timezone.utc)
        update_fields: Dict[str, Any] = {"updated_at": now}

        if sensor_in.name is not None:
            update_fields["name"] = sensor_in.name.strip()
        if sensor_in.sensor_type is not None:
            update_fields["sensor_type"] = sensor_in.sensor_type.value
        if sensor_in.unit is not None:
            update_fields["unit"] = sensor_in.unit.strip()
        if sensor_in.threshold is not None:
            update_fields["threshold"] = float(sensor_in.threshold)
        if sensor_in.linked_situation_id is not None:
            update_fields["linked_situation_id"] = sensor_in.linked_situation_id.strip().upper() if sensor_in.linked_situation_id.strip() else None
        if sensor_in.description is not None:
            update_fields["description"] = sensor_in.description.strip()

        # Location coordinates and structured metadata
        existing_loc = sensor.get("location") or {}
        new_lat = sensor_in.latitude if sensor_in.latitude is not None else sensor.get("latitude")
        new_lon = sensor_in.longitude if sensor_in.longitude is not None else sensor.get("longitude")
        new_loc_name = sensor_in.location_name if sensor_in.location_name is not None else sensor.get("location_name")

        if sensor_in.location is not None:
            loc_dict = sensor_in.location.model_dump()
            update_fields["location"] = loc_dict
            update_fields["latitude"] = sensor_in.location.latitude
            update_fields["longitude"] = sensor_in.location.longitude
            if sensor_in.location.address:
                update_fields["location_name"] = sensor_in.location.address
        elif sensor_in.latitude is not None or sensor_in.longitude is not None or sensor_in.location_name is not None:
            loc_dict = {
                **existing_loc,
                "latitude": new_lat,
                "longitude": new_lon,
                "address": new_loc_name,
            }
            update_fields["location"] = loc_dict
            update_fields["latitude"] = new_lat
            update_fields["longitude"] = new_lon
            if sensor_in.location_name is not None:
                update_fields["location_name"] = new_loc_name

        # Coverage radius and unit configuration
        if sensor_in.coverage is not None:
            update_fields["coverage"] = sensor_in.coverage.model_dump()
        elif sensor_in.coverage_radius_value is not None:
            unit_str = sensor_in.coverage_radius_unit or "km"
            mult = 1000.0 if "km" in unit_str.lower() else 1.0
            r_m = sensor_in.coverage_radius_value * mult
            update_fields["coverage"] = {
                "radius_meters": r_m,
                "display_value": sensor_in.coverage_radius_value,
                "display_unit": "km" if mult == 1000.0 else "m",
            }

        await db["sensors"].update_one(
            {"sensor_id": clean_id},
            {"$set": update_fields}
        )

        updated_doc = await db["sensors"].find_one({"sensor_id": clean_id})
        logger.info(f"Sensor {clean_id} updated by {actor.get('full_name')}. Fields: {list(update_fields.keys())}")
        return self._format_sensor_response(updated_doc)

    async def get_sensor(
        self,
        db: AsyncIOMotorDatabase,
        sensor_id: str,
    ) -> Optional[SensorResponse]:
        """
        Retrieves a sensor document by ID.
        """
        clean_id = sensor_id.strip().upper()
        doc = await db["sensors"].find_one({"sensor_id": clean_id})
        if not doc:
            return None
        return self._format_sensor_response(doc)

    async def list_sensors(
        self,
        db: AsyncIOMotorDatabase,
        sensor_type: Optional[str] = None,
        status: Optional[str] = None,
        in_alert: Optional[bool] = None,
        linked_situation_id: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> PaginatedSensorsResponse:
        """
        Lists sensors with optional filtering and pagination.
        """
        query: Dict[str, Any] = {}
        if sensor_type and sensor_type.upper() != "ALL":
            query["sensor_type"] = sensor_type.upper()
        if status and status.upper() != "ALL":
            query["status"] = status.upper()
        if in_alert is not None:
            query["in_alert"] = in_alert
        if linked_situation_id:
            query["linked_situation_id"] = linked_situation_id.strip().upper()
        if search and search.strip():
            s = search.strip()
            query["$or"] = [
                {"name": {"$regex": s, "$options": "i"}},
                {"location_name": {"$regex": s, "$options": "i"}},
                {"sensor_id": {"$regex": s, "$options": "i"}},
            ]

        total = await db["sensors"].count_documents(query)
        total_pages = max(1, (total + limit - 1) // limit)
        skip = (page - 1) * limit

        cursor = db["sensors"].find(query).sort([("created_at", -1)]).skip(skip).limit(limit)
        docs = await cursor.to_list(length=limit)

        items = [self._format_sensor_response(d) for d in docs]
        return PaginatedSensorsResponse(
            items=items,
            total=total,
            page=page,
            limit=limit,
            total_pages=total_pages,
        )

    async def get_sensor_stats(
        self,
        db: AsyncIOMotorDatabase,
    ) -> SensorStatsResponse:
        """
        Dynamically calculates sensor statistics from actual persisted runtime records.
        Zero hardcoded counts.
        """
        total = await db["sensors"].count_documents({})
        active = await db["sensors"].count_documents({"status": SensorStatus.ACTIVE.value})
        paused = await db["sensors"].count_documents({"status": SensorStatus.PAUSED.value})
        inactive = await db["sensors"].count_documents({"status": SensorStatus.INACTIVE.value})
        draft = await db["sensors"].count_documents({"status": SensorStatus.DRAFT.value})
        in_alert = await db["sensors"].count_documents({"in_alert": True})

        # Calculate readings recorded today
        now = datetime.now(timezone.utc)
        today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        readings_today = await db["sensor_readings"].count_documents({
            "timestamp": {"$gte": today_start}
        })

        # Sensor type distribution
        pipeline = [
            {"$group": {"_id": "$sensor_type", "count": {"$sum": 1}}}
        ]
        type_aggs = await db["sensors"].aggregate(pipeline).to_list(length=20)
        type_counts = {item["_id"]: item["count"] for item in type_aggs if item.get("_id")}

        return SensorStatsResponse(
            total_sensors=total,
            active_sensors=active,
            paused_sensors=paused,
            inactive_sensors=inactive,
            draft_sensors=draft,
            sensors_in_alert=in_alert,
            total_readings_today=readings_today,
            type_counts=type_counts,
        )

    # --- Sensor Lifecycle State Transitions ---

    async def activate_sensor(
        self,
        db: AsyncIOMotorDatabase,
        sensor_id: str,
        actor: Dict[str, Any],
    ) -> SensorResponse:
        """
        Transitions sensor state from DRAFT or PAUSED to ACTIVE.
        """
        clean_id = sensor_id.strip().upper()
        sensor = await db["sensors"].find_one({"sensor_id": clean_id})
        if not sensor:
            raise ValueError(f"Sensor {clean_id} not found.")

        current_status = sensor.get("status")
        if current_status == SensorStatus.ACTIVE.value:
            return self._format_sensor_response(sensor)

        if current_status not in [SensorStatus.DRAFT.value, SensorStatus.PAUSED.value]:
            raise ValueError(f"Cannot activate sensor in {current_status} state. Only DRAFT or PAUSED sensors can be activated.")

        now = datetime.now(timezone.utc)
        await db["sensors"].update_one(
            {"sensor_id": clean_id},
            {"$set": {"status": SensorStatus.ACTIVE.value, "updated_at": now}}
        )
        sensor["status"] = SensorStatus.ACTIVE.value
        sensor["updated_at"] = now

        logger.info(f"Sensor {clean_id} activated by {actor.get('full_name')}.")
        return self._format_sensor_response(sensor)

    async def pause_sensor(
        self,
        db: AsyncIOMotorDatabase,
        sensor_id: str,
        actor: Dict[str, Any],
    ) -> SensorResponse:
        """
        Transitions sensor state from ACTIVE to PAUSED. Halts active streaming if running.
        """
        clean_id = sensor_id.strip().upper()
        sensor = await db["sensors"].find_one({"sensor_id": clean_id})
        if not sensor:
            raise ValueError(f"Sensor {clean_id} not found.")

        current_status = sensor.get("status")
        if current_status == SensorStatus.PAUSED.value:
            return self._format_sensor_response(sensor)

        if current_status != SensorStatus.ACTIVE.value:
            raise ValueError(f"Cannot pause sensor in {current_status} state. Only ACTIVE sensors can be paused.")

        now = datetime.now(timezone.utc)
        await db["sensors"].update_one(
            {"sensor_id": clean_id},
            {"$set": {
                "status": SensorStatus.PAUSED.value,
                "active_stream_session_id": None,
                "updated_at": now,
            }}
        )
        sensor["status"] = SensorStatus.PAUSED.value
        sensor["active_stream_session_id"] = None
        sensor["updated_at"] = now

        logger.info(f"Sensor {clean_id} paused by {actor.get('full_name')}.")
        return self._format_sensor_response(sensor)

    async def resume_sensor(
        self,
        db: AsyncIOMotorDatabase,
        sensor_id: str,
        actor: Dict[str, Any],
    ) -> SensorResponse:
        """
        Transitions sensor state from PAUSED to ACTIVE.
        """
        return await self.activate_sensor(db, sensor_id, actor)

    async def deactivate_sensor(
        self,
        db: AsyncIOMotorDatabase,
        sensor_id: str,
        actor: Dict[str, Any],
    ) -> SensorResponse:
        """
        Transitions sensor state to INACTIVE. Halts active streaming if running.
        """
        clean_id = sensor_id.strip().upper()
        sensor = await db["sensors"].find_one({"sensor_id": clean_id})
        if not sensor:
            raise ValueError(f"Sensor {clean_id} not found.")

        now = datetime.now(timezone.utc)
        await db["sensors"].update_one(
            {"sensor_id": clean_id},
            {"$set": {
                "status": SensorStatus.INACTIVE.value,
                "active_stream_session_id": None,
                "updated_at": now,
            }}
        )
        sensor["status"] = SensorStatus.INACTIVE.value
        sensor["active_stream_session_id"] = None
        sensor["updated_at"] = now

        logger.info(f"Sensor {clean_id} deactivated by {actor.get('full_name')}.")
        return self._format_sensor_response(sensor)

    # --- Live Reading Ingestion & Threshold Evaluation Engine ---

    async def record_reading(
        self,
        db: AsyncIOMotorDatabase,
        sensor_id: str,
        reading_in: SensorReadingCreate,
        actor: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Ingests a live sensor reading, verifies sensor is ACTIVE, persists reading to DB,
        evaluates against threshold, executes state-aware transition detection, and links to Situation Intelligence.
        """
        clean_id = sensor_id.strip().upper()
        sensor = await db["sensors"].find_one({"sensor_id": clean_id})
        if not sensor:
            raise ValueError(f"Sensor {clean_id} not found.")

        # Validate sensor is ACTIVE
        current_status = sensor.get("status")
        if current_status != SensorStatus.ACTIVE.value:
            raise ValueError(
                f"Sensor '{sensor.get('name')}' is currently in {current_status} state. "
                f"Only ACTIVE sensors can submit live readings."
            )

        now = datetime.now(timezone.utc)
        value = float(reading_in.value)
        threshold = float(sensor.get("threshold", 0.0))
        unit = sensor.get("unit", "units")
        prev_reading = sensor.get("current_reading")

        is_breach = value > threshold
        reading_id = generate_reading_id()

        # Construct and persist reading record
        reading = SensorReading(
            reading_id=reading_id,
            sensor_id=clean_id,
            value=value,
            unit=unit,
            previous_value=float(prev_reading) if prev_reading is not None else None,
            timestamp=now,
            source_type=reading_in.source_type,
            simulation=True,
            threshold=threshold,
            is_breach=is_breach,
            created_by=actor.get("id") if actor else None,
            created_by_name=actor.get("full_name") if actor else "Automated Sensor Stream",
            notes=reading_in.notes,
        )

        reading_dict = reading.model_dump()
        reading_dict["timestamp"] = reading_dict["timestamp"].isoformat()
        await db["sensor_readings"].insert_one(reading_dict)

        # Update sensor's latest reading snapshot
        await db["sensors"].update_one(
            {"sensor_id": clean_id},
            {"$set": {
                "current_reading": value,
                "previous_reading": float(prev_reading) if prev_reading is not None else None,
                "last_updated": now,
                "updated_at": now,
            }}
        )

        # -------------------------------------------------------------
        # THRESHOLD ENGINE: State-Aware Transition Detection
        # -------------------------------------------------------------
        was_in_alert = bool(sensor.get("in_alert", False))
        transition_type = "NORMAL"
        alert_result: Optional[SensorAlert] = None
        monitoring_event_result = None

        if is_breach and not was_in_alert:
            # Transition: NORMAL -> THRESHOLD_BREACHED
            transition_type = "THRESHOLD_BREACHED"
            alert_id = generate_sensor_alert_id()
            event_id = f"EVT-SNS-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{clean_id[-4:]}"

            # Calculate severity based on breach magnitude
            severity = SeverityLevel.HIGH
            if value >= threshold * 1.3:
                severity = SeverityLevel.CRITICAL

            # Resolve situation link (explicit or spatial proximity)
            situation_id = await self._resolve_situation_link(db, sensor)

            alert_msg = (
                f"CRITICAL SENSOR BREACH: {sensor.get('name')} ({sensor.get('sensor_type')}) "
                f"reading of {value} {unit} exceeds threshold of {threshold} {unit} at {sensor.get('location_name')}."
            )

            alert_result = SensorAlert(
                alert_id=alert_id,
                event_id=event_id,
                sensor_id=clean_id,
                sensor_name=sensor.get("name"),
                sensor_type=SensorType(sensor.get("sensor_type")),
                reading_id=reading_id,
                severity=severity,
                threshold=threshold,
                current_value=value,
                previous_value=float(prev_reading) if prev_reading is not None else None,
                unit=unit,
                location_name=sensor.get("location_name"),
                latitude=float(sensor.get("latitude")),
                longitude=float(sensor.get("longitude")),
                coverage_radius_meters=float(sensor.get("coverage", {}).get("radius_meters", 2000.0)),
                situation_id=situation_id,
                status=SensorAlertStatus.ACTIVE_BREACH,
                message=alert_msg,
                created_at=now,
            )

            alert_dict = alert_result.model_dump()
            alert_dict["created_at"] = alert_dict["created_at"].isoformat()
            await db["sensor_alerts"].insert_one(alert_dict)

            # Update sensor alert state
            await db["sensors"].update_one(
                {"sensor_id": clean_id},
                {"$set": {
                    "in_alert": True,
                    "current_alert_id": alert_id,
                    "linked_situation_id": situation_id,
                }}
            )

            cov_radius_m = float(sensor.get("coverage", {}).get("radius_meters", 2000.0))

            # Publish unified MonitoringEvent
            monitoring_event_result = await MonitoringService.record_change_event(
                event_type=MonitoringEventType.SENSOR_THRESHOLD_BREACHED,
                source_type=EventSourceType.SIMULATED_SENSOR,
                source_id=clean_id,
                previous_state={"current_reading": prev_reading, "in_alert": False},
                new_state={"current_reading": value, "in_alert": True, "alert_id": alert_id},
                situation_id=situation_id,
                location={"latitude": sensor.get("latitude"), "longitude": sensor.get("longitude"), "location_name": sensor.get("location_name")},
                actor=actor or {"id": "SYSTEM_SENSOR", "full_name": "IoT Sensor Intake Simulator"},
                metadata={
                    "sensor_id": clean_id,
                    "sensor_name": sensor.get("name"),
                    "sensor_type": sensor.get("sensor_type"),
                    "reading_id": reading_id,
                    "current_value": value,
                    "previous_value": prev_reading,
                    "threshold": threshold,
                    "unit": unit,
                    "simulation": True,
                    "alert_id": alert_id,
                    "severity": severity.value,
                    "message": alert_msg,
                    "coverage_radius_meters": cov_radius_m,
                    "coverage_radius_km": round(cov_radius_m / 1000.0, 2),
                },
                db=db,
            )

        elif is_breach and was_in_alert:
            # Transition: CONTINUED_BREACH (No duplicate alert created)
            transition_type = "CONTINUED_BREACH"
            current_alert_id = sensor.get("current_alert_id")
            if current_alert_id:
                await db["sensor_alerts"].update_one(
                    {"alert_id": current_alert_id},
                    {"$set": {
                        "current_value": value,
                        "previous_value": float(prev_reading) if prev_reading is not None else None,
                        "reading_id": reading_id,
                    }}
                )

        elif not is_breach and was_in_alert:
            # Transition: THRESHOLD_BREACHED -> RECOVERED
            transition_type = "RECOVERED"
            current_alert_id = sensor.get("current_alert_id")
            if current_alert_id:
                await db["sensor_alerts"].update_one(
                    {"alert_id": current_alert_id},
                    {"$set": {
                        "status": SensorAlertStatus.RESOLVED_RECOVERED.value,
                        "resolved_at": now.isoformat(),
                    }}
                )

            # Clear sensor alert state
            await db["sensors"].update_one(
                {"sensor_id": clean_id},
                {"$set": {
                    "in_alert": False,
                    "current_alert_id": None,
                }}
            )

            recovery_msg = (
                f"SENSOR RECOVERY: {sensor.get('name')} reading returned to {value} {unit} "
                f"(normal, below threshold of {threshold} {unit}) at {sensor.get('location_name')}."
            )

            monitoring_event_result = await MonitoringService.record_change_event(
                event_type=MonitoringEventType.SENSOR_RECOVERED,
                source_type=EventSourceType.SIMULATED_SENSOR,
                source_id=clean_id,
                previous_state={"current_reading": prev_reading, "in_alert": True},
                new_state={"current_reading": value, "in_alert": False},
                situation_id=sensor.get("linked_situation_id"),
                location={"latitude": sensor.get("latitude"), "longitude": sensor.get("longitude"), "location_name": sensor.get("location_name")},
                actor=actor or {"id": "SYSTEM_SENSOR", "full_name": "IoT Sensor Intake Simulator"},
                metadata={
                    "sensor_id": clean_id,
                    "sensor_name": sensor.get("name"),
                    "sensor_type": sensor.get("sensor_type"),
                    "reading_id": reading_id,
                    "current_value": value,
                    "previous_value": prev_reading,
                    "threshold": threshold,
                    "unit": unit,
                    "simulation": True,
                    "message": recovery_msg,
                },
                db=db,
            )

        else:
            # Transition: NORMAL
            transition_type = "NORMAL"

        return {
            "reading": reading,
            "transition_type": transition_type,
            "is_breach": is_breach,
            "alert": alert_result,
            "monitoring_event": monitoring_event_result,
        }

    async def get_sensor_readings(
        self,
        db: AsyncIOMotorDatabase,
        sensor_id: str,
        page: int = 1,
        limit: int = 50,
    ) -> PaginatedReadingsResponse:
        """
        Retrieves paginated history of genuine persisted readings for a sensor.
        """
        clean_id = sensor_id.strip().upper()
        total = await db["sensor_readings"].count_documents({"sensor_id": clean_id})
        total_pages = max(1, (total + limit - 1) // limit)
        skip = (page - 1) * limit

        cursor = db["sensor_readings"].find({"sensor_id": clean_id}).sort([("timestamp", -1)]).skip(skip).limit(limit)
        docs = await cursor.to_list(length=limit)

        items = []
        for d in docs:
            ts = d.get("timestamp")
            if isinstance(ts, str):
                try:
                    d["timestamp"] = datetime.fromisoformat(ts)
                except Exception:
                    d["timestamp"] = datetime.now(timezone.utc)
            items.append(SensorReading(**d))

        return PaginatedReadingsResponse(
            items=items,
            total=total,
            page=page,
            limit=limit,
            total_pages=total_pages,
        )

    async def get_sensor_alerts(
        self,
        db: AsyncIOMotorDatabase,
        sensor_id: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> PaginatedAlertsResponse:
        """
        Retrieves sensor alerts/events.
        """
        query: Dict[str, Any] = {}
        if sensor_id:
            query["sensor_id"] = sensor_id.strip().upper()
        if status and status.upper() != "ALL":
            query["status"] = status.upper()

        total = await db["sensor_alerts"].count_documents(query)
        total_pages = max(1, (total + limit - 1) // limit)
        skip = (page - 1) * limit

        cursor = db["sensor_alerts"].find(query).sort([("created_at", -1)]).skip(skip).limit(limit)
        docs = await cursor.to_list(length=limit)

        items = []
        for d in docs:
            c_at = d.get("created_at")
            if isinstance(c_at, str):
                try:
                    d["created_at"] = datetime.fromisoformat(c_at)
                except Exception:
                    d["created_at"] = datetime.now(timezone.utc)
            r_at = d.get("resolved_at")
            if isinstance(r_at, str):
                try:
                    d["resolved_at"] = datetime.fromisoformat(r_at)
                except Exception:
                    pass
            items.append(SensorAlert(**d))

        return PaginatedAlertsResponse(
            items=items,
            total=total,
            page=page,
            limit=limit,
            total_pages=total_pages,
        )

    # --- Helper Methods ---

    async def _resolve_situation_link(
        self,
        db: AsyncIOMotorDatabase,
        sensor: Dict[str, Any],
    ) -> Optional[str]:
        """
        Resolves situation linkage: explicitly linked situation takes precedence;
        otherwise checks for active situations within sensor's configured coverage radius.
        """
        explicit_id = sensor.get("linked_situation_id")
        if explicit_id:
            sit = await db["situations"].find_one({"situation_id": explicit_id.strip().upper()})
            if sit:
                return explicit_id.strip().upper()

        # Spatial search for active nearby situations within sensor coverage radius
        lat = sensor.get("latitude")
        lon = sensor.get("longitude")
        if lat is not None and lon is not None:
            cov_dict = sensor.get("coverage") or {}
            coverage_radius_m = cov_dict.get("radius_meters", 2000.0)
            sensor_range_km = float(coverage_radius_m) / 1000.0

            active_sits = await db["situations"].find({
                "status": {"$nin": ["RESOLVED", "CLOSED"]}
            }).to_list(length=50)

            best_sit_id = None
            min_dist = float("inf")

            for s in active_sits:
                center = s.get("center_location", {})
                s_lat = center.get("latitude")
                s_lon = center.get("longitude")
                if s_lat is not None and s_lon is not None:
                    dist_km = haversine_distance_km(lat, lon, s_lat, s_lon)
                    # Geographic rule: situation center must be within sensor coverage radius
                    if dist_km <= sensor_range_km and dist_km < min_dist:
                        min_dist = dist_km
                        best_sit_id = s.get("situation_id")

            if best_sit_id:
                return best_sit_id

        return None

    def _format_sensor_response(self, doc: Dict[str, Any]) -> SensorResponse:
        """
        Formats a MongoDB document into a strongly typed SensorResponse.
        """
        c_at = doc.get("created_at")
        if isinstance(c_at, str):
            try:
                c_at = datetime.fromisoformat(c_at)
            except Exception:
                c_at = datetime.now(timezone.utc)
        elif not c_at:
            c_at = datetime.now(timezone.utc)

        u_at = doc.get("updated_at")
        if isinstance(u_at, str):
            try:
                u_at = datetime.fromisoformat(u_at)
            except Exception:
                u_at = datetime.now(timezone.utc)
        elif not u_at:
            u_at = datetime.now(timezone.utc)

        l_up = doc.get("last_updated")
        if isinstance(l_up, str):
            try:
                l_up = datetime.fromisoformat(l_up)
            except Exception:
                l_up = None

        loc_raw = doc.get("location")
        loc_obj: Optional[SensorLocation] = None
        if isinstance(loc_raw, dict) and "latitude" in loc_raw and "longitude" in loc_raw:
            try:
                loc_obj = SensorLocation(**loc_raw)
            except Exception:
                loc_obj = SensorLocation(
                    latitude=float(doc["latitude"]),
                    longitude=float(doc["longitude"]),
                    address=doc.get("location_name"),
                )
        else:
            loc_obj = SensorLocation(
                latitude=float(doc["latitude"]),
                longitude=float(doc["longitude"]),
                address=doc.get("location_name"),
            )

        cov_raw = doc.get("coverage")
        cov_obj: Optional[SensorCoverage] = None
        if isinstance(cov_raw, dict) and "radius_meters" in cov_raw:
            try:
                cov_obj = SensorCoverage(**cov_raw)
            except Exception:
                cov_obj = SensorCoverage(radius_meters=2000.0, display_value=2.0, display_unit="km")
        else:
            cov_obj = SensorCoverage(radius_meters=2000.0, display_value=2.0, display_unit="km")

        return SensorResponse(
            sensor_id=doc["sensor_id"],
            name=doc["name"],
            sensor_type=SensorType(doc["sensor_type"]),
            status=SensorStatus(doc["status"]),
            location_name=doc["location_name"],
            latitude=float(doc["latitude"]),
            longitude=float(doc["longitude"]),
            location=loc_obj,
            coverage=cov_obj,
            unit=doc.get("unit", "units"),
            threshold=float(doc["threshold"]),
            current_reading=float(doc["current_reading"]) if doc.get("current_reading") is not None else None,
            previous_reading=float(doc["previous_reading"]) if doc.get("previous_reading") is not None else None,
            last_updated=l_up,
            in_alert=bool(doc.get("in_alert", False)),
            current_alert=doc.get("current_alert"),
            linked_situation_id=doc.get("linked_situation_id"),
            active_stream_session_id=doc.get("active_stream_session_id"),
            is_streaming=bool(doc.get("active_stream_session_id")),
            created_by=doc.get("created_by"),
            created_by_name=doc.get("created_by_name"),
            created_at=c_at,
            updated_at=u_at,
            description=doc.get("description"),
        )

    # =========================================================================
    # PHASE D: Sensor Health & Stale Data Intelligence
    # =========================================================================

    DEFAULT_STALE_THRESHOLD_SECONDS = 300.0  # 5 minutes

    def compute_sensor_health(
        self,
        doc: Dict[str, Any],
        stale_threshold_seconds: float = DEFAULT_STALE_THRESHOLD_SECONDS,
        eval_time: Optional[datetime] = None,
    ) -> SensorHealthDetail:
        """
        Deterministically evaluates health, freshness, and operational usability
        of a sensor from persisted database records.
        Strict zero dummy data policy: never fabricates timestamps or uptime.
        """
        now = eval_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        status_str = doc.get("status", SensorStatus.DRAFT.value)
        sensor_status = SensorStatus(status_str) if status_str in SensorStatus._value2member_map_ else SensorStatus.DRAFT

        loc_raw = doc.get("location")
        loc_obj: Optional[SensorLocation] = None
        if isinstance(loc_raw, dict) and "latitude" in loc_raw and "longitude" in loc_raw:
            try:
                loc_obj = SensorLocation(**loc_raw)
            except Exception:
                loc_obj = SensorLocation(
                    latitude=float(doc.get("latitude", 0.0)),
                    longitude=float(doc.get("longitude", 0.0)),
                    address=doc.get("location_name"),
                )
        else:
            loc_obj = SensorLocation(
                latitude=float(doc.get("latitude", 0.0)),
                longitude=float(doc.get("longitude", 0.0)),
                address=doc.get("location_name"),
            )

        cov_raw = doc.get("coverage")
        cov_obj: Optional[SensorCoverage] = None
        if isinstance(cov_raw, dict) and "radius_meters" in cov_raw:
            try:
                cov_obj = SensorCoverage(**cov_raw)
            except Exception:
                cov_obj = SensorCoverage(radius_meters=2000.0, display_value=2.0, display_unit="km")
        else:
            cov_obj = SensorCoverage(radius_meters=2000.0, display_value=2.0, display_unit="km")

        unit = doc.get("unit", "units")
        threshold = float(doc.get("threshold", 0.0))
        current_reading = float(doc["current_reading"]) if doc.get("current_reading") is not None else None
        prev_reading = float(doc["previous_reading"]) if doc.get("previous_reading") is not None else None
        in_alert = bool(doc.get("in_alert", False))
        current_alert_id = doc.get("current_alert_id")
        linked_situation_id = doc.get("linked_situation_id")

        # 1. Inactive / Paused / Draft states
        if sensor_status in [SensorStatus.INACTIVE, SensorStatus.PAUSED, SensorStatus.DRAFT]:
            return SensorHealthDetail(
                sensor_id=doc["sensor_id"],
                name=doc["name"],
                sensor_type=SensorType(doc["sensor_type"]),
                status=sensor_status,
                location_name=doc.get("location_name", "Unknown Location"),
                latitude=float(doc.get("latitude", 0.0)),
                longitude=float(doc.get("longitude", 0.0)),
                location=loc_obj,
                coverage=cov_obj,
                unit=unit,
                threshold=threshold,
                reporting_state=SensorReportingState.INACTIVE,
                health_state=SensorHealthState.INACTIVE,
                last_reading_at=None,
                reading_age_seconds=None,
                reading_age_human="Sensor inactive/paused",
                stale_threshold_seconds=stale_threshold_seconds,
                latest_reading_id=None,
                latest_reading_value=current_reading,
                previous_reading_value=prev_reading,
                is_breach=in_alert,
                in_alert=in_alert,
                current_alert_id=current_alert_id,
                linked_situation_id=linked_situation_id,
                is_usable_for_intelligence=False,
                reliability_score=0.0,
                reason=f"Sensor is currently in {sensor_status.value} state and not in active monitoring mode.",
                evaluated_at=now,
            )

        # 2. Active sensor - check last_updated timestamp
        last_up_raw = doc.get("last_updated")
        last_dt: Optional[datetime] = None
        if isinstance(last_up_raw, str):
            try:
                last_dt = datetime.fromisoformat(last_up_raw.replace("Z", "+00:00"))
            except Exception:
                last_dt = None
        elif isinstance(last_up_raw, datetime):
            last_dt = last_up_raw

        if last_dt is not None and last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)

        # 3. If no reading has ever been recorded
        if last_dt is None or current_reading is None:
            return SensorHealthDetail(
                sensor_id=doc["sensor_id"],
                name=doc["name"],
                sensor_type=SensorType(doc["sensor_type"]),
                status=sensor_status,
                location_name=doc.get("location_name", "Unknown Location"),
                latitude=float(doc.get("latitude", 0.0)),
                longitude=float(doc.get("longitude", 0.0)),
                location=loc_obj,
                coverage=cov_obj,
                unit=unit,
                threshold=threshold,
                reporting_state=SensorReportingState.NEVER_REPORTED,
                health_state=SensorHealthState.NEVER_REPORTED,
                last_reading_at=None,
                reading_age_seconds=None,
                reading_age_human="Never reported",
                stale_threshold_seconds=stale_threshold_seconds,
                latest_reading_id=None,
                latest_reading_value=None,
                previous_reading_value=None,
                is_breach=False,
                in_alert=False,
                current_alert_id=None,
                linked_situation_id=linked_situation_id,
                is_usable_for_intelligence=False,
                reliability_score=0.0,
                reason="Sensor is active but has never transmitted telemetry.",
                evaluated_at=now,
            )

        # 4. Check for timestamp corruption
        age_seconds = (now - last_dt).total_seconds()
        if age_seconds < -300.0:  # More than 5 min into future -> corrupted clock
            return SensorHealthDetail(
                sensor_id=doc["sensor_id"],
                name=doc["name"],
                sensor_type=SensorType(doc["sensor_type"]),
                status=sensor_status,
                location_name=doc.get("location_name", "Unknown Location"),
                latitude=float(doc.get("latitude", 0.0)),
                longitude=float(doc.get("longitude", 0.0)),
                location=loc_obj,
                coverage=cov_obj,
                unit=unit,
                threshold=threshold,
                reporting_state=SensorReportingState.UNAVAILABLE,
                health_state=SensorHealthState.UNAVAILABLE,
                last_reading_at=last_dt,
                reading_age_seconds=None,
                reading_age_human="Data unavailable (clock anomaly)",
                stale_threshold_seconds=stale_threshold_seconds,
                latest_reading_id=None,
                latest_reading_value=current_reading,
                previous_reading_value=prev_reading,
                is_breach=in_alert,
                in_alert=in_alert,
                current_alert_id=current_alert_id,
                linked_situation_id=linked_situation_id,
                is_usable_for_intelligence=False,
                reliability_score=0.0,
                reason="Sensor telemetry timestamp is corrupted or in future.",
                evaluated_at=now,
            )

        age_seconds = max(0.0, age_seconds)

        # 5. Format human age
        if age_seconds < 60:
            human_age = f"{int(age_seconds)}s ago"
        elif age_seconds < 3600:
            human_age = f"{int(age_seconds / 60)}m ago"
        elif age_seconds < 86400:
            human_age = f"{int(age_seconds / 3600)}h ago"
        else:
            human_age = f"{int(age_seconds / 86400)}d ago"

        # 6. Evaluate Stale vs Healthy
        if age_seconds > stale_threshold_seconds:
            return SensorHealthDetail(
                sensor_id=doc["sensor_id"],
                name=doc["name"],
                sensor_type=SensorType(doc["sensor_type"]),
                status=sensor_status,
                location_name=doc.get("location_name", "Unknown Location"),
                latitude=float(doc.get("latitude", 0.0)),
                longitude=float(doc.get("longitude", 0.0)),
                location=loc_obj,
                coverage=cov_obj,
                unit=unit,
                threshold=threshold,
                reporting_state=SensorReportingState.STALE,
                health_state=SensorHealthState.STALE,
                last_reading_at=last_dt,
                reading_age_seconds=round(age_seconds, 1),
                reading_age_human=f"Stale — last reading {human_age}",
                stale_threshold_seconds=stale_threshold_seconds,
                latest_reading_id=None,
                latest_reading_value=current_reading,
                previous_reading_value=prev_reading,
                is_breach=in_alert,
                in_alert=in_alert,
                current_alert_id=current_alert_id,
                linked_situation_id=linked_situation_id,
                is_usable_for_intelligence=True,
                reliability_score=0.35,
                reason=f"Data is stale (last reading {human_age}, threshold {stale_threshold_seconds:.0f}s). Historical context only.",
                evaluated_at=now,
            )
        else:
            h_state = SensorHealthState.IN_ALERT if in_alert else SensorHealthState.HEALTHY
            return SensorHealthDetail(
                sensor_id=doc["sensor_id"],
                name=doc["name"],
                sensor_type=SensorType(doc["sensor_type"]),
                status=sensor_status,
                location_name=doc.get("location_name", "Unknown Location"),
                latitude=float(doc.get("latitude", 0.0)),
                longitude=float(doc.get("longitude", 0.0)),
                location=loc_obj,
                coverage=cov_obj,
                unit=unit,
                threshold=threshold,
                reporting_state=SensorReportingState.HEALTHY,
                health_state=h_state,
                last_reading_at=last_dt,
                reading_age_seconds=round(age_seconds, 1),
                reading_age_human=f"Fresh ({human_age})",
                stale_threshold_seconds=stale_threshold_seconds,
                latest_reading_id=None,
                latest_reading_value=current_reading,
                previous_reading_value=prev_reading,
                is_breach=in_alert,
                in_alert=in_alert,
                current_alert_id=current_alert_id,
                linked_situation_id=linked_situation_id,
                is_usable_for_intelligence=True,
                reliability_score=1.0,
                reason="Sensor is actively reporting fresh telemetry within threshold.",
                evaluated_at=now,
            )

    async def get_sensors_health(
        self,
        db: AsyncIOMotorDatabase,
        sensor_type: Optional[str] = None,
        health_state: Optional[str] = None,
        status: Optional[str] = None,
        linked_situation_id: Optional[str] = None,
        zone: Optional[str] = None,
        stale_threshold_seconds: Optional[float] = None,
        page: int = 1,
        limit: int = 50,
    ) -> SensorHealthResponse:
        """
        Lists health and staleness intelligence for genuine registered sensors.
        Zero dummy data.
        """
        effective_threshold = stale_threshold_seconds if (stale_threshold_seconds and stale_threshold_seconds > 0) else self.DEFAULT_STALE_THRESHOLD_SECONDS

        query: Dict[str, Any] = {}
        if sensor_type and sensor_type.upper() != "ALL":
            query["sensor_type"] = sensor_type.upper()
        if status and status.upper() != "ALL":
            query["status"] = status.upper()
        if linked_situation_id:
            query["linked_situation_id"] = linked_situation_id.strip().upper()
        if zone and zone.strip():
            query["$or"] = [
                {"location.zone": {"$regex": zone.strip(), "$options": "i"}},
                {"location_name": {"$regex": zone.strip(), "$options": "i"}},
            ]

        cursor = db["sensors"].find(query).sort([("created_at", -1)])
        all_docs = await cursor.to_list(length=1000)

        now = datetime.now(timezone.utc)
        all_health: List[SensorHealthDetail] = [
            self.compute_sensor_health(d, stale_threshold_seconds=effective_threshold, eval_time=now)
            for d in all_docs
        ]

        # Calculate dynamic summary statistics
        total = len(all_health)
        healthy_count = sum(1 for h in all_health if h.reporting_state == SensorReportingState.HEALTHY)
        stale_count = sum(1 for h in all_health if h.reporting_state == SensorReportingState.STALE)
        never_reported_count = sum(1 for h in all_health if h.reporting_state == SensorReportingState.NEVER_REPORTED)
        inactive_count = sum(1 for h in all_health if h.reporting_state == SensorReportingState.INACTIVE)
        unavailable_count = sum(1 for h in all_health if h.reporting_state == SensorReportingState.UNAVAILABLE)
        in_alert_count = sum(1 for h in all_health if h.in_alert)

        # Apply health_state filter if requested
        if health_state and health_state.upper() != "ALL":
            target_hs = health_state.upper()
            filtered_items = [
                h for h in all_health
                if h.health_state.value == target_hs or h.reporting_state.value == target_hs
            ]
        else:
            filtered_items = all_health

        filtered_total = len(filtered_items)
        total_pages = max(1, (filtered_total + limit - 1) // limit)
        skip = (page - 1) * limit
        paginated_items = filtered_items[skip : skip + limit]

        summary = SensorHealthSummary(
            total_sensors=total,
            healthy_count=healthy_count,
            stale_count=stale_count,
            never_reported_count=never_reported_count,
            inactive_count=inactive_count,
            unavailable_count=unavailable_count,
            in_alert_count=in_alert_count,
            stale_threshold_seconds=effective_threshold,
            evaluated_at=now,
        )

        return SensorHealthResponse(
            summary=summary,
            items=paginated_items,
            total=filtered_total,
            page=page,
            limit=limit,
            total_pages=total_pages,
        )

    async def get_sensor_health_detail(
        self,
        db: AsyncIOMotorDatabase,
        sensor_id: str,
        stale_threshold_seconds: Optional[float] = None,
    ) -> Optional[SensorHealthDetail]:
        """
        Retrieves detailed health breakdown for a single sensor.
        """
        clean_id = sensor_id.strip().upper()
        doc = await db["sensors"].find_one({"sensor_id": clean_id})
        if not doc:
            return None

        threshold = stale_threshold_seconds if (stale_threshold_seconds and stale_threshold_seconds > 0) else self.DEFAULT_STALE_THRESHOLD_SECONDS
        return self.compute_sensor_health(doc, stale_threshold_seconds=threshold)

    async def record_stale_event_if_needed(
        self,
        db: AsyncIOMotorDatabase,
        sensor_id: str,
        actor: Optional[Dict[str, Any]] = None,
    ) -> Optional[MonitoringEvent]:
        """
        Emits SENSOR_DATA_STALE monitoring event with idempotency deduplication.
        Does not spam monitoring events if already emitted recently.
        """
        health = await self.get_sensor_health_detail(db, sensor_id)
        if not health or health.reporting_state != SensorReportingState.STALE:
            return None

        clean_id = sensor_id.strip().upper()
        now = datetime.now(timezone.utc)
        ten_mins_ago = now - timedelta(minutes=10)

        # Idempotency check: check if a SENSOR_DATA_STALE event was recorded for this sensor in the last 10 minutes
        existing_event = await db["monitoring_events"].find_one({
            "source_type": EventSourceType.SIMULATED_SENSOR.value,
            "source_id": clean_id,
            "event_type": MonitoringEventType.SENSOR_DATA_STALE.value,
            "timestamp": {"$gte": ten_mins_ago},
        })

        if existing_event:
            return None

        # Emit idempotent SENSOR_DATA_STALE event
        event = await MonitoringService.record_change_event(
            event_type=MonitoringEventType.SENSOR_DATA_STALE,
            source_type=EventSourceType.SIMULATED_SENSOR,
            source_id=clean_id,
            previous_state={"reporting_state": "HEALTHY"},
            new_state={
                "reporting_state": "STALE",
                "reading_age_seconds": health.reading_age_seconds,
                "reading_age_human": health.reading_age_human,
                "last_reading_at": health.last_reading_at.isoformat() if health.last_reading_at else None,
            },
            situation_id=health.linked_situation_id,
            location={
                "latitude": health.latitude,
                "longitude": health.longitude,
                "location_name": health.location_name,
            },
            actor=actor or {"id": "SYSTEM_SENSOR_MONITOR", "full_name": "Sensor Freshness Monitor"},
            metadata={
                "sensor_id": clean_id,
                "sensor_name": health.name,
                "sensor_type": health.sensor_type.value,
                "stale_threshold_seconds": health.stale_threshold_seconds,
                "reading_age_seconds": health.reading_age_seconds,
                "reason": health.reason,
            },
            db=db,
        )
        return event


sensor_service = SensorService()
