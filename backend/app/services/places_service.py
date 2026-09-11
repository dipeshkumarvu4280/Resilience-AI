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
                    d_type_raw = doc.get("destination_type")
                    try:
                        d_type = DestinationType(d_type_raw) if d_type_raw else cls._map_category_to_destination_type(need_category)
                    except Exception:
                        d_type = cls._map_category_to_destination_type(need_category)

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
                        "destination_type": str(p.get("destination_type")),
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
                    d_type_raw = doc.get("destination_type")
                    try:
                        d_type = DestinationType(d_type_raw) if d_type_raw else cls._map_category_to_destination_type(need_category)
                    except Exception:
                        d_type = cls._map_category_to_destination_type(need_category)

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
            "POLICE": ["police", "local_government_office"],
            "FIRE": ["fire_station", "hospital", "medical_clinic", "community_center"],
            "TRANSIT": ["bus_station", "bus_stop", "transit_station"],
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
                                    "destination_type": cls._map_types_to_destination_type(p_types, need_category),
                                    "latitude": float(p_lat),
                                    "longitude": float(p_lng),
                                    "address": p.get("formattedAddress") or "Google Verified Site",
                                    "distance_km": round(dist_km, 2),
                                    "provider": "Google Places Live Discovery",
                                    "last_checked": datetime.now(timezone.utc).isoformat(),
                                    "rating": p.get("rating"),
                                    "open_now": p.get("currentOpeningHours", {}).get("openNow"),
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
        restaurants, rice traders, and irrelevant businesses from entering emergency recommendations.
        """
        if not place_types:
            return True
        cat = need_category.upper()
        types_lower = [str(t).lower() for t in place_types]
        types_set = set(types_lower)

        disallowed_commercial = {
            "restaurant", "food", "grocery_or_supermarket", "supermarket",
            "store", "clothing_store", "wholesaler", "liquor_store",
            "bakery", "cafe", "meal_takeaway", "meal_delivery",
            "beauty_salon", "hair_care", "laundry", "bar", "convenience_store",
            "department_store", "shoe_store", "shopping_mall", "home_goods_store"
        }

        if cat in ["MEDICAL", "ROAD_ACCIDENT"]:
            valid_med = {"hospital", "medical_clinic", "doctor", "health", "pharmacy", "dentist", "physiotherapist"}
            if not types_set.intersection(valid_med):
                return False
            if types_set.intersection(disallowed_commercial) and not types_set.intersection({"hospital", "doctor", "medical_clinic"}):
                return False
            return True
        elif cat == "POLICE":
            valid_pol = {"police", "local_government_office", "courthouse", "law_enforcement"}
            if not types_set.intersection(valid_pol):
                return False
            if types_set.intersection(disallowed_commercial):
                return False
            return True
        elif cat == "FIRE":
            valid_fire = {"fire_station", "hospital", "medical_clinic", "doctor", "community_center", "city_hall", "local_government_office"}
            if not types_set.intersection(valid_fire):
                return False
            if types_set.intersection(disallowed_commercial) and not types_set.intersection({"hospital", "doctor", "fire_station"}):
                return False
            return True
        elif cat == "TRANSIT":
            return bool(types_set.intersection({"bus_station", "transit_station", "bus_stop", "train_station", "subway_station", "light_rail_station"}))
        elif cat in ["SHELTER", "FLOOD"]:
            valid_shl = {"community_center", "city_hall", "local_government_office", "civic_center", "place_of_worship", "school", "stadium", "hospital", "medical_clinic"}
            if types_set.intersection(disallowed_commercial) and not types_set.intersection({"hospital", "medical_clinic"}):
                return False
            return bool(types_set.intersection(valid_shl))

        return True

    @classmethod
    def _map_types_to_destination_type(cls, place_types: List[str], default_category: str) -> DestinationType:
        if not place_types:
            return cls._map_category_to_destination_type(default_category)
        t_set = set(str(t).lower() for t in place_types)
        if t_set.intersection({"hospital", "medical_clinic", "doctor", "health"}):
            return DestinationType.HEALTHCARE
        elif t_set.intersection({"police"}):
            return DestinationType.POLICE
        elif t_set.intersection({"fire_station"}):
            return DestinationType.FIRE_STATION
        elif t_set.intersection({"bus_station", "transit_station", "bus_stop"}):
            return DestinationType.BUS_STATION
        elif t_set.intersection({"community_center", "city_hall", "local_government_office"}):
            return DestinationType.SHELTER
        return cls._map_category_to_destination_type(default_category)

    @classmethod
    def _map_category_to_destination_type(cls, category: str) -> DestinationType:
        cat_u = category.upper()
        if "MED" in cat_u or "HOSP" in cat_u:
            return DestinationType.HEALTHCARE
        elif "POLICE" in cat_u or "SEC" in cat_u:
            return DestinationType.POLICE
        elif "FIRE" in cat_u:
            return DestinationType.FIRE_STATION
        elif "BUS" in cat_u or "TRANSIT" in cat_u:
            return DestinationType.BUS_STATION
        elif "ASSEMBLY" in cat_u:
            return DestinationType.SAFE_ASSEMBLY_AREA
        return DestinationType.SHELTER
