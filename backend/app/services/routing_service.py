import math
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.db.mongodb import db_manager
from app.models.enums import RouteStatus, SeverityLevel
from app.models.safety_guidance import RouteDetails, HazardAvoidanceZone
from app.services.resource_matching import haversine_distance_km

logger = logging.getLogger("resilience.routing")


def decode_google_polyline(encoded: str) -> List[List[float]]:
    """
    Decodes a Google encoded polyline string into a list of [latitude, longitude] pairs.
    """
    points: List[List[float]] = []
    index = 0
    length = len(encoded)
    lat = 0
    lng = 0

    while index < length:
        # Decode latitude
        shift = 0
        result = 0
        while True:
            if index >= length:
                break
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlat = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += dlat

        # Decode longitude
        shift = 0
        result = 0
        while True:
            if index >= length:
                break
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlng = ~(result >> 1) if (result & 1) else (result >> 1)
        lng += dlng

        points.append([round(lat * 1e-5, 6), round(lng * 1e-5, 6)])

    return points


class RoutingService:
    """
    Real Road-Network Coordinate Routing & Hazard-Aware Navigation Service.
    
    CRITICAL ARCHITECTURAL CONSTRAINTS:
    - Calculates genuine distances, durations, and road-following polyline coordinates using real road networks.
    - Primary: Google Routes API (New computeRoutes).
    - Secondary: Google Directions API (Driving mode).
    - NEVER generates straight lines, coordinate interpolations, or field-crossing shortcuts.
    - Returns ROUTE_UNAVAILABLE if genuine road-network routing fails.
    """

    # In-memory TTL cache for genuine Google Routes responses
    _routes_cache: Dict[str, Dict[str, Any]] = {}
    _CACHE_TTL_SECONDS: float = 86400.0  # 24 hours

    # Optional test injection override
    _custom_router = None

    @classmethod
    def set_custom_router(cls, router_fn):
        """Allows test fixtures to provide deterministic road graph responses in isolated unit test environments."""
        cls._custom_router = router_fn

    @classmethod
    def clear_cache(cls):
        """Clears in-memory routes cache."""
        cls._routes_cache.clear()

    @classmethod
    def _get_cache_key(cls, origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float) -> str:
        return f"{round(origin_lat, 4)}_{round(origin_lng, 4)}_{round(dest_lat, 4)}_{round(dest_lng, 4)}"

    @classmethod
    async def calculate_hazard_aware_route(
        cls,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> RouteDetails:
        """
        Calculates a real hazard-aware road route between citizen origin and verified destination.
        """
        if not (-90.0 <= origin_lat <= 90.0 and -180.0 <= origin_lng <= 180.0):
            return cls._make_unavailable_route(origin_lat, origin_lng, dest_lat, dest_lng, "Invalid origin coordinates.")
        if not (-90.0 <= dest_lat <= 90.0 and -180.0 <= dest_lng <= 180.0):
            return cls._make_unavailable_route(origin_lat, origin_lng, dest_lat, dest_lng, "Invalid destination coordinates.")

        straight_dist_km = haversine_distance_km(origin_lat, origin_lng, dest_lat, dest_lng)
        if straight_dist_km < 0.001:
            # Same location - zero distance, no polyline needed
            return RouteDetails(
                origin_latitude=origin_lat,
                origin_longitude=origin_lng,
                destination_latitude=dest_lat,
                destination_longitude=dest_lng,
                distance_km=0.0,
                estimated_duration_minutes=0.0,
                route_status=RouteStatus.CALCULATED,
                polyline_points=[],
                route_warnings=["You are currently at the verified destination site."],
                avoid_areas=[],
                provider="Local Direct Proximity",
                calculated_at=datetime.now(timezone.utc),
            )

        road_route = None
        # 1. Check if test router injected
        if cls._custom_router is not None:
            try:
                import inspect
                sig = inspect.signature(cls._custom_router)
                if len(sig.parameters) >= 5:
                    res = await cls._custom_router(origin_lat, origin_lng, dest_lat, dest_lng, db)
                else:
                    res = await cls._custom_router(origin_lat, origin_lng, dest_lat, dest_lng)
                
                if isinstance(res, RouteDetails):
                    return res
                elif isinstance(res, tuple) and len(res) == 4:
                    pts, d_km, dur_min, prov = res
                    if not pts or len(pts) < 2:
                        return cls._make_unavailable_route(origin_lat, origin_lng, dest_lat, dest_lng, "Safe road route unavailable.")
                    road_route = {
                        "polyline_points": pts,
                        "distance_km": d_km,
                        "duration_minutes": dur_min,
                        "provider": prov,
                    }
            except Exception as custom_err:
                logger.warning(f"Custom router execution notice: {custom_err}")

        # 2. Attempt Real Road Network Routing with persistent & memory cache fallback
        if road_route is None:
            road_route = await cls._fetch_real_road_route(origin_lat, origin_lng, dest_lat, dest_lng, db=db)
        
        if not road_route:
            return cls._make_unavailable_route(
                origin_lat, origin_lng, dest_lat, dest_lng,
                "No accessible driving route between coordinates.",
                status=RouteStatus.ROUTE_UNAVAILABLE,
            )

        if "error_type" in road_route:
            err_type = road_route.get("error_type")
            err_msg = road_route.get("message", "Route calculation error.")
            if err_type == "PROVIDER_QUOTA_EXCEEDED":
                return cls._make_unavailable_route(
                    origin_lat, origin_lng, dest_lat, dest_lng,
                    err_msg,
                    status=RouteStatus.ROUTE_PROVIDER_ERROR,
                )
            elif err_type == "NO_ROUTE_FOUND":
                return cls._make_unavailable_route(
                    origin_lat, origin_lng, dest_lat, dest_lng,
                    err_msg,
                    status=RouteStatus.ROUTE_UNAVAILABLE,
                )
            else:
                return cls._make_unavailable_route(
                    origin_lat, origin_lng, dest_lat, dest_lng,
                    err_msg,
                    status=RouteStatus.ROUTE_PROVIDER_ERROR,
                )

        if not road_route.get("polyline_points") or len(road_route["polyline_points"]) < 2:
            return cls._make_unavailable_route(
                origin_lat, origin_lng, dest_lat, dest_lng,
                "No valid driving route corridor returned.",
                status=RouteStatus.ROUTE_UNAVAILABLE,
            )

        road_dist_km = road_route["distance_km"]
        road_duration_min = road_route["duration_minutes"]
        polyline_points = road_route["polyline_points"]
        encoded_polyline = road_route.get("encoded_polyline")
        provider_name = road_route["provider"]
        is_restricted = road_route.get("is_restricted", False)

        # 3. Intersect real road corridor with active hazards in MongoDB
        route_warnings: List[str] = list(road_route.get("warnings", []))
        avoid_areas: List[HazardAvoidanceZone] = []
        is_unsafe = False

        if is_restricted:
            if "Available route has access restrictions." not in route_warnings:
                route_warnings.insert(0, "Available route has access restrictions.")

        if db is None:
            db = db_manager.db

        if db is not None:
            try:
                mid_lat = (origin_lat + dest_lat) / 2.0
                mid_lng = (origin_lng + dest_lng) / 2.0
                scan_radius = max(straight_dist_km / 2.0 + 2.0, 5.0)

                cursor = db["situations"].find({
                    "status": {"$in": ["ACTIVE", "RESPONSE_IN_PROGRESS", "OFFICER_REVIEW", "MONITORING"]}
                })

                async for sit_doc in cursor:
                    c_loc = sit_doc.get("center_location") or sit_doc.get("location") or {}
                    s_lat = c_loc.get("latitude")
                    s_lng = c_loc.get("longitude")
                    if s_lat is None or s_lng is None:
                        continue

                    s_lat_f = float(s_lat)
                    s_lng_f = float(s_lng)
                    s_dist = haversine_distance_km(mid_lat, mid_lng, s_lat_f, s_lng_f)
                    
                    min_corridor_dist = min(
                        [haversine_distance_km(pt[0], pt[1], s_lat_f, s_lng_f) for pt in polyline_points]
                    ) if polyline_points else s_dist

                    impact_zone = sit_doc.get("impact_zone")
                    radius_raw = (impact_zone.get("radius_km") if isinstance(impact_zone, dict) else None) or c_loc.get("radius_km") or 1.0
                    try:
                        radius_val = float(radius_raw)
                    except Exception:
                        radius_val = 1.0

                    if s_dist <= scan_radius or min_corridor_dist <= (radius_val + 2.0):
                        dest_hazard_dist = haversine_distance_km(dest_lat, dest_lng, s_lat_f, s_lng_f)
                        sit_type = sit_doc.get("emergency_type") or sit_doc.get("title") or "Hazard Zone"
                        raw_sev = sit_doc.get("severity_level", "MEDIUM")
                        sit_sev_str = str(raw_sev.value if hasattr(raw_sev, "value") else raw_sev)
                        
                        hazard_zone = HazardAvoidanceZone(
                            hazard_id=str(sit_doc.get("situation_id", "HAZ-001")),
                            hazard_type=str(sit_type),
                            latitude=s_lat_f,
                            longitude=s_lng_f,
                            radius_km=round(radius_val, 2),
                            warning_message=f"Active {sit_type} situation ({sit_sev_str}) located {min_corridor_dist:.1f}km from transit corridor.",
                        )
                        avoid_areas.append(hazard_zone)
                        route_warnings.append(
                            f"Caution: Approaching {sit_type} zone ({min_corridor_dist:.1f} km away). Maintain situational awareness."
                        )

                        if dest_hazard_dist < 0.3 and ("CRITICAL" in sit_sev_str.upper() or "HIGH" in sit_sev_str.upper()):
                            is_unsafe = True
                            route_warnings.append("Destination is currently in immediate proximity to a critical hazard zone.")

            except Exception as e:
                logger.warning(f"Hazard intersection check warning: {e}", exc_info=True)

        if is_restricted:
            status = RouteStatus.RESTRICTED
        elif is_unsafe:
            status = RouteStatus.ROUTE_UNSAFE
        else:
            status = RouteStatus.CALCULATED

        return RouteDetails(
            origin_latitude=origin_lat,
            origin_longitude=origin_lng,
            destination_latitude=dest_lat,
            destination_longitude=dest_lng,
            distance_km=round(road_dist_km, 2),
            estimated_duration_minutes=round(road_duration_min, 1),
            route_status=status,
            polyline_points=polyline_points,
            encoded_polyline=encoded_polyline,
            route_warnings=route_warnings,
            avoid_areas=avoid_areas,
            provider=provider_name,
            calculated_at=datetime.now(timezone.utc),
        )

    @classmethod
    async def _fetch_real_road_route(
        cls,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Fetches genuine road geometry using Google Routes API (New).
        Google Routes API is the authoritative routing provider for Citizen Safety Guidance.
        """
        import time

        cache_key = cls._get_cache_key(origin_lat, origin_lng, dest_lat, dest_lng)
        now_ts = time.time()

        # A. Check In-Memory Cache
        if cache_key in cls._routes_cache:
            entry = cls._routes_cache[cache_key]
            if (now_ts - entry.get("timestamp", 0)) < cls._CACHE_TTL_SECONDS:
                logger.info(f"Using in-memory cached Google Route for key {cache_key}")
                return entry["data"]

        # B. Check MongoDB Persistent Cache
        if db is None:
            db = db_manager.db

        if db is not None:
            try:
                cached_doc = await db["google_routes_cache"].find_one({"cache_key": cache_key})
                if cached_doc and cached_doc.get("polyline_points") and len(cached_doc["polyline_points"]) >= 2:
                    route_data = {
                        "distance_km": float(cached_doc.get("distance_km", 0.0)),
                        "duration_minutes": float(cached_doc.get("duration_minutes", 0.0)),
                        "polyline_points": cached_doc.get("polyline_points", []),
                        "encoded_polyline": cached_doc.get("encoded_polyline"),
                        "provider": cached_doc.get("provider", "Google Routes API (Driving)"),
                        "is_restricted": cached_doc.get("is_restricted", False),
                        "warnings": cached_doc.get("warnings", []),
                    }
                    cls._routes_cache[cache_key] = {"data": route_data, "timestamp": now_ts}
                    logger.info(f"Using MongoDB cached Google Route for key {cache_key}")
                    return route_data
            except Exception as db_err:
                logger.warning(f"Error checking MongoDB routes cache: {db_err}")

        # C. Call Google Routes API (New) - computeRoutes
        google_api_key = settings.GOOGLE_MAPS_API_KEY or settings.VITE_GOOGLE_MAPS_API_KEY
        if not google_api_key or not google_api_key.strip():
            logger.warning("Google Maps API Key missing for Google Routes API")
            return {"error_type": "PROVIDER_ERROR", "message": "Google Maps API Key missing."}

        key_clean = google_api_key.strip()
        timeout_sec = getattr(settings, "ROUTING_TIMEOUT_SECONDS", 8.0)

        logger.info(
            f"[ROUTING_DIAGNOSTIC] Initiating Google Routes API request: "
            f"origin=({origin_lat}, {origin_lng}), destination=({dest_lat}, {dest_lng})"
        )

        try:
            routes_url = "https://routes.googleapis.com/directions/v2:computeRoutes"
            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": key_clean,
                "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline,routes.warnings,routes.travelAdvisory",
            }
            body = {
                "origin": {
                    "location": {
                        "latLng": {
                            "latitude": origin_lat,
                            "longitude": origin_lng,
                        }
                    }
                },
                "destination": {
                    "location": {
                        "latLng": {
                            "latitude": dest_lat,
                            "longitude": dest_lng,
                        }
                    }
                },
                "travelMode": "DRIVE",
                "routingPreference": "TRAFFIC_AWARE",
                "computeAlternativeRoutes": False,
                "routeModifiers": {
                    "avoidTolls": False,
                    "avoidHighways": False,
                    "avoidFerries": False,
                },
                "polylineQuality": "HIGH_QUALITY",
                "polylineEncoding": "ENCODED_POLYLINE",
                "languageCode": "en-US",
                "units": "METRIC",
            }
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                resp = await client.post(routes_url, json=body, headers=headers)
                logger.info(f"[ROUTING_DIAGNOSTIC] Google Routes API HTTP Status: {resp.status_code}")
                
                if resp.status_code == 200:
                    data = resp.json()
                    routes = data.get("routes", [])
                    logger.info(f"[ROUTING_DIAGNOSTIC] routes[] count: {len(routes)}")
                    
                    if not routes:
                        logger.warning(f"[ROUTING_DIAGNOSTIC] Google Routes returned 0 routes: {data}")
                        return {"error_type": "NO_ROUTE_FOUND", "message": "Google Routes found no drivable route."}

                    r = routes[0]
                    dist_meters = r.get("distanceMeters", 0)
                    dur_str = r.get("duration", "0s")
                    dur_seconds = 0.0
                    if isinstance(dur_str, str):
                        dur_str_clean = dur_str.rstrip("s")
                        try:
                            dur_seconds = float(dur_str_clean)
                        except Exception:
                            dur_seconds = 0.0
                    elif isinstance(dur_str, (int, float)):
                        dur_seconds = float(dur_str)

                    poly_str = r.get("polyline", {}).get("encodedPolyline", "")
                    points = decode_google_polyline(poly_str) if poly_str else []

                    # Extract warnings and travel advisory restrictions
                    raw_warnings = r.get("warnings", [])
                    travel_advisory = r.get("travelAdvisory", {})
                    warnings_list: List[str] = []
                    is_restricted = False

                    if isinstance(raw_warnings, list):
                        for w in raw_warnings:
                            if isinstance(w, str):
                                warnings_list.append(w)
                            elif isinstance(w, dict) and "text" in w:
                                warnings_list.append(w["text"])

                    combined_warning_text = (" ".join(warnings_list) + " " + str(travel_advisory)).lower()
                    if any(kw in combined_warning_text for kw in ["restricted", "private road", "permit required", "closed to public", "access restriction", "access restrictions"]):
                        is_restricted = True

                    logger.info(
                        f"[ROUTING_DIAGNOSTIC] Route parsed: distanceMeters={dist_meters}, "
                        f"durationSeconds={dur_seconds}, polylinePointsCount={len(points)}, "
                        f"encodedPolylineLength={len(poly_str)}, isRestricted={is_restricted}, "
                        f"warningsCount={len(warnings_list)}"
                    )

                    if dist_meters > 0 and len(points) >= 2:
                        dist_km = round(dist_meters / 1000.0, 2)
                        dur_min = round(dur_seconds / 60.0, 1)
                        if dur_min <= 0.0 and dist_km > 0:
                            dur_min = round(max(1.0, (dist_km / 40.0) * 60.0), 1)

                        route_res = {
                            "distance_km": dist_km,
                            "duration_minutes": dur_min,
                            "polyline_points": points,
                            "encoded_polyline": poly_str,
                            "provider": "Google Routes API (Driving)",
                            "is_restricted": is_restricted,
                            "warnings": warnings_list,
                        }
                        # Save to in-memory cache
                        cls._routes_cache[cache_key] = {"data": route_res, "timestamp": now_ts}

                        # Save to MongoDB persistent cache
                        if db is not None:
                            try:
                                await db["google_routes_cache"].update_one(
                                    {"cache_key": cache_key},
                                    {
                                        "$set": {
                                            "cache_key": cache_key,
                                            "origin_latitude": origin_lat,
                                            "origin_longitude": origin_lng,
                                            "destination_latitude": dest_lat,
                                            "destination_longitude": dest_lng,
                                            "distance_km": dist_km,
                                            "duration_minutes": dur_min,
                                            "polyline_points": points,
                                            "encoded_polyline": poly_str,
                                            "provider": "Google Routes API (Driving)",
                                            "is_restricted": is_restricted,
                                            "warnings": warnings_list,
                                            "last_updated": datetime.now(timezone.utc),
                                        }
                                    },
                                    upsert=True,
                                )
                            except Exception as save_err:
                                logger.warning(f"Error persisting Google route to MongoDB: {save_err}")

                        return route_res
                    else:
                        logger.warning(f"[ROUTING_DIAGNOSTIC] Invalid route geometry from Google Routes: dist={dist_meters}, points={len(points)}")
                        return {"error_type": "NO_ROUTE_FOUND", "message": "Google Routes returned invalid geometry."}
                elif resp.status_code == 429:
                    logger.warning(f"[ROUTING_DIAGNOSTIC] Google Routes API HTTP 429 Quota Exhausted: {resp.text}")
                    return {
                        "error_type": "PROVIDER_QUOTA_EXCEEDED",
                        "message": "Google Routes API quota limit reached (HTTP 429). Live driving route computation temporarily unavailable."
                    }
                else:
                    logger.warning(f"[ROUTING_DIAGNOSTIC] Google Routes API HTTP {resp.status_code}: {resp.text}")
                    return {
                        "error_type": "PROVIDER_ERROR",
                        "message": f"Google Routes API returned HTTP {resp.status_code}."
                    }
        except Exception as r_err:
            logger.warning(f"[ROUTING_DIAGNOSTIC] Google Routes API exception: {r_err}")
            return {
                "error_type": "PROVIDER_ERROR",
                "message": f"Google Routes API network error: {r_err}"
            }

        return None

    @classmethod
    def _make_unavailable_route(
        cls,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        reason: str = "NO_ACCESSIBLE_DRIVING_ROUTE",
        status: RouteStatus = RouteStatus.ROUTE_UNAVAILABLE,
    ) -> RouteDetails:
        return RouteDetails(
            origin_latitude=origin_lat,
            origin_longitude=origin_lng,
            destination_latitude=dest_lat,
            destination_longitude=dest_lng,
            distance_km=0.0,
            estimated_duration_minutes=0.0,
            route_status=status,
            polyline_points=[],
            encoded_polyline=None,
            route_warnings=[reason],
            avoid_areas=[],
            provider="None",
            calculated_at=datetime.now(timezone.utc),
        )

