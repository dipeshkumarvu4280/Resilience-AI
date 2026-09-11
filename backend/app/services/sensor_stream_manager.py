import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.enums import SensorReadingSource, SimulationTrend, SensorStatus
from app.models.sensor import (
    generate_session_id,
    LiveStreamStartRequest,
    LiveStreamSession,
    LiveStreamSessionResponse,
    SensorReadingCreate,
)
from app.services.sensor_service import sensor_service
from app.db.mongodb import db_manager

logger = logging.getLogger("resilience.sensor_stream_manager")


class SensorStreamManager:
    """
    Manages runtime live simulation sessions for IoT sensors.
    Drives dynamic, parameter-configured reading streams without hardcoded values.
    Provides cancellation safety, duplicate start protection, and clean lifecycle management.
    """

    def __init__(self):
        # In-memory registry of active stream tasks keyed by sensor_id
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._active_sessions: Dict[str, LiveStreamSession] = {}

    async def start_stream(
        self,
        db: AsyncIOMotorDatabase,
        sensor_id: str,
        config: LiveStreamStartRequest,
        actor: Dict[str, Any],
    ) -> LiveStreamSessionResponse:
        """
        Starts a live simulation stream for an ACTIVE sensor.
        If a stream is already running for the sensor, returns the active session (idempotent).
        """
        clean_id = sensor_id.strip().upper()

        # Validate sensor exists and is ACTIVE
        sensor = await db["sensors"].find_one({"sensor_id": clean_id})
        if not sensor:
            raise ValueError(f"Sensor {clean_id} not found.")

        if sensor.get("status") != SensorStatus.ACTIVE.value:
            raise ValueError(
                f"Cannot start live stream for sensor in '{sensor.get('status')}' state. "
                f"Sensor must be ACTIVE."
            )

        # Duplicate protection: if already running, return existing session
        if clean_id in self._active_tasks and not self._active_tasks[clean_id].done():
            existing_session = self._active_sessions.get(clean_id)
            if existing_session:
                logger.info(f"Idempotent stream start: Sensor {clean_id} already has running stream {existing_session.session_id}.")
                return self._format_session_response(existing_session)

        now = datetime.now(timezone.utc)
        session_id = generate_session_id()

        session = LiveStreamSession(
            session_id=session_id,
            sensor_id=clean_id,
            status="RUNNING",
            started_by=actor.get("id"),
            started_by_name=actor.get("full_name"),
            started_at=now,
            stopped_at=None,
            configuration=config.model_dump(),
            readings_emitted=0,
        )

        # Persist session to MongoDB
        session_dict = session.model_dump()
        session_dict["started_at"] = session_dict["started_at"].isoformat()
        await db["sensor_sessions"].insert_one(session_dict)

        # Update sensor document with active session ID
        await db["sensors"].update_one(
            {"sensor_id": clean_id},
            {"$set": {"active_stream_session_id": session_id}}
        )

        self._active_sessions[clean_id] = session

        # Spawn background generation loop task
        task = asyncio.create_task(
            self._stream_generation_loop(
                db=db,
                sensor_id=clean_id,
                session=session,
                config=config,
                actor=actor,
            )
        )
        self._active_tasks[clean_id] = task

        logger.info(
            f"Live simulation stream started for sensor {clean_id} "
            f"(Session: {session_id}, Trend: {config.trend.value}, Interval: {config.interval_seconds}s)."
        )

        return self._format_session_response(session)

    async def stop_stream(
        self,
        db: AsyncIOMotorDatabase,
        sensor_id: str,
        actor: Optional[Dict[str, Any]] = None,
    ) -> Optional[LiveStreamSessionResponse]:
        """
        Stops an active simulation stream for a sensor.
        Cancels the background task and updates persisted session state.
        """
        clean_id = sensor_id.strip().upper()

        task = self._active_tasks.pop(clean_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        session = self._active_sessions.pop(clean_id, None)
        now = datetime.now(timezone.utc)

        if session:
            session.status = "STOPPED"
            session.stopped_at = now

            await db["sensor_sessions"].update_one(
                {"session_id": session.session_id},
                {"$set": {
                    "status": "STOPPED",
                    "stopped_at": now.isoformat(),
                    "readings_emitted": session.readings_emitted,
                }}
            )

        # Clear sensor's active session reference
        await db["sensors"].update_one(
            {"sensor_id": clean_id},
            {"$set": {"active_stream_session_id": None}}
        )

        logger.info(f"Live simulation stream stopped for sensor {clean_id}.")
        return self._format_session_response(session) if session else None

    async def get_stream_status(
        self,
        sensor_id: str,
    ) -> Optional[LiveStreamSessionResponse]:
        """
        Returns the active streaming session info for a sensor if running.
        """
        clean_id = sensor_id.strip().upper()
        session = self._active_sessions.get(clean_id)
        if session and clean_id in self._active_tasks and not self._active_tasks[clean_id].done():
            return self._format_session_response(session)
        return None

    async def stop_all_streams(self, db: Optional[AsyncIOMotorDatabase] = None):
        """
        Stops all running simulation tasks (e.g. on application shutdown or test teardown).
        """
        sensor_ids = list(self._active_tasks.keys())
        for s_id in sensor_ids:
            task = self._active_tasks.pop(s_id, None)
            if task and not task.done():
                task.cancel()
        self._active_sessions.clear()

        if db is not None:
            await db["sensors"].update_many({}, {"$set": {"active_stream_session_id": None}})
            await db["sensor_sessions"].update_many({"status": "RUNNING"}, {"$set": {"status": "STOPPED"}})

    # --- Background Simulation Loop ---

    async def _stream_generation_loop(
        self,
        db: AsyncIOMotorDatabase,
        sensor_id: str,
        session: LiveStreamSession,
        config: LiveStreamStartRequest,
        actor: Dict[str, Any],
    ):
        """
        Asynchronous generation loop emitting dynamic sensor readings per interval.
        """
        current_value = float(config.starting_value)
        step_size = float(config.step_size) if config.step_size else (config.max_value - config.min_value) * 0.05
        if step_size <= 0:
            step_size = 0.1

        try:
            while True:
                # 1. Emit reading to sensor service
                reading_in = SensorReadingCreate(
                    value=round(current_value, 2),
                    source_type=SensorReadingSource.LIVE_SIMULATION,
                    simulation=True,
                    notes=f"Auto-stream ({config.trend.value}) Session {session.session_id}",
                )

                try:
                    await sensor_service.record_reading(
                        db=db,
                        sensor_id=sensor_id,
                        reading_in=reading_in,
                        actor=actor,
                    )
                    session.readings_emitted += 1
                except Exception as e:
                    logger.error(f"Error in sensor stream emission for {sensor_id}: {e}")
                    # If sensor is no longer active, stop stream
                    if "Only ACTIVE sensors" in str(e):
                        break

                # 2. Wait for next interval
                await asyncio.sleep(config.interval_seconds)

                # 3. Calculate next value based on trend
                if config.trend == SimulationTrend.RISING:
                    current_value = min(config.max_value, current_value + step_size)
                    if current_value >= config.max_value:
                        # Slight fluctuation at peak
                        current_value = config.max_value - random.uniform(0.0, step_size * 0.2)
                elif config.trend == SimulationTrend.FALLING:
                    current_value = max(config.min_value, current_value - step_size)
                    if current_value <= config.min_value:
                        current_value = config.min_value + random.uniform(0.0, step_size * 0.2)
                else:  # FLUCTUATING
                    delta = (random.random() * 2 - 1) * step_size
                    current_value = max(config.min_value, min(config.max_value, current_value + delta))

        except asyncio.CancelledError:
            logger.info(f"Stream generation loop cancelled for sensor {sensor_id}.")
        except Exception as e:
            logger.error(f"Unexpected error in stream loop for sensor {sensor_id}: {e}")
        finally:
            self._active_tasks.pop(sensor_id, None)
            self._active_sessions.pop(sensor_id, None)


    def is_streaming(self, sensor_id: str) -> bool:
        clean_id = sensor_id.strip().upper()
        return clean_id in self._active_tasks and not self._active_tasks[clean_id].done()

    def _format_session_response(self, session: LiveStreamSession) -> LiveStreamSessionResponse:
        return LiveStreamSessionResponse(
            session_id=session.session_id,
            sensor_id=session.sensor_id,
            status=session.status,
            started_at=session.started_at,
            stopped_at=session.stopped_at,
            configuration=session.configuration,
            readings_emitted=session.readings_emitted,
        )


sensor_stream_manager = SensorStreamManager()
