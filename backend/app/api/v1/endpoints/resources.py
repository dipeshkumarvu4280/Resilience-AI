import logging
import math
from datetime import datetime, timezone
from typing import Optional, List, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongodb import get_database
from app.api.deps import require_resource_manager, get_current_user, require_resource_operator
from app.models.user import UserResponse
from app.models.enums import (
    ResourceType,
    ResourceStatus,
    ResourceCondition,
    TimelineEventType,
    MonitoringEventType,
    EventSourceType,
)
from app.models.resource import (
    ResourceCreate,
    ResourceUpdate,
    ResourceQuantityUpdate,
    ResourceStatusUpdate,
    ResourceResponse,
    PaginatedResourcesResponse,
    ResourceStatsResponse,
    ResourceLocation,
    generate_resource_id,
    ResourceBottleneckItem,
    ResourceBottlenecksResponse,
)
from app.services.monitoring.monitoring_service import MonitoringService
from app.services.resource_bottleneck_service import resource_bottleneck_service


logger = logging.getLogger("resilience.resources")
router = APIRouter()


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
    return dt


def safe_resource_type(val: Any) -> ResourceType:
    if isinstance(val, ResourceType):
        return val
    try:
        return ResourceType(val)
    except Exception:
        if isinstance(val, str):
            v_lower = val.strip().lower()
            if v_lower in ["medical", "medicine", "med"]:
                return ResourceType.MEDICINE
            for member in ResourceType:
                if member.value.lower() == v_lower or member.name.lower() == v_lower:
                    return member
        return ResourceType.OTHER


def parse_resource_doc(doc: dict) -> ResourceResponse:
    loc_dict = doc.get("location", {})
    return ResourceResponse(
        resource_id=doc["resource_id"],
        name=doc["name"],
        resource_type=safe_resource_type(doc.get("resource_type")),
        category=doc.get("category"),
        quantity_total=float(doc.get("quantity_total", 0.0)),
        quantity_available=float(doc.get("quantity_available", 0.0)),
        unit=doc.get("unit", "units"),
        location=ResourceLocation(**loc_dict),
        status=ResourceStatus(doc.get("status", ResourceStatus.AVAILABLE.value)) if doc.get("status") in ResourceStatus._value2member_map_ else ResourceStatus.AVAILABLE,
        condition=ResourceCondition(doc.get("condition", ResourceCondition.GOOD.value)) if doc.get("condition") in ResourceCondition._value2member_map_ else ResourceCondition.GOOD,
        owner=doc.get("owner"),
        contact=doc.get("contact"),
        notes=doc.get("notes"),
        created_by=doc.get("created_by"),
        created_by_name=doc.get("created_by_name"),
        updated_by=doc.get("updated_by"),
        updated_by_name=doc.get("updated_by_name"),
        created_at=ensure_utc(doc.get("created_at")) or datetime.now(timezone.utc),
        updated_at=ensure_utc(doc.get("updated_at")) or datetime.now(timezone.utc),
    )


RESOURCE_DOMAINS: dict = {
    "medical": [ResourceType.MEDICINE.value, ResourceType.FIRST_AID.value, ResourceType.MEDICAL_EQUIPMENT.value, ResourceType.HEALTHCARE.value],
    "medical-supplies": [ResourceType.MEDICINE.value, ResourceType.FIRST_AID.value, ResourceType.MEDICAL_EQUIPMENT.value, ResourceType.HEALTHCARE.value],
    "food-water": [ResourceType.WATER.value, ResourceType.FOOD.value],
    "rations-water": [ResourceType.WATER.value, ResourceType.FOOD.value],
    "rations": [ResourceType.WATER.value, ResourceType.FOOD.value],
    "equipment": [ResourceType.RESCUE_EQUIPMENT.value, ResourceType.PROTECTIVE_EQUIPMENT.value, ResourceType.GENERATOR.value, ResourceType.FUEL.value, ResourceType.COMMUNICATION_EQUIPMENT.value],
    "heavy-equipment": [ResourceType.RESCUE_EQUIPMENT.value, ResourceType.PROTECTIVE_EQUIPMENT.value, ResourceType.GENERATOR.value, ResourceType.FUEL.value, ResourceType.COMMUNICATION_EQUIPMENT.value],
    "vehicles": [ResourceType.TRANSPORT.value],
    "fleet": [ResourceType.TRANSPORT.value],
    "inventory": [ResourceType.WATER.value, ResourceType.FOOD.value, ResourceType.BLANKETS.value, ResourceType.CLOTHING.value],
    "stockpile": [ResourceType.WATER.value, ResourceType.FOOD.value, ResourceType.BLANKETS.value, ResourceType.CLOTHING.value],
    "shelters": [ResourceType.SHELTER.value],
    "shelter": [ResourceType.SHELTER.value],
}


def extract_type_filter(
    domain: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_types: Optional[List[str]] = None,
    resource_types_bracket: Optional[List[str]] = None,
) -> Optional[dict]:
    types = []

    # 1. Match Domain if provided
    if domain and domain.strip() and domain.strip().lower() != "all":
        d_key = domain.strip().lower()
        if d_key in RESOURCE_DOMAINS:
            types.extend(RESOURCE_DOMAINS[d_key])

    # 2. Match singular or comma-separated resource_type
    if resource_type and resource_type.strip() and resource_type.strip().lower() != "all":
        types.extend([t.strip() for t in resource_type.split(",") if t.strip() and t.strip().lower() != "all"])

    # 3. Match repeated resource_types list
    if resource_types:
        for t in resource_types:
            if t and t.strip() and t.strip().lower() != "all":
                types.extend([x.strip() for x in t.split(",") if x.strip() and x.strip().lower() != "all"])

    # 4. Match Axios default bracket format (resource_types[])
    if resource_types_bracket:
        for t in resource_types_bracket:
            if t and t.strip() and t.strip().lower() != "all":
                types.extend([x.strip() for x in t.split(",") if x.strip() and x.strip().lower() != "all"])

    types = list(dict.fromkeys(types))
    if not types:
        return None
    if len(types) == 1:
        return {"resource_type": types[0]}
    return {"resource_type": {"$in": types}}


@router.get("/stats", response_model=ResourceStatsResponse)
async def get_resource_stats(
    domain: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_types: Optional[List[str]] = Query(None),
    resource_types_bracket: Optional[List[str]] = Query(None, alias="resource_types[]"),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(get_current_user),
):
    """
    Live real-time resource inventory statistics directly from MongoDB.
    Supports domain, resource_type, or resource_types filtering.
    No hardcoded numbers or fake statistics.
    """
    base_filter = extract_type_filter(domain, resource_type, resource_types, resource_types_bracket) or {}

    total_query = {**base_filter}
    available_query = {**base_filter, "status": ResourceStatus.AVAILABLE.value}
    partially_query = {**base_filter, "status": ResourceStatus.PARTIALLY_AVAILABLE.value}
    unavailable_query = {**base_filter, "status": ResourceStatus.UNAVAILABLE.value}

    total = await db["resources"].count_documents(total_query)
    available = await db["resources"].count_documents(available_query)
    partially = await db["resources"].count_documents(partially_query)
    unavailable = await db["resources"].count_documents(unavailable_query)

    # Group by resource type
    type_counts = {}
    match_stage = [{"$match": base_filter}] if base_filter else []
    pipeline = match_stage + [{"$group": {"_id": "$resource_type", "count": {"$sum": 1}}}]
    cursor = db["resources"].aggregate(pipeline)
    async for item in cursor:
        if item["_id"]:
            type_counts[str(item["_id"])] = item["count"]

    return ResourceStatsResponse(
        total_resources=total,
        available_resources=available,
        partially_available=partially,
        unavailable=unavailable,
        type_counts=type_counts,
    )


@router.get("", response_model=PaginatedResourcesResponse)
async def list_resources(
    domain: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_types: Optional[List[str]] = Query(None),
    resource_types_bracket: Optional[List[str]] = Query(None, alias="resource_types[]"),
    status_filter: Optional[ResourceStatus] = Query(None, alias="status"),
    zone: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(get_current_user),
):
    """
    Paginated, searchable, filterable resource inventory for authorized personnel.
    Supports domain, resource_type, and multiple resource_types domain filtering.
    """
    query = extract_type_filter(domain, resource_type, resource_types, resource_types_bracket) or {}

    if status_filter:
        query["status"] = status_filter.value
    if zone and zone.strip():
        query["$or"] = [
            {"location.zone_or_district": {"$regex": zone.strip(), "$options": "i"}},
            {"location.district": {"$regex": zone.strip(), "$options": "i"}},
            {"location.city": {"$regex": zone.strip(), "$options": "i"}},
        ]
    if search and search.strip():
        term = search.strip()
        search_or = [
            {"resource_id": {"$regex": term, "$options": "i"}},
            {"name": {"$regex": term, "$options": "i"}},
            {"category": {"$regex": term, "$options": "i"}},
            {"owner": {"$regex": term, "$options": "i"}},
            {"location.address": {"$regex": term, "$options": "i"}},
            {"location.city": {"$regex": term, "$options": "i"}},
        ]
        if "$or" in query:
            query = {"$and": [query, {"$or": search_or}]}
        else:
            query["$or"] = search_or

    total = await db["resources"].count_documents(query)
    total_pages = max(1, math.ceil(total / limit))
    skip = (page - 1) * limit

    cursor = db["resources"].find(query).sort("created_at", -1).skip(skip).limit(limit)
    items = []
    async for doc in cursor:
        items.append(parse_resource_doc(doc))

    return PaginatedResourcesResponse(
        items=items,
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@router.post("", response_model=ResourceResponse, status_code=status.HTTP_201_CREATED)
async def create_resource(
    payload: ResourceCreate,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_resource_manager),
):
    """
    Register a new emergency resource asset into the active logistics registry.
    Requires Resource Manager or Admin role.
    """
    resource_id = generate_resource_id()
    now = datetime.now(timezone.utc)

    # Server-side validation
    if payload.quantity_available > payload.quantity_total:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Available quantity cannot exceed total quantity.",
        )

    doc = {
        "resource_id": resource_id,
        "name": payload.name.strip(),
        "resource_type": payload.resource_type.value,
        "category": payload.category.strip() if payload.category else None,
        "quantity_total": float(payload.quantity_total),
        "quantity_available": float(payload.quantity_available),
        "unit": payload.unit.strip(),
        "location": payload.location.model_dump(),
        "status": payload.status.value,
        "condition": payload.condition.value,
        "owner": payload.owner.strip() if payload.owner else None,
        "contact": payload.contact.strip() if payload.contact else None,
        "notes": payload.notes.strip() if payload.notes else None,
        "created_by": current_user.id,
        "created_by_name": current_user.full_name,
        "updated_by": current_user.id,
        "updated_by_name": current_user.full_name,
        "created_at": now,
        "updated_at": now,
    }

    await db["resources"].insert_one(doc)

    # Centralized audit logging
    await db["audit_logs"].insert_one({
        "event_id": f"EVT-{resource_id[-8:]}",
        "action": TimelineEventType.RESOURCE_CREATED.value,
        "actor_id": current_user.id,
        "actor_name": current_user.full_name,
        "actor_role": current_user.role.value,
        "resource_id": resource_id,
        "details": f"Resource '{payload.name}' ({payload.resource_type.value}, {payload.quantity_total} {payload.unit}) provisioned by {current_user.full_name}.",
        "timestamp": now,
    })

    # Dispatch Phase 6 Monitoring Event
    try:
        source_type = EventSourceType.RESOURCE_INVENTORY
        event_type = MonitoringEventType.RESOURCE_CREATED
        if payload.resource_type.value == "Shelter":
            source_type = EventSourceType.SHELTER_FACILITY
            event_type = MonitoringEventType.SHELTER_AVAILABLE
        elif payload.resource_type.value in ["Medical", "Healthcare", "Medical Equipment"]:
            source_type = EventSourceType.HEALTHCARE_FACILITY
            event_type = MonitoringEventType.HEALTHCARE_FACILITY_AVAILABLE

        await MonitoringService.record_change_event(
            event_type=event_type,
            source_type=source_type,
            source_id=resource_id,
            previous_state={},
            new_state={
                "name": payload.name.strip(),
                "resource_type": payload.resource_type.value,
                "quantity_total": float(payload.quantity_total),
                "quantity_available": float(payload.quantity_available),
                "status": payload.status.value,
            },
            actor={
                "id": current_user.id,
                "full_name": current_user.full_name,
                "role": current_user.role.value,
            },
            location=payload.location.model_dump(),
            db=db,
        )
    except Exception as mon_err:
        logger.warning(f"Failed to record monitoring event for created resource {resource_id}: {mon_err}")

    return parse_resource_doc(doc)


# --- Phase D: Resource Bottleneck Intelligence Endpoints ---

@router.get("/bottlenecks", response_model=ResourceBottlenecksResponse)
async def get_resource_bottlenecks(
    situation_id: Optional[str] = Query(None, description="Filter by situation ID"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    severity: Optional[str] = Query(None, description="Filter by bottleneck severity"),
    zone: Optional[str] = Query(None, description="Filter by zone"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_resource_operator),
):
    """
    Deterministically computes operational resource bottlenecks, shortfalls, and multi-incident contention
    from authoritative Needs Assessments, actual physical inventory, active allocations, and task consumption.
    Strict zero dummy data policy.
    """
    try:
        return await resource_bottleneck_service.analyze_bottlenecks(
            db=db,
            situation_id=situation_id,
            resource_type=resource_type,
            severity=severity,
            zone=zone,
            page=page,
            limit=limit,
        )
    except Exception as e:
        logger.error(f"Failed to calculate resource bottlenecks: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to evaluate resource bottlenecks.",
        )


@router.get("/bottlenecks/{bottleneck_id}", response_model=ResourceBottleneckItem)
async def get_resource_bottleneck_detail(
    bottleneck_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_resource_operator),
):
    """
    Retrieves detailed breakdown and root-cause explanation for a specific bottleneck.
    """
    result = await resource_bottleneck_service.analyze_bottlenecks(db=db, limit=100)
    for b in result.items:
        if b.bottleneck_id == bottleneck_id:
            return b
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Resource bottleneck '{bottleneck_id}' not found.",
    )


@router.get("/{resource_id}", response_model=ResourceResponse)
async def get_resource_by_id(
    resource_id: str,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(get_current_user),
):
    """
    Retrieve single resource asset details by resource_id.
    """
    clean_id = resource_id.strip().upper()
    doc = await db["resources"].find_one({"resource_id": clean_id})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource '{resource_id}' not found in registry.",
        )
    return parse_resource_doc(doc)


@router.patch("/{resource_id}", response_model=ResourceResponse)
async def update_resource(
    resource_id: str,
    payload: ResourceUpdate,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_resource_manager),
):
    """
    Update attributes of an existing resource.
    """
    clean_id = resource_id.strip().upper()
    existing = await db["resources"].find_one({"resource_id": clean_id})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource '{resource_id}' not found.",
        )

    now = datetime.now(timezone.utc)
    update_data = {"updated_at": now, "updated_by": current_user.id, "updated_by_name": current_user.full_name}

    if payload.name is not None:
        update_data["name"] = payload.name.strip()
    if payload.resource_type is not None:
        update_data["resource_type"] = payload.resource_type.value
    if payload.category is not None:
        update_data["category"] = payload.category.strip()
    if payload.unit is not None:
        update_data["unit"] = payload.unit.strip()
    if payload.location is not None:
        update_data["location"] = payload.location.model_dump()
    if payload.condition is not None:
        update_data["condition"] = payload.condition.value
    if payload.owner is not None:
        update_data["owner"] = payload.owner.strip()
    if payload.contact is not None:
        update_data["contact"] = payload.contact.strip()
    if payload.notes is not None:
        update_data["notes"] = payload.notes.strip()

    total = payload.quantity_total if payload.quantity_total is not None else existing.get("quantity_total", 0.0)
    avail = payload.quantity_available if payload.quantity_available is not None else existing.get("quantity_available", 0.0)

    if avail > total:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Available quantity cannot exceed total quantity.",
        )

    if payload.quantity_total is not None:
        update_data["quantity_total"] = float(payload.quantity_total)
    if payload.quantity_available is not None:
        update_data["quantity_available"] = float(payload.quantity_available)

    # Automatic status adjustment based on available quantity
    if payload.status is not None:
        update_data["status"] = payload.status.value
    elif payload.quantity_available is not None:
        if avail == 0:
            update_data["status"] = ResourceStatus.UNAVAILABLE.value
        elif avail < total:
            update_data["status"] = ResourceStatus.PARTIALLY_AVAILABLE.value
        else:
            update_data["status"] = ResourceStatus.AVAILABLE.value

    await db["resources"].update_one(
        {"resource_id": clean_id},
        {"$set": update_data}
    )

    # Audit log
    await db["audit_logs"].insert_one({
        "event_id": f"EVT-UPD-{clean_id[-8:]}",
        "action": TimelineEventType.RESOURCE_UPDATED.value,
        "actor_id": current_user.id,
        "actor_name": current_user.full_name,
        "actor_role": current_user.role.value,
        "resource_id": clean_id,
        "details": f"Resource '{clean_id}' updated by {current_user.full_name}.",
        "timestamp": now,
    })

    updated_doc = await db["resources"].find_one({"resource_id": clean_id})

    # Dispatch Phase 6 Monitoring Event
    try:
        source_type = EventSourceType.RESOURCE_INVENTORY
        event_type = MonitoringEventType.RESOURCE_QUANTITY_CHANGED if "quantity_available" in update_data else MonitoringEventType.RESOURCE_STATUS_CHANGED
        if existing.get("resource_type") == "Shelter":
            source_type = EventSourceType.SHELTER_FACILITY
            event_type = MonitoringEventType.SHELTER_CAPACITY_CHANGED if "quantity_available" in update_data else MonitoringEventType.SHELTER_STATUS_CHANGED

        await MonitoringService.record_change_event(
            event_type=event_type,
            source_type=source_type,
            source_id=clean_id,
            previous_state={
                "name": existing.get("name"),
                "resource_type": existing.get("resource_type"),
                "quantity_available": existing.get("quantity_available"),
                "quantity_total": existing.get("quantity_total"),
                "status": existing.get("status"),
                "condition": existing.get("condition"),
            },
            new_state={
                "name": updated_doc.get("name"),
                "resource_type": updated_doc.get("resource_type"),
                "quantity_available": updated_doc.get("quantity_available"),
                "quantity_total": updated_doc.get("quantity_total"),
                "status": updated_doc.get("status"),
                "condition": updated_doc.get("condition"),
            },
            actor={
                "id": current_user.id,
                "full_name": current_user.full_name,
                "role": current_user.role.value,
            },
            location=updated_doc.get("location"),
            db=db,
        )
    except Exception as e:
        logger.warning(f"Failed to record monitoring event for updated resource {clean_id}: {e}")

    return parse_resource_doc(updated_doc)


@router.patch("/{resource_id}/quantity", response_model=ResourceResponse)
async def update_resource_quantity(
    resource_id: str,
    payload: ResourceQuantityUpdate,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_resource_manager),
):
    """
    Update stock levels of a registered resource.
    """
    clean_id = resource_id.strip().upper()
    existing = await db["resources"].find_one({"resource_id": clean_id})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource '{resource_id}' not found.",
        )

    total = payload.quantity_total if payload.quantity_total is not None else float(existing.get("quantity_total", 0.0))
    avail = float(payload.quantity_available)

    if avail > total:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Available quantity ({avail}) cannot exceed total quantity ({total}).",
        )

    now = datetime.now(timezone.utc)
    new_status = ResourceStatus.AVAILABLE.value
    if avail == 0:
        new_status = ResourceStatus.UNAVAILABLE.value
    elif avail < total:
        new_status = ResourceStatus.PARTIALLY_AVAILABLE.value

    update_fields = {
        "quantity_available": avail,
        "quantity_total": total,
        "status": new_status,
        "updated_at": now,
        "updated_by": current_user.id,
        "updated_by_name": current_user.full_name,
    }

    await db["resources"].update_one(
        {"resource_id": clean_id},
        {"$set": update_fields}
    )

    reason_str = f" Reason: {payload.reason}" if payload.reason else ""
    await db["audit_logs"].insert_one({
        "event_id": f"EVT-QTY-{clean_id[-8:]}",
        "action": TimelineEventType.RESOURCE_QUANTITY_UPDATED.value,
        "actor_id": current_user.id,
        "actor_name": current_user.full_name,
        "actor_role": current_user.role.value,
        "resource_id": clean_id,
        "details": f"Available stock for '{clean_id}' updated to {avail}/{total} by {current_user.full_name}.{reason_str}",
        "timestamp": now,
    })

    updated_doc = await db["resources"].find_one({"resource_id": clean_id})

    # Dispatch Phase 6 Monitoring Event
    try:
        source_type = EventSourceType.RESOURCE_INVENTORY
        event_type = MonitoringEventType.RESOURCE_QUANTITY_CHANGED
        if existing.get("resource_type") == "Shelter":
            source_type = EventSourceType.SHELTER_FACILITY
            event_type = MonitoringEventType.SHELTER_CAPACITY_CHANGED

        await MonitoringService.record_change_event(
            event_type=event_type,
            source_type=source_type,
            source_id=clean_id,
            previous_state={
                "name": existing.get("name"),
                "resource_type": existing.get("resource_type"),
                "quantity_available": existing.get("quantity_available"),
                "quantity_total": existing.get("quantity_total"),
                "current_occupancy": existing.get("current_occupancy", 0.0),
                "status": existing.get("status"),
            },
            new_state={
                "name": updated_doc.get("name"),
                "resource_type": updated_doc.get("resource_type"),
                "quantity_available": updated_doc.get("quantity_available"),
                "quantity_total": updated_doc.get("quantity_total"),
                "current_occupancy": updated_doc.get("current_occupancy", 0.0),
                "status": updated_doc.get("status"),
            },
            actor={
                "id": current_user.id,
                "full_name": current_user.full_name,
                "role": current_user.role.value,
            },
            location=updated_doc.get("location"),
            db=db,
        )
    except Exception as e:
        logger.warning(f"Failed to record monitoring event for resource {clean_id}: {e}")

    return parse_resource_doc(updated_doc)



@router.patch("/{resource_id}/status", response_model=ResourceResponse)
async def update_resource_status(
    resource_id: str,
    payload: ResourceStatusUpdate,
    db: AsyncIOMotorDatabase = Depends(get_database),
    current_user: UserResponse = Depends(require_resource_manager),
):
    """
    Manually update operational status of a resource (e.g. mark UNAVAILABLE due to maintenance).
    """
    clean_id = resource_id.strip().upper()
    existing = await db["resources"].find_one({"resource_id": clean_id})
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource '{resource_id}' not found.",
        )

    now = datetime.now(timezone.utc)
    await db["resources"].update_one(
        {"resource_id": clean_id},
        {
            "$set": {
                "status": payload.status.value,
                "updated_at": now,
                "updated_by": current_user.id,
                "updated_by_name": current_user.full_name,
            }
        }
    )

    reason_str = f" Reason: {payload.reason}" if payload.reason else ""
    await db["audit_logs"].insert_one({
        "event_id": f"EVT-STA-{clean_id[-8:]}",
        "action": TimelineEventType.RESOURCE_STATUS_CHANGED.value,
        "actor_id": current_user.id,
        "actor_name": current_user.full_name,
        "actor_role": current_user.role.value,
        "resource_id": clean_id,
        "previous_value": existing.get("status"),
        "new_value": payload.status.value,
        "details": f"Resource '{clean_id}' status changed from {existing.get('status')} to {payload.status.value} by {current_user.full_name}.{reason_str}",
        "timestamp": now,
    })

    updated_doc = await db["resources"].find_one({"resource_id": clean_id})

    # Dispatch Phase 6 Monitoring Event
    try:
        source_type = EventSourceType.RESOURCE_INVENTORY
        event_type = MonitoringEventType.RESOURCE_STATUS_CHANGED
        if existing.get("resource_type") == "Shelter":
            source_type = EventSourceType.SHELTER_FACILITY
            event_type = MonitoringEventType.SHELTER_STATUS_CHANGED

        await MonitoringService.record_change_event(
            event_type=event_type,
            source_type=source_type,
            source_id=clean_id,
            previous_state={
                "name": existing.get("name"),
                "resource_type": existing.get("resource_type"),
                "status": existing.get("status"),
                "quantity_available": existing.get("quantity_available"),
                "quantity_total": existing.get("quantity_total"),
                "current_occupancy": existing.get("current_occupancy", 0.0),
            },
            new_state={
                "name": updated_doc.get("name"),
                "resource_type": updated_doc.get("resource_type"),
                "status": updated_doc.get("status"),
                "quantity_available": updated_doc.get("quantity_available"),
                "quantity_total": updated_doc.get("quantity_total"),
                "current_occupancy": updated_doc.get("current_occupancy", 0.0),
            },
            actor={
                "id": current_user.id,
                "full_name": current_user.full_name,
                "role": current_user.role.value,
            },
            location=updated_doc.get("location"),
            db=db,
        )
    except Exception as e:
        logger.warning(f"Failed to record status monitoring event for resource {clean_id}: {e}")

    return parse_resource_doc(updated_doc)

