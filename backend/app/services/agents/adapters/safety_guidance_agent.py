import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongodb import db_manager
from app.models.enums import (
    SeverityLevel,
    DestinationType,
    RouteStatus,
    GuidanceApprovalState,
    ResourceType,
    ResourceStatus,
)
from app.models.safety_guidance import (
    CitizenSafetyGuidance,
    VerifiedDestination,
    RouteDetails,
    HazardAvoidanceZone,
    generate_guidance_id,
    generate_secure_access_token,
)
from app.services.resource_matching import haversine_distance_km
from app.services.routing_service import RoutingService
from app.services.places_service import PlacesService
from app.services.notification.web_push_service import WebPushService

logger = logging.getLogger("resilience.agents.safety_guidance")


class SafetyGuidanceAgent:
    """
    Citizen Safety Guidance Advisory Agent.
    
    PURPOSE:
    Analyzes real citizen emergency reports, geolocation, multimodal evidence,
    and live operational facility availability to synthesize tailored civilian safety guidance.
    
    CRITICAL NON-NEGOTIABLE PRINCIPLES:
    - Purely ADVISORY for citizen life-safety.
    - NEVER dispatches responders, allocates emergency resources, or consumes inventory.
    - ZERO dummy or hardcoded facilities: queries real operational facilities via Places API, OSM, and MongoDB.
    - ZERO static dummy routes: computes real hazard-aware navigation corridors.
    - HITL Enforcement: Critical evacuation orders require Emergency Officer review.
    """

    @classmethod
    async def generate_safety_guidance(
        cls,
        report_id: str,
        db: Optional[AsyncIOMotorDatabase] = None,
        force_refresh: bool = False,
        change_reason: Optional[str] = None,
        trigger_event_id: Optional[str] = None,
    ) -> CitizenSafetyGuidance:
        """
        Generates or retrieves structured, contextual Safety Guidance for a citizen emergency report.
        """
        if db is None:
            db = db_manager.db
        if db is None:
            raise ValueError("MongoDB database connection is not initialized.")

        # 1. Check for existing active guidance if not force refreshing
        if not force_refresh:
            existing = await db["citizen_safety_guidance"].find_one({
                "report_id": report_id,
                "status": "ACTIVE",
            })
            if existing:
                return cls._doc_to_guidance(existing)

        # 2. Fetch authoritative citizen report document
        report_doc = await db["citizen_reports"].find_one({"report_id": report_id})
        if not report_doc:
            raise ValueError(f"Citizen report {report_id} not found.")

        # Extract coordinates
        loc_data = report_doc.get("location", {})
        origin_lat = float(loc_data.get("latitude", 0.0))
        origin_lng = float(loc_data.get("longitude", 0.0))
        emergency_type = report_doc.get("emergency_type", "Other")
        description = report_doc.get("description", "")
        situation_id = report_doc.get("situation_id")

        # Visual evidence & LLM extractions if present
        visual_evidence = report_doc.get("visual_evidence") or {}
        llm_extraction = report_doc.get("llm_extraction") or {}
        evidence_verification = report_doc.get("evidence_verification") or {}

        # 3. Assess Risk Level
        risk_level = cls._determine_risk_level(report_doc, visual_evidence)

        # 4. Deterministic Destination Intelligence: Real-Time Places + MongoDB facilities
        destination, dest_reason, nearby_alternatives = await cls._find_verified_destination(
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            emergency_type=emergency_type,
            db=db,
            description=description,
            visual_evidence=visual_evidence,
            llm_extraction=llm_extraction,
        )

        # 5. Real Routing (Google-Only Road Graph)
        route: Optional[RouteDetails] = None
        route_warnings: List[str] = []
        if destination:
            route = await RoutingService.calculate_hazard_aware_route(
                origin_lat=origin_lat,
                origin_lng=origin_lng,
                dest_lat=destination.latitude,
                dest_lng=destination.longitude,
                db=db,
            )
            route_warnings.extend(route.route_warnings)
            if route.route_status in (RouteStatus.CALCULATED, RouteStatus.RESTRICTED) and route.estimated_duration_minutes > 0:
                destination.distance_km = float(route.distance_km)
                destination.estimated_drive_minutes = float(route.estimated_duration_minutes)

        # 6. Contextual Immediate Actions and Precautions
        immediate_actions, precautions = cls._synthesize_contextual_actions(
            emergency_type=emergency_type,
            description=description,
            risk_level=risk_level,
            destination=destination,
            visual_evidence=visual_evidence,
            llm_extraction=llm_extraction,
            route=route,
        )

        # 7. HITL Policy: Critical evacuation directives require officer approval
        requires_approval = (risk_level == SeverityLevel.CRITICAL and destination is not None)
        approval_state = (
            GuidanceApprovalState.PENDING_REVIEW if requires_approval else GuidanceApprovalState.AUTO_PUBLISHED
        )

        # Version calculation & history preservation
        prev_cursor = db["citizen_safety_guidance"].find({"report_id": report_id}).sort("version", -1)
        prev_docs = await prev_cursor.to_list(10)
        next_version = (prev_docs[0].get("version", 0) + 1) if prev_docs else 1

        if prev_docs:
            await db["citizen_safety_guidance"].update_many(
                {"report_id": report_id, "status": "ACTIVE"},
                {"$set": {"status": "SUPERSEDED"}}
            )

        guidance_id = generate_guidance_id()
        token = generate_secure_access_token()
        now_utc = datetime.now(timezone.utc)

        guidance = CitizenSafetyGuidance(
            guidance_id=guidance_id,
            secure_access_token=token,
            report_id=report_id,
            situation_id=situation_id,
            generated_at=now_utc,
            valid_until=now_utc + timedelta(hours=4),
            status="ACTIVE",
            emergency_type=str(emergency_type),
            risk_level=risk_level,
            immediate_actions=immediate_actions,
            precautions=precautions,
            recommended_destination=destination,
            destination_reason=dest_reason,
            nearby_alternatives=nearby_alternatives,
            route=route,
            route_warnings=route_warnings,
            avoid_locations=route.avoid_areas if route else [],
            confidence=0.92 if destination else 0.85,
            evidence_references=[
                f"Report #{report_id} Location: ({origin_lat:.4f}, {origin_lng:.4f})",
                f"Emergency Classification: {emergency_type}",
            ],
            requires_officer_approval=requires_approval,
            approval_state=approval_state,
            version=next_version,
            change_reason=change_reason,
            trigger_event_id=trigger_event_id,
        )

        # Persist to MongoDB
        await db["citizen_safety_guidance"].insert_one(guidance.model_dump())

        # Update report document with guidance metadata
        await db["citizen_reports"].update_one(
            {"report_id": report_id},
            {
                "$set": {
                    "safety_guidance_id": guidance_id,
                    "safety_guidance_token": token,
                    "updated_at": now_utc,
                }
            },
        )

        # If auto-published, broadcast push notification to registered browsers
        if approval_state == GuidanceApprovalState.AUTO_PUBLISHED:
            try:
                await WebPushService.notify_citizen_guidance_update(guidance, db=db)
            except Exception as push_err:
                logger.warning(f"Web push dispatch exception for guidance {guidance_id}: {push_err}")

        return guidance

    @classmethod
    async def _find_verified_destination(
        cls,
        origin_lat: float,
        origin_lng: float,
        emergency_type: str,
        db: AsyncIOMotorDatabase,
        description: str = "",
        visual_evidence: Optional[Dict[str, Any]] = None,
        llm_extraction: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[VerifiedDestination], str, List[VerifiedDestination]]:
        """
        Discovers genuine, active operational facilities (shelters, hospitals, police, fire stations, bus transit)
        from Google Places / OSM and MongoDB collections, strictly aligned with citizen emergency need.
        Ranks candidate facilities by fastest road drive time and road safety.
        Returns: (primary_destination, reason, nearby_alternatives)
        """
        vis_ev = visual_evidence or {}
        llm_ext = llm_extraction or {}
        context_text = f"{emergency_type} {description} {vis_ev.get('hazard_type', '')} {llm_ext.get('summary', '')}".lower()

        # Determine need category
        need_category = "SHELTER"
        dest_type_primary = DestinationType.SHELTER

        if any(w in context_text for w in [
            "medical", "injury", "injured", "casualt", "bleeding", "unconscious",
            "heart", "trauma", "ambulance", "accident", "doctor", "hospital", "patient"
        ]):
            need_category = "MEDICAL"
            dest_type_primary = DestinationType.HEALTHCARE
        elif any(w in context_text for w in [
            "police", "security", "threat", "violence", "attack", "robbery", "assault",
            "crime", "riot", "missing person", "hostile", "gunshot"
        ]):
            need_category = "POLICE"
            dest_type_primary = DestinationType.POLICE
        elif any(w in context_text for w in [
            "fire", "smoke", "flame", "explosion", "burning", "gas leak"
        ]):
            need_category = "FIRE"
            dest_type_primary = DestinationType.FIRE_STATION
        elif any(w in context_text for w in [
            "bus", "transit", "evacuation bus", "train station", "metro", "transport"
        ]):
            need_category = "TRANSIT"
            dest_type_primary = DestinationType.BUS_STATION

        candidate_dests: List[VerifiedDestination] = []
        seen_coordinates: set = set()

        def _coord_key(lat: float, lng: float) -> Tuple[float, float]:
            return (round(lat, 3), round(lng, 3))

        # 1. Real-time Live Discovery via PlacesService (Google Places API New searchNearby)
        if origin_lat != 0.0 or origin_lng != 0.0:
            try:
                live_places = await PlacesService.discover_nearby_facilities(
                    lat=origin_lat,
                    lng=origin_lng,
                    need_category=need_category,
                    radius_meters=15000,
                    db=db,
                )
                for p in live_places:
                    ck = _coord_key(p["latitude"], p["longitude"])
                    if ck in seen_coordinates:
                        continue
                    seen_coordinates.add(ck)

                    p_type = p.get("destination_type", dest_type_primary)
                    if isinstance(p_type, str):
                        try:
                            p_type = DestinationType(p_type)
                        except Exception:
                            p_type = dest_type_primary

                    dist_km = p.get("distance_km", round(haversine_distance_km(origin_lat, origin_lng, p["latitude"], p["longitude"]), 2))
                    drive_min = p.get("estimated_drive_minutes") or PlacesService.estimate_drive_time_minutes(dist_km)

                    candidate_dests.append(
                        VerifiedDestination(
                            destination_id=p.get("place_id") or f"PLC-{p['latitude']:.4f}-{p['longitude']:.4f}",
                            destination_name=p["name"],
                            destination_type=p_type,
                            latitude=float(p["latitude"]),
                            longitude=float(p["longitude"]),
                            address_or_landmark=p.get("address") or "Live verified facility location",
                            distance_km=float(dist_km),
                            estimated_drive_minutes=float(drive_min),
                            rating=p.get("rating"),
                            open_now=p.get("open_now"),
                            place_id=p.get("place_id"),
                            provider=p.get("provider", "places_service"),
                            last_checked=datetime.now(timezone.utc),
                            operational_status="OPERATIONAL",
                            suitability_reason=f"Real-time verified operational {p_type.value.replace('_', ' ').lower()} ({dist_km:.1f} km, ~{int(drive_min)} min drive).",
                            contact_phone=p.get("contact_phone"),
                        )
                    )
            except Exception as e:
                logger.warning(f"Live places discovery failed: {e}")

        # 2. Local Operational Database Query (MongoDB: healthcare_facilities and resources)
        if need_category == "MEDICAL":
            hcf_cursor = db["healthcare_facilities"].find({
                "status": {"$nin": ["CLOSED", "INACTIVE", "DECOMMISSIONED", "DESTROYED"]}
            })
            async for doc in hcf_cursor:
                loc = doc.get("location", {})
                f_lat = loc.get("latitude")
                f_lng = loc.get("longitude")
                if f_lat is not None and f_lng is not None:
                    lat_f, lng_f = float(f_lat), float(f_lng)
                    ck = _coord_key(lat_f, lng_f)
                    if ck in seen_coordinates:
                        continue
                    seen_coordinates.add(ck)
                    dist = haversine_distance_km(origin_lat, origin_lng, lat_f, lng_f)
                    if dist <= 50.0:
                        drive_min = PlacesService.estimate_drive_time_minutes(dist)
                        cap = doc.get("capacity") or {}
                        tot_cap = float(cap.get("total") or doc.get("total_beds", 0.0))
                        avail_cap = float(cap.get("available") or doc.get("available_beds", tot_cap))
                        candidate_dests.append(
                            VerifiedDestination(
                                destination_id=doc.get("facility_id") or str(doc.get("_id", "HCF-001")),
                                destination_name=doc.get("name", "Verified Healthcare Facility"),
                                destination_type=DestinationType.HEALTHCARE,
                                latitude=lat_f,
                                longitude=lng_f,
                                address_or_landmark=doc.get("location", {}).get("address") or doc.get("address") or "Operational Medical Center",
                                distance_km=round(dist, 2),
                                estimated_drive_minutes=drive_min,
                                available_capacity=avail_cap if avail_cap > 0 else None,
                                total_capacity=tot_cap if tot_cap > 0 else None,
                                operational_status="OPERATIONAL",
                                provider="mongodb_healthcare_facilities",
                                last_checked=datetime.now(timezone.utc),
                                suitability_reason=f"Operational healthcare center ({dist:.1f} km, ~{int(drive_min)} min drive).",
                                contact_phone=doc.get("contact_info", {}).get("phone") or doc.get("phone"),
                            )
                        )

        # Query resources collection for matching operational physical facility destinations (e.g., shelters, police, fire, assembly points)
        if need_category in ["SHELTER", "TRANSIT", "POLICE", "FIRE"]:
            res_regex_map = {
                "POLICE": "(?i)police|law enforcement|patrol|security",
                "FIRE": "(?i)fire|fire station|brigade",
                "TRANSIT": "(?i)bus station|transit center|evacuation terminal|transport hub",
                "SHELTER": "(?i)shelter|evacuation center|assembly point|relief camp|community center",
            }
            res_regex = res_regex_map.get(need_category, "(?i)shelter|evacuation|assembly")
            res_cursor = db["resources"].find({
                "status": {"$in": [ResourceStatus.AVAILABLE.value, "AVAILABLE", "OPERATIONAL", "ACTIVE"]},
                "$or": [
                    {"resource_type": {"$regex": res_regex}},
                    {"type": {"$regex": res_regex}},
                    {"name": {"$regex": res_regex}},
                ]
            })
            async for doc in res_cursor:
                # Exclude commodity items / consumable supplies
                doc_name = str(doc.get("name", "")).lower()
                if any(w in doc_name for w in ["oxygen", "kit", "water bottle", "blanket", "food packet", "medicine", "generator", "tent supply"]):
                    continue

                loc = doc.get("location", {})
                f_lat = loc.get("latitude")
                f_lng = loc.get("longitude")
                if f_lat is not None and f_lng is not None:
                    lat_f, lng_f = float(f_lat), float(f_lng)
                    ck = _coord_key(lat_f, lng_f)
                    if ck in seen_coordinates:
                        continue
                    seen_coordinates.add(ck)
                    dist = haversine_distance_km(origin_lat, origin_lng, lat_f, lng_f)
                    if dist <= 50.0:
                        drive_min = PlacesService.estimate_drive_time_minutes(dist)
                        cap_sub = doc.get("capacity") or {}
                        tot_cap = float(cap_sub.get("total") or doc.get("quantity_total") or 0.0)
                        avail_cap = float(cap_sub.get("available") or doc.get("quantity_available") or tot_cap)
                        dtype = dest_type_primary
                        if need_category == "SHELTER":
                            r_type_raw = str(doc.get("resource_type") or doc.get("type") or "").upper()
                            dtype = DestinationType.SAFE_ASSEMBLY_AREA if "ASSEMBLY" in r_type_raw else DestinationType.SHELTER

                        candidate_dests.append(
                            VerifiedDestination(
                                destination_id=doc.get("resource_id") or str(doc.get("_id", "RES-001")),
                                destination_name=doc.get("name", f"Verified Operational {dtype.value.replace('_', ' ').title()}"),
                                destination_type=dtype,
                                latitude=lat_f,
                                longitude=lng_f,
                                address_or_landmark=doc.get("location", {}).get("address") or doc.get("address") or "Operational Emergency Site",
                                distance_km=round(dist, 2),
                                estimated_drive_minutes=drive_min,
                                available_capacity=avail_cap if avail_cap > 0 else None,
                                total_capacity=tot_cap if tot_cap > 0 else None,
                                operational_status="OPERATIONAL",
                                provider="mongodb_resources",
                                last_checked=datetime.now(timezone.utc),
                                suitability_reason=f"Operational {dtype.value.replace('_', ' ').lower()} ({dist:.1f} km, ~{int(drive_min)} min drive).",
                                contact_phone=doc.get("contact_info", {}).get("phone") or doc.get("phone_number") or doc.get("phone"),
                            )
                        )

        if not candidate_dests:
            return None, "NO_VERIFIED_DESTINATION_AVAILABLE", []

        # 3. Real Road Candidate Routing & Safe Corridor Ranking
        # Pre-sort candidate pool by initial proximity
        candidate_dests.sort(key=lambda d: (d.distance_km, d.estimated_drive_minutes or 999.0))
        top_candidates = candidate_dests[:6]

        # Calculate actual road routes for the top reachable candidate facilities
        if (origin_lat != 0.0 or origin_lng != 0.0) and db is not None:
            for cand in top_candidates:
                try:
                    cand_route = await RoutingService.calculate_hazard_aware_route(
                        origin_lat=origin_lat,
                        origin_lng=origin_lng,
                        dest_lat=cand.latitude,
                        dest_lng=cand.longitude,
                        db=db,
                    )
                    if cand_route.route_status in (RouteStatus.CALCULATED, RouteStatus.RESTRICTED) and cand_route.estimated_duration_minutes > 0:
                        cand.estimated_drive_minutes = float(cand_route.estimated_duration_minutes)
                        cand.distance_km = float(cand_route.distance_km)
                        p_name = cand.destination_name
                        restriction_note = " (access restriction warning)" if cand_route.route_status == RouteStatus.RESTRICTED else ""
                        cand.suitability_reason = (
                            f"Verified road-accessible {cand.destination_type.value.replace('_', ' ').lower()} "
                            f"({cand.distance_km:.1f} km road distance, ~{int(cand.estimated_drive_minutes)} min drive){restriction_note}."
                        )
                    elif cand_route.route_status == RouteStatus.ROUTE_UNSAFE:
                        # Road corridor is compromised by hazard/obstruction
                        cand.estimated_drive_minutes = (cand.estimated_drive_minutes or 50.0) + 1000.0
                except Exception as route_err:
                    logger.debug(f"Candidate route evaluation notice for {cand.destination_name}: {route_err}")

        # Rank candidates strictly by fastest actual road travel duration and road distance
        candidate_dests.sort(key=lambda d: (d.estimated_drive_minutes or 999.0, d.distance_km))

        primary_dest = candidate_dests[0]
        alternatives = candidate_dests[1:4]  # Up to 3 alternative nearby facilities

        dest_type_str = primary_dest.destination_type.value.replace('_', ' ').lower()
        est_drive_str = f", ~{int(primary_dest.estimated_drive_minutes)} min drive" if primary_dest.estimated_drive_minutes and primary_dest.estimated_drive_minutes < 500 else ""
        reason_str = (
            f"Fastest road-accessible verified operational {dest_type_str} "
            f"({primary_dest.distance_km:.1f} km{est_drive_str}) with confirmed road routing."
        )

        return primary_dest, reason_str, alternatives

    @classmethod
    def _determine_risk_level(cls, report_doc: Dict[str, Any], visual_evidence: Dict[str, Any]) -> SeverityLevel:
        impact = str(report_doc.get("citizen_impact_level", "")).upper()
        if impact == "CRITICAL":
            return SeverityLevel.CRITICAL
        elif impact == "HIGH":
            return SeverityLevel.HIGH

        vis_hazard = str(visual_evidence.get("hazard_type", "")).upper()
        if vis_hazard in ["STRUCTURAL_COLLAPSE", "BUILDING_COLLAPSE", "FIRE"] and visual_evidence.get("status") == "SUCCESS":
            return SeverityLevel.HIGH

        desc_lower = str(report_doc.get("description", "")).lower()
        if any(w in desc_lower for w in ["trapped", "buried", "bleeding", "unconscious", "explosion"]):
            return SeverityLevel.CRITICAL
        elif any(w in desc_lower for w in ["rising fast", "submerged", "fire spreading", "blocked"]):
            return SeverityLevel.HIGH

        return SeverityLevel.MEDIUM

    @classmethod
    def _synthesize_contextual_actions(
        cls,
        emergency_type: str,
        description: str,
        risk_level: SeverityLevel,
        destination: Optional[VerifiedDestination],
        visual_evidence: Dict[str, Any],
        llm_extraction: Dict[str, Any],
        route: Optional[RouteDetails],
    ) -> Tuple[List[str], List[str]]:
        """
        Synthesizes specific, contextual action items and precautions based on live evidence.
        """
        et_lower = str(emergency_type).lower()
        desc_lower = description.lower()
        actions: List[str] = []
        precautions: List[str] = []

        # Contextual actions based on emergency type & evidence
        if "flood" in et_lower or "water" in desc_lower:
            actions.append("Move to highest accessible floor or elevated ground immediately.")
            actions.append("Avoid walking, wading, or driving through moving floodwaters.")
            precautions.append("Turn off main electrical breaker and gas valve if safely accessible.")
            precautions.append("Keep emergency kit, medications, and fully charged phone sealed in waterproof bag.")
        elif "fire" in et_lower or "smoke" in desc_lower:
            actions.append("Evacuate building immediately via nearest safe ground exit; stay low under smoke.")
            actions.append("Close doors behind you to slow flame progression.")
            precautions.append("Never use elevators during a structural fire emergency.")
            precautions.append("Cover mouth and nose with a damp cloth if smoke is present.")
        elif "landslide" in et_lower or "collapse" in desc_lower:
            actions.append("Move away from steep slopes, retaining walls, and compromised foundations.")
            actions.append("Listen for unusual cracking sounds, tumbling rocks, or sudden water surges.")
            precautions.append("Avoid river valleys and low-lying drainage channels during active slope movement.")
        elif "medical" in et_lower or "accident" in desc_lower:
            actions.append("Keep patient still, calm, and warm; do not move injured persons unless immediate hazard threatens.")
            actions.append("Apply direct clean pressure to severe bleeding wounds.")
            precautions.append("Clear access path for arriving emergency medical responders.")
        else:
            actions.append("Remain in a safe, sheltered location and await direct responder coordination.")
            precautions.append("Keep communication lines clear for emergency responder updates.")

        # Destination & Route Context
        if destination:
            actions.append(f"Follow verified route towards {destination.destination_name} ({destination.distance_km:.1f} km).")
        else:
            actions.append("No safe evacuation destination is currently confirmed. Remain sheltered in place.")

        if route and route.route_warnings:
            for w in route.route_warnings[:2]:
                precautions.append(f"Route Advisory: {w}")

        return actions, precautions

    @classmethod
    async def evaluate_and_update_guidance_for_event(
        cls,
        event: Any,
        impact: Optional[Any] = None,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> List[CitizenSafetyGuidance]:
        """
        Dynamically re-evaluates active Citizen Safety Guidance when an authentic operational event occurs.
        
        Evaluates:
        1. Destination Impact: Recommended facility closed, destroyed, or fully occupied.
        2. Route Corridor Impact: Road blocked, flood surge, or sensor hazard within spatial corridor buffer.
        3. Situation Escalation: Evolving hazard radius or severity change.
        
        Produces immutable, versioned guidance (V1 -> V2 -> V3) with auditable supersession.
        """
        if db is None:
            db = db_manager.db
        if db is None:
            return []

        updated_guidances: List[CitizenSafetyGuidance] = []
        cursor = db["citizen_safety_guidance"].find({"status": "ACTIVE"})

        now_utc = datetime.now(timezone.utc)
        event_source_type = getattr(event, "source_type", None)
        if hasattr(event_source_type, "value"):
            event_source_type_val = event_source_type.value
        else:
            event_source_type_val = str(event_source_type or "")

        event_source_id = str(getattr(event, "source_id", "") or "")
        event_new_state = getattr(event, "new_state", {}) or {}
        event_location = getattr(event, "location", None) or event_new_state.get("location") or {}
        event_lat = event_location.get("latitude")
        event_lng = event_location.get("longitude")
        event_id = str(getattr(event, "event_id", "") or f"EVT-{now_utc.timestamp()}")
        event_type_str = str(getattr(getattr(event, "event_type", ""), "value", getattr(event, "event_type", "")))

        async for doc in cursor:
            guidance = cls._doc_to_guidance(doc)
            
            # 1. Staleness check
            if guidance.valid_until and now_utc > guidance.valid_until:
                await db["citizen_safety_guidance"].update_one(
                    {"guidance_id": guidance.guidance_id},
                    {"$set": {"is_stale": True, "status": "STALE", "updated_at": now_utc}}
                )
                continue

            is_affected = False
            change_reasons: List[str] = []
            from app.models.enums import SafetyNotificationType
            notification_type = SafetyNotificationType.SAFETY_GUIDANCE_UPDATED

            # 2. Destination Suitability Impact Check
            if guidance.recommended_destination:
                dest_id = guidance.recommended_destination.destination_id
                if event_source_id and event_source_id == dest_id:
                    new_status = str(event_new_state.get("status", "")).upper()
                    new_avail = event_new_state.get("quantity_available") or event_new_state.get("capacity", {}).get("available")
                    if new_status in ["UNAVAILABLE", "CLOSED", "DAMAGED", "OFFLINE"] or (new_avail is not None and float(new_avail) <= 0):
                        is_affected = True
                        notification_type = SafetyNotificationType.DESTINATION_UPDATED
                        change_reasons.append(f"Designated facility ({guidance.recommended_destination.destination_name}) status changed ({new_status or 'Capacity Full'}).")

            # 3. Spatial Route Corridor & Hazard Proximity Check
            if event_lat is not None and event_lng is not None and guidance.route:
                e_lat = float(event_lat)
                e_lng = float(event_lng)
                
                dist_to_origin = haversine_distance_km(guidance.route.origin_latitude, guidance.route.origin_longitude, e_lat, e_lng)
                dist_to_dest = haversine_distance_km(guidance.route.destination_latitude, guidance.route.destination_longitude, e_lat, e_lng)
                
                min_corridor_dist = min(
                    [haversine_distance_km(pt[0], pt[1], e_lat, e_lng) for pt in guidance.route.polyline_points]
                ) if guidance.route.polyline_points else min(dist_to_origin, dist_to_dest)

                # Buffer: event within 1.2km of route waypoints or near endpoints
                if min_corridor_dist <= 1.2 or dist_to_origin <= 1.0 or dist_to_dest <= 0.8:
                    is_affected = True
                    if "ROAD_BLOCK" in event_type_str or "BLOCKED" in str(event_new_state.get("status", "")).upper():
                        notification_type = SafetyNotificationType.ROUTE_UPDATED
                        change_reasons.append(f"Transit corridor compromised by road blockage ({min_corridor_dist:.1f} km away).")
                    elif "FLOOD" in event_type_str or "FIRE" in event_type_str or "SURGE" in event_type_str or "LANDSLIDE" in event_type_str:
                        notification_type = SafetyNotificationType.HAZARD_WARNING
                        change_reasons.append(f"Hazard activity ({event_type_str}) detected near transit path ({min_corridor_dist:.1f} km).")
                    else:
                        notification_type = SafetyNotificationType.ROUTE_UPDATED
                        change_reasons.append(f"Operational change {event_type_str} detected along navigation path.")

            # 4. Situation Correlation Check
            if guidance.situation_id and getattr(event, "situation_id", None) == guidance.situation_id:
                if "SEVERITY" in event_type_str or "ESCALAT" in event_type_str or "EXPAND" in event_type_str:
                    is_affected = True
                    notification_type = SafetyNotificationType.SAFETY_GUIDANCE_UPDATED
                    change_reasons.append("Correlated emergency situation severity or impact zone has expanded.")

            if not is_affected:
                continue

            # 5. Dynamic Re-evaluation of Destination & Route
            origin_lat = guidance.route.origin_latitude if guidance.route else 0.0
            origin_lng = guidance.route.origin_longitude if guidance.route else 0.0
            
            if origin_lat == 0.0 or origin_lng == 0.0:
                rep = await db["citizen_reports"].find_one({"report_id": guidance.report_id})
                if rep:
                    loc = rep.get("location", {})
                    origin_lat = float(loc.get("latitude", 0.0))
                    origin_lng = float(loc.get("longitude", 0.0))

            new_dest, dest_reason, new_alts = await cls._find_verified_destination(
                origin_lat=origin_lat,
                origin_lng=origin_lng,
                emergency_type=guidance.emergency_type,
                db=db,
                description="; ".join(change_reasons),
            )

            new_route: Optional[RouteDetails] = None
            new_warnings: List[str] = []
            if new_dest:
                new_route = await RoutingService.calculate_hazard_aware_route(
                    origin_lat=origin_lat,
                    origin_lng=origin_lng,
                    dest_lat=new_dest.latitude,
                    dest_lng=new_dest.longitude,
                    db=db,
                )
                new_warnings.extend(new_route.route_warnings)
                if new_route.route_status == RouteStatus.ROUTE_UNSAFE:
                    notification_type = SafetyNotificationType.ROUTE_UNAVAILABLE

            fresh_actions, fresh_precautions = cls._synthesize_contextual_actions(
                emergency_type=guidance.emergency_type,
                description="; ".join(change_reasons),
                risk_level=guidance.risk_level,
                destination=new_dest,
                visual_evidence={},
                llm_extraction={},
                route=new_route,
            )

            # 6. Construct Immutable New Guidance Version
            new_version_num = guidance.version + 1
            new_guidance_id = generate_guidance_id()
            new_token = generate_secure_access_token()

            prior_history = list(guidance.history or [])
            prior_history.append({
                "guidance_id": guidance.guidance_id,
                "version": guidance.version,
                "generated_at": guidance.generated_at,
                "superseded_at": now_utc,
                "reason": "; ".join(change_reasons),
                "trigger_event_id": event_id,
            })

            requires_officer_review = bool(
                (guidance.risk_level == SeverityLevel.CRITICAL)
                or (new_route is not None and new_route.route_status == RouteStatus.ROUTE_UNSAFE)
            )
            approval_state = GuidanceApprovalState.PENDING_REVIEW if requires_officer_review else GuidanceApprovalState.AUTO_PUBLISHED

            new_guidance = CitizenSafetyGuidance(
                guidance_id=new_guidance_id,
                secure_access_token=new_token,
                report_id=guidance.report_id,
                situation_id=guidance.situation_id,
                generated_at=now_utc,
                valid_until=now_utc + timedelta(hours=4),
                status="ACTIVE",
                emergency_type=guidance.emergency_type,
                risk_level=guidance.risk_level,
                immediate_actions=fresh_actions,
                precautions=fresh_precautions,
                recommended_destination=new_dest,
                destination_reason=dest_reason,
                nearby_alternatives=new_alts,
                route=new_route,
                route_warnings=new_warnings,
                avoid_locations=new_route.avoid_areas if new_route else [],
                confidence=0.92 if new_dest else 0.85,
                evidence_references=guidance.evidence_references + [f"Dynamic Update Trigger: {event_type_str} ({event_id})"],
                requires_officer_approval=requires_officer_review,
                approval_state=approval_state,
                version=new_version_num,
                supersedes_guidance_id=guidance.guidance_id,
                superseded_by_guidance_id=None,
                trigger_event_id=event_id,
                change_reason="; ".join(change_reasons),
                is_stale=False,
                history=prior_history,
            )

            # Mark previous guidance as SUPERSEDED
            await db["citizen_safety_guidance"].update_one(
                {"guidance_id": guidance.guidance_id},
                {
                    "$set": {
                        "status": "SUPERSEDED",
                        "superseded_by_guidance_id": new_guidance_id,
                        "updated_at": now_utc,
                    }
                }
            )

            # Insert new guidance
            await db["citizen_safety_guidance"].insert_one(new_guidance.model_dump())

            # Update report pointer
            await db["citizen_reports"].update_one(
                {"report_id": guidance.report_id},
                {
                    "$set": {
                        "safety_guidance_id": new_guidance_id,
                        "safety_guidance_token": new_token,
                        "updated_at": now_utc,
                    }
                }
            )

            # If auto-published, broadcast push notification to registered devices
            if approval_state == GuidanceApprovalState.AUTO_PUBLISHED:
                try:
                    await WebPushService.notify_citizen_guidance_update(
                        new_guidance,
                        notification_type=notification_type,
                        event_id=event_id,
                        db=db,
                    )
                except Exception as push_err:
                    logger.warning(f"Push notification error on dynamic update for {new_guidance_id}: {push_err}")

            updated_guidances.append(new_guidance)
            logger.info(f"Dynamically generated Guidance {new_guidance_id} (v{new_version_num}) superseding {guidance.guidance_id} triggered by event {event_id}.")

        return updated_guidances

    @staticmethod
    def _doc_to_guidance(doc: Dict[str, Any]) -> CitizenSafetyGuidance:
        # Reconstruct verified destination if present
        dest_doc = doc.get("recommended_destination")
        dest_obj = VerifiedDestination(**dest_doc) if dest_doc else None

        # Reconstruct nearby alternatives
        nearby_alts_raw = doc.get("nearby_alternatives", [])
        nearby_alts = [VerifiedDestination(**a) for a in nearby_alts_raw if isinstance(a, dict)]

        # Reconstruct route if present
        route_doc = doc.get("route")
        route_obj = RouteDetails(**route_doc) if route_doc else None

        # Reconstruct avoid areas
        avoid_list = [HazardAvoidanceZone(**a) for a in doc.get("avoid_locations", [])]

        raw_risk = doc.get("risk_level", "MEDIUM")
        try:
            risk_enum = SeverityLevel(raw_risk)
        except Exception:
            risk_enum = SeverityLevel.MEDIUM

        raw_approval = doc.get("approval_state", "AUTO_PUBLISHED")
        try:
            approval_enum = GuidanceApprovalState(raw_approval)
        except Exception:
            approval_enum = GuidanceApprovalState.AUTO_PUBLISHED

        now_utc = datetime.now(timezone.utc)
        
        valid_until_raw = doc.get("valid_until")
        if isinstance(valid_until_raw, datetime):
            valid_until = valid_until_raw.replace(tzinfo=timezone.utc) if valid_until_raw.tzinfo is None else valid_until_raw
        else:
            valid_until = now_utc

        generated_at_raw = doc.get("generated_at")
        if isinstance(generated_at_raw, datetime):
            generated_at = generated_at_raw.replace(tzinfo=timezone.utc) if generated_at_raw.tzinfo is None else generated_at_raw
        else:
            generated_at = now_utc

        reviewed_at_raw = doc.get("reviewed_at")
        if isinstance(reviewed_at_raw, datetime):
            reviewed_at = reviewed_at_raw.replace(tzinfo=timezone.utc) if reviewed_at_raw.tzinfo is None else reviewed_at_raw
        else:
            reviewed_at = reviewed_at_raw

        is_stale_flag = bool(doc.get("is_stale", False)) or (valid_until is not None and now_utc > valid_until)

        return CitizenSafetyGuidance(
            guidance_id=doc.get("guidance_id", "GUD-UNKNOWN"),
            secure_access_token=doc.get("secure_access_token", ""),
            report_id=doc.get("report_id", ""),
            situation_id=doc.get("situation_id"),
            generated_at=generated_at,
            valid_until=valid_until,
            status=doc.get("status", "ACTIVE"),
            emergency_type=doc.get("emergency_type", "Other"),
            risk_level=risk_enum,
            immediate_actions=doc.get("immediate_actions", []),
            precautions=doc.get("precautions", []),
            recommended_destination=dest_obj,
            destination_reason=doc.get("destination_reason"),
            nearby_alternatives=nearby_alts,
            route=route_obj,
            route_warnings=doc.get("route_warnings", []),
            avoid_locations=avoid_list,
            confidence=float(doc.get("confidence", 0.90)),
            evidence_references=doc.get("evidence_references", []),
            requires_officer_approval=bool(doc.get("requires_officer_approval", False)),
            approval_state=approval_enum,
            officer_review_notes=doc.get("officer_review_notes"),
            reviewed_by=doc.get("reviewed_by"),
            reviewed_at=doc.get("reviewed_at"),
            version=int(doc.get("version", 1)),
            supersedes_guidance_id=doc.get("supersedes_guidance_id"),
            superseded_by_guidance_id=doc.get("superseded_by_guidance_id"),
            trigger_event_id=doc.get("trigger_event_id"),
            change_reason=doc.get("change_reason"),
            is_stale=is_stale_flag,
            history=doc.get("history", []),
        )
