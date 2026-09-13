import logging
from typing import List, Dict, Any, Tuple
from app.models.predictive import (
    EscalationRiskLevel,
    TrendDirection,
    PredictiveDataSufficiency,
    ForecastHorizonResult,
)
from app.services.predictive.interfaces import (
    PredictiveModel,
    RawIncidentData,
    ExtractedFeatureSet,
)

logger = logging.getLogger("resilience.predictive.deterministic_engine")


class DeterministicEscalationModel(PredictiveModel):
    """
    Phase 1 Authoritative Deterministic Incident Escalation Risk Predictor.
    
    FORMULA ARCHITECTURE:
    - Analyzes temporal velocity and multi-source corroborating signals.
    - Normalized mathematical formulation bounded in [0.0, 1.0].
    - Zero stochastic hallucinations, zero hidden LLM calculations for numeric risk.
    - Fully explainable factor contributions with data sufficiency safeguards.
    """

    @property
    def name(self) -> str:
        return "deterministic_escalation_v1"

    @property
    def version(self) -> str:
        return "1.0"

    def predict_horizon(
        self,
        horizon_minutes: int,
        feature_set: ExtractedFeatureSet,
        raw_data: RawIncidentData,
    ) -> ForecastHorizonResult:
        """
        Calculates deterministic escalation risk score and trend for a specific forecast horizon.
        """
        data_status = feature_set.data_status
        f_dict = feature_set.feature_dict
        total_pts = feature_set.total_data_points

        # Handle zero or insufficient data states truthfully
        if data_status == PredictiveDataSufficiency.NO_DATA or total_pts == 0:
            sit_doc = raw_data.situation_doc or {}
            raw_sev_score = float(sit_doc.get("severity_score", 0.0))
            base_score = max(0.0, min(1.0, raw_sev_score / 10.0))
            return ForecastHorizonResult(
                horizon_minutes=horizon_minutes,
                risk_level=self._score_to_level(base_score),
                risk_score=round(base_score, 2),
                raw_score=round(base_score, 2),
                projected_score=round(base_score, 2),
                trend=TrendDirection.UNKNOWN,
                data_status=PredictiveDataSufficiency.NO_DATA,
                confidence_score=0.0,
                confidence_label="UNAVAILABLE",
                contributing_factors=[
                    f"No dynamic records within selected {raw_data.window_minutes}m window. Score anchored to authoritative baseline severity ({raw_sev_score:.1f}/10)."
                ],
                limitations=[
                    f"No operational telemetry or reports recorded in the last {raw_data.window_minutes} minutes. Select 'Last 6 hours' or 'Last 24 hours' in the Historical Window selector to include earlier telemetry records."
                ],
            )

        if data_status == PredictiveDataSufficiency.INSUFFICIENT_DATA:
            # If 60m horizon with only 1 data point, return INSUFFICIENT_DATA
            sit_doc = raw_data.situation_doc or {}
            base_score = float(sit_doc.get("severity_score", 3.0)) / 10.0
            return ForecastHorizonResult(
                horizon_minutes=horizon_minutes,
                risk_level=self._score_to_level(base_score),
                risk_score=round(base_score, 2),
                trend=TrendDirection.UNKNOWN,
                data_status=PredictiveDataSufficiency.INSUFFICIENT_DATA,
                confidence_score=0.20,
                confidence_label="LOW",
                contributing_factors=["Single static observation available; baseline severity mapped directly."],
                limitations=["Insufficient temporal data points to establish a rate of change or trend."],
            )

        # -------------------------------------------------------------
        # 1. Base Authoritative Severity Anchor (0.0 to 1.0)
        # -------------------------------------------------------------
        sit_doc = raw_data.situation_doc or {}
        raw_sev_score = float(sit_doc.get("severity_score", 0.0))
        baseline_anchor = max(0.0, min(1.0, raw_sev_score / 10.0))
        em_type = str(sit_doc.get("emergency_type", "EMERGENCY")).upper()

        # -------------------------------------------------------------
        # 2. Extract Individual Dynamic Signals & Velocity
        # -------------------------------------------------------------
        # A. Report Acceleration Signal (-1.0 to +1.0)
        report_rate_change = f_dict.get("report_rate_change", 0.0)
        crit_rep_ratio = f_dict.get("critical_report_ratio", 0.0)
        has_reps = f_dict.get("incident_report_count", 0.0) > 0 or ("report_rate_change" in f_dict)
        rep_signal = (report_rate_change * 0.7) + ((crit_rep_ratio - 0.5) * 0.3) if has_reps else 0.0

        # B. Sensor Breach & Trend Velocity (-1.0 to +1.0)
        sensor_usable = f_dict.get("sensor_usable_count", 0.0) > 0
        sensor_breach_ratio = f_dict.get("sensor_breach_ratio", 0.0)
        sensor_trend = f_dict.get("sensor_reading_trend", 0.0)
        sensor_alert_cnt = f_dict.get("sensor_active_alert_count", 0.0)
        sensor_velocity = sensor_trend if sensor_usable else None

        # C. Field Condition Worsening Signal (-1.0 to +1.0)
        has_fld = f_dict.get("field_verification_count", 0.0) > 0
        fld_worsening = f_dict.get("field_condition_worsening_ratio", 0.0) if has_fld else None

        # D. Monitoring Invalidation & Telemetry Event Signal (0.0 to 1.0)
        has_mon = f_dict.get("monitoring_event_count", 0.0) > 0
        mon_crit_ratio = f_dict.get("critical_monitoring_impact_ratio", 0.0) if has_mon else None

        # E. Task Blockage & Bottleneck Signal (0.0 to 1.0)
        has_tasks = (f_dict.get("active_task_count", 0.0) + f_dict.get("blocked_task_count", 0.0)) > 0
        task_blockage = f_dict.get("task_blockage_ratio", 0.0) if has_tasks else None

        # F. Hazard-Aware Weather & Atmospheric Temporal Signal (-1.0 to +1.0)
        weather = raw_data.weather_evidence
        matched_forecast_period = None
        weather_signal = 0.0
        weather_weight = 0.0
        has_weather = weather is not None and weather.data_status in ["FRESH", "STALE"]
        w_discount = 1.0 if (weather and weather.data_status == "FRESH") else 0.65

        if has_weather and weather:
            matched_forecast_period = next(
                (p for p in weather.forecast_periods if p.horizon_minutes == horizon_minutes),
                None
            )
            f_precip = matched_forecast_period.precipitation_mm if matched_forecast_period else weather.precipitation_mm
            f_prob = matched_forecast_period.precipitation_probability if matched_forecast_period else weather.precipitation_probability
            f_temp = matched_forecast_period.temperature_c if matched_forecast_period else weather.temperature_c
            f_wind = matched_forecast_period.wind_speed_mps if matched_forecast_period else weather.wind_speed_mps
            f_gust = matched_forecast_period.wind_gust_mps if matched_forecast_period else weather.wind_gust_mps

            if em_type in ["FLOOD", "WATER_LOGGING", "DAM_BURST", "FLASH_FLOOD"]:
                weather_weight = 0.20 * w_discount
                p_val = f_precip if f_precip is not None else 0.0
                prob_val = (f_prob / 100.0) if f_prob is not None else 0.5
                if p_val > 0.0:
                    weather_signal = min(1.0, (p_val / 20.0) * (0.5 + prob_val * 0.5))
                elif prob_val > 0.7:
                    weather_signal = 0.15
                else:
                    weather_signal = -0.10  # Zero rainfall provides mild stabilizing effect

            elif em_type in ["CYCLONE", "STORM", "HURRICANE", "GALE"]:
                weather_weight = 0.25 * w_discount
                w_val = f_wind if f_wind is not None else 0.0
                g_val = f_gust if f_gust is not None else w_val
                weather_signal = min(1.0, max(0.0, (w_val - 8.0) / 25.0 + (g_val - 12.0) / 35.0))

            elif em_type in ["HEATWAVE", "DROUGHT"]:
                weather_weight = 0.25 * w_discount
                t_val = f_temp if f_temp is not None else 30.0
                weather_signal = min(1.0, max(0.0, (t_val - 36.0) / 12.0))

            elif em_type in ["FIRE", "WILDFIRE", "FOREST_FIRE"]:
                weather_weight = 0.20 * w_discount
                t_val = f_temp if f_temp is not None else 25.0
                w_val = f_wind if f_wind is not None else 0.0
                hum_val = weather.humidity_percent if weather.humidity_percent is not None else 50.0
                hum_dryness = max(0.0, (40.0 - hum_val) / 40.0)
                weather_signal = min(1.0, (t_val - 28.0) / 20.0 * 0.4 + (w_val / 15.0) * 0.3 + hum_dryness * 0.3)

            else:
                # Contextual only for other incidents (accidents, building collapse, medical)
                weather_weight = 0.04 * w_discount
                if (f_precip or 0.0) > 10.0 or (f_wind or 0.0) > 15.0:
                    weather_signal = 0.30
                else:
                    weather_signal = 0.0

        # -------------------------------------------------------------
        # 3. Dynamic Velocity Synthesis & Horizon Factor Projections
        # -------------------------------------------------------------
        h_ratio = horizon_minutes / 30.0
        h_proj_factor = pow(h_ratio, 0.75)

        incident_comp = (rep_signal * 0.25) * h_proj_factor if has_reps else 0.0
        sensor_comp = (sensor_velocity * 0.30) * h_proj_factor if sensor_velocity is not None else 0.0
        field_comp = ((fld_worsening - 0.2) * 0.20) * h_proj_factor if fld_worsening is not None else 0.0
        monitoring_comp = ((mon_crit_ratio - 0.2) * 0.15) * h_proj_factor if mon_crit_ratio is not None else 0.0
        weather_comp = (weather_signal * weather_weight) * h_proj_factor if has_weather else 0.0

        task_penalty = 0.0
        if task_blockage is not None and task_blockage > 0.2:
            task_penalty = (task_blockage * 0.08) * (h_ratio - 0.5)

        net_velocity = (
            (rep_signal * 0.25 if has_reps else 0.0)
            + (sensor_velocity * 0.30 if sensor_velocity is not None else 0.0)
            + ((fld_worsening - 0.2) * 0.20 if fld_worsening is not None else 0.0)
            + ((mon_crit_ratio - 0.2) * 0.15 if mon_crit_ratio is not None else 0.0)
            + (weather_signal * weather_weight if has_weather else 0.0)
        )

        raw_projected = baseline_anchor + (net_velocity * h_proj_factor) + task_penalty
        CEILING = 0.98
        FLOOR = 0.05
        final_risk_score = round(max(FLOOR, min(CEILING, raw_projected)), 3)
        is_capped = bool(raw_projected >= CEILING)

        # -------------------------------------------------------------
        # 4. Trend Direction Classification
        # -------------------------------------------------------------
        if total_pts < 2 and not has_weather:
            trend = TrendDirection.UNKNOWN
        elif net_velocity >= 0.02:
            trend = TrendDirection.RISING
        elif net_velocity <= -0.02:
            trend = TrendDirection.FALLING
        else:
            trend = TrendDirection.STABLE

        risk_level = self._score_to_level(final_risk_score)

        # -------------------------------------------------------------
        # 5. Explainable Contributing Factors
        # -------------------------------------------------------------
        factors: List[str] = []
        if report_rate_change > 0.15:
            factors.append(f"↑ Report intake rate accelerating (+{report_rate_change:.0%})")
        elif report_rate_change < -0.15:
            factors.append(f"↓ Report intake rate decelerating ({report_rate_change:.0%})")

        if sensor_usable:
            if sensor_breach_ratio > 0.0:
                factors.append(f"IoT sensor threshold breach ({sensor_breach_ratio:.0%} breach ratio)")
            if sensor_trend > 0.02:
                factors.append(f"↑ Sensor telemetry showing rising trajectory (+{sensor_trend:.1%})")
            elif sensor_trend < -0.02:
                factors.append(f"↓ Sensor telemetry showing receding water level ({sensor_trend:.1%})")
            else:
                factors.append(f"→ Sensor telemetry showing steady water level ({sensor_trend:+.1%})")
            if sensor_alert_cnt > 0:
                factors.append(f"Active sensor threshold breach alerts ({int(sensor_alert_cnt)} active)")

        if fld_worsening is not None and fld_worsening > 0:
            factors.append("↑ Ground responder live verifications confirm worsening hazard conditions")

        if mon_crit_ratio is not None and mon_crit_ratio > 0:
            factors.append(f"↑ Live monitoring telemetry detected {mon_crit_ratio:.0%} high-impact operational changes")

        if task_blockage is not None and task_blockage > 0.25:
            factors.append(f"↑ Field task bottleneck pressure ({task_blockage:.0%} active tasks blocked)")

        # Weather Factor Explainability
        if has_weather and weather:
            f_p = matched_forecast_period.precipitation_mm if matched_forecast_period else weather.precipitation_mm
            f_pb = matched_forecast_period.precipitation_probability if matched_forecast_period else weather.precipitation_probability
            f_w = matched_forecast_period.wind_speed_mps if matched_forecast_period else weather.wind_speed_mps
            f_t = matched_forecast_period.temperature_c if matched_forecast_period else weather.temperature_c

            if em_type in ["FLOOD", "WATER_LOGGING", "DAM_BURST"] and f_p is not None and f_p > 0.2:
                factors.append(f"↑ Forecast precipitation (+{horizon_minutes}m: {f_p:.1f}mm rain, {f_pb or 0:.0f}% prob) elevates flood risk")
            elif em_type in ["CYCLONE", "STORM"] and f_w is not None and f_w > 10.0:
                factors.append(f"↑ High forecast wind speed (+{horizon_minutes}m: {f_w:.1f}m/s) intensifies cyclone hazard")
            elif em_type in ["HEATWAVE"] and f_t is not None and f_t > 38.0:
                factors.append(f"↑ Extreme ambient heat (+{horizon_minutes}m: {f_t:.1f}°C) elevates critical heatwave severity")
            elif weather.condition:
                factors.append(f"Atmospheric conditions ({weather.provider}): {weather.condition} ({weather.temperature_c or 'N/A'}°C, {weather.precipitation_mm or 0.0}mm/h rain)")

        if not factors:
            factors.append(f"Stable incident progression anchored to baseline operational severity ({raw_sev_score:.1f}/10)")

        # -------------------------------------------------------------
        # 6. Confidence Score & Limitations (Multi-Source Deduplicated)
        # -------------------------------------------------------------
        independent_sources = feature_set.independent_physical_sources_count
        base_confidence = 0.50
        if independent_sources >= 3 or total_pts >= 10:
            base_confidence += 0.30
        elif independent_sources >= 2 or total_pts >= 5:
            base_confidence += 0.20
        elif total_pts >= 2:
            base_confidence += 0.10

        if sensor_usable:
            base_confidence += 0.10
        if has_fld:
            base_confidence += 0.10
        if has_weather:
            base_confidence += 0.05

        confidence_score = round(max(0.30, min(0.95, base_confidence)), 2)
        confidence_label = "HIGH" if confidence_score >= 0.75 else ("MEDIUM" if confidence_score >= 0.55 else "LOW")

        limitations = list(feature_set.limitations)
        if horizon_minutes == 60 and total_pts < 5:
            limitations.append("60-minute forecast projection has elevated uncertainty due to limited long-term history.")
        if is_capped:
            limitations.append(f"Advisory risk score capped at safety ceiling ({CEILING}) while continuous raw projection is {raw_projected:.3f}.")

        return ForecastHorizonResult(
            horizon_minutes=horizon_minutes,
            risk_level=risk_level,
            risk_score=final_risk_score,
            raw_score=round(raw_projected, 3),
            projected_score=round(raw_projected, 3),
            is_capped=is_capped,
            ceiling_threshold=CEILING,
            trend=trend,
            data_status=data_status,
            confidence_score=confidence_score,
            confidence_label=confidence_label,
            contributing_factors=factors,
            limitations=limitations,
            weather_contribution=round(weather_comp, 3),
            sensor_contribution=round(sensor_comp, 3),
            incident_contribution=round(incident_comp, 3),
            field_contribution=round(field_comp, 3),
            monitoring_contribution=round(monitoring_comp, 3),
            task_contribution=round(task_penalty, 3),
            weather_forecast=matched_forecast_period,
        )

    def _score_to_level(self, score: float) -> str:
        if score >= 0.85:
            return EscalationRiskLevel.CRITICAL
        elif score >= 0.65:
            return EscalationRiskLevel.HIGH
        elif score >= 0.35:
            return EscalationRiskLevel.MEDIUM
        return EscalationRiskLevel.LOW
