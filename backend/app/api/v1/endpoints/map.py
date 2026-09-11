from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.db.mongodb import get_database
from app.api.deps import require_officer
from app.models.user import UserResponse
from app.models.enums import EmergencyType, SeverityLevel
from app.models.map import PublicActiveHotspotsResponse, OfficerMapDataResponse
from app.services.map_service import MapService

router = APIRouter()


@router.get("/active-hotspots", response_model=PublicActiveHotspotsResponse)
async def get_public_active_hotspots(
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Public-safe real-time active emergency hotspots from MongoDB Atlas.
    Strictly excludes resolved/closed incidents and strips all personal and operational details.
    """
    return await MapService.get_public_active_hotspots(db=db)


@router.get("/officer/data", response_model=OfficerMapDataResponse)
@router.get("/officer/active-incidents", response_model=OfficerMapDataResponse)
async def get_officer_map_data(
    view_mode: str = Query("active", description="Filter map layers: 'active', 'history', or 'all'"),
    emergency_type: Optional[EmergencyType] = None,
    severity_level: Optional[SeverityLevel] = None,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_officer),
):
    """
    Authorized geospatial map feed for emergency officers and operational commanders.
    Partitioned into active operations vs historical archive.
    """
    return await MapService.get_officer_map_data(
        view_mode=view_mode,
        emergency_type=emergency_type,
        severity_level=severity_level,
        db=db,
    )
