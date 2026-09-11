import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongodb import get_database
from app.api.deps import require_resource_manager, get_current_user
from app.models.user import UserResponse
from app.models.enums import (
    TimelineEventType,
    MonitoringEventType,
    EventSourceType,
    UserRole,
)
from app.models.healthcare import (
    HealthcareFacilityType,
    HealthcareOperationalStatus,
    HealthcareCapabilities,
    HealthcareLocation,
    HealthcareFacilityCreate,
    HealthcareFacilityUpdate,
    HealthcareCapacityUpdate,
    HealthcareFacilityResponse,
    PaginatedHealthcareFacilitiesResponse,
    HealthcareStatsResponse,
)
from app.services.monitoring.monitoring_service import MonitoringService
from app.services.timeline import record_timeline_event

logger = logging.getLogger("resilience.healthcare")
router = APIRouter()


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
    return dt


def generate_facility_id() -> str:
    return f"HCF-{uuid.uuid4().hex[:6].upper()}"


def serialize_facility_doc(doc: Dict[str, Any]) -> HealthcareFacilityResponse:
    total_beds = int(doc.get("total_beds", 0))
    occupied_beds = int(doc.get("occupied_beds", 0))
    avail_beds = max(0, total_beds - occupied_beds)
    bed_rate = round((occupied_beds / total_beds * 100.0), 1) if total_beds > 0 else 0.0

    total_icu = int(doc.get("total_icu_beds", 0))
    occupied_icu = int(doc.get("occupied_icu_beds", 0))
    avail_icu = max(0, total_icu - occupied_icu)
    icu_rate = round((occupied_icu / total_icu * 100.0), 1) if total_icu > 0 else 0.0

    total_em = int(doc.get("total_emergency_beds", 0))
    occupied_em = int(doc.get("occupied_emergency_beds", 0))
    avail_em = max(0, total_em - occupied_em)
    em_rate = round((occupied_em / total_em * 100.0), 1) if total_em > 0 else 0.0

    v_total = int(doc.get("ventilators_total", 0))
    v_avail = int(doc.get("ventilators_available", v_total))

    ox_total = int(doc.get("oxygen_supported_beds", 0))
    ox_avail = int(doc.get("oxygen_available_capacity", ox_total))

    loc_dict = doc.get("location", {})
    if not isinstance(loc_dict, dict):
        loc_dict = {}

    location = HealthcareLocation(
        latitude=float(loc_dict.get("latitude", 12.9716)),
        longitude=float(loc_dict.get("longitude", 77.5946)),
        address=str(loc_dict.get("address", "Designated Healthcare Facility")),
        city=str(loc_dict.get("city", "Bangalore")),
        district=str(loc_dict.get("district", "Urban")),
        state=str(loc_dict.get("state", "Karnataka")),
        country=str(loc_dict.get("country", "India")),
        postal_code=str(loc_dict.get("postal_code", "560001")),
        zone=str(loc_dict.get("zone", "Central")),
    )

    caps_dict = doc.get("capabilities", {})
    if not isinstance(caps_dict, dict):
        caps_dict = {}

    capabilities = HealthcareCapabilities(
        emergency_care=bool(caps_dict.get("emergency_care", True)),
        trauma_care=bool(caps_dict.get("trauma_care", False)),
        icu=bool(caps_dict.get("icu", total_icu > 0)),
        surgery=bool(caps_dict.get("surgery", False)),
        oxygen_support=bool(caps_dict.get("oxygen_support", ox_total > 0)),
        ventilator_support=bool(caps_dict.get("ventilator_support", v_total > 0)),
        ambulance_support=bool(caps_dict.get("ambulance_support", False)),
        pediatric_care=bool(caps_dict.get("pediatric_care", False)),
        burn_unit=bool(caps_dict.get("burn_unit", False)),
        other_capabilities=caps_dict.get("other_capabilities", []),
    )

    created_at = ensure_utc(doc.get("created_at")) or datetime.now(timezone.utc)
    updated_at = ensure_utc(doc.get("updated_at")) or datetime.now(timezone.utc)
    last_updated = ensure_utc(doc.get("last_updated")) or updated_at

    return HealthcareFacilityResponse(
        _id=str(doc.get("_id", "")),
        facility_id=str(doc.get("facility_id", "")),
        facility_name=str(doc.get("facility_name") or doc.get("name", "Healthcare Facility")),
        facility_type=HealthcareFacilityType(doc.get("facility_type", HealthcareFacilityType.HOSPITAL.value)),
        location=location,
        total_beds=total_beds,
        occupied_beds=occupied_beds,
        available_beds=avail_beds,
        bed_occupancy_rate=bed_rate,
        total_icu_beds=total_icu,
        occupied_icu_beds=occupied_icu,
        available_icu_beds=avail_icu,
        icu_occupancy_rate=icu_rate,
        total_emergency_beds=total_em,
        occupied_emergency_beds=occupied_em,
        available_emergency_beds=avail_em,
        emergency_occupancy_rate=em_rate,
        ventilators_total=v_total,
        ventilators_available=v_avail,
        oxygen_supported_beds=ox_total,
        oxygen_available_capacity=ox_avail,
        capabilities=capabilities,
        status=HealthcareOperationalStatus(doc.get("status", HealthcareOperationalStatus.ACTIVE.value)),
        condition=str(doc.get("condition", "EXCELLENT")),
        accessibility=str(doc.get("accessibility", "FULLY_ACCESSIBLE")),
        contact_phone=doc.get("contact_phone"),
        contact_email=doc.get("contact_email"),
        operating_hours=str(doc.get("operating_hours", "24/7")),
        created_by_id=doc.get("created_by_id"),
        created_by_name=doc.get("created_by_name"),
        last_updated_by_id=doc.get("last_updated_by_id"),
        last_updated_by_name=doc.get("last_updated_by_name"),
        last_updated=last_updated,
        created_at=created_at,
        updated_at=updated_at,
    )


@router.get("/facilities", response_model=PaginatedHealthcareFacilitiesResponse)
async def list_healthcare_facilities(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search by facility name or address"),
    district: Optional[str] = Query(None, description="Filter by district"),
    zone: Optional[str] = Query(None, description="Filter by zone"),
    facility_type: Optional[HealthcareFacilityType] = Query(None, description="Filter by facility type"),
    status: Optional[HealthcareOperationalStatus] = Query(None, description="Filter by status"),
    trauma_capable: Optional[bool] = Query(None, description="Filter trauma capable"),
    icu_capable: Optional[bool] = Query(None, description="Filter ICU capable"),
    oxygen_capable: Optional[bool] = Query(None, description="Filter oxygen capable"),
    min_available_beds: Optional[int] = Query(None, ge=0, description="Filter minimum available general beds"),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(get_current_user),
):
    query: Dict[str, Any] = {"is_deleted": {"$ne": True}}

    if search:
        search_regex = {"$regex": search.strip(), "$options": "i"}
        query["$or"] = [
            {"facility_name": search_regex},
            {"name": search_regex},
            {"location.address": search_regex},
            {"location.city": search_regex},
            {"location.district": search_regex},
            {"facility_id": search_regex},
        ]

    if district:
        query["location.district"] = {"$regex": f"^{district.strip()}$", "$options": "i"}

    if zone:
        query["location.zone"] = {"$regex": f"^{zone.strip()}$", "$options": "i"}

    if facility_type:
        query["facility_type"] = facility_type.value

    if status:
        query["status"] = status.value

    if trauma_capable is not None:
        query["capabilities.trauma_care"] = trauma_capable

    if icu_capable is not None:
        query["capabilities.icu"] = icu_capable

    if oxygen_capable is not None:
        query["capabilities.oxygen_support"] = oxygen_capable

    if min_available_beds is not None:
        query["$expr"] = {"$gte": [{"$subtract": ["$total_beds", "$occupied_beds"]}, min_available_beds]}

    total_count = await db["healthcare_facilities"].count_documents(query)
    total_pages = max(1, math.ceil(total_count / limit))
    skip = (page - 1) * limit

    cursor = db["healthcare_facilities"].find(query).sort("created_at", -1).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)

    items = [serialize_facility_doc(d) for d in docs]

    return PaginatedHealthcareFacilitiesResponse(
        items=items,
        total_count=total_count,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@router.get("/facilities/stats", response_model=HealthcareStatsResponse)
async def get_healthcare_stats(
    district: Optional[str] = Query(None),
    zone: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(get_current_user),
):
    query: Dict[str, Any] = {"is_deleted": {"$ne": True}}
    if district:
        query["location.district"] = {"$regex": f"^{district.strip()}$", "$options": "i"}
    if zone:
        query["location.zone"] = {"$regex": f"^{zone.strip()}$", "$options": "i"}

    cursor = db["healthcare_facilities"].find(query)
    
    total_fac = 0
    active_fac = 0
    tot_beds = 0
    occ_beds = 0
    tot_icu = 0
    occ_icu = 0
    tot_em = 0
    occ_em = 0
    tot_vent = 0
    avail_vent = 0
    tot_ox = 0
    avail_ox = 0

    async for doc in cursor:
        total_fac += 1
        st = str(doc.get("status", "ACTIVE")).upper()
        if st in ["ACTIVE", "OPERATIONAL", "AVAILABLE"]:
            active_fac += 1
        
        tb = int(doc.get("total_beds", 0))
        ob = int(doc.get("occupied_beds", 0))
        tot_beds += tb
        occ_beds += ob
        
        ti = int(doc.get("total_icu_beds", 0))
        oi = int(doc.get("occupied_icu_beds", 0))
        tot_icu += ti
        occ_icu += oi
        
        te = int(doc.get("total_emergency_beds", 0))
        oe = int(doc.get("occupied_emergency_beds", 0))
        tot_em += te
        occ_em += oe
        
        tv = int(doc.get("ventilators_total", 0))
        av = int(doc.get("ventilators_available", tv))
        tot_vent += tv
        avail_vent += av
        
        to = int(doc.get("oxygen_supported_beds", 0))
        ao = int(doc.get("oxygen_available_capacity", to))
        tot_ox += to
        avail_ox += ao

    avail_beds = max(0, tot_beds - occ_beds)
    avail_icu = max(0, tot_icu - occ_icu)
    avail_em = max(0, tot_em - occ_em)
    
    bed_util = round((occ_beds / tot_beds * 100.0), 1) if tot_beds > 0 else 0.0
    icu_util = round((occ_icu / tot_icu * 100.0), 1) if tot_icu > 0 else 0.0

    return HealthcareStatsResponse(
        total_facilities=total_fac,
        active_facilities=active_fac,
        total_available_beds=avail_beds,
        total_occupied_beds=occ_beds,
        total_beds=tot_beds,
        available_icu_beds=avail_icu,
        total_icu_beds=tot_icu,
        available_emergency_beds=avail_em,
        total_emergency_beds=tot_em,
        available_ventilators=avail_vent,
        total_ventilators=tot_vent,
        available_oxygen_capacity=avail_ox,
        total_oxygen_supported_beds=tot_ox,
        overall_bed_utilization=bed_util,
        overall_icu_utilization=icu_util,
    )


@router.get("/facilities/{facility_id}", response_model=HealthcareFacilityResponse)
async def get_healthcare_facility(
    facility_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(get_current_user),
):
    query: Dict[str, Any] = {
        "$and": [
            {"is_deleted": {"$ne": True}},
            {
                "$or": [
                    {"facility_id": facility_id},
                    {"facility_id": facility_id.strip().upper()},
                ]
            },
        ]
    }
    if ObjectId.is_valid(facility_id):
        query["$and"][1]["$or"].append({"_id": ObjectId(facility_id)})

    doc = await db["healthcare_facilities"].find_one(query)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Healthcare facility '{facility_id}' not found",
        )

    return serialize_facility_doc(doc)


@router.post("/facilities", response_model=HealthcareFacilityResponse, status_code=status.HTTP_201_CREATED)
async def create_healthcare_facility(
    payload: HealthcareFacilityCreate,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_resource_manager),
):
    # Enforce derived availability and consistency
    if payload.occupied_beds > payload.total_beds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Occupied beds ({payload.occupied_beds}) cannot exceed total beds ({payload.total_beds})",
        )
    if payload.occupied_icu_beds > payload.total_icu_beds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Occupied ICU beds ({payload.occupied_icu_beds}) cannot exceed total ICU beds ({payload.total_icu_beds})",
        )
    if payload.occupied_emergency_beds > payload.total_emergency_beds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Occupied emergency beds ({payload.occupied_emergency_beds}) cannot exceed total emergency beds ({payload.total_emergency_beds})",
        )

    now = datetime.now(timezone.utc)
    fac_id = generate_facility_id()

    # Ensure unique facility_id
    while await db["healthcare_facilities"].find_one({"facility_id": fac_id}):
        fac_id = generate_facility_id()

    doc = {
        "facility_id": fac_id,
        "facility_name": payload.facility_name.strip(),
        "facility_type": payload.facility_type.value,
        "location": payload.location.model_dump(),
        "total_beds": payload.total_beds,
        "occupied_beds": payload.occupied_beds,
        "available_beds": max(0, payload.total_beds - payload.occupied_beds),
        "total_icu_beds": payload.total_icu_beds,
        "occupied_icu_beds": payload.occupied_icu_beds,
        "available_icu_beds": max(0, payload.total_icu_beds - payload.occupied_icu_beds),
        "total_emergency_beds": payload.total_emergency_beds,
        "occupied_emergency_beds": payload.occupied_emergency_beds,
        "available_emergency_beds": max(0, payload.total_emergency_beds - payload.occupied_emergency_beds),
        "ventilators_total": payload.ventilators_total,
        "ventilators_available": payload.ventilators_available if payload.ventilators_available is not None else payload.ventilators_total,
        "oxygen_supported_beds": payload.oxygen_supported_beds,
        "oxygen_available_capacity": payload.oxygen_available_capacity if payload.oxygen_available_capacity is not None else payload.oxygen_supported_beds,
        "capabilities": payload.capabilities.model_dump(),
        "status": payload.status.value,
        "condition": payload.condition,
        "accessibility": payload.accessibility,
        "contact_phone": payload.contact_phone,
        "contact_email": payload.contact_email,
        "operating_hours": payload.operating_hours,
        "created_by_id": current_user.id,
        "created_by_name": current_user.full_name,
        "last_updated_by_id": current_user.id,
        "last_updated_by_name": current_user.full_name,
        "is_deleted": False,
        "created_at": now,
        "updated_at": now,
        "last_updated": now,
    }

    res = await db["healthcare_facilities"].insert_one(doc)
    doc["_id"] = res.inserted_id

    await record_timeline_event(
        db=db,
        report_id=fac_id,
        event_type=TimelineEventType.HEALTHCARE_FACILITY_CREATED,
        details=f"Healthcare facility '{payload.facility_name}' ({fac_id}) registered with {payload.total_beds} total beds ({max(0, payload.total_beds - payload.occupied_beds)} available) and {payload.total_icu_beds} ICU beds.",
        actor_id=current_user.id,
        actor_name=current_user.full_name,
        actor_role=current_user.role,
    )

    return serialize_facility_doc(doc)


@router.patch("/facilities/{facility_id}/capacity", response_model=HealthcareFacilityResponse)
async def update_healthcare_capacity(
    facility_id: str,
    payload: HealthcareCapacityUpdate,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_resource_manager),
):
    query: Dict[str, Any] = {
        "$and": [
            {"is_deleted": {"$ne": True}},
            {
                "$or": [
                    {"facility_id": facility_id},
                    {"facility_id": facility_id.strip().upper()},
                ]
            },
        ]
    }
    if ObjectId.is_valid(facility_id):
        query["$and"][1]["$or"].append({"_id": ObjectId(facility_id)})

    existing = await db["healthcare_facilities"].find_one(query)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Healthcare facility '{facility_id}' not found",
        )

    total_beds = int(existing.get("total_beds", 0))
    total_icu = int(existing.get("total_icu_beds", 0))
    total_em = int(existing.get("total_emergency_beds", 0))
    total_vent = int(existing.get("ventilators_total", 0))
    total_ox = int(existing.get("oxygen_supported_beds", 0))

    new_occ_beds = payload.occupied_beds if payload.occupied_beds is not None else int(existing.get("occupied_beds", 0))
    new_occ_icu = payload.occupied_icu_beds if payload.occupied_icu_beds is not None else int(existing.get("occupied_icu_beds", 0))
    new_occ_em = payload.occupied_emergency_beds if payload.occupied_emergency_beds is not None else int(existing.get("occupied_emergency_beds", 0))
    new_avail_vent = payload.ventilators_available if payload.ventilators_available is not None else int(existing.get("ventilators_available", total_vent))
    new_avail_ox = payload.oxygen_available_capacity if payload.oxygen_available_capacity is not None else int(existing.get("oxygen_available_capacity", total_ox))

    # Strict capacity validation
    if new_occ_beds < 0 or new_occ_beds > total_beds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Occupied beds ({new_occ_beds}) must be between 0 and total beds ({total_beds})",
        )
    if new_occ_icu < 0 or new_occ_icu > total_icu:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Occupied ICU beds ({new_occ_icu}) must be between 0 and total ICU beds ({total_icu})",
        )
    if new_occ_em < 0 or new_occ_em > total_em:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Occupied emergency beds ({new_occ_em}) must be between 0 and total emergency beds ({total_em})",
        )
    if new_avail_vent < 0 or new_avail_vent > total_vent:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Available ventilators ({new_avail_vent}) must be between 0 and total ventilators ({total_vent})",
        )
    if new_avail_ox < 0 or new_avail_ox > total_ox:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Available oxygen capacity ({new_avail_ox}) must be between 0 and total oxygen beds ({total_ox})",
        )

    new_avail_beds = max(0, total_beds - new_occ_beds)
    new_avail_icu = max(0, total_icu - new_occ_icu)
    new_avail_em = max(0, total_em - new_occ_em)

    prev_avail_beds = max(0, total_beds - int(existing.get("occupied_beds", 0)))
    prev_avail_icu = max(0, total_icu - int(existing.get("occupied_icu_beds", 0)))

    now = datetime.now(timezone.utc)
    update_doc = {
        "occupied_beds": new_occ_beds,
        "available_beds": new_avail_beds,
        "occupied_icu_beds": new_occ_icu,
        "available_icu_beds": new_avail_icu,
        "occupied_emergency_beds": new_occ_em,
        "available_emergency_beds": new_avail_em,
        "ventilators_available": new_avail_vent,
        "oxygen_available_capacity": new_avail_ox,
        "last_updated_by_id": current_user.id,
        "last_updated_by_name": current_user.full_name,
        "last_updated": now,
        "updated_at": now,
    }

    await db["healthcare_facilities"].update_one({"_id": existing["_id"]}, {"$set": update_doc})

    # Trigger Monitoring Event for Live Monitoring and Dynamic Replanning
    canonical_fac_id = existing.get("facility_id", facility_id)
    fac_name = existing.get("facility_name") or existing.get("name", "Healthcare Facility")

    await MonitoringService.record_change_event(
        event_type=MonitoringEventType.HEALTHCARE_CAPACITY_CHANGED,
        source_type=EventSourceType.HEALTHCARE_FACILITY,
        source_id=canonical_fac_id,
        previous_state={
            "facility_id": canonical_fac_id,
            "facility_name": fac_name,
            "total_beds": total_beds,
            "occupied_beds": int(existing.get("occupied_beds", 0)),
            "available_beds": prev_avail_beds,
            "total_icu_beds": total_icu,
            "occupied_icu_beds": int(existing.get("occupied_icu_beds", 0)),
            "available_icu_beds": prev_avail_icu,
            "status": existing.get("status", "ACTIVE"),
        },
        new_state={
            "facility_id": canonical_fac_id,
            "facility_name": fac_name,
            "total_beds": total_beds,
            "occupied_beds": new_occ_beds,
            "available_beds": new_avail_beds,
            "total_icu_beds": total_icu,
            "occupied_icu_beds": new_occ_icu,
            "available_icu_beds": new_avail_icu,
            "status": existing.get("status", "ACTIVE"),
        },
        location=existing.get("location"),
        actor={
            "id": current_user.id,
            "full_name": current_user.full_name,
            "role": current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
        },
        metadata={"reason": payload.reason or "Capacity update by Resource Manager"},
        db=db,
    )

    await record_timeline_event(
        db=db,
        report_id=canonical_fac_id,
        event_type=TimelineEventType.HEALTHCARE_CAPACITY_UPDATED,
        details=f"Bed occupancy updated for {fac_name} ({canonical_fac_id}): Occupied={new_occ_beds}/{total_beds} (Available={new_avail_beds}), ICU Occupied={new_occ_icu}/{total_icu} (Available={new_avail_icu}).",
        actor_id=current_user.id,
        actor_name=current_user.full_name,
        actor_role=current_user.role,
    )

    updated = await db["healthcare_facilities"].find_one({"_id": existing["_id"]})
    return serialize_facility_doc(updated)


@router.patch("/facilities/{facility_id}/status", response_model=HealthcareFacilityResponse)
async def update_healthcare_status(
    facility_id: str,
    new_status: HealthcareOperationalStatus = Query(...),
    reason: Optional[str] = Query(None),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_resource_manager),
):
    query: Dict[str, Any] = {
        "$and": [
            {"is_deleted": {"$ne": True}},
            {
                "$or": [
                    {"facility_id": facility_id},
                    {"facility_id": facility_id.strip().upper()},
                ]
            },
        ]
    }
    if ObjectId.is_valid(facility_id):
        query["$and"][1]["$or"].append({"_id": ObjectId(facility_id)})

    existing = await db["healthcare_facilities"].find_one(query)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Healthcare facility '{facility_id}' not found",
        )

    now = datetime.now(timezone.utc)
    old_status = existing.get("status", "ACTIVE")

    await db["healthcare_facilities"].update_one(
        {"_id": existing["_id"]},
        {
            "$set": {
                "status": new_status.value,
                "last_updated_by_id": current_user.id,
                "last_updated_by_name": current_user.full_name,
                "last_updated": now,
                "updated_at": now,
            }
        },
    )

    canonical_fac_id = existing.get("facility_id", facility_id)
    fac_name = existing.get("facility_name") or existing.get("name", "Healthcare Facility")

    await MonitoringService.record_change_event(
        event_type=MonitoringEventType.HEALTHCARE_CAPACITY_CHANGED,
        source_type=EventSourceType.HEALTHCARE_FACILITY,
        source_id=canonical_fac_id,
        previous_state={
            "facility_id": canonical_fac_id,
            "facility_name": fac_name,
            "status": old_status,
            "available_beds": existing.get("available_beds", 0),
        },
        new_state={
            "facility_id": canonical_fac_id,
            "facility_name": fac_name,
            "status": new_status.value,
            "available_beds": existing.get("available_beds", 0) if new_status == HealthcareOperationalStatus.ACTIVE else 0,
        },
        location=existing.get("location"),
        actor={
            "id": current_user.id,
            "full_name": current_user.full_name,
            "role": current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
        },
        metadata={"reason": reason or f"Operational status changed from {old_status} to {new_status.value}"},
        db=db,
    )

    await record_timeline_event(
        db=db,
        report_id=canonical_fac_id,
        event_type=TimelineEventType.HEALTHCARE_STATUS_CHANGED,
        details=f"Operational status for {fac_name} ({canonical_fac_id}) changed from {old_status} to {new_status.value}. {reason or ''}",
        actor_id=current_user.id,
        actor_name=current_user.full_name,
        actor_role=current_user.role,
    )

    updated = await db["healthcare_facilities"].find_one({"_id": existing["_id"]})
    return serialize_facility_doc(updated)


@router.patch("/facilities/{facility_id}", response_model=HealthcareFacilityResponse)
async def update_healthcare_facility(
    facility_id: str,
    payload: HealthcareFacilityUpdate,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_resource_manager),
):
    query: Dict[str, Any] = {
        "$and": [
            {"is_deleted": {"$ne": True}},
            {
                "$or": [
                    {"facility_id": facility_id},
                    {"facility_id": facility_id.strip().upper()},
                ]
            },
        ]
    }
    if ObjectId.is_valid(facility_id):
        query["$and"][1]["$or"].append({"_id": ObjectId(facility_id)})

    existing = await db["healthcare_facilities"].find_one(query)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Healthcare facility '{facility_id}' not found",
        )

    now = datetime.now(timezone.utc)
    update_data: Dict[str, Any] = {
        "last_updated_by_id": current_user.id,
        "last_updated_by_name": current_user.full_name,
        "last_updated": now,
        "updated_at": now,
    }

    if payload.facility_name is not None:
        update_data["facility_name"] = payload.facility_name.strip()
    if payload.facility_type is not None:
        update_data["facility_type"] = payload.facility_type.value
    if payload.location is not None:
        update_data["location"] = payload.location.model_dump()
    if payload.capabilities is not None:
        update_data["capabilities"] = payload.capabilities.model_dump()
    if payload.status is not None:
        update_data["status"] = payload.status.value
    if payload.condition is not None:
        update_data["condition"] = payload.condition
    if payload.accessibility is not None:
        update_data["accessibility"] = payload.accessibility
    if payload.contact_phone is not None:
        update_data["contact_phone"] = payload.contact_phone
    if payload.contact_email is not None:
        update_data["contact_email"] = payload.contact_email
    if payload.operating_hours is not None:
        update_data["operating_hours"] = payload.operating_hours

    # Capacity updates with validation
    tot_beds = payload.total_beds if payload.total_beds is not None else int(existing.get("total_beds", 0))
    occ_beds = payload.occupied_beds if payload.occupied_beds is not None else int(existing.get("occupied_beds", 0))
    if occ_beds > tot_beds or occ_beds < 0 or tot_beds < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Occupied beds ({occ_beds}) cannot exceed total beds ({tot_beds})",
        )
    update_data["total_beds"] = tot_beds
    update_data["occupied_beds"] = occ_beds
    update_data["available_beds"] = max(0, tot_beds - occ_beds)

    tot_icu = payload.total_icu_beds if payload.total_icu_beds is not None else int(existing.get("total_icu_beds", 0))
    occ_icu = payload.occupied_icu_beds if payload.occupied_icu_beds is not None else int(existing.get("occupied_icu_beds", 0))
    if occ_icu > tot_icu or occ_icu < 0 or tot_icu < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Occupied ICU beds ({occ_icu}) cannot exceed total ICU beds ({tot_icu})",
        )
    update_data["total_icu_beds"] = tot_icu
    update_data["occupied_icu_beds"] = occ_icu
    update_data["available_icu_beds"] = max(0, tot_icu - occ_icu)

    tot_em = payload.total_emergency_beds if payload.total_emergency_beds is not None else int(existing.get("total_emergency_beds", 0))
    occ_em = payload.occupied_emergency_beds if payload.occupied_emergency_beds is not None else int(existing.get("occupied_emergency_beds", 0))
    if occ_em > tot_em or occ_em < 0 or tot_em < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Occupied emergency beds ({occ_em}) cannot exceed total emergency beds ({tot_em})",
        )
    update_data["total_emergency_beds"] = tot_em
    update_data["occupied_emergency_beds"] = occ_em
    update_data["available_emergency_beds"] = max(0, tot_em - occ_em)

    if payload.ventilators_total is not None:
        update_data["ventilators_total"] = payload.ventilators_total
    if payload.ventilators_available is not None:
        update_data["ventilators_available"] = payload.ventilators_available
    if payload.oxygen_supported_beds is not None:
        update_data["oxygen_supported_beds"] = payload.oxygen_supported_beds
    if payload.oxygen_available_capacity is not None:
        update_data["oxygen_available_capacity"] = payload.oxygen_available_capacity

    await db["healthcare_facilities"].update_one({"_id": existing["_id"]}, {"$set": update_data})

    canonical_fac_id = existing.get("facility_id", facility_id)
    fac_name = update_data.get("facility_name", existing.get("facility_name", "Healthcare Facility"))

    await record_timeline_event(
        db=db,
        report_id=canonical_fac_id,
        event_type=TimelineEventType.HEALTHCARE_FACILITY_UPDATED,
        details=f"Healthcare facility '{fac_name}' ({canonical_fac_id}) details updated by {current_user.full_name}.",
        actor_id=current_user.id,
        actor_name=current_user.full_name,
        actor_role=current_user.role,
    )

    updated = await db["healthcare_facilities"].find_one({"_id": existing["_id"]})
    return serialize_facility_doc(updated)


@router.delete("/facilities/{facility_id}", status_code=status.HTTP_200_OK)
async def delete_healthcare_facility(
    facility_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_resource_manager),
):
    query: Dict[str, Any] = {
        "$and": [
            {"is_deleted": {"$ne": True}},
            {
                "$or": [
                    {"facility_id": facility_id},
                    {"facility_id": facility_id.strip().upper()},
                ]
            },
        ]
    }
    if ObjectId.is_valid(facility_id):
        query["$and"][1]["$or"].append({"_id": ObjectId(facility_id)})

    existing = await db["healthcare_facilities"].find_one(query)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Healthcare facility '{facility_id}' not found",
        )

    now = datetime.now(timezone.utc)
    await db["healthcare_facilities"].update_one(
        {"_id": existing["_id"]},
        {"$set": {"is_deleted": True, "status": "CLOSED", "updated_at": now, "deleted_at": now, "deleted_by_id": current_user.id}},
    )

    return {"status": "SUCCESS", "message": f"Healthcare facility '{existing.get('facility_id')}' successfully archived."}
