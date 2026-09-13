# PREDICTIVE ANALYSIS — PHASE 1 ARCHITECTURE & SPECIFICATION
## Real-Data Predictive Intelligence Foundation

> **CRITICAL ARCHITECTURAL STATEMENT**:
> "Phase 1 uses a deterministic predictive model and does not claim machine-learned probability without sufficient calibrated training data."
> All forecasts are strictly derived from genuine persisted database records with transparent feature provenance and explicit data sufficiency evaluation.

---

## 1. Purpose & Objectives

The **Predictive Intelligence Engine (Phase 1)** provides advisory, evidence-backed forecasting of emergency incident escalation risk across configurable temporal horizons (15 minutes, 30 minutes, 60 minutes).

### Core Operational Principles
1. **Zero Dummy Data**: No mock records, synthetic seed trends, fabricated sensor readings, or placeholder charts are ever generated or returned. If data is sparse or absent, the system truthfully returns `INSUFFICIENT_DATA` or `NO_DATA`.
2. **Advisory Decision Support Only**: Predictions never automatically alter authoritative severity, change Needs Assessments, allocate resources, activate shelters, dispatch units, send public alerts, or close incidents. Human-in-the-loop Emergency Officer authority is 100% authoritative.
3. **No 10th Operational Agent**: Phase 1 is built as a modular service layer (`PredictiveService`) providing advisory context to existing components (`Situation Intelligence`, `PriorityAgent`, `Central Orchestrator`).
4. **Deterministic & Explainable**: Numeric risk scores ($0.0 \le \text{risk\_score} \le 1.0$) are calculated using reproducible mathematical formulas with full provenance for each feature.

---

## 2. Architecture & Data Flow

```
+-----------------------------------------------------------------------------------+
|                           GENUINE MONGODB PERSISTENCE                             |
|  - situations           - citizen_reports       - sensors & sensor_readings       |
|  - sensor_alerts        - field_verifications   - monitoring_events & impacts     |
|  - response_tasks       - timeline_events       - resource_allocations            |
+------------------------------------------+----------------------------------------+
                                           | (Bounded Time-Window Queries)
                                           v
+-----------------------------------------------------------------------------------+
|                    DETERMINISTIC FEATURE EXTRACTION LAYER                         |
|  - Report intake rate & acceleration (\Delta reports)                             |
|  - Sensor health gating (Healthy: 1.0, Stale: 0.5 discount, Inactive: Excluded)   |
|  - Sensor reading trajectory & active breach alert pressure                       |
|  - Field verification ground observations (Condition worsening ratio)            |
|  - Live monitoring invalidations & high-impact telemetry events                   |
|  - Operational response task blockage ratio & bottlenecks                         |
+------------------------------------------+----------------------------------------+
                                           |
                                           v
+-----------------------------------------------------------------------------------+
|                         DATA SUFFICIENCY ENGINE                                   |
|  Evaluates real evidence points:                                                  |
|  - NO_DATA              - INSUFFICIENT_DATA                                       |
|  - LIMITED_DATA         - SUFFICIENT_DATA                                         |
|  Distinguishes real zero vs missing sensors/verifications                         |
+------------------------------------------+----------------------------------------+
                                           |
                                           v
+-----------------------------------------------------------------------------------+
|                DETERMINISTIC ESCALATION PREDICTOR (Phase 1)                       |
|  - Dynamic normalized signal synthesis                                            |
|  - Horizon sensitivity modulation (15m: velocity, 30m: baseline, 60m: bottleneck) |
|  - Trend direction classifier: RISING | STABLE | FALLING | UNKNOWN                |
|  - Bounded Risk Score (0.0 to 1.0) -> LOW, MEDIUM, HIGH, CRITICAL                 |
+------------------------------------------+----------------------------------------+
                                           |
                                           v
+-----------------------------------------------------------------------------------+
|               AUTHENTICATED PREDICTIVE API & OFFICER UI                           |
|  - GET /api/v1/officer/predictive/incidents/{incident_id}                         |
|  - GET /api/v1/officer/predictive/incidents/{incident_id}/trend                   |
|  - GET /api/v1/officer/predictive/incidents/{incident_id}/features                |
|  - Embedded Predictive Intelligence Panel in Situation Details Console            |
+-----------------------------------------------------------------------------------+
```

---

## 3. Data Sources & Fields Used

| Domain Collection | Database Fields Evaluated | Purpose in Prediction |
| :--- | :--- | :--- |
| `situations` | `severity_score`, `severity_level`, `impact_zone.radius_km`, `estimated_affected_population`, `created_at` | Provides baseline severity anchor and spatial footprint. |
| `citizen_reports` | `created_at`, `citizen_impact_level`, `priority`, `emergency_type` | Computes report intake velocity, acceleration, and critical report ratios. |
| `sensors` & `sensor_readings` | `value`, `threshold`, `is_breach`, `timestamp`, `health_state`, `reporting_state`, `status`, `coverage` | Evaluates physical IoT telemetry trajectory and threshold breaches with sensor health gating. |
| `sensor_alerts` | `alert_id`, `status`, `threshold`, `current_value`, `created_at` | Tracks active critical hazard breaches in the incident area. |
| `field_verifications` | `verification_status`, `observation_category`, `submitted_at`, `notes` | Captures ground responder condition worsening vs confirmation signals. |
| `monitoring_events` | `event_type`, `impact_level`, `plan_status`, `detected_at` | Measures telemetry event frequency and operational plan invalidations. |
| `response_tasks` | `status` (`IN_PROGRESS`, `PENDING`, `BLOCKED`, `FAILED`) | Measures task blockage ratio and responder bottleneck pressure. |

---

## 4. Feature Engineering & Provenance

Every extracted feature includes deterministic metadata:
```json
{
  "name": "report_rate_change",
  "value": 0.50,
  "source": "citizen_reports",
  "time_window": "60m",
  "data_points": 4,
  "description": "Temporal acceleration in report intake (recent half: 3 vs early half: 1)"
}
```

### Calculated Features
1. `incident_report_count`: Total reports within historical window $[t - W, t]$.
2. `report_rate_change`: Relative velocity comparing recent half of window $[t - \frac{W}{2}, t]$ against early half $[t - W, t - \frac{W}{2}]$:
   $$\Delta_{\text{rep}} = \frac{N_{\text{recent}} - N_{\text{early}}}{N_{\text{recent}} + N_{\text{early}}}$$
3. `critical_report_ratio`: Proportion of reports with `CRITICAL` or `HIGH` citizen impact.
4. `sensor_breach_ratio`: Proportion of sensor readings exceeding alert thresholds.
5. `sensor_reading_trend`: Normalized trajectory of numeric sensor readings over time.
6. `field_condition_worsening_ratio`: Ground reports flagging `CONDITION_CHANGED` or worsening hazard.
7. `critical_monitoring_impact_ratio`: Ratio of monitoring telemetry events triggering high/critical operational impact.
8. `task_blockage_ratio`: Proportion of active response tasks currently `BLOCKED`.

---

## 5. Sensor Health & Stale Data Intelligence Gating

IoT sensors are filtered through the canonical **Sensor Health** rules:
- **HEALTHY** sensors: Full evidentiary contribution ($w_{\text{sensor}} = 1.0$).
- **STALE** sensors ($> 5$ minutes since reading): Evidentiary weight discounted by 50% ($w_{\text{sensor}} = 0.5$). Explicit limitation warning added to forecast.
- **INACTIVE / UNAVAILABLE / NEVER_REPORTED**: Excluded entirely ($w_{\text{sensor}} = 0.0$).

---

## 6. Trend Detection & Risk Scoring

### Trend Direction Classification
- **RISING**: Net positive momentum ($> +0.12$) or accelerating report rate ($> +20\%$).
- **FALLING**: Net negative momentum ($< -0.15$) or decelerating report rate ($< -25\%$).
- **STABLE**: Rate of change within $[-0.15, +0.12]$.
- **UNKNOWN**: Insufficient data points ($< 2$) to establish direction.

### Normalized Risk Score Formula
The escalation risk score is computed by synthesizing available weighted signals:

$$\text{Risk Score} = \frac{w_0 S_{\text{base}} + w_{\text{rep}} S_{\text{rep}} + w_{\text{sns}} S_{\text{sns}} + w_{\text{fld}} S_{\text{fld}} + w_{\text{mon}} S_{\text{mon}} + w_{\text{tsk}} S_{\text{tsk}}}{\sum w_i} \times H_{\text{factor}}$$

Where:
- $S_{\text{base}} = \frac{\text{Authoritative Severity Score}}{10.0}$
- $H_{\text{factor}}$ adjusts sensitivity for forecast horizon (15m, 30m, 60m).
- Score is bounded in $[0.05, 0.98]$ and mapped to qualitative risk levels:

| Risk Score Range | Escalation Risk Level |
| :--- | :--- |
| $0.00 \le \text{score} < 0.35$ | **LOW** |
| $0.35 \le \text{score} < 0.65$ | **MEDIUM** |
| $0.65 \le \text{score} < 0.85$ | **HIGH** |
| $0.85 \le \text{score} \le 1.00$ | **CRITICAL** |

---

## 7. Data Sufficiency States

| State | Criterion | Action |
| :--- | :--- | :--- |
| `NO_DATA` | 0 database records found for incident in window. | Risk score = 0.0, trend = `UNKNOWN`, honest empty state. |
| `INSUFFICIENT_DATA` | Exactly 1 static record or 0 temporal velocity points. | Baseline severity mapped directly, trend = `UNKNOWN`, confidence = LOW (0.20). |
| `LIMITED_DATA` | 2–4 records with single source domain. | Advisory forecast returned with constrained confidence ($< 0.55$) and limitation notice. |
| `SUFFICIENT_DATA` | $\ge 5$ records or multi-source corroborated evidence. | Full forecast across all horizons with high confidence. |

---

## 8. Forecast Horizons Supported

1. **15 Minutes**: High sensitivity to immediate intake rate and physical sensor velocity.
2. **30 Minutes (Standard)**: Balanced synthesis of trend velocity and sustained situational pressure.
3. **60 Minutes**: Incorporates prolonged task bottlenecks and cumulative area expansion. Returns `INSUFFICIENT_DATA` if long-term historical records are unavailable.

---

## 9. Human-in-the-Loop & Safety Boundaries

Predictive Analysis is strictly advisory:
- **Zero Automated Severity Overrides**: Does not modify `severity_score` or `severity_level` in `situations`.
- **Zero Resource Actions**: Does not allocate resources, modify inventory, or consume supplies.
- **Zero Operational Dispatches**: Does not dispatch volunteers or field response units.
- **Zero Public Alerts**: Does not send automated SMS or WhatsApp notifications.

---

## 10. API Specification

### Endpoints
- `GET /api/v1/officer/predictive/incidents/{incident_id}?window_minutes=60&horizon_minutes=30`
- `GET /api/v1/officer/predictive/incidents/{incident_id}/trend?window_minutes=60`
- `GET /api/v1/officer/predictive/incidents/{incident_id}/features?window_minutes=60`
- `GET /api/v1/officer/predictive/health`

### Sample Response Contract
```json
{
  "incident_id": "SIT-884A29BC",
  "incident_title": "Urban Flood Surge Monitoring",
  "emergency_type": "FLOOD",
  "prediction_status": "AVAILABLE",
  "data_status": "SUFFICIENT_DATA",
  "current_authoritative_severity": "HIGH",
  "current_severity_score": 7.5,
  "is_officer_override": false,
  "forecast": {
    "horizon_minutes": 30,
    "risk_level": "HIGH",
    "risk_score": 0.78,
    "trend": "RISING",
    "data_status": "SUFFICIENT_DATA",
    "confidence_score": 0.85,
    "confidence_label": "HIGH",
    "contributing_factors": [
      "↑ Report frequency accelerating (+50% intake rate)",
      "↑ Corroborating IoT sensors in breach (100% reading breach ratio)"
    ],
    "limitations": []
  },
  "horizons": {
    "15m": { "horizon_minutes": 15, "risk_level": "HIGH", "risk_score": 0.82, "trend": "RISING" },
    "30m": { "horizon_minutes": 30, "risk_level": "HIGH", "risk_score": 0.78, "trend": "RISING" },
    "60m": { "horizon_minutes": 60, "risk_level": "HIGH", "risk_score": 0.76, "trend": "RISING" }
  },
  "features": [
    {
      "name": "report_rate_change",
      "value": 0.5,
      "source": "citizen_reports",
      "time_window": "60m",
      "data_points": 3
    }
  ],
  "missing_features": [],
  "evidence": [
    {
      "source_type": "CITIZEN_REPORT",
      "source_id": "REP-2",
      "timestamp": "2026-09-13T10:45:00Z",
      "contribution": "Recent report intake flagging CRITICAL impact",
      "weight": 0.85
    }
  ],
  "data_points_used": {
    "citizen_reports": 3,
    "sensors": 1,
    "sensor_readings": 4,
    "sensor_alerts": 1,
    "field_verifications": 0,
    "monitoring_events": 0,
    "response_tasks": 0
  },
  "historical_window_minutes": 60,
  "model": {
    "name": "deterministic_escalation_v1",
    "version": "1.0",
    "type": "Deterministic Predictive Intelligence Engine",
    "method": "Temporal Rate & Weighted Multi-Source Signal Synthesis"
  },
  "advisory_notice": "ADVISORY ONLY: Predictive Analysis estimates escalation risk from genuine temporal trends. It does NOT automatically change authoritative severity, allocate resources, or dispatch responders. Emergency Officer verification remains mandatory.",
  "generated_at": "2026-09-13T11:00:00Z"
}
```

---

## 11. UI Architecture

The **Predictive Intelligence Panel** is seamlessly embedded into `SituationDetailsModal.tsx` and adheres strictly to the approved Resilience UI design system:
- **Color Tokens**: Semantic emergency indicators (Emerald for Low, Blue for Stable, Yellow for Medium, Amber for High, Red for Critical).
- **Controls**: Interactive Forecast Horizon tabs (15m, 30m, 60m) and Historical Window selector (60m, 6h, 24h).
- **Current State vs Predicted Future State**: Visual card pairing with clear visual hierarchy separating officer authority from advisory forecast.
- **Why This Prediction**: Bulleted list of human-readable contributing signals with provenance.
- **Data Points Evaluated**: Transparent record count cards.
- **Honest Empty State**: Informative fallback banner explaining lack of historical data without fake charts.

---

## 12. Future Phase 2 ML Roadmap

The system is designed with abstract interfaces (`PredictiveFeatureProvider`, `PredictiveModel`) enabling seamless Phase 2 integration without API schema breaking changes:
1. **Calibrated Machine Learning Models**: Gradient boosting / time-series models trained on verified historical incident datasets.
2. **Resource Demand Forecasting**: Quantitative prediction of needed medical supplies, potable water, and rescue boats based on incident expansion trajectories.
3. **Shelter Occupancy Dynamics**: Arrival rate forecasting for active evacuation zones.
4. **Spatial Hazard Dispersion**: Geospatial spread simulation linking weather forecasts and terrain elevation models.
