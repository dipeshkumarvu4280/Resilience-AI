import logging
import asyncio
import time
from typing import Optional, Dict, Any, Tuple
import httpx

from app.core.config import settings

logger = logging.getLogger("resilience.geocoding")

# In-memory cache for reverse geocoding: (rounded_lat, rounded_lon) -> (address_dict, timestamp)
_GEOCODE_CACHE: Dict[Tuple[float, float], Tuple[Dict[str, Any], float]] = {}
_CACHE_TTL_SECONDS = 3600 * 24  # 24 hours
_LAST_REQUEST_TIME: float = 0.0
_REQUEST_LOCK = asyncio.Lock()


def validate_coordinates(lat: float, lon: float) -> bool:
    """Validate latitude and longitude ranges."""
    try:
        lat_f = float(lat)
        lon_f = float(lon)
        return (-90.0 <= lat_f <= 90.0) and (-180.0 <= lon_f <= 180.0)
    except (TypeError, ValueError):
        return False


def _get_cache_key(lat: float, lon: float) -> Tuple[float, float]:
    """Round coordinates to 5 decimal places (~1.1 meter accuracy) for caching."""
    return (round(float(lat), 5), round(float(lon), 5))


async def reverse_geocode_coordinates(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """
    Reverse geocodes (lat, lon) coordinates into a human-readable address.
    Uses OpenStreetMap Nominatim with strict rate limiting, caching, and timeout safety.
    Returns a dict containing 'address', 'display_name', 'city', 'state', 'country', 'postal_code',
    or None if resolution fails.
    """
    if not validate_coordinates(lat, lon):
        logger.warning(f"Invalid coordinates rejected in reverse_geocode: lat={lat}, lon={lon}")
        return None

    cache_key = _get_cache_key(lat, lon)
    now = time.time()

    # Check in-memory cache
    if cache_key in _GEOCODE_CACHE:
        cached_result, timestamp = _GEOCODE_CACHE[cache_key]
        if now - timestamp < _CACHE_TTL_SECONDS:
            return cached_result

    # Outbound call rate limiter to respect Nominatim 1 req/sec policy
    global _LAST_REQUEST_TIME
    async with _REQUEST_LOCK:
        # Re-check cache in case another coroutine populated it
        if cache_key in _GEOCODE_CACHE:
            cached_result, timestamp = _GEOCODE_CACHE[cache_key]
            if now - timestamp < _CACHE_TTL_SECONDS:
                return cached_result

        elapsed = now - _LAST_REQUEST_TIME
        if elapsed < 1.0:
            await asyncio.sleep(1.0 - elapsed)

        params = {
            "lat": f"{float(lat):.6f}",
            "lon": f"{float(lon):.6f}",
            "format": "json",
            "addressdetails": "1",
        }
        headers = {
            "User-Agent": settings.GEOCODING_USER_AGENT,
            "Accept": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=settings.GEOCODING_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    settings.GEOCODING_BASE_URL,
                    params=params,
                    headers=headers,
                )
                _LAST_REQUEST_TIME = time.time()

                if response.status_code != 200:
                    logger.warning(
                        f"Nominatim reverse geocode returned status {response.status_code} for ({lat:.4f}, {lon:.4f})"
                    )
                    return None

                data = response.json()
                if not data or "display_name" not in data:
                    logger.info(f"No address found for coordinates ({lat:.4f}, {lon:.4f})")
                    return None

                display_name = data.get("display_name", "")
                addr_details = data.get("address", {})

                # 1. Street Address / Landmark parsing
                house_number = addr_details.get("house_number")
                road = (
                    addr_details.get("road")
                    or addr_details.get("street")
                    or addr_details.get("pedestrian")
                    or addr_details.get("footway")
                    or addr_details.get("path")
                )
                neighbourhood = (
                    addr_details.get("neighbourhood")
                    or addr_details.get("suburb")
                    or addr_details.get("quarter")
                    or addr_details.get("residential")
                    or addr_details.get("locality")
                    or addr_details.get("hamlet")
                )
                landmark = (
                    addr_details.get("amenity")
                    or addr_details.get("building")
                    or addr_details.get("landmark")
                    or addr_details.get("historic")
                    or addr_details.get("tourism")
                    or addr_details.get("shop")
                )

                street_parts = []
                if landmark:
                    street_parts.append(landmark)
                if house_number and road:
                    street_parts.append(f"{house_number} {road}")
                elif road:
                    street_parts.append(road)
                elif house_number:
                    street_parts.append(house_number)
                if neighbourhood and neighbourhood not in street_parts:
                    street_parts.append(neighbourhood)

                if street_parts:
                    street_address = ", ".join(street_parts)
                else:
                    parts = [p.strip() for p in display_name.split(",") if p.strip()]
                    street_address = ", ".join(parts[:2]) if len(parts) >= 2 else (parts[0] if parts else display_name)

                # 2. Zone / District parsing
                district = (
                    addr_details.get("city_district")
                    or addr_details.get("district")
                    or addr_details.get("subdistrict")
                    or addr_details.get("borough")
                    or addr_details.get("county")
                    or addr_details.get("state_district")
                    or addr_details.get("municipality")
                )
                city = (
                    addr_details.get("city")
                    or addr_details.get("town")
                    or addr_details.get("village")
                    or addr_details.get("municipality")
                    or addr_details.get("county")
                )
                state = addr_details.get("state") or addr_details.get("region")
                country = addr_details.get("country")
                postal_code = addr_details.get("postcode")

                zone_parts = []
                if district:
                    zone_parts.append(district)
                if city and city != district:
                    zone_parts.append(city)
                elif not district and state:
                    zone_parts.append(state)

                zone_or_district = ", ".join(zone_parts) if zone_parts else (city or state or None)

                result = {
                    "address": display_name,
                    "display_name": display_name,
                    "street_address": street_address,
                    "landmark": landmark,
                    "zone_or_district": zone_or_district,
                    "district": district or zone_or_district,
                    "city": city,
                    "state": state,
                    "country": country,
                    "postal_code": postal_code,
                }

                # Store in cache
                _GEOCODE_CACHE[cache_key] = (result, time.time())
                return result

        except httpx.TimeoutException:
            logger.warning(f"Reverse geocoding timed out for coordinates ({lat:.4f}, {lon:.4f})")
            return None
        except Exception as exc:
            logger.warning(f"Reverse geocoding request failed for ({lat:.4f}, {lon:.4f}): {exc}")
            return None
