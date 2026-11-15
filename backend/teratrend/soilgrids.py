"""TeraTrend ISRIC SoilGrids REST API supplement.

Optional non-NASA live soil properties supplement (disabled by default).
Strict timeout, in-memory caching, graceful failure, and clearly labeled non-NASA provenance.
"""
import logging
from typing import Any, Dict, Optional
import requests

from config import ENABLE_SOILGRIDS_LIVE

log = logging.getLogger("teratrend")

_SOILGRIDS_CACHE: Dict[str, Dict[str, Any]] = {}


def fetch_soilgrids_supplement(lat: float, lon: float, timeout_sec: float = 5.0) -> Optional[Dict[str, Any]]:
    """Fetch supplementary high-resolution soil estimates from ISRIC SoilGrids REST API.
    
    Returns None if feature disabled or service unavailable.
    """
    if not ENABLE_SOILGRIDS_LIVE:
        return None

    cache_key = f"{lat:.3f}_{lon:.3f}"
    if cache_key in _SOILGRIDS_CACHE:
        return _SOILGRIDS_CACHE[cache_key]

    url = "https://rest.isric.org/soilgrids/v2.0/properties/query"
    params = {
        "lat": lat,
        "lon": lon,
        "property": ["phhox", "soc", "clay", "sand", "silt", "cec"],
        "depth": "0-5cm",
        "value": "mean"
    }

    try:
        resp = requests.get(url, params=params, timeout=timeout_sec)
        if resp.status_code != 200:
            log.warning(f"SoilGrids API returned HTTP {resp.status_code}")
            return None

        data = resp.json()
        layers = data.get("properties", {}).get("layers", [])
        props: Dict[str, Any] = {}

        for l in layers:
            name = l.get("name")
            depths = l.get("depths", [])
            if depths and "values" in depths[0]:
                mean_val = depths[0]["values"].get("mean")
                if mean_val is not None:
                    # Conversion based on ISRIC scale factors
                    if name == "phhox":
                        props["soil_ph_top_isric"] = round(mean_val / 10.0, 2)
                    elif name == "soc":
                        props["soil_organic_carbon_g_kg"] = round(mean_val / 10.0, 2)
                    elif name in ["clay", "sand", "silt"]:
                        props[f"soil_{name}_fraction_pct"] = round(mean_val / 10.0, 1)
                    elif name == "cec":
                        props["soil_cec_cmol_kg"] = round(mean_val / 10.0, 1)

        result = {
            "source": "ISRIC SoilGrids 250m (non-NASA supplement)",
            "enabled": True,
            "status": "success",
            "properties": props,
            "disclaimer": "ISRIC SoilGrids data is provided as a non-NASA supplementary reference and does not replace primary HWSD assessments."
        }
        _SOILGRIDS_CACHE[cache_key] = result
        return result

    except requests.exceptions.Timeout:
        log.warning("SoilGrids API request timed out.")
        return None
    except Exception as e:
        log.warning(f"SoilGrids request failed: {e}")
        return None
