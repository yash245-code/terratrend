"""TeraTrend geocoding module via OpenStreetMap Nominatim.

Includes rate limiting (1 req/sec), in-memory caching, graceful timeout handling,
and strict validation against official India polygon geometry.
Results are explicitly labeled non-NASA open data.
"""
import logging
import time
from typing import Any, Dict, List, Optional
import requests

from config import BBOX_INDIA, GEOCODER_USER_AGENT
from teratrend.regions import is_inside_india

log = logging.getLogger("teratrend")

_GEOCODE_CACHE: Dict[str, Dict[str, Any]] = {}
_LAST_REQUEST_TIME: float = 0.0


def geocode(query: str, timeout_sec: float = 10.0) -> Dict[str, Any]:
    """Geocode an Indian place name or address query using OSM Nominatim.
    
    Filters results against official India sovereign boundary polygon.
    """
    global _LAST_REQUEST_TIME
    q_clean = query.strip()
    if not q_clean:
        return {"available": False, "reason": "Empty search query."}

    # Check cache
    cache_key = q_clean.lower()
    if cache_key in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[cache_key]

    # Rate limiting: max 1 request per second
    now = time.time()
    time_since_last = now - _LAST_REQUEST_TIME
    if time_since_last < 1.0:
        time.sleep(1.0 - time_since_last)
    _LAST_REQUEST_TIME = time.time()

    # Bounding box for India: min_lon, max_lat, max_lon, min_lat for Nominatim viewbox
    # viewbox=<left>,<top>,<right>,<bottom>
    min_lon, min_lat, max_lon, max_lat = BBOX_INDIA
    viewbox = f"{min_lon},{max_lat},{max_lon},{min_lat}"

    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": q_clean,
        "format": "json",
        "viewbox": viewbox,
        "bounded": 1,
        "limit": 5,
        "addressdetails": 1
    }
    headers = {
        "User-Agent": GEOCODER_USER_AGENT
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=timeout_sec)
        if resp.status_code != 200:
            return {
                "available": False,
                "reason": f"Geocoding service returned HTTP {resp.status_code}.",
                "source": "OpenStreetMap Nominatim (non-NASA)"
            }

        items = resp.json()
        if not items:
            # Retry without bounded viewbox if needed, then filter
            params["bounded"] = 0
            params["countrycodes"] = "in"
            resp2 = requests.get(url, params=params, headers=headers, timeout=timeout_sec)
            if resp2.status_code == 200:
                items = resp2.json()

        if not items:
            res = {
                "available": False,
                "reason": f"No locations found matching '{q_clean}' in India.",
                "source": "OpenStreetMap Nominatim (non-NASA)"
            }
            _GEOCODE_CACHE[cache_key] = res
            return res

        # Filter candidates strictly using official India boundary polygon
        valid_match = None
        for item in items:
            try:
                lat = float(item["lat"])
                lon = float(item["lon"])
                if is_inside_india(lat, lon):
                    valid_match = {
                        "available": True,
                        "query": q_clean,
                        "display_name": item.get("display_name"),
                        "lat": round(lat, 5),
                        "lon": round(lon, 5),
                        "type": item.get("type"),
                        "importance": item.get("importance"),
                        "source": "OpenStreetMap Nominatim (non-NASA, verified in India)"
                    }
                    break
            except (ValueError, KeyError):
                continue

        if not valid_match:
            res = {
                "available": False,
                "reason": f"Found results for '{q_clean}', but coordinates are outside official Indian territory.",
                "source": "OpenStreetMap Nominatim (non-NASA)"
            }
        else:
            res = valid_match

        _GEOCODE_CACHE[cache_key] = res
        return res

    except requests.exceptions.Timeout:
        log.warning(f"Geocoding request timed out for query '{q_clean}'")
        return {
            "available": False,
            "reason": "Geocoding request timed out.",
            "source": "OpenStreetMap Nominatim (non-NASA)"
        }
    except Exception as e:
        log.error(f"Geocoding error for '{q_clean}': {e}")
        return {
            "available": False,
            "reason": f"Geocoding error: {str(e)}",
            "source": "OpenStreetMap Nominatim (non-NASA)"
        }
