from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongodb import get_database
from app.api.deps import require_officer
from app.models.user import UserResponse
from app.models.analytics import (
    AnalyticsTimeRange,
    EmergencyAnalyticsOverview,
    ResponseMilestoneTimeline,
    BottleneckInsight,
    ResourceUtilizationAnalytics,
    ShelterAnalytics,
    HealthcareAnalytics,
    VolunteerPerformanceAnalytics,
    FleetAnalytics,
    ReplanningIntelligence,
    IncidentComparisonResponse,
    DecisionSupportResponse,
    PostIncidentIntelligence,
)
from app.services.analytics_service import AnalyticsService

router = APIRouter()


@router.get("/overview", response_model=EmergencyAnalyticsOverview)
async def get_analytics_overview(
    time_range: AnalyticsTimeRange = Query(AnalyticsTimeRange.ALL_TIME),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    disaster_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Get consolidated Emergency Intelligence & Analytics overview directly from MongoDB Atlas.
    """
    return await AnalyticsService.get_overview(
        db=db,
        time_range=time_range,
        start_date=start_date,
        end_date=end_date,
        disaster_type=disaster_type,
        severity=severity,
        zone=zone,
    )


@router.get("/milestones", response_model=ResponseMilestoneTimeline)
async def get_response_milestones(
    time_range: AnalyticsTimeRange = Query(AnalyticsTimeRange.ALL_TIME),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    disaster_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Get step-by-step response milestone duration distributions (min, median, avg, max).
    """
    return await AnalyticsService.get_milestones(
        db=db,
        time_range=time_range,
        start_date=start_date,
        end_date=end_date,
        disaster_type=disaster_type,
        severity=severity,
        zone=zone,
    )


@router.get("/bottlenecks", response_model=List[BottleneckInsight])
async def get_response_bottlenecks(
    time_range: AnalyticsTimeRange = Query(AnalyticsTimeRange.ALL_TIME),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    disaster_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Get detected response bottlenecks with empirical evidence and actionable recommendations.
    """
    return await AnalyticsService.get_bottlenecks(
        db=db,
        time_range=time_range,
        start_date=start_date,
        end_date=end_date,
        disaster_type=disaster_type,
        severity=severity,
        zone=zone,
    )


@router.get("/resources", response_model=ResourceUtilizationAnalytics)
async def get_resource_utilization(
    time_range: AnalyticsTimeRange = Query(AnalyticsTimeRange.ALL_TIME),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    disaster_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Get supply stockpile utilization, consumption, and category breakdown.
    """
    return await AnalyticsService.get_resource_analytics(
        db=db,
        time_range=time_range,
        start_date=start_date,
        end_date=end_date,
        disaster_type=disaster_type,
        severity=severity,
        zone=zone,
    )


@router.get("/shelters", response_model=ShelterAnalytics)
async def get_shelter_utilization(
    time_range: AnalyticsTimeRange = Query(AnalyticsTimeRange.ALL_TIME),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    disaster_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Get shelter capacity, current occupancy, and displaced population relief stats.
    """
    return await AnalyticsService.get_shelter_analytics(
        db=db,
        time_range=time_range,
        start_date=start_date,
        end_date=end_date,
        disaster_type=disaster_type,
        severity=severity,
        zone=zone,
    )


@router.get("/healthcare", response_model=HealthcareAnalytics)
async def get_healthcare_utilization(
    time_range: AnalyticsTimeRange = Query(AnalyticsTimeRange.ALL_TIME),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    disaster_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Get hospital bed availability, ICU occupancy, and patient evacuation demand.
    """
    return await AnalyticsService.get_healthcare_analytics(
        db=db,
        time_range=time_range,
        start_date=start_date,
        end_date=end_date,
        disaster_type=disaster_type,
        severity=severity,
        zone=zone,
    )


@router.get("/volunteers", response_model=VolunteerPerformanceAnalytics)
async def get_volunteer_performance(
    time_range: AnalyticsTimeRange = Query(AnalyticsTimeRange.ALL_TIME),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    disaster_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Get volunteer responder mission performance, completion rates, and skill demands.
    """
    return await AnalyticsService.get_volunteer_analytics(
        db=db,
        time_range=time_range,
        start_date=start_date,
        end_date=end_date,
        disaster_type=disaster_type,
        severity=severity,
        zone=zone,
    )


@router.get("/fleet", response_model=FleetAnalytics)
async def get_fleet_performance(
    time_range: AnalyticsTimeRange = Query(AnalyticsTimeRange.ALL_TIME),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    disaster_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Get emergency vehicle fleet utilization, route disruptions, and transit metrics.
    """
    return await AnalyticsService.get_fleet_analytics(
        db=db,
        time_range=time_range,
        start_date=start_date,
        end_date=end_date,
        disaster_type=disaster_type,
        severity=severity,
        zone=zone,
    )


@router.get("/replanning", response_model=ReplanningIntelligence)
async def get_replanning_intelligence(
    time_range: AnalyticsTimeRange = Query(AnalyticsTimeRange.ALL_TIME),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    disaster_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Get monitoring event statistics, impactful event triggers, and plan revision dynamics.
    """
    return await AnalyticsService.get_replanning_analytics(
        db=db,
        time_range=time_range,
        start_date=start_date,
        end_date=end_date,
        disaster_type=disaster_type,
        severity=severity,
        zone=zone,
    )


@router.get("/comparison", response_model=IncidentComparisonResponse)
async def get_incident_comparison(
    dimension: str = Query("emergency_type", pattern="^(emergency_type|severity_level|zone)$"),
    time_range: AnalyticsTimeRange = Query(AnalyticsTimeRange.ALL_TIME),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    disaster_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Get comparative analytics across disaster types, severity levels, or operational zones.
    """
    return await AnalyticsService.get_incident_comparison(
        db=db,
        dimension=dimension,
        time_range=time_range,
        start_date=start_date,
        end_date=end_date,
        disaster_type=disaster_type,
        severity=severity,
        zone=zone,
    )


@router.get("/decision-support", response_model=DecisionSupportResponse)
async def get_decision_support_signals(
    time_range: AnalyticsTimeRange = Query(AnalyticsTimeRange.ALL_TIME),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    disaster_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Get real-time deterministic decision support advisory alerts and recommendations.
    """
    return await AnalyticsService.get_decision_support(
        db=db,
        time_range=time_range,
        start_date=start_date,
        end_date=end_date,
        disaster_type=disaster_type,
        severity=severity,
        zone=zone,
    )


@router.get("/post-incident/{situation_id}", response_model=PostIncidentIntelligence)
async def get_post_incident_intelligence(
    situation_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Get authoritative 12-factor post-incident debrief intelligence for a resolved situation.
    """
    result = await AnalyticsService.get_post_incident_intelligence(db=db, situation_id=situation_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Situation {situation_id} not found.",
        )
    return result
