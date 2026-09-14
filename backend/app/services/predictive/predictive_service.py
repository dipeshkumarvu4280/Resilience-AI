import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.predictive import (
    IncidentPredictionResponse,
    ForecastHorizonResult,
    PredictiveTrendResponse,
    PredictiveTrendPoint,
    PredictiveFeaturesResponse,
    PredictiveHealthResponse,
    PredictiveDataSufficiency,
    EscalationRiskLevel,
    TrendDirection,
)
from app.services.predictive.interfaces import (
    RawIncidentData,
    PredictiveFeatureProvider,
    PredictiveModel,
)
from app.services.predictive.feature_engine import (
    DeterministicFeatureProvider,
    _to_utc,
)
from app.services.predictive.deterministic_escalation_engine import (
    DeterministicEscalationModel,
)
from app.services.resource_matching import haversine_distance_km

logger = logging.getLogger("resilience.predictive.service")


from app.services.weather import weather_service


class PredictiveService:
    """
    Core Predictive Analysis Engine (Phase 1).
    Provides advisory temporal risk forecasting derived exclusively from genuine persisted records
    and real atmospheric weather telemetry.
    Strictly read-only; zero automatic mutations or operational changes.
    """

    def __init__(
        self,
        feature_provider: Optional[PredictiveFeatureProvider] = None,
        model: Optional[PredictiveModel] = None,
    ):
        self.feature_provider = feature_provider or DeterministicFeatureProvider()
        self.model = model or DeterministicEscalationModel()
        self._cache: Dict[str, Tuple[str, Any]] = {}

    async def get_incident_prediction(
        self,
        db: AsyncIOMotorDatabase,
        incident_id: str,
        window_minutes: int = 60,
        forecast_horizon_minutes: int = 30,
        use_cache: bool = True,
    ) -> IncidentPredictionResponse:
        """
        Calculates advisory escalation risk forecast across multiple horizons (15m, 30m, 60m)
        with real-world weather fusion.
        """
        clean_id = incident_id.strip().upper()
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=max(15, window_minutes))

        # 1. Fetch genuine raw operational records + real weather
        raw_data = await self._fetch_raw_incident_data(db, clean_id, window_start, now, window_minutes)

        # 2. Compute state fingerprint for deterministic cache check
        fingerprint = self._compute_state_fingerprint(raw_data)
        cache_key = f"{clean_id}:{window_minutes}:{forecast_horizon_minutes}:{self.model.version}"

        if use_cache and cache_key in self._cache:
            cached_fp, cached_response = self._cache[cache_key]
            if cached_fp == fingerprint:
                return cached_response

        # 3. Extract features via deterministic feature provider
        feature_set = await self.feature_provider.extract_features(raw_data)

        # 4. Predict for all supported horizons (15m, 30m, 60m)
        horizons_dict: Dict[str, ForecastHorizonResult] = {}
        for h_min in [15, 30, 60]:
            h_res = self.model.predict_horizon(h_min, feature_set, raw_data)
            horizons_dict[f"{h_min}m"] = h_res

        primary_horizon_key = f"{forecast_horizon_minutes}m" if f"{forecast_horizon_minutes}m" in horizons_dict else "30m"
        primary_forecast = horizons_dict[primary_horizon_key]
        all_capped = all(h.is_capped for h in horizons_dict.values()) if horizons_dict else False

        # 5. Extract authoritative current situation severity
        sit_doc = raw_data.situation_doc or {}
        curr_sev = str(sit_doc.get("severity_level", "MEDIUM")).upper()
        curr_score = float(sit_doc.get("severity_score", 0.0))
        is_override = bool(sit_doc.get("officer_override_severity"))

        inc_title = sit_doc.get("title") or (raw_data.report_docs[0].get("description", clean_id) if raw_data.report_docs else clean_id)
        em_type = str(sit_doc.get("emergency_type", (raw_data.report_docs[0].get("emergency_type") if raw_data.report_docs else "EMERGENCY")))

        prediction_status = "AVAILABLE"
        if feature_set.data_status == PredictiveDataSufficiency.NO_DATA:
            prediction_status = "NO_DATA"
        elif feature_set.data_status == PredictiveDataSufficiency.INSUFFICIENT_DATA:
            prediction_status = "INSUFFICIENT_DATA"
        elif feature_set.data_status == PredictiveDataSufficiency.LIMITED_DATA:
            prediction_status = "LIMITED"

        response = IncidentPredictionResponse(
            incident_id=clean_id,
            incident_title=inc_title,
            emergency_type=em_type,
            prediction_status=prediction_status,
            data_status=feature_set.data_status,
            current_authoritative_severity=curr_sev,
            current_severity_score=curr_score,
            is_officer_override=is_override,
            forecast=primary_forecast,
            horizons=horizons_dict,
            all_horizons_capped=all_capped,
            independent_sources_count=feature_set.independent_physical_sources_count,
            independent_physical_sources_count=feature_set.independent_physical_sources_count,
            external_context_sources_count=feature_set.external_context_sources_count,
            weather=raw_data.weather_evidence,
            features=feature_set.features,
            missing_features=feature_set.missing_features,
            evidence=feature_set.evidence_items,
            data_points_used=feature_set.data_points_used,
            historical_window_minutes=window_minutes,
            model={
                "name": self.model.name,
                "version": self.model.version,
                "type": "Deterministic Predictive Intelligence Engine",
                "method": "Temporal Rate, Atmospheric Context & Weighted Multi-Source Signal Synthesis",
            },
            limitations=primary_forecast.limitations,
            generated_at=now,
        )

        if use_cache:
            self._cache[cache_key] = (fingerprint, response)

        return response

    async def get_incident_trend(
        self,
        db: AsyncIOMotorDatabase,
        incident_id: str,
        window_minutes: int = 60,
    ) -> PredictiveTrendResponse:
        """
        Returns observed historical progression and predicted future horizon points.
        """
        prediction = await self.get_incident_prediction(db, incident_id, window_minutes=window_minutes)
        now = datetime.now(timezone.utc)

        # Baseline point (current)
        curr_score = min(1.0, prediction.current_severity_score / 10.0)
        curr_level = prediction.current_authoritative_severity

        timeline_points: List[PredictiveTrendPoint] = [
            PredictiveTrendPoint(
                time_label="Current",
                minutes_from_now=0,
                risk_score=round(curr_score, 2),
                risk_level=curr_level,
                is_forecast=False,
                data_status="CURRENT_STATE",
            )
        ]

        # Forecast horizon points
        for h_key, h_res in prediction.horizons.items():
            timeline_points.append(
                PredictiveTrendPoint(
                    time_label=f"+{h_res.horizon_minutes}m",
                    minutes_from_now=h_res.horizon_minutes,
                    risk_score=h_res.risk_score,
                    risk_level=h_res.risk_level,
                    is_forecast=True,
                    data_status=h_res.data_status,
                )
            )

        summary = (
            f"Escalation trend is {prediction.forecast.trend} with {prediction.forecast.risk_level} "
            f"projected risk at {prediction.forecast.horizon_minutes}m horizon (score: {prediction.forecast.risk_score:.2f})."
        )

        return PredictiveTrendResponse(
            incident_id=incident_id,
            data_status=prediction.data_status,
            trend_direction=prediction.forecast.trend,
            historical_window_minutes=window_minutes,
            timeline_points=timeline_points,
            summary=summary,
            generated_at=now,
        )

    async def get_incident_features(
        self,
        db: AsyncIOMotorDatabase,
        incident_id: str,
        window_minutes: int = 60,
    ) -> PredictiveFeaturesResponse:
        """
        Returns detailed extracted features and their exact record provenance.
        """
        prediction = await self.get_incident_prediction(db, incident_id, window_minutes=window_minutes)
        total_pts = sum(prediction.data_points_used.values())
        return PredictiveFeaturesResponse(
            incident_id=incident_id,
            historical_window_minutes=window_minutes,
            data_status=prediction.data_status,
            features=prediction.features,
            missing_features=prediction.missing_features,
            total_records_evaluated=total_pts,
            records_by_source=prediction.data_points_used,
            generated_at=datetime.now(timezone.utc),
        )

    def get_health(self) -> PredictiveHealthResponse:
        return PredictiveHealthResponse(
            status="HEALTHY",
            engine_version="1.0-phase1",
            model_name=self.model.name,
            supported_horizons_minutes=[15, 30, 60],
            default_window_minutes=60,
            zero_dummy_data_enforced=True,
            advisory_mode_enforced=True,
            checked_at=datetime.now(timezone.utc),
        )

    # -------------------------------------------------------------------------
    # Internal Helpers & Data Aggregation
    # -------------------------------------------------------------------------

    async def _fetch_raw_incident_data(
        self,
        db: AsyncIOMotorDatabase,
        clean_id: str,
        window_start: datetime,
        window_end: datetime,
        window_minutes: int,
    ) -> RawIncidentData:
        is_situation = clean_id.startswith("SIT-")
        situation_doc: Optional[Dict[str, Any]] = None
        report_ids: List[str] = []
        situation_id: Optional[str] = clean_id if is_situation else None

        # 1. Situation Resolution
        if is_situation:
            situation_doc = await db["situations"].find_one({"situation_id": clean_id})
            if situation_doc:
                report_ids = situation_doc.get("report_ids", [])
        else:
            report_doc = await db["citizen_reports"].find_one({"report_id": clean_id})
            if report_doc:
                report_ids = [clean_id]
                situation_id = report_doc.get("situation_id")
                if situation_id:
                    situation_doc = await db["situations"].find_one({"situation_id": situation_id})

        # 2. Citizen Reports within Window
        from app.models.enums import ReportStatus
        rep_query: Dict[str, Any] = {"status": {"$ne": ReportStatus.REJECTED.value}}
        if report_ids:
            rep_query["report_id"] = {"$in": report_ids}
        elif situation_id:
            rep_query["situation_id"] = situation_id

        report_docs: List[Dict[str, Any]] = []
        if rep_query:
            report_docs = await db["citizen_reports"].find(rep_query).sort("created_at", 1).to_list(length=1000)

        # 3. Location and Impact Center Resolution (Strictly authoritative incident coordinates)
        center_lat: Optional[float] = None
        center_lon: Optional[float] = None
        impact_radius_km = 3.0

        if situation_doc:
            center_loc = situation_doc.get("center_location") or {}
            if center_loc.get("latitude") is not None and center_loc.get("longitude") is not None:
                center_lat = float(center_loc["latitude"])
                center_lon = float(center_loc["longitude"])
            impact_zone = situation_doc.get("impact_zone") or {}
            impact_radius_km = float(impact_zone.get("radius_km", impact_radius_km))
        elif report_docs:
            r0 = report_docs[0]
            loc = r0.get("location") or {}
            if loc.get("latitude") is not None and loc.get("longitude") is not None:
                center_lat = float(loc["latitude"])
                center_lon = float(loc["longitude"])
            elif r0.get("latitude") is not None and r0.get("longitude") is not None:
                center_lat = float(r0["latitude"])
                center_lon = float(r0["longitude"])

        # Fetch Real Weather for Authoritative Coordinates
        weather_ev = await weather_service.get_weather_for_incident(center_lat, center_lon, use_cache=True)

        # 4. Correlated IoT Sensors & Telemetry
        sensor_docs: List[Dict[str, Any]] = []
        sensor_readings: List[Dict[str, Any]] = []
        sensor_alerts: List[Dict[str, Any]] = []

        # Find sensors matching linked situation or within spatial radius
        all_sensors = await db["sensors"].find({}).to_list(length=500)
        matched_sensor_ids: List[str] = []
        for s in all_sensors:
            linked_sit = s.get("linked_situation_id")
            s_lat = s.get("latitude")
            s_lon = s.get("longitude")
            s_cov = (s.get("coverage") or {}).get("radius_meters", 2000.0) / 1000.0

            is_match = False
            if situation_id and linked_sit == situation_id:
                is_match = True
            elif center_lat is not None and center_lon is not None and s_lat is not None and s_lon is not None:
                dist = haversine_distance_km(center_lat, center_lon, float(s_lat), float(s_lon))
                if dist <= (impact_radius_km + s_cov):
                    is_match = True

            if is_match:
                sensor_docs.append(s)
                matched_sensor_ids.append(s["sensor_id"])

        if matched_sensor_ids:
            raw_rds = await db["sensor_readings"].find({
                "sensor_id": {"$in": matched_sensor_ids},
            }).sort("timestamp", 1).to_list(length=5000)
            for rd in raw_rds:
                rd_ts = _to_utc(rd.get("timestamp"))
                if rd_ts is None or (window_start <= rd_ts <= window_end):
                    sensor_readings.append(rd)

            raw_als = await db["sensor_alerts"].find({
                "sensor_id": {"$in": matched_sensor_ids},
            }).sort("created_at", 1).to_list(length=1000)
            for al in raw_als:
                al_ts = _to_utc(al.get("created_at"))
                if al_ts is None or (window_start <= al_ts <= window_end):
                    sensor_alerts.append(al)

        # 5. Field Verifications
        fv_query: Dict[str, Any] = {
            "$or": [
                {"target_id": clean_id},
                {"target_id": {"$in": report_ids}},
            ]
        }
        if situation_id:
            fv_query["$or"].append({"metadata.situation_id": situation_id})

        field_verifications: List[Dict[str, Any]] = []
        raw_fvs = await db["field_verifications"].find(fv_query).sort("submitted_at", 1).to_list(length=1000)
        for fv in raw_fvs:
            fv_ts = _to_utc(fv.get("submitted_at", fv.get("created_at")))
            if fv_ts is None or (window_start <= fv_ts <= window_end):
                field_verifications.append(fv)

        # 6. Live Monitoring Telemetry & Impact Events
        mon_query: Dict[str, Any] = {
            "$or": [
                {"source_id": clean_id},
                {"source_id": {"$in": report_ids}},
            ]
        }
        if situation_id:
            mon_query["$or"].append({"situation_id": situation_id})

        monitoring_events: List[Dict[str, Any]] = []
        raw_mes = await db["monitoring_events"].find(mon_query).sort("detected_at", 1).to_list(length=1000)
        for me in raw_mes:
            me_ts = _to_utc(me.get("detected_at", me.get("timestamp")))
            if me_ts is None or (window_start <= me_ts <= window_end):
                monitoring_events.append(me)

        # 7. Change Impacts
        change_impacts: List[Dict[str, Any]] = []
        if situation_id:
            raw_cis = await db["change_impacts"].find({"situation_id": situation_id}).sort("analyzed_at", 1).to_list(length=1000)
            for ci in raw_cis:
                ci_ts = _to_utc(ci.get("analyzed_at", ci.get("created_at")))
                if ci_ts is None or (window_start <= ci_ts <= window_end):
                    change_impacts.append(ci)

        # 8. Operational Response Tasks
        response_tasks: List[Dict[str, Any]] = []
        task_query: Dict[str, Any] = {}
        if situation_id:
            task_query["situation_id"] = situation_id
        elif report_ids:
            task_query["report_id"] = {"$in": report_ids}

        if task_query:
            response_tasks = await db["response_tasks"].find(task_query).to_list(length=1000)

        return RawIncidentData(
            incident_id=clean_id,
            is_situation=is_situation,
            situation_doc=situation_doc,
            report_docs=report_docs,
            sensor_docs=sensor_docs,
            sensor_readings=sensor_readings,
            sensor_alerts=sensor_alerts,
            field_verifications=field_verifications,
            monitoring_events=monitoring_events,
            change_impacts=change_impacts,
            response_tasks=response_tasks,
            weather_evidence=weather_ev,
            window_start=window_start,
            window_end=window_end,
            window_minutes=window_minutes,
        )

    def _compute_state_fingerprint(self, raw_data: RawIncidentData) -> str:
        """
        Creates an immutable deterministic fingerprint of the underlying database state and weather observation.
        Any new reading, report, verification, task, or weather update will alter this fingerprint.
        """
        fp_parts: List[str] = [raw_data.incident_id]

        sit_doc = raw_data.situation_doc or {}
        fp_parts.append(str(sit_doc.get("updated_at", sit_doc.get("created_at", ""))))
        fp_parts.append(str(sit_doc.get("severity_score", "")))

        for r in raw_data.report_docs:
            fp_parts.append(f"rep:{r.get('report_id')}:{r.get('status')}")

        for rd in raw_data.sensor_readings:
            fp_parts.append(f"srd:{rd.get('reading_id')}:{rd.get('value')}")

        for fv in raw_data.field_verifications:
            fp_parts.append(f"fv:{fv.get('verification_id')}:{fv.get('verification_status')}")

        for me in raw_data.monitoring_events:
            fp_parts.append(f"me:{me.get('event_id')}:{me.get('impact_level')}")

        for t in raw_data.response_tasks:
            fp_parts.append(f"tsk:{t.get('task_id')}:{t.get('status')}")

        if raw_data.weather_evidence:
            w = raw_data.weather_evidence
            fp_parts.append(f"wx:{w.provider}:{w.data_status}:{w.temperature_c}:{w.precipitation_mm}:{w.observation_timestamp}")

        raw_str = "|".join(fp_parts)
        return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()[:16]


# Singleton Service Instance
predictive_service = PredictiveService()
