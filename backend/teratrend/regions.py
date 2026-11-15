"""TeraTrend administrative boundary and regional lookup.

Pure shapely 2.x point-in-polygon validation against official India boundary.
Does NOT import Flask or any network library.
"""
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from shapely.geometry import Point, shape
from shapely.prepared import prep
from shapely.strtree import STRtree

from config import INDIA_DISTRICTS_GEOJSON, INDIA_STATES_GEOJSON
from teratrend.schemas import Region

class OutOfIndiaError(Exception):
    """Exception raised when coordinates fall outside the official territory of India."""
    def __init__(self, message: str = "TeraTrend currently covers India only", code: str = "OUT_OF_INDIA"):
        super().__init__(message)
        self.message = message
        self.code = code


UNION_TERRITORIES = {
    "andaman & nicobar island",
    "andaman & nicobar islands",
    "chandigarh",
    "dadara & nagar havelli",
    "dadra & nagar haveli and daman & diu",
    "daman & diu",
    "delhi",
    "nct of delhi",
    "jammu & kashmir",
    "ladakh",
    "lakshadweep",
    "puducherry",
}

STATE_NAME_STANDARDIZATION = {
    "Andaman & Nicobar Island": "Andaman & Nicobar Islands",
    "Arunanchal Pradesh": "Arunachal Pradesh",
    "Dadara & Nagar Havelli": "Dadra & Nagar Haveli and Daman & Diu",
    "Daman & Diu": "Dadra & Nagar Haveli and Daman & Diu",
    "NCT of Delhi": "Delhi",
}

# In-memory spatial index cache
_LOADED_GEOJSON_PATH: Optional[Path] = None
_STATE_GEOMS: List[Tuple[Any, Dict[str, Any]]] = []
_STATE_TREE: Optional[STRtree] = None
_PREPARED_STATES: List[Tuple[Any, Dict[str, Any]]] = []
_UNION_INDIA_GEOM = None
_PREPARED_INDIA = None


def load_boundaries(geojson_path: Optional[Path] = None, force_reload: bool = False) -> None:
    """Load and index state boundary polygons from GeoJSON using Shapely 2.0 STRtree."""
    global _LOADED_GEOJSON_PATH, _STATE_GEOMS, _STATE_TREE, _PREPARED_STATES, _UNION_INDIA_GEOM, _PREPARED_INDIA
    path = geojson_path or INDIA_STATES_GEOJSON
    if not force_reload and _LOADED_GEOJSON_PATH == path and _STATE_TREE is not None:
        return

    if not path.exists():
        raise FileNotFoundError(
            f"Official boundary file missing: {path}. "
            "Please ensure data/boundaries/india_states.geojson is placed."
        )

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    geoms = []
    props_list = []
    prepared_list = []

    for feat in data.get("features", []):
        geom = shape(feat["geometry"])
        props = feat.get("properties", {})
        geoms.append(geom)
        props_list.append(props)
        prepared_list.append((prep(geom), props))

    _STATE_GEOMS = list(zip(geoms, props_list))
    _PREPARED_STATES = prepared_list
    _STATE_TREE = STRtree(geoms)
    _LOADED_GEOJSON_PATH = path

    # Build unary union for master India polygon check
    from shapely.ops import unary_union
    _UNION_INDIA_GEOM = unary_union(geoms)
    _PREPARED_INDIA = prep(_UNION_INDIA_GEOM)


def get_india_union_geometry(geojson_path: Optional[Path] = None):
    """Return the merged unified India polygon."""
    load_boundaries(geojson_path)
    return _UNION_INDIA_GEOM


def is_inside_india(lat: float, lon: float, geojson_path: Optional[Path] = None) -> bool:
    """Test whether a point coordinate is inside the official boundary of India."""
    load_boundaries(geojson_path)
    pt = Point(lon, lat)
    if _PREPARED_INDIA is not None:
        return _PREPARED_INDIA.contains(pt) or _PREPARED_INDIA.intersects(pt)
    return False


def locate(lat: float, lon: float, geojson_path: Optional[Path] = None) -> Region:
    """Resolve administrative state, UT status, and district for an Indian coordinate.
    
    Raises:
        OutOfIndiaError: If (lat, lon) is outside India's sovereign boundary.
    """
    load_boundaries(geojson_path)
    pt = Point(lon, lat)

    # First fast check against overall India boundary
    if _PREPARED_INDIA is not None and not (_PREPARED_INDIA.contains(pt) or _PREPARED_INDIA.intersects(pt)):
        raise OutOfIndiaError(f"Coordinate ({lat:.4f}, {lon:.4f}) is outside India. TeraTrend currently covers India only.")

    # Query STRtree for candidate polygons
    assert _STATE_TREE is not None
    candidate_indices = _STATE_TREE.query(pt)

    matched_props = None
    for idx in candidate_indices:
        prep_geom, props = _PREPARED_STATES[idx]
        if prep_geom.contains(pt) or prep_geom.intersects(pt):
            matched_props = props
            break

    if not matched_props:
        raise OutOfIndiaError(f"Coordinate ({lat:.4f}, {lon:.4f}) is outside India. TeraTrend currently covers India only.")

    raw_name = (
        matched_props.get("ST_NM") or
        matched_props.get("state_name") or
        matched_props.get("NAME_1") or
        "India"
    )
    standard_name = STATE_NAME_STANDARDIZATION.get(raw_name, raw_name)
    is_ut = standard_name.lower() in UNION_TERRITORIES or raw_name.lower() in UNION_TERRITORIES

    district = matched_props.get("DISTRICT") or matched_props.get("district_name") or matched_props.get("NAME_2")

    return Region(
        state=standard_name,
        is_union_territory=is_ut,
        district=district
    )
