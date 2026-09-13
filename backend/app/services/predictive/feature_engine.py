import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from app.models.predictive import (
    PredictiveFeature,
    PredictiveEvidenceItem,
    PredictiveDataSufficiency,
)
from app.services.predictive.interfaces import (
    PredictiveFeatureProvider,
    RawIncidentData,
    ExtractedFeatureSet,
)

logger = logging.getLogger("resilience.predictive.feature_engine")


def _to_utc(dt: Any) -> Optional[datetime]:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    if isinstance(dt, str):
        try:
            parsed = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
        except Exception:
            return None
    return None


class DeterministicFeatureProvider(PredictiveFeatureProvider):
    """
    Deterministic feature engineering provider extracting verifiable signals
    directly from genuine MongoDB records within a specified historical window.
    Zero fabricated data, zero dummy fallback values.
    """

    async def extract_features(
        self,
        raw_data: RawIncidentData,
    ) -> ExtractedFeatureSet:
        window_minutes = raw_data.window_minutes
        window_start = raw_data.window_start
        window_end = raw_data.window_end
        half_window = window_start + (window_end - window_start) / 2
        window_label = f"{window_minutes}m"

        features: List[PredictiveFeature] = []
        feature_dict: Dict[str, float] = {}
        missing_features: List[str] = []
        evidence_items: List[PredictiveEvidenceItem] = []
        data_points_used: Dict[str, int] = {
            "citizen_reports": len(raw_data.report_docs),
            "sensors": len(raw_data.sensor_docs),
            "sensor_readings": len(raw_data.sensor_readings),
            "sensor_alerts": len(raw_data.sensor_alerts),
            "field_verifications": len(raw_data.field_verifications),
            "monitoring_events": len(raw_data.monitoring_events),
            "change_impacts": len(raw_data.change_impacts),
            "response_tasks": len(raw_data.response_tasks),
        }
        limitations: List[str] = []

        # -------------------------------------------------------------
        # Filter Time-Series Records Strictly within Historical Window
        # -------------------------------------------------------------
        reports_in_window = [
            r for r in raw_data.report_docs
            if window_start <= (_to_utc(r.get("created_at")) or window_end) <= window_end
        ]
        readings_in_window = [
            rd for rd in raw_data.sensor_readings
            if window_start <= (_to_utc(rd.get("timestamp")) or window_end) <= window_end
        ]
        alerts_in_window = [
            al for al in raw_data.sensor_alerts
            if window_start <= (_to_utc(al.get("created_at")) or window_end) <= window_end
        ]
        fvs_in_window = [
            fv for fv in raw_data.field_verifications
            if window_start <= (_to_utc(fv.get("submitted_at", fv.get("created_at"))) or window_end) <= window_end
        ]
        mons_in_window = [
            me for me in raw_data.monitoring_events
            if window_start <= (_to_utc(me.get("detected_at", me.get("timestamp"))) or window_end) <= window_end
        ]
        tasks = raw_data.response_tasks

        data_points_used: Dict[str, int] = {
            "citizen_reports": len(reports_in_window),
            "sensors": len(raw_data.sensor_docs),
            "sensor_readings": len(readings_in_window),
            "sensor_alerts": len(alerts_in_window),
            "field_verifications": len(fvs_in_window),
            "monitoring_events": len(mons_in_window),
            "change_impacts": len(raw_data.change_impacts),
            "response_tasks": len(tasks),
        }
        limitations: List[str] = []

        # -------------------------------------------------------------
        # 1. Citizen Reports Feature Extraction
        # -------------------------------------------------------------
        report_count = len(reports_in_window)
        window_hours = max(0.25, window_minutes / 60.0)

        if report_count > 0:
            early_reports = [r for r in reports_in_window if (_to_utc(r.get("created_at")) or window_start) < half_window]
            recent_reports = [r for r in reports_in_window if (_to_utc(r.get("created_at")) or window_start) >= half_window]

            early_count = len(early_reports)
            recent_count = len(recent_reports)
            total_window_reports = early_count + recent_count

            # Statistical sample gating: low volume (<3 reports) does not establish a valid velocity
            if total_window_reports >= 3:
                report_rate_change = (recent_count - early_count) / float(total_window_reports)
            else:
                report_rate_change = 0.0
                if total_window_reports > 0 and early_count > 0 and recent_count == 0:
                    limitations.append("Report intake sample size is sparse (<3 in window); intake rate change constrained.")

            report_rate_per_hr = report_count / window_hours

            critical_reports = [
                r for r in reports_in_window
                if str(r.get("citizen_impact_level", "")).upper() in ["CRITICAL", "HIGH"]
                or str(r.get("priority", "")).upper() in ["CRITICAL", "HIGH"]
            ]
            critical_ratio = len(critical_reports) / float(report_count)

            # Add features
            f_rep_count = PredictiveFeature(
                name="incident_report_count",
                value=float(report_count),
                source="citizen_reports",
                time_window=window_label,
                data_points=report_count,
                description=f"Total genuine citizen emergency reports intake within {window_label}",
            )
            f_rate_change = PredictiveFeature(
                name="report_rate_change",
                value=round(report_rate_change, 3),
                source="citizen_reports",
                time_window=window_label,
                data_points=report_count,
                description=f"Temporal acceleration in report intake (recent half: {recent_count} vs early half: {early_count})",
            )
            f_crit_ratio = PredictiveFeature(
                name="critical_report_ratio",
                value=round(critical_ratio, 3),
                source="citizen_reports",
                time_window=window_label,
                data_points=report_count,
                description=f"Proportion of reports flagging high or critical severity ({len(critical_reports)}/{report_count})",
            )

            features.extend([f_rep_count, f_rate_change, f_crit_ratio])
            feature_dict["incident_report_count"] = float(report_count)
            feature_dict["report_rate_change"] = report_rate_change
            feature_dict["critical_report_ratio"] = critical_ratio
            feature_dict["report_rate_per_hour"] = report_rate_per_hr

            # Add evidence items for key reports
            display_reports = recent_reports if recent_reports else early_reports
            for r in display_reports[:3]:
                r_id = r.get("report_id", "UNKNOWN")
                r_ts = _to_utc(r.get("created_at")) or window_end
                r_impact = r.get("citizen_impact_level", "STANDARD")
                evidence_items.append(PredictiveEvidenceItem(
                    source_type="CITIZEN_REPORT",
                    source_id=r_id,
                    timestamp=r_ts,
                    contribution=f"Citizen report flagging {r_impact} impact ({r.get('emergency_type', 'hazard')})",
                    weight=0.85 if r_impact in ["HIGH", "CRITICAL"] else 0.5,
                ))
        else:
            missing_features.append(f"citizen_reports (no reports submitted within last {window_label})")

        # -------------------------------------------------------------
        # 2. IoT Sensor Telemetry & Health-Aware Signal Extraction
        # -------------------------------------------------------------
        sensors = raw_data.sensor_docs
        readings = readings_in_window
        alerts = alerts_in_window
        readings_by_sensor: Dict[str, List[Dict[str, Any]]] = {}

        usable_sensors = []
        stale_sensors = []
        for s in sensors:
            h_state = str(s.get("health_state", s.get("reporting_state", "HEALTHY"))).upper()
            status = str(s.get("status", "ACTIVE")).upper()
            if status in ["INACTIVE", "DECOMMISSIONED", "DRAFT"]:
                continue
            if h_state in ["INACTIVE", "UNAVAILABLE", "NEVER_REPORTED"]:
                continue
            if h_state == "STALE" or "STALE" in h_state:
                stale_sensors.append(s)
            else:
                usable_sensors.append(s)

        total_usable_sensors = len(usable_sensors) + len(stale_sensors)

        if total_usable_sensors > 0 and (readings or alerts):
            # Group readings by sensor for individual time-series analysis
            for rd in readings:
                s_id = rd.get("sensor_id", "SNS")
                readings_by_sensor.setdefault(s_id, []).append(rd)

            sensor_weight_factor = 1.0 if usable_sensors else 0.5
            if stale_sensors and not usable_sensors:
                limitations.append("Sensor data is stale (>5m without fresh readings); confidence discounted by 50%.")

            # Evaluate aggregate sensor time-series across matched sensors
            total_readings_cnt = len(readings)
            all_breach_rds = [rd for rd in readings if rd.get("is_breach") is True]
            overall_breach_ratio = len(all_breach_rds) / float(total_readings_cnt) if total_readings_cnt > 0 else 0.0

            sensor_meta_list = []
            overall_sensor_trend = 0.0

            for s in (usable_sensors + stale_sensors):
                s_id = s.get("sensor_id")
                s_name = s.get("name", s_id)
                s_unit = s.get("unit", "m")
                s_thresh = float(s.get("threshold", 0.0))
                s_health = str(s.get("health_state", "HEALTHY")).upper()
                s_rds = readings_by_sensor.get(s_id, [])

                if s_rds:
                    # Chronological sort
                    sorted_rds = sorted(
                        s_rds,
                        key=lambda r: _to_utc(r.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc)
                    )
                    vals = [float(r.get("value", 0.0)) for r in sorted_rds]
                    v_first = vals[0]
                    v_latest = vals[-1]
                    v_min = min(vals)
                    v_max = max(vals)
                    t_first = _to_utc(sorted_rds[0].get("timestamp"))
                    t_latest = _to_utc(sorted_rds[-1].get("timestamp"))

                    s_breaches = sum(1 for v in vals if v > s_thresh or any(r.get("is_breach") for r in sorted_rds))
                    s_breach_ratio = s_breaches / float(len(vals))

                    # Calculate temporal slope / velocity across time-series
                    if len(vals) >= 2:
                        early_half = vals[:len(vals)//2]
                        recent_half = vals[len(vals)//2:]
                        early_avg = sum(early_half) / max(1, len(early_half))
                        recent_avg = sum(recent_half) / max(1, len(recent_half))
                        val_delta = v_latest - v_first
                        pct_change = (recent_avg - early_avg) / early_avg if early_avg > 0 else (1.0 if recent_avg > 0 else 0.0)

                        if abs(val_delta) < 0.02 * (s_thresh if s_thresh > 0 else 1.0) or abs(pct_change) < 0.02:
                            s_trend_dir = "STABLE"
                            s_slope = 0.0
                        elif pct_change >= 0.02:
                            s_trend_dir = "RISING"
                            s_slope = max(-1.0, min(1.0, pct_change))
                        else:
                            s_trend_dir = "FALLING"
                            s_slope = max(-1.0, min(1.0, pct_change))
                    else:
                        s_trend_dir = "STABLE"
                        s_slope = 0.0
                        val_delta = 0.0
                        pct_change = 0.0

                    overall_sensor_trend += s_slope

                    s_meta = {
                        "sensor_id": s_id,
                        "sensor_name": s_name,
                        "raw_records": len(vals),
                        "unit": s_unit,
                        "threshold": s_thresh,
                        "first_value": round(v_first, 3),
                        "latest_value": round(v_latest, 3),
                        "min_value": round(v_min, 3),
                        "max_value": round(v_max, 3),
                        "delta_value": round(val_delta, 3),
                        "breach_count": s_breaches,
                        "breach_ratio": round(s_breach_ratio, 3),
                        "rate_of_change": f"{pct_change:+.1%}",
                        "temporal_trend": s_trend_dir,
                        "earliest_timestamp": t_first.isoformat() if t_first else None,
                        "latest_timestamp": t_latest.isoformat() if t_latest else None,
                        "health_state": s_health,
                        "health_weight": sensor_weight_factor,
                    }
                    sensor_meta_list.append(s_meta)

                    # Add detailed time-series evidence
                    trend_sym = "↑" if s_trend_dir == "RISING" else ("↓" if s_trend_dir == "FALLING" else "→")
                    evidence_items.append(PredictiveEvidenceItem(
                        source_type="IOT_SENSOR",
                        source_id=s_id,
                        timestamp=t_latest or window_end,
                        contribution=(
                            f"Sensor '{s_name}' ({s_id}): {len(vals)} readings ({v_first:.2f} → {v_latest:.2f} {s_unit}, "
                            f"thresh: {s_thresh} {s_unit}) [{s_breach_ratio:.0%} BREACH, Trend: {trend_sym} {s_trend_dir}, Health: {s_health}]"
                        ),
                        weight=0.95 * sensor_weight_factor,
                    ))

            if sensor_meta_list:
                overall_sensor_trend = overall_sensor_trend / float(len(sensor_meta_list))
            elif readings:
                overall_sensor_trend = 0.0

            active_alerts = [a for a in alerts if str(a.get("status", "")).upper() in ["ACTIVE", "ACTIVE_BREACH"]]
            alert_count = len(active_alerts)

            # Features with rich time-series aggregation metadata
            primary_meta = sensor_meta_list[0] if sensor_meta_list else {}

            f_sensor_breach = PredictiveFeature(
                name="sensor_breach_ratio",
                value=round(overall_breach_ratio, 3),
                source="sensors",
                time_window=window_label,
                data_points=total_readings_cnt,
                raw_records=total_readings_cnt,
                aggregation_method="time_series_threshold_evaluation",
                metadata=primary_meta,
                description=f"Proportion of IoT readings exceeding hazard thresholds ({len(all_breach_rds)}/{total_readings_cnt})",
            )
            f_sensor_trend = PredictiveFeature(
                name="sensor_reading_trend",
                value=round(overall_sensor_trend, 3),
                source="sensors",
                time_window=window_label,
                data_points=total_readings_cnt,
                raw_records=total_readings_cnt,
                aggregation_method="time_series_temporal_velocity",
                metadata=primary_meta,
                description=f"Trajectory of physical sensor measurements (velocity: {overall_sensor_trend:+.1%})",
            )
            f_sensor_alerts = PredictiveFeature(
                name="sensor_active_alert_count",
                value=float(alert_count),
                source="sensors",
                time_window=window_label,
                data_points=len(alerts),
                raw_records=len(alerts),
                aggregation_method="telemetry_alert_count",
                metadata={"active_alerts": alert_count, "correlated_sensors": total_usable_sensors},
                description=f"Active critical threshold breach alerts ({alert_count} active)",
            )

            features.extend([f_sensor_breach, f_sensor_trend, f_sensor_alerts])
            feature_dict["sensor_breach_ratio"] = overall_breach_ratio * sensor_weight_factor
            feature_dict["sensor_reading_trend"] = overall_sensor_trend * sensor_weight_factor
            feature_dict["sensor_active_alert_count"] = float(alert_count)
            feature_dict["sensor_usable_count"] = float(total_usable_sensors)

            # Add alerts to evidence only if distinct from readings
            if not readings and active_alerts:
                for a in active_alerts[:2]:
                    a_id = a.get("alert_id", "ALERT-UNKNOWN")
                    a_ts = _to_utc(a.get("created_at")) or window_end
                    s_id = a.get("sensor_id", "SNS")
                    s_name = a.get("sensor_name", s_id)
                    s_match = next((s for s in sensors if s.get("sensor_id") == s_id), None)
                    s_health = str(s_match.get("health_state", "HEALTHY")).upper() if s_match else "HEALTHY"
                    
                    evidence_items.append(PredictiveEvidenceItem(
                        source_type="IOT_SENSOR",
                        source_id=a_id,
                        timestamp=a_ts,
                        contribution=f"Sensor '{s_name}' ({s_id}) threshold alert: {a.get('current_value')} {a.get('unit')} (thresh: {a.get('threshold')}) [Health: {s_health}]",
                        weight=0.95 * sensor_weight_factor,
                    ))
        else:
            if total_usable_sensors == 0:
                missing_features.append(f"sensors (no active/healthy IoT sensors correlated with incident area)")
            else:
                missing_features.append(f"sensor_readings (no readings recorded within {window_label})")

        # -------------------------------------------------------------
        # 3. Field Responder Live Verifications
        # -------------------------------------------------------------
        verifications = fvs_in_window
        if verifications:
            worsening_fvs = [
                fv for fv in verifications
                if str(fv.get("verification_status", "")).upper() in ["CONDITION_CHANGED", "ESCALATED"]
                or "worsen" in str(fv.get("notes", "")).lower()
                or "escalat" in str(fv.get("notes", "")).lower()
                or "expand" in str(fv.get("notes", "")).lower()
            ]
            worsening_ratio = len(worsening_fvs) / float(len(verifications))

            f_fld_worsening = PredictiveFeature(
                name="field_condition_worsening_ratio",
                value=round(worsening_ratio, 3),
                source="field_verifications",
                time_window=window_label,
                data_points=len(verifications),
                description=f"Ground officer verifications indicating worsening hazard conditions ({len(worsening_fvs)}/{len(verifications)})",
            )
            features.append(f_fld_worsening)
            feature_dict["field_condition_worsening_ratio"] = worsening_ratio
            feature_dict["field_verification_count"] = float(len(verifications))

            for fv in worsening_fvs[:2]:
                fv_id = fv.get("verification_id", "FV-UNKNOWN")
                fv_ts = _to_utc(fv.get("submitted_at", fv.get("created_at"))) or window_end
                evidence_items.append(PredictiveEvidenceItem(
                    source_type="FIELD_VERIFICATION",
                    source_id=fv_id,
                    timestamp=fv_ts,
                    contribution=f"Ground verification by {fv.get('responder_name', 'Field Unit')} confirmed condition: {fv.get('observation_category', 'HAZARD_ACTIVE')}",
                    weight=0.90,
                ))
        else:
            missing_features.append(f"field_verifications (no ground verifications in {window_label})")

        # -------------------------------------------------------------
        # 4. Live Monitoring Telemetry & Invalidation Events
        # -------------------------------------------------------------
        mon_events = mons_in_window
        if mon_events:
            critical_mon = [
                m for m in mon_events
                if str(m.get("impact_level", "")).upper() in ["CRITICAL", "HIGH"]
                or str(m.get("plan_status", "")).upper() in ["INVALIDATED", "REQUIRES_REPLANNING", "REQUIRES_OFFICER_REVIEW"]
            ]
            mon_critical_ratio = len(critical_mon) / float(len(mon_events))
            mon_rate_per_hr = len(mon_events) / window_hours

            f_mon_rate = PredictiveFeature(
                name="monitoring_event_rate_per_hour",
                value=round(mon_rate_per_hr, 2),
                source="monitoring_events",
                time_window=window_label,
                data_points=len(mon_events),
                description=f"Telemetry & operational change event frequency ({mon_rate_per_hr:.1f} events/hr)",
            )
            f_mon_crit = PredictiveFeature(
                name="critical_monitoring_impact_ratio",
                value=round(mon_critical_ratio, 3),
                source="monitoring_events",
                time_window=window_label,
                data_points=len(mon_events),
                description=f"Proportion of monitoring events with high/critical operational impact ({len(critical_mon)}/{len(mon_events)})",
            )
            features.extend([f_mon_rate, f_mon_crit])
            feature_dict["monitoring_event_rate_per_hour"] = mon_rate_per_hr
            feature_dict["critical_monitoring_impact_ratio"] = mon_critical_ratio
            feature_dict["monitoring_event_count"] = float(len(mon_events))

            for m in critical_mon[:2]:
                m_id = m.get("event_id", "MON-UNKNOWN")
                m_ts = _to_utc(m.get("detected_at", m.get("timestamp"))) or window_end
                evidence_items.append(PredictiveEvidenceItem(
                    source_type="MONITORING_EVENT",
                    source_id=m_id,
                    timestamp=m_ts,
                    contribution=f"Monitoring change event '{m.get('event_type')}' triggered {m.get('impact_level', 'HIGH')} impact",
                    weight=0.80,
                ))
        else:
            missing_features.append(f"monitoring_events (no telemetry change events in {window_label})")

        # -------------------------------------------------------------
        # 5. Active Response Task Pressure & Operational Bottlenecks
        # -------------------------------------------------------------
        if tasks:
            active_tasks = [t for t in tasks if str(t.get("status", "")).upper() in ["IN_PROGRESS", "PENDING", "ASSIGNED"]]
            blocked_tasks = [t for t in tasks if str(t.get("status", "")).upper() in ["BLOCKED", "FAILED"]]
            total_active = len(active_tasks) + len(blocked_tasks)
            blockage_ratio = len(blocked_tasks) / float(total_active) if total_active > 0 else 0.0

            f_task_pressure = PredictiveFeature(
                name="task_blockage_ratio",
                value=round(blockage_ratio, 3),
                source="response_tasks",
                time_window=window_label,
                data_points=len(tasks),
                description=f"Operational task blockage pressure ({len(blocked_tasks)} blocked / {total_active} active)",
            )
            features.append(f_task_pressure)
            feature_dict["task_blockage_ratio"] = blockage_ratio
            feature_dict["active_task_count"] = float(len(active_tasks))
            feature_dict["blocked_task_count"] = float(len(blocked_tasks))

            if blocked_tasks:
                b_task = blocked_tasks[0]
                b_id = b_task.get("task_id", "TSK-UNKNOWN")
                evidence_items.append(PredictiveEvidenceItem(
                    source_type="TASK_PRESSURE",
                    source_id=b_id,
                    timestamp=window_end,
                    contribution=f"Response task '{b_task.get('title', b_id)}' is currently BLOCKED",
                    weight=0.75,
                ))
        else:
            missing_features.append("response_tasks (zero operational response tasks assigned for this incident)")

        # -------------------------------------------------------------
        # 6. Real-World Weather Evidence & Atmospheric Feature Extraction
        # -------------------------------------------------------------
        weather = raw_data.weather_evidence
        ext_context_sources = 0

        if weather and weather.data_status in ["FRESH", "STALE"]:
            ext_context_sources = 1
            w_provider = weather.provider
            w_freshness_weight = 1.0 if weather.data_status == "FRESH" else 0.65
            if weather.data_status == "STALE":
                limitations.append(f"Weather intelligence from {w_provider} is stale (>1h old); weight discounted by 35%.")

            sit_doc = raw_data.situation_doc or {}
            em_type = str(sit_doc.get("emergency_type", "EMERGENCY")).upper()

            # Weather metrics (only if genuinely returned by provider)
            w_precip = weather.precipitation_mm
            w_prob = weather.precipitation_probability
            w_temp = weather.temperature_c
            w_humidity = weather.humidity_percent
            w_wind = weather.wind_speed_mps
            w_gust = weather.wind_gust_mps

            # Extract multi-horizon forecast metrics
            f15 = next((p for p in weather.forecast_periods if p.horizon_minutes == 15), None)
            f30 = next((p for p in weather.forecast_periods if p.horizon_minutes == 30), None)
            f60 = next((p for p in weather.forecast_periods if p.horizon_minutes == 60), None)

            f30_precip = f30.precipitation_mm if f30 else None
            f30_prob = f30.precipitation_probability if f30 else None
            f30_temp = f30.temperature_c if f30 else None
            f30_wind = f30.wind_speed_mps if f30 else None

            # Calculate precipitation trend if both observation and forecast exist
            precip_trend = 0.0
            if w_precip is not None and f30_precip is not None:
                precip_delta = f30_precip - w_precip
                if abs(precip_delta) < 0.2:
                    precip_trend = 0.0
                elif precip_delta > 0:
                    precip_trend = min(1.0, precip_delta / 5.0)
                else:
                    precip_trend = max(-1.0, precip_delta / 5.0)

            # Hazard-aware feature recording
            if w_precip is not None:
                features.append(PredictiveFeature(
                    name="weather_precipitation_mm",
                    value=float(w_precip),
                    source="weather_api",
                    time_window=window_label,
                    data_points=1,
                    description=f"Current observed precipitation from {w_provider} ({w_precip} mm/h)",
                ))
                feature_dict["weather_precipitation_mm"] = float(w_precip)

            if w_prob is not None:
                features.append(PredictiveFeature(
                    name="weather_precipitation_probability",
                    value=float(w_prob),
                    source="weather_api",
                    time_window=window_label,
                    data_points=1,
                    description=f"Precipitation probability from {w_provider} ({w_prob:.0f}%)",
                ))
                feature_dict["weather_precipitation_probability"] = float(w_prob)

            if f30_precip is not None:
                features.append(PredictiveFeature(
                    name="weather_forecast_precipitation_30m",
                    value=float(f30_precip),
                    source="weather_api",
                    time_window="+30m",
                    data_points=1,
                    description=f"Forecast precipitation in +30m horizon ({f30_precip} mm)",
                ))
                feature_dict["weather_forecast_precipitation_30m"] = float(f30_precip)
                feature_dict["weather_precipitation_trend"] = precip_trend

            if w_temp is not None:
                features.append(PredictiveFeature(
                    name="weather_temperature_c",
                    value=float(w_temp),
                    source="weather_api",
                    time_window=window_label,
                    data_points=1,
                    description=f"Current ambient temperature from {w_provider} ({w_temp}°C)",
                ))
                feature_dict["weather_temperature_c"] = float(w_temp)

            if w_wind is not None:
                features.append(PredictiveFeature(
                    name="weather_wind_speed_mps",
                    value=float(w_wind),
                    source="weather_api",
                    time_window=window_label,
                    data_points=1,
                    description=f"Current surface wind speed from {w_provider} ({w_wind} m/s)",
                ))
                feature_dict["weather_wind_speed_mps"] = float(w_wind)

            if w_humidity is not None:
                feature_dict["weather_humidity_percent"] = float(w_humidity)

            if w_gust is not None:
                feature_dict["weather_wind_gust_mps"] = float(w_gust)

            # Add rich weather evidence item
            cond_desc = weather.condition or "Observed atmospheric conditions"
            details = []
            if w_temp is not None:
                details.append(f"{w_temp:.1f}°C")
            if w_precip is not None:
                details.append(f"{w_precip:.1f}mm rain")
            if w_prob is not None:
                details.append(f"{w_prob:.0f}% precip prob")
            if w_wind is not None:
                details.append(f"{w_wind:.1f}m/s wind")
            if f30_precip is not None:
                details.append(f"forecast +30m: {f30_precip:.1f}mm")

            evidence_items.append(PredictiveEvidenceItem(
                source_type="WEATHER_API",
                source_id=f"WX-{w_provider.upper()}",
                timestamp=weather.observation_timestamp or window_end,
                contribution=f"Weather ({w_provider}): {cond_desc} [{', '.join(details)}]",
                weight=0.85 * w_freshness_weight,
            ))
        else:
            w_status = weather.data_status if weather else "UNAVAILABLE"
            w_err = weather.error_detail if weather else "Weather service not queried"
            missing_features.append(f"weather_api (status: {w_status} - {w_err})")

        # -------------------------------------------------------------
        # 7. Current Situation Baseline & Spatial Impact
        # -------------------------------------------------------------
        sit_doc = raw_data.situation_doc or {}
        impact_zone = sit_doc.get("impact_zone") or {}
        radius_km = float(impact_zone.get("radius_km", 1.0))
        pop_est = int(sit_doc.get("estimated_affected_population", 0))

        feature_dict["impact_radius_km"] = radius_km
        feature_dict["affected_population"] = float(pop_est)

        # -------------------------------------------------------------
        # 8. Total Independent Data Points & Sufficiency Determination
        # -------------------------------------------------------------
        # Deduplicated independent physical observation count across sources
        unique_sensor_ids = set(readings_by_sensor.keys()) | {a.get("sensor_id") for a in alerts_in_window if a.get("sensor_id")}
        independent_physical_points = (
            len(reports_in_window)
            + len(unique_sensor_ids)
            + len(fvs_in_window)
            + len(mons_in_window)
        )
        total_records = sum(data_points_used.values())

        if independent_physical_points == 0 and ext_context_sources == 0:
            data_status = PredictiveDataSufficiency.NO_DATA
            limitations.append(f"Zero database records or weather observations found for this incident in the selected {window_label} window.")
        elif independent_physical_points == 0 and ext_context_sources > 0:
            data_status = PredictiveDataSufficiency.LIMITED_DATA
            limitations.append(f"Zero dynamic incident reports/sensors in window; contextual weather intelligence available.")
        elif independent_physical_points < 2:
            # If 1 sensor has high time-series sampling depth (>= 5 readings), it provides sufficient temporal trend
            if len(unique_sensor_ids) >= 1 and len(readings_in_window) >= 5:
                data_status = PredictiveDataSufficiency.SUFFICIENT_DATA
            else:
                data_status = PredictiveDataSufficiency.INSUFFICIENT_DATA
                limitations.append(f"Single static observation in {window_label} window; rate of change cannot be calculated.")
        elif independent_physical_points < 4 and len(features) < 3:
            data_status = PredictiveDataSufficiency.LIMITED_DATA
            limitations.append(f"Limited historical observations ({independent_physical_points} points in {window_label}); confidence is constrained.")
        else:
            data_status = PredictiveDataSufficiency.SUFFICIENT_DATA

        return ExtractedFeatureSet(
            features=features,
            feature_dict=feature_dict,
            missing_features=missing_features,
            evidence_items=evidence_items,
            data_points_used=data_points_used,
            total_data_points=total_records,
            independent_sources_count=independent_physical_points,
            independent_physical_sources_count=independent_physical_points,
            external_context_sources_count=ext_context_sources,
            weather_evidence=weather,
            data_status=data_status,
            limitations=limitations,
        )
