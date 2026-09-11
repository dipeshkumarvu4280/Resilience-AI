import math
import re
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.models.enums import ResourceStatus, ResourceCondition, NeedUrgency
from app.models.resource import (
    EmergencyNeedItem,
    ResourceMatchCandidate,
    NeedMatchResult,
    ResourceMatchingResponse,
    ResourceLocation,
)


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points on the Earth in kilometers."""
    R = 6371.0  # Earth's radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(R * c, 2)


async def match_resources_for_needs(
    db: AsyncIOMotorDatabase,
    report_id: str,
    report_location: Dict[str, Any],
    needs: List[EmergencyNeedItem],
) -> ResourceMatchingResponse:
    rep_lat = report_location.get("latitude", 0.0)
    rep_lon = report_location.get("longitude", 0.0)

    needs_results: List[NeedMatchResult] = []

    for need in needs:
        # Search real resources matching resource_type with available stock
        r_type_val = need.resource_type.value if hasattr(need.resource_type, "value") else str(need.resource_type)
        r_type_clean = r_type_val.lower().replace("_", " ").strip()
        
        # Build flexible keyword list for matching
        keywords = [r_type_val, r_type_clean]
        if "water" in r_type_clean:
            keywords.extend(["water", "potable", "drinking", "jerry"])
        elif "blanket" in r_type_clean or "bed" in r_type_clean:
            keywords.extend(["blanket", "bedding", "thermal", "sheet"])
        elif "food" in r_type_clean or "ration" in r_type_clean:
            keywords.extend(["food", "ration", "meal", "grocery", "grain"])
        elif "med" in r_type_clean or "first aid" in r_type_clean:
            keywords.extend(["medical", "medicine", "first aid", "kit", "pharma"])
        elif "shelter" in r_type_clean or "tent" in r_type_clean:
            keywords.extend(["shelter", "tent", "tarpaulin", "tarp"])

        regex_pattern = "|".join([re.escape(k) for k in set(keywords) if k])

        query = {
            "$or": [
                {"resource_type": {"$regex": regex_pattern, "$options": "i"}},
                {"category": {"$regex": regex_pattern, "$options": "i"}},
                {"name": {"$regex": regex_pattern, "$options": "i"}},
                {"item_name": {"$regex": regex_pattern, "$options": "i"}},
                {"type": {"$regex": regex_pattern, "$options": "i"}},
            ],
            "quantity_available": {"$gt": 0},
            "status": {"$in": ["AVAILABLE", "PARTIALLY_AVAILABLE", "OPERATIONAL", "Operational", "ACTIVE", "Active"]},
        }
        cursor = db["resources"].find(query)
        candidates_list: List[ResourceMatchCandidate] = []
        total_matched_avail = 0.0

        async for r_doc in cursor:
            loc = r_doc.get("location", {})
            r_lat = loc.get("latitude", 0.0)
            r_lon = loc.get("longitude", 0.0)

            dist_km = haversine_distance_km(rep_lat, rep_lon, r_lat, r_lon)
            qty_avail = float(r_doc.get("quantity_available", 0.0))
            total_matched_avail += qty_avail

            # Scoring factors
            prox_score = max(0.1, 1.0 - (dist_km / 100.0))
            cond_val = r_doc.get("condition", ResourceCondition.GOOD.value)
            cond_score = 1.0 if cond_val == ResourceCondition.GOOD.value else (0.7 if cond_val == ResourceCondition.LIMITED.value else 0.2)
            stat_val = r_doc.get("status", ResourceStatus.AVAILABLE.value)
            stat_score = 1.0 if stat_val == ResourceStatus.AVAILABLE.value else 0.8

            match_score = round(float(0.5 * prox_score + 0.3 * cond_score + 0.2 * stat_score), 3)

            reasons = [
                f"Resource Type: {need.resource_type.value}",
                f"Distance: {dist_km} km from incident site",
                f"Available: {qty_avail} {r_doc.get('unit', need.unit)}",
                f"Facility Condition: {cond_val}",
            ]

            candidates_list.append(ResourceMatchCandidate(
                resource_id=r_doc["resource_id"],
                name=r_doc["name"],
                resource_type=need.resource_type,
                quantity_available=qty_avail,
                unit=r_doc.get("unit", need.unit),
                distance_km=dist_km,
                match_score=match_score,
                location=ResourceLocation(**loc),
                status=ResourceStatus(stat_val),
                condition=ResourceCondition(cond_val),
                reasoning=reasons,
                recommended_allocation=0.0,
            ))

        # Sort candidates descending by match score
        candidates_list.sort(key=lambda c: c.match_score, reverse=True)

        # Calculate recommended allocations sequentially across top matches
        remaining_req = need.requested_quantity
        for cand in candidates_list:
            alloc_qty = min(remaining_req, cand.quantity_available)
            cand.recommended_allocation = round(alloc_qty, 2)
            remaining_req -= alloc_qty
            if remaining_req <= 0:
                break

        is_fully = total_matched_avail >= need.requested_quantity

        needs_results.append(NeedMatchResult(
            need_id=need.need_id,
            resource_type=need.resource_type,
            requested_quantity=need.requested_quantity,
            unit=need.unit,
            urgency=need.urgency,
            candidates=candidates_list,
            total_matched_available=round(total_matched_avail, 2),
            is_fully_matchable=is_fully,
        ))

    return ResourceMatchingResponse(
        report_id=report_id,
        needs_matches=needs_results,
        generated_at=datetime.now(timezone.utc),
        ai_explanation=None,
    )
