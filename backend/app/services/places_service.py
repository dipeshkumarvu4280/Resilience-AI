import logging
import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.models.enums import DestinationType
from app.services.resource_matching import haversine_distance_km

logger = logging.getLogger("resilience.places")


class PlacesService:
    """
    Real-Time Places Discovery Service using Google Places API (New).
    
    CRITICAL CONSTRAINTS:
    - NEVER returns hardcoded, fake, or synthetic facility names or coordinates.
    - Uses Google Places API (New searchNearby) with strict locationRestriction circle and DISTANCE ranking.
    - Does NOT use natural-language text search (searchText) with embedded coordinates or soft locationBias.
    - Does NOT substitute distant prominent city facilities for local rural emergencies.
    - Caches genuine Google Places responses in-memory and in MongoDB to minimize quota consumption.
    - When quota is exhausted (HTTP 429 / RESOURCE_EXHAUSTED), uses genuine cached Google Places if available,
      or returns a truthful failure state (GOOGLE_PLACES_QUOTA_EXCEEDED).
    - Returns structured real place objects with verified place_id, name, lat, lng, address, and discovery timestamp.
    """

    # In-memory TTL cache for genuine Google Places responses
    _places_cache: Dict[str, Dict[str, Any]] = {}
    _CACHE_TTL_SECONDS: float = 3600.0  # 1 hour in-memory cache

    # Optional test injection override for deterministic testing
    _custom_places_provider = None

    @classmethod
    def set_custom_places_provider(cls, provider_fn):
        """Allows isolated unit test fixtures to supply controlled place discovery responses."""
        cls._custom_places_provider = provider_fn

    @classmethod
    def clear_cache(cls):
        """Clears the in-memory places cache."""
        cls._places_cache.clear()

    @classmethod
    def estimate_drive_time_minutes(cls, distance_km: float) -> float:
        """
        Estimates real civilian road driving time in minutes based on distance.
        Uses 40 km/h average emergency civilian speed (1.5 min per km) with 1.0 min minimum.
        """
        if distance_km <= 0:
            return 1.0
        return round(max(1.0, (distance_km / 40.0) * 60.0), 1)

    @classmethod
    def _get_cache_key(cls, lat: float, lng: float, category: str, radius_meters: int) -> str:
        return f"{round(lat, 3)}_{round(lng, 3)}_{category.upper()}_{radius_meters}"

    @classmethod
    async def discover_nearby_facilities(
        cls,
        origin_lat: Optional[float] = None,
        origin_lng: Optional[float] = None,
        need_category: str = "GENERAL",
        radius_meters: int = 15000,
        max_results: int = 5,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> List[Dict[str, Any]]:
        """
        Discovers genuine nearby emergency facilities based on the citizen's need category.
        
        Supported need categories:
        - 'MEDICAL' -> Hospital, Medical Clinic, Doctor
        - 'POLICE' -> Police Station, Law Enforcement
        - 'FIRE' -> Fire Station, Emergency Medical Aid, Civic Assembly
        - 'TRANSIT' -> Bus Station, Transit Station
        - 'SHELTER' -> Community Center, Evacuation Shelter, Civic Hall
        - 'FLOOD' -> Evacuation Center, Community Center, Hospital
        """
        actual_lat = origin_lat if origin_lat is not None else lat
        actual_lng = origin_lng if origin_lng is not None else lng
        if actual_lat is None or actual_lng is None:
            return []

        # 1. Check test injection override
        if cls._custom_places_provider is not None:
            try:
                res = await cls._custom_places_provider(actual_lat, actual_lng, need_category, radius_meters)
                if isinstance(res, list):
                    return res[:max_results]
            except Exception as e:
                logger.warning(f"Custom places provider execution warning: {e}")

        # 2. Check in-memory cache for recent genuine Google Places response
        cache_key = cls._get_cache_key(actual_lat, actual_lng, need_category, radius_meters)
        cached_entry = cls._places_cache.get(cache_key)
        if cached_entry:
            age = time.time() - cached_entry.get("timestamp", 0)
            if age < cls._CACHE_TTL_SECONDS:
                cached_results = cached_entry.get("results", [])
                logger.info(f"Serving {len(cached_results)} genuine Google Places from in-memory cache for {cache_key} (age: {age:.0f}s)")
                return cached_results[:max_results]

        # 3. Check MongoDB persistent cache for genuine Google Places responses
        if db is not None:
            try:
                mongo_cached = await cls._fetch_from_mongo_cache(db, actual_lat, actual_lng, need_category, radius_meters)
                if mongo_cached:
                    cls._places_cache[cache_key] = {
                        "timestamp": time.time(),
                        "results": mongo_cached,
                    }
                    logger.info(f"Serving {len(mongo_cached)} genuine Google Places from MongoDB persistent cache for {cache_key}")
                    return mongo_cached[:max_results]
            except Exception as m_err:
                logger.debug(f"MongoDB places cache read notice: {m_err}")

        # 4. Fetch live from Google Places API (New searchNearby)
        google_results = await cls._fetch_google_places(
            origin_lat=actual_lat,
            origin_lng=actual_lng,
            need_category=need_category,
            radius_meters=radius_meters,
        )
        if google_results:
            # Store in in-memory cache
            cls._places_cache[cache_key] = {
                "timestamp": time.time(),
                "results": google_results,
            }
            # Persist genuine provider places to MongoDB
            if db is not None:
                try:
                    await cls._save_to_mongo_cache(db, google_results, need_category)
                except Exception as save_err:
                    logger.debug(f"MongoDB places cache write notice: {save_err}")

            return google_results[:max_results]

        # 5. If live Google fetch returned 429 or empty, query any existing genuine Google Places near coordinates from MongoDB
        if db is not None:
            try:
                fallback_places = await cls._query_nearby_mongo_places(db, actual_lat, actual_lng, need_category, radius_meters)
                if fallback_places:
                    logger.info(f"Retrieved {len(fallback_places)} previously verified Google Places from persistent store during quota limit.")
                    return fallback_places[:max_results]
            except Exception as fb_err:
                logger.debug(f"Nearby MongoDB places query notice: {fb_err}")

        return []

    @classmethod
    async def _fetch_from_mongo_cache(
        cls,
        db: AsyncIOMotorDatabase,
        origin_lat: float,
        origin_lng: float,
        need_category: str,
        radius_meters: int,
    ) -> List[Dict[str, Any]]:
        cursor = db["google_places_cache"].find({
            "category": need_category.upper(),
        })
        results = []
        radius_km = radius_meters / 1000.0
        async for doc in cursor:
            p_lat = doc.get("latitude")
            p_lng = doc.get("longitude")
            if p_lat is not None and p_lng is not None:
                dist = haversine_distance_km(origin_lat, origin_lng, float(p_lat), float(p_lng))
                if dist <= radius_km:
                    p_types = doc.get("google_place_types") or []
                    if p_types:
                        d_type = cls.normalize_google_place_type(p_types)
                    else:
                        d_type_raw = str(doc.get("destination_type") or "").replace("DestinationType.", "").strip().upper()
                        try:
                            d_type = DestinationType(d_type_raw) if d_type_raw else cls.normalize_google_place_type(p_types)
                        except Exception:
                            d_type = cls.normalize_google_place_type(p_types)

                    results.append({
                        "facility_id": f"PLC-{doc.get('place_id', str(time.time()))}",
                        "place_id": doc.get("place_id"),
                        "name": doc.get("name"),
                        "destination_type": d_type,
                        "latitude": float(p_lat),
                        "longitude": float(p_lng),
                        "address": doc.get("address") or "Google Verified Site",
                        "distance_km": round(dist, 2),
                        "provider": "Google Places (Persistent Provider Store)",
                        "last_checked": datetime.now(timezone.utc).isoformat(),
                        "rating": doc.get("rating"),
                        "open_now": doc.get("open_now"),
                        "google_place_types": p_types,
                    })
        results.sort(key=lambda x: x["distance_km"])
        return results

    @classmethod
    async def _save_to_mongo_cache(
        cls,
        db: AsyncIOMotorDatabase,
        places: List[Dict[str, Any]],
        need_category: str,
    ):
        for p in places:
            p_id = p.get("place_id")
            if not p_id:
                continue
            d_type_val = p.get("destination_type")
            if isinstance(d_type_val, DestinationType):
                d_type_str = d_type_val.value
            else:
                d_type_str = str(d_type_val).replace("DestinationType.", "").strip().upper()

            await db["google_places_cache"].update_one(
                {"place_id": p_id},
                {
                    "$set": {
                        "place_id": p_id,
                        "name": p.get("name"),
                        "address": p.get("address"),
                        "latitude": p.get("latitude"),
                        "longitude": p.get("longitude"),
                        "rating": p.get("rating"),
                        "open_now": p.get("open_now"),
                        "category": need_category.upper(),
                        "destination_type": d_type_str,
                        "google_place_types": p.get("google_place_types", []),
                        "provider": "GOOGLE",
                        "last_updated": datetime.now(timezone.utc),
                    }
                },
                upsert=True,
            )

    @classmethod
    async def _query_nearby_mongo_places(
        cls,
        db: AsyncIOMotorDatabase,
        origin_lat: float,
        origin_lng: float,
        need_category: str,
        radius_meters: int,
    ) -> List[Dict[str, Any]]:
        cursor = db["google_places_cache"].find({})
        results = []
        radius_km = radius_meters / 1000.0
        async for doc in cursor:
            p_lat = doc.get("latitude")
            p_lng = doc.get("longitude")
            if p_lat is not None and p_lng is not None:
                dist = haversine_distance_km(origin_lat, origin_lng, float(p_lat), float(p_lng))
                if dist <= radius_km:
                    p_types = doc.get("google_place_types") or []
                    if p_types:
                        d_type = cls.normalize_google_place_type(p_types)
                    else:
                        d_type_raw = str(doc.get("destination_type") or "").replace("DestinationType.", "").strip().upper()
                        try:
                            d_type = DestinationType(d_type_raw) if d_type_raw else cls.normalize_google_place_type(p_types)
                        except Exception:
                            d_type = cls.normalize_google_place_type(p_types)

                    results.append({
                        "facility_id": f"PLC-{doc.get('place_id', str(time.time()))}",
                        "place_id": doc.get("place_id"),
                        "name": doc.get("name"),
                        "destination_type": d_type,
                        "latitude": float(p_lat),
                        "longitude": float(p_lng),
                        "address": doc.get("address") or "Google Verified Site",
                        "distance_km": round(dist, 2),
                        "provider": "Google Places (Verified Provider Store)",
                        "last_checked": datetime.now(timezone.utc).isoformat(),
                        "rating": doc.get("rating"),
                        "open_now": doc.get("open_now"),
                        "google_place_types": p_types,
                    })
        results.sort(key=lambda x: x["distance_km"])
        return results

    @classmethod
    async def _fetch_google_places(
        cls,
        origin_lat: float,
        origin_lng: float,
        need_category: str,
        radius_meters: int,
    ) -> List[Dict[str, Any]]:
        google_api_key = settings.GOOGLE_MAPS_API_KEY or settings.VITE_GOOGLE_MAPS_API_KEY
        if not google_api_key or not google_api_key.strip():
            logger.warning("Google Maps API key not configured for Places discovery.")
            return []

        key_clean = google_api_key.strip()
        timeout_sec = getattr(settings, "ROUTING_TIMEOUT_SECONDS", 6.0)

        # 1. Primary: Google Places API (New) - places.googleapis.com/v1/places:searchNearby
        new_types = {
            "MEDICAL": ["hospital", "medical_clinic", "doctor"],
            "POLICE": ["police"],
            "FIRE": ["fire_station"],
            "TRANSIT": ["bus_station", "transit_station"],
            "SHELTER": ["community_center", "city_hall", "local_government_office"],
            "FLOOD": ["community_center", "city_hall", "local_government_office", "hospital", "medical_clinic"],
        }
        included_types = new_types.get(need_category.upper(), ["hospital"])

        try:
            async with httpx.AsyncClient(timeout=timeout_sec) as client:
                new_url = "https://places.googleapis.com/v1/places:searchNearby"
                new_headers = {
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": key_clean,
                    "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.location,places.rating,places.userRatingCount,places.currentOpeningHours,places.businessStatus,places.types",
                }
                new_body = {
                    "includedTypes": included_types,
                    "languageCode": "en",
                    "maxResultCount": 20,
                    "rankPreference": "DISTANCE",
                    "locationRestriction": {
                        "circle": {
                            "center": {
                                "latitude": origin_lat,
                                "longitude": origin_lng,
                            },
                            "radius": float(min(radius_meters, 50000)),
                        }
                    },
                }
                new_resp = await client.post(new_url, json=new_body, headers=new_headers)
                if new_resp.status_code == 200:
                    new_data = new_resp.json()
                    places = new_data.get("places", [])
                    if places:
                        results = []
                        for p in places:
                            # Skip closed/decommissioned facilities
                            b_status = p.get("businessStatus", "OPERATIONAL")
                            if b_status in ["CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"]:
                                continue

                            p_types = p.get("types", [])
                            if not cls._is_valid_place_type(p_types, need_category):
                                continue

                            loc = p.get("location", {})
                            p_lat = loc.get("latitude")
                            p_lng = loc.get("longitude")
                            name = p.get("displayName", {}).get("text")
                            if p_lat is not None and p_lng is not None and name:
                                dist_km = haversine_distance_km(origin_lat, origin_lng, float(p_lat), float(p_lng))
                                results.append({
                                    "facility_id": f"PLC-{p.get('id', str(time.time()))}",
                                    "place_id": p.get("id"),
                                    "name": name,
                                    "destination_type": cls.normalize_google_place_type(p_types),
                                    "latitude": float(p_lat),
                                    "longitude": float(p_lng),
                                    "address": p.get("formattedAddress") or "Google Verified Site",
                                    "distance_km": round(dist_km, 2),
                                    "provider": "Google Places Live Discovery",
                                    "last_checked": datetime.now(timezone.utc).isoformat(),
                                    "rating": p.get("rating"),
                                    "open_now": p.get("currentOpeningHours", {}).get("openNow"),
                                    "google_place_types": p_types,
                                })
                        # Sort strictly by geographic distance from origin
                        results.sort(key=lambda x: x["distance_km"])
                        if results:
                            return results
                elif new_resp.status_code == 429 or "RESOURCE_EXHAUSTED" in new_resp.text:
                    logger.warning("GOOGLE_PLACES_QUOTA_EXCEEDED: Google Places (New searchNearby) daily quota limit reached (HTTP 429).")
                    return []
                else:
                    logger.info(f"Google Places (New searchNearby) HTTP {new_resp.status_code}: {new_resp.text}")
        except Exception as new_err:
            logger.info(f"Places API (New searchNearby) notice: {new_err}")

        return []

    @classmethod
    def _is_valid_place_type(cls, place_types: List[str], need_category: str) -> bool:
        """
        Strict situation-aware type filter to prevent commercial stores, wholesalers,
        restaurants, salons, tailor shops, decorators, lighting shops, electrical businesses,
        and irrelevant commercial places from entering emergency recommendations.
        """
        if not place_types:
            return False

        types_lower = [str(t).lower() for t in place_types]
        types_set = set(types_lower)

        disallowed_commercial = {
            "restaurant", "food", "grocery_or_supermarket", "supermarket",
            "store", "clothing_store", "wholesaler", "liquor_store",
            "bakery", "cafe", "meal_takeaway", "meal_delivery",
            "beauty_salon", "hair_care", "spa", "laundry", "bar", "night_club",
            "convenience_store", "department_store", "shoe_store", "shopping_mall",
            "home_goods_store", "jewelry_store", "florist", "furniture_store",
            "electronics_store", "book_store", "pet_store", "car_dealer",
            "car_repair", "car_wash", "gas_station", "parking", "bank",
            "atm", "real_estate_agency", "travel_agency", "insurance_agency",
            "hair_salon", "beauty_parlor", "tailor", "hairdresser", "event_venue",
            "lighting_store", "electrician", "hardware_store", "home_improvement_store",
            "general_contractor", "plumber", "painter", "roofing_contractor",
            "locksmith", "commercial_services", "lodging", "hotel", "motel",
            "party_store", "event_planner", "wedding_service"
        }

        # Any commercial business without an explicit operational emergency facility type is rejected
        operational_types = {
            "hospital", "medical_clinic", "doctor", "health", "pharmacy", "medical_center",
            "fire_station",
            "police", "law_enforcement",
            "bus_station", "transit_station", "train_station",
            "community_center", "city_hall", "local_government_office", "school", "stadium", "civic_center"
        }

        if not types_set.intersection(operational_types):
            return False

        # If it has commercial types without possessing genuine emergency services types, reject
        has_primary_emergency = bool(types_set.intersection({
            "hospital", "doctor", "medical_clinic", "fire_station", "police", "law_enforcement"
        }))
        if types_set.intersection(disallowed_commercial) and not has_primary_emergency:
            return False

        cat = need_category.upper()
        if cat in ["MEDICAL", "ROAD_ACCIDENT"]:
            return bool(types_set.intersection({"hospital", "medical_clinic", "doctor", "health", "pharmacy", "medical_center"}))
        elif cat == "POLICE":
            return bool(types_set.intersection({"police", "law_enforcement"}))
        elif cat == "FIRE":
            # Fire search returns fire stations, hospitals/clinics/doctors, or community centers
            return bool(types_set.intersection({"fire_station", "hospital", "medical_clinic", "doctor", "community_center", "city_hall"}))
        elif cat == "TRANSIT":
            return bool(types_set.intersection({"bus_station", "transit_station", "bus_stop", "train_station", "subway_station", "light_rail_station"}))
        elif cat in ["SHELTER", "FLOOD"]:
            return bool(types_set.intersection({"community_center", "city_hall", "local_government_office", "civic_center", "place_of_worship", "school", "stadium", "hospital", "medical_clinic"}))

        return True

    @classmethod
    def is_operational_facility_for_context(
        cls,
        place: Any,
        incident_type: str = "GENERAL",
        requested_facility_type: Optional[Any] = None,
    ) -> bool:
        """
        Authoritative validation function:
        is_operational_facility_for_context(place, incident_type, requested_facility_type)

        Enforces strict operational emergency facility validation:
        - For FIRE_STATION: VALID only when actual Google Places types support fire station ('fire_station').
        - For HEALTHCARE / HOSPITAL: VALID only when actual Google Places types support hospital/medical facility
          ('hospital', 'medical_clinic', 'doctor', 'health', 'pharmacy', 'medical_center').
        - For POLICE: VALID only when actual Google Places types support police ('police', 'law_enforcement').
        - For BUS_STATION / TRANSIT: VALID only when actual Google Places types support transit ('bus_station', 'transit_station', 'train_station', etc.).
        - For SHELTER: VALID only when actual Google Places types support shelter/evacuation facility
          ('community_center', 'city_hall', 'local_government_office', 'school', 'stadium', 'civic_center').

        Commercial businesses, shops, decorators, lighting stores, electricians, salons, tailors, restaurants,
        and general businesses are strictly INVALID.
        NEVER silently coerces INVALID -> requested facility type.
        """
        if not place:
            return False

        # Extract place types and destination type whether dict or object
        if isinstance(place, dict):
            raw_types = place.get("google_place_types") or place.get("types") or []
            provider = str(place.get("provider", "")).lower()
            dest_type = place.get("destination_type")
        else:
            raw_types = getattr(place, "google_place_types", []) or []
            provider = str(getattr(place, "provider", "")).lower()
            dest_type = getattr(place, "destination_type", None)

        # Allow genuine verified MongoDB collections
        if "mongodb_healthcare_facilities" in provider:
            if requested_facility_type:
                req_str = str(requested_facility_type).upper()
                return "HEALTH" in req_str or "HOSPITAL" in req_str or "MEDICAL" in req_str
            return True

        if "mongodb_resources" in provider:
            if requested_facility_type:
                req_str = str(requested_facility_type).replace("DestinationType.", "").upper()
                d_str = str(dest_type).replace("DestinationType.", "").upper()
                return req_str == d_str
            return True

        if not raw_types:
            # If raw_types is not provided (e.g. pre-normalized mock dict / model)
            if dest_type is not None:
                d_str = str(dest_type).replace("DestinationType.", "").strip().upper()
                if d_str in ["OTHER", ""]:
                    return False
                if requested_facility_type is not None:
                    req_str = str(requested_facility_type).replace("DestinationType.", "").strip().upper()
                    if req_str in ["FIRE_STATION", "FIRE"]:
                        return d_str in ["FIRE_STATION", "FIRE"]
                    elif req_str in ["HEALTHCARE", "HOSPITAL", "MEDICAL"]:
                        return d_str in ["HEALTHCARE", "HOSPITAL", "MEDICAL"]
                    elif req_str in ["POLICE", "POLICE_STATION"]:
                        return d_str in ["POLICE", "POLICE_STATION"]
                    elif req_str in ["BUS_STATION", "TRANSIT"]:
                        return d_str in ["BUS_STATION", "TRANSIT"]
                    elif req_str in ["SHELTER", "SAFE_ASSEMBLY_AREA"]:
                        return d_str in ["SHELTER", "SAFE_ASSEMBLY_AREA"]
                return True
            return False

        types_set = set(str(t).lower() for t in raw_types)

        # Verify against general type validity
        if not cls._is_valid_place_type(raw_types, incident_type):
            return False

        # Validate against requested facility type
        if requested_facility_type is not None:
            req_str = str(requested_facility_type).replace("DestinationType.", "").strip().upper()
            if req_str in ["FIRE_STATION", "FIRE"]:
                return "fire_station" in types_set
            elif req_str in ["HEALTHCARE", "HOSPITAL", "MEDICAL"]:
                return bool(types_set.intersection({"hospital", "medical_clinic", "doctor", "health", "pharmacy", "medical_center"}))
            elif req_str in ["POLICE", "POLICE_STATION"]:
                return bool(types_set.intersection({"police", "law_enforcement"}))
            elif req_str in ["BUS_STATION", "TRANSIT"]:
                return bool(types_set.intersection({"bus_station", "transit_station", "bus_stop", "train_station", "subway_station", "light_rail_station"}))
            elif req_str in ["SHELTER", "SAFE_ASSEMBLY_AREA"]:
                return bool(types_set.intersection({"community_center", "city_hall", "local_government_office", "civic_center", "place_of_worship", "school", "stadium"}))

        # If no specific facility type requested, ensure it's not DestinationType.OTHER
        norm_type = cls.normalize_google_place_type(raw_types)
        return norm_type != DestinationType.OTHER

    @classmethod
    def normalize_google_place_type(cls, place_types: List[str]) -> DestinationType:
        """
        Authoritative Google Places Type Normalizer.
        Deterministic precedence based on operational emergency response taxonomy:
        1. Healthcare (hospital, clinic, doctor, health, pharmacy) -> HEALTHCARE
        2. Fire Station (fire_station) -> FIRE_STATION
        3. Police Station (police, law_enforcement) -> POLICE
        4. Transit / Evacuation transport (bus_station, transit_station, train_station, etc.) -> BUS_STATION
        5. Shelter / Civic Center (community_center, city_hall, local_government_office, school, stadium) -> SHELTER
        6. Other -> OTHER
        """
        if not place_types:
            return DestinationType.OTHER

        types_set = set(str(t).lower() for t in place_types)

        # 1. Healthcare / Medical
        if types_set.intersection({"hospital", "medical_clinic", "doctor", "health", "pharmacy", "medical_center"}):
            return DestinationType.HEALTHCARE

        # 2. Fire Station / Rescue
        if types_set.intersection({"fire_station"}):
            return DestinationType.FIRE_STATION

        # 3. Police / Law Enforcement
        if types_set.intersection({"police", "law_enforcement"}):
            return DestinationType.POLICE

        # 4. Transit / Evacuation Bus
        if types_set.intersection({"bus_station", "transit_station", "bus_stop", "train_station", "subway_station", "light_rail_station"}):
            return DestinationType.BUS_STATION

        # 5. Evacuation Shelter / Civic Centers / Assembly
        if types_set.intersection({"community_center", "city_hall", "local_government_office", "civic_center", "place_of_worship", "school", "stadium", "campground"}):
            return DestinationType.SHELTER

        return DestinationType.OTHER
