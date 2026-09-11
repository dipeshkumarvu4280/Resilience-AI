import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongodb import get_database
from app.api.deps import require_officer, get_current_user
from app.models.user import UserResponse
from app.models.sensor import (
    SensorCreate,
    SensorUpdate,
    SensorReadingCreate,
    LiveStreamStartRequest,
    SensorResponse,
    PaginatedSensorsResponse,
    SensorStatsResponse,
    PaginatedReadingsResponse,
    PaginatedAlertsResponse,
    LiveStreamSessionResponse,
    SensorHealthDetail,
    SensorHealthResponse,
)
from app.services.sensor_service import sensor_service
from app.services.sensor_stream_manager import sensor_stream_manager

logger = logging.getLogger("resilience.api.sensors")
router = APIRouter()


@router.post(
    "",
    response_model=SensorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new IoT sensor",
    description="Registers a new sensor in DRAFT state. Zero default or sample readings are created automatically.",
)
async def create_sensor(
    sensor_in: SensorCreate,
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    try:
        actor = {
            "id": current_user.id,
            "full_name": current_user.full_name,
            "role": current_user.role.value,
        }
        return await sensor_service.create_sensor(db=db, sensor_in=sensor_in, actor=actor)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create sensor: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create sensor.")


@router.get(
    "/stats",
    response_model=SensorStatsResponse,
    summary="Get aggregated sensor KPIs",
    description="Calculates real-time sensor metrics dynamically from persisted database records.",
)
async def get_sensor_stats(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    try:
        return await sensor_service.get_sensor_stats(db=db)
    except Exception as e:
        logger.error(f"Failed to calculate sensor stats: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to calculate sensor metrics.")


@router.get(
    "",
    response_model=PaginatedSensorsResponse,
    summary="List all sensors with filters",
)
async def list_sensors(
    sensor_type: Optional[str] = Query(None, description="Filter by sensor type"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by sensor status"),
    in_alert: Optional[bool] = Query(None, description="Filter by alert status"),
    linked_situation_id: Optional[str] = Query(None, description="Filter by linked situation ID"),
    search: Optional[str] = Query(None, description="Search by name, location or ID"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    try:
        return await sensor_service.list_sensors(
            db=db,
            sensor_type=sensor_type,
            status=status_filter,
            in_alert=in_alert,
            linked_situation_id=linked_situation_id,
            search=search,
            page=page,
            limit=limit,
        )
    except Exception as e:
        logger.error(f"Failed to list sensors: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve sensor catalog.")


@router.get(
    "/health",
    response_model=SensorHealthResponse,
    summary="Get sensor health and staleness intelligence",
    description="Deterministically evaluates health, freshness, data age, and reporting status for genuine registered sensors.",
)
async def get_sensors_health(
    sensor_type: Optional[str] = Query(None, description="Filter by sensor type"),
    health_state: Optional[str] = Query(None, description="Filter by health state (HEALTHY, STALE, INACTIVE, NEVER_REPORTED, UNAVAILABLE)"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by sensor status"),
    linked_situation_id: Optional[str] = Query(None, description="Filter by linked situation ID"),
    zone: Optional[str] = Query(None, description="Filter by zone or location"),
    stale_threshold_seconds: Optional[float] = Query(None, ge=10.0, le=86400.0, description="Override staleness threshold in seconds"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    try:
        return await sensor_service.get_sensors_health(
            db=db,
            sensor_type=sensor_type,
            health_state=health_state,
            status=status_filter,
            linked_situation_id=linked_situation_id,
            zone=zone,
            stale_threshold_seconds=stale_threshold_seconds,
            page=page,
            limit=limit,
        )
    except Exception as e:
        logger.error(f"Failed to retrieve sensor health: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to calculate sensor health.")


@router.get(
    "/{sensor_id}",
    response_model=SensorResponse,
    summary="Get sensor details by ID",
)
async def get_sensor(
    sensor_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    sensor = await sensor_service.get_sensor(db=db, sensor_id=sensor_id)
    if not sensor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Sensor '{sensor_id}' not found.")
    return sensor


@router.get(
    "/{sensor_id}/health",
    response_model=SensorHealthDetail,
    summary="Get single sensor health and staleness breakdown",
    description="Provides traceable, explainable health diagnostics for a specific sensor.",
)
async def get_single_sensor_health(
    sensor_id: str,
    stale_threshold_seconds: Optional[float] = Query(None, ge=10.0, le=86400.0),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    health = await sensor_service.get_sensor_health_detail(
        db=db,
        sensor_id=sensor_id,
        stale_threshold_seconds=stale_threshold_seconds,
    )
    if not health:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Sensor '{sensor_id}' not found.")
    return health


@router.put(
    "/{sensor_id}",
    response_model=SensorResponse,
    summary="Update sensor location, range, and configuration",
    description="Updates physical coordinates, coverage radius, address metadata, or operational parameters. Audits all changes.",
)
@router.patch(
    "/{sensor_id}",
    response_model=SensorResponse,
    summary="Partial update of sensor location, range, and configuration",
)
async def update_sensor(
    sensor_id: str,
    sensor_in: SensorUpdate,
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    try:
        actor = {
            "id": current_user.id,
            "full_name": current_user.full_name,
            "role": current_user.role.value,
        }
        return await sensor_service.update_sensor(
            db=db,
            sensor_id=sensor_id,
            sensor_in=sensor_in,
            actor=actor,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update sensor {sensor_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update sensor.")


@router.post(
    "/{sensor_id}/activate",
    response_model=SensorResponse,
    summary="Activate a sensor",
)
async def activate_sensor(
    sensor_id: str,
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    try:
        actor = {"id": current_user.id, "full_name": current_user.full_name, "role": current_user.role.value}
        return await sensor_service.activate_sensor(db=db, sensor_id=sensor_id, actor=actor)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to activate sensor {sensor_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to activate sensor.")


@router.post(
    "/{sensor_id}/pause",
    response_model=SensorResponse,
    summary="Pause a sensor",
)
async def pause_sensor(
    sensor_id: str,
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    try:
        # Halt stream if running
        await sensor_stream_manager.stop_stream(db=db, sensor_id=sensor_id, actor={"id": current_user.id, "full_name": current_user.full_name})
        actor = {"id": current_user.id, "full_name": current_user.full_name, "role": current_user.role.value}
        return await sensor_service.pause_sensor(db=db, sensor_id=sensor_id, actor=actor)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to pause sensor {sensor_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to pause sensor.")


@router.post(
    "/{sensor_id}/resume",
    response_model=SensorResponse,
    summary="Resume a paused sensor",
)
async def resume_sensor(
    sensor_id: str,
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    try:
        actor = {"id": current_user.id, "full_name": current_user.full_name, "role": current_user.role.value}
        return await sensor_service.resume_sensor(db=db, sensor_id=sensor_id, actor=actor)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to resume sensor {sensor_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to resume sensor.")


@router.post(
    "/{sensor_id}/deactivate",
    response_model=SensorResponse,
    summary="Deactivate a sensor",
)
async def deactivate_sensor(
    sensor_id: str,
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    try:
        # Halt stream if running
        await sensor_stream_manager.stop_stream(db=db, sensor_id=sensor_id, actor={"id": current_user.id, "full_name": current_user.full_name})
        actor = {"id": current_user.id, "full_name": current_user.full_name, "role": current_user.role.value}
        return await sensor_service.deactivate_sensor(db=db, sensor_id=sensor_id, actor=actor)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to deactivate sensor {sensor_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to deactivate sensor.")


@router.patch(
    "/{sensor_id}/status",
    response_model=SensorResponse,
    summary="Update sensor status",
)
async def update_sensor_status(
    sensor_id: str,
    payload: Dict[str, Any],
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    try:
        actor = {"id": current_user.id, "full_name": current_user.full_name, "role": current_user.role.value}
        target_status = payload.get("status")
        if target_status == "ACTIVE":
            return await sensor_service.activate_sensor(db=db, sensor_id=sensor_id, actor=actor)
        elif target_status == "PAUSED":
            await sensor_stream_manager.stop_stream(db=db, sensor_id=sensor_id, actor={"id": current_user.id, "full_name": current_user.full_name})
            return await sensor_service.pause_sensor(db=db, sensor_id=sensor_id, actor=actor)
        elif target_status == "INACTIVE":
            await sensor_stream_manager.stop_stream(db=db, sensor_id=sensor_id, actor={"id": current_user.id, "full_name": current_user.full_name})
            return await sensor_service.deactivate_sensor(db=db, sensor_id=sensor_id, actor=actor)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status transition to '{target_status}'.")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/{sensor_id}/readings",
    status_code=status.HTTP_201_CREATED,
    summary="Submit a live sensor reading",
    description="Validates that sensor is ACTIVE, persists reading, evaluates threshold, and updates intelligence.",
)
async def record_sensor_reading(
    sensor_id: str,
    reading_in: SensorReadingCreate,
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    try:
        actor = {"id": current_user.id, "full_name": current_user.full_name, "role": current_user.role.value}
        result = await sensor_service.record_reading(
            db=db,
            sensor_id=sensor_id,
            reading_in=reading_in,
            actor=actor,
        )
        return {
            "success": True,
            "reading": result["reading"],
            "transition_type": result["transition_type"],
            "is_breach": result["is_breach"],
            "alert": result["alert"],
            "value": result["reading"].value,
            "sensor_id": result["reading"].sensor_id,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to record sensor reading for {sensor_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to process sensor reading.")


@router.get(
    "/{sensor_id}/readings",
    response_model=PaginatedReadingsResponse,
    summary="Get reading history for a sensor",
)
async def get_sensor_readings(
    sensor_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    try:
        return await sensor_service.get_sensor_readings(db=db, sensor_id=sensor_id, page=page, limit=limit)
    except Exception as e:
        logger.error(f"Failed to retrieve sensor readings for {sensor_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve sensor readings.")


@router.get(
    "/{sensor_id}/events",
    response_model=PaginatedAlertsResponse,
    summary="Get threshold breach and recovery alerts for a sensor",
)
async def get_sensor_events(
    sensor_id: str,
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    try:
        return await sensor_service.get_sensor_alerts(
            db=db,
            sensor_id=sensor_id,
            status=status_filter,
            page=page,
            limit=limit,
        )
    except Exception as e:
        logger.error(f"Failed to retrieve sensor events for {sensor_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve sensor events.")


# --- Telemetry & Analytics ---

@router.get(
    "/{sensor_id}/telemetry",
    summary="Get sensor telemetry statistics",
)
async def get_sensor_telemetry(
    sensor_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    clean_id = sensor_id.strip().upper()
    sensor = await db["sensors"].find_one({"sensor_id": clean_id})
    if not sensor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sensor not found")
    readings = await db["sensor_readings"].find({"sensor_id": clean_id}).to_list(length=1000)
    total_readings = len(readings)
    values = [r.get("value", 0.0) for r in readings]
    breached_count = sum(1 for r in readings if r.get("is_breach", False))
    return {
        "sensor_id": clean_id,
        "total_readings": total_readings,
        "min_value": min(values) if values else 0.0,
        "max_value": max(values) if values else 0.0,
        "avg_value": sum(values) / total_readings if total_readings > 0 else 0.0,
        "breached_readings_count": breached_count,
        "current_value": sensor.get("current_reading"),
        "is_breached": bool(sensor.get("in_alert", False)),
    }


# --- Live Simulation Streaming Endpoints ---

@router.post(
    "/{sensor_id}/live-stream/start",
    response_model=LiveStreamSessionResponse,
    summary="Start live simulation stream for a sensor",
)
@router.post(
    "/{sensor_id}/stream/start",
    response_model=LiveStreamSessionResponse,
    summary="Start live simulation stream for a sensor (alias)",
)
async def start_live_stream(
    sensor_id: str,
    config: LiveStreamStartRequest,
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    try:
        actor = {"id": current_user.id, "full_name": current_user.full_name, "role": current_user.role.value}
        return await sensor_stream_manager.start_stream(
            db=db,
            sensor_id=sensor_id,
            config=config,
            actor=actor,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to start live stream for {sensor_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to start live stream.")


@router.post(
    "/{sensor_id}/live-stream/stop",
    summary="Stop active simulation stream for a sensor",
)
@router.post(
    "/{sensor_id}/stream/stop",
    summary="Stop active simulation stream for a sensor (alias)",
)
async def stop_live_stream(
    sensor_id: str,
    current_user: UserResponse = Depends(require_officer),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    try:
        actor = {"id": current_user.id, "full_name": current_user.full_name}
        session = await sensor_stream_manager.stop_stream(db=db, sensor_id=sensor_id, actor=actor)
        return {"success": True, "message": "Live simulation stream stopped.", "session": session, "status": "STOPPED"}
    except Exception as e:
        logger.error(f"Failed to stop live stream for {sensor_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to stop live stream.")


@router.get(
    "/{sensor_id}/live-stream/status",
    summary="Check active stream status for a sensor",
)
@router.get(
    "/{sensor_id}/stream/status",
    summary="Check active stream status for a sensor (alias)",
)
async def get_live_stream_status(
    sensor_id: str,
    current_user: UserResponse = Depends(get_current_user),
):
    session = await sensor_stream_manager.get_stream_status(sensor_id=sensor_id)
    return {"is_streaming": session is not None, "session": session}
