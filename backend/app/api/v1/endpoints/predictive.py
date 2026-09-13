import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongodb import get_database
from app.api.deps import require_officer
from app.models.user import UserResponse
from app.models.predictive import (
    IncidentPredictionResponse,
    PredictiveTrendResponse,
    PredictiveFeaturesResponse,
    PredictiveHealthResponse,
)
from app.services.predictive.predictive_service import predictive_service

logger = logging.getLogger("resilience.predictive.api")
router = APIRouter()


@router.get(
    "/incidents/{incident_id}",
    response_model=IncidentPredictionResponse,
    summary="Get Deterministic Incident Escalation Forecast",
    description=(
        "Returns advisory escalation risk predictions across multiple horizons (15m, 30m, 60m) "
        "derived strictly from genuine persisted database records. Strict zero-dummy-data and non-mutation guarantees."
    ),
)
async def get_incident_prediction(
    incident_id: str,
    window_minutes: int = Query(60, ge=15, le=1440, description="Historical observation window in minutes (15m to 24h)"),
    horizon_minutes: int = Query(30, ge=15, le=60, description="Primary forecast horizon (15, 30, or 60 minutes)"),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    try:
        prediction = await predictive_service.get_incident_prediction(
            db=db,
            incident_id=incident_id,
            window_minutes=window_minutes,
            forecast_horizon_minutes=horizon_minutes,
        )
        return prediction
    except Exception as e:
        logger.error(f"Error computing prediction for incident {incident_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate predictive intelligence: {str(e)}",
        )


@router.get(
    "/incidents/{incident_id}/trend",
    response_model=PredictiveTrendResponse,
    summary="Get Incident Escalation Temporal Progression & Horizon Trend",
    description="Returns current authoritative baseline along with computed 15m, 30m, and 60m projection points.",
)
async def get_incident_trend(
    incident_id: str,
    window_minutes: int = Query(60, ge=15, le=1440),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    try:
        return await predictive_service.get_incident_trend(
            db=db,
            incident_id=incident_id,
            window_minutes=window_minutes,
        )
    except Exception as e:
        logger.error(f"Error computing trend for incident {incident_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to extract predictive trend: {str(e)}",
        )


@router.get(
    "/incidents/{incident_id}/features",
    response_model=PredictiveFeaturesResponse,
    summary="Get Explainable Feature Provenance",
    description="Returns all extracted features with exact record counts and database source provenance.",
)
async def get_incident_features(
    incident_id: str,
    window_minutes: int = Query(60, ge=15, le=1440),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    try:
        return await predictive_service.get_incident_features(
            db=db,
            incident_id=incident_id,
            window_minutes=window_minutes,
        )
    except Exception as e:
        logger.error(f"Error extracting features for incident {incident_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to extract predictive features: {str(e)}",
        )


@router.get(
    "/health",
    response_model=PredictiveHealthResponse,
    summary="Predictive Intelligence Health Check",
    description="Returns operational status of the predictive engine and data pipelines.",
)
async def get_predictive_health(
    current_user: UserResponse = Depends(require_officer),
):
    return predictive_service.get_health()
