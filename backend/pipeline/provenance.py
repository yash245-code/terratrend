"""TeraTrend data provenance and metadata tracking.

Queries NASA CMR for collections, versions, DOIs, and citations,
and records cryptographic SHA-256 hashes of generated processed cubes.
Gracefully handles offline environments.
"""
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional
import importlib.metadata

from config import DATASETS, INDIA_GRID_NC, PROCESSED_DIR, PROVENANCE_JSON

log = logging.getLogger("teratrend")


def compute_file_sha256(filepath: Path) -> str:
    """Compute SHA-256 hash of a file."""
    if not filepath.exists():
        return ""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def fetch_cmr_collection_metadata(short_name: str, version: Optional[str] = None) -> Dict[str, Any]:
    """Query CMR for authoritative collection metadata. Degrades gracefully on network failure."""
    try:
        from cmr.queries import CollectionQuery
        q = CollectionQuery().short_name(short_name)
        if version:
            q = q.version(version)
        res = q.get(1)
        if not res and version:
            # Retry without version
            res = CollectionQuery().short_name(short_name).get(1)

        if res:
            c = res[0]
            return {
                "id": c.get("id"),
                "title": c.get("title"),
                "version_id": c.get("version_id"),
                "doi": c.get("doi"),
                "summary": c.get("summary"),
                "time_start": c.get("time_start"),
                "time_end": c.get("time_end")
            }
    except Exception as e:
        log.warning(f"CMR metadata query failed for {short_name}: {e}")

    return {
        "id": None,
        "title": None,
        "version_id": version,
        "doi": None,
        "cmr_status": "offline_fallback"
    }


def record_dataset_provenance(
    dataset_key: str,
    cube_path: Path,
    granule_count: int = 0,
    backend_used: str = "auto",
    actual_extent: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Compile complete provenance record for a processed cube."""
    ds_meta = DATASETS.get(dataset_key, {})
    cmr_info = fetch_cmr_collection_metadata(
        ds_meta.get("collection", ""),
        ds_meta.get("version")
    )

    sha256 = compute_file_sha256(cube_path) if cube_path.exists() else None

    record = {
        "dataset_key": dataset_key,
        "label": ds_meta.get("label"),
        "provider": ds_meta.get("provider"),
        "collection": ds_meta.get("collection"),
        "version": ds_meta.get("version"),
        "doi": ds_meta.get("doi") or cmr_info.get("doi"),
        "concept_id": ds_meta.get("concept_id") or cmr_info.get("id"),
        "cmr_metadata": cmr_info,
        "cube_path": str(cube_path.name),
        "sha256": sha256,
        "granule_count": granule_count,
        "access_date_utc": datetime.now(timezone.utc).isoformat(),
        "backend": backend_used,
        "regrid_method": ds_meta.get("regrid_method"),
        "variables": list(ds_meta.get("variables", {}).keys()),
        "actual_extent": actual_extent
    }
    return record


def build_provenance_report(output_path: Optional[Path] = None) -> Dict[str, Any]:
    """Generate and write complete provenance.json file."""
    out_file = output_path or PROVENANCE_JSON

    # Installed library versions
    lib_names = [
        "xarray", "netCDF4", "h5netcdf", "numpy", "pandas",
        "pymannkendall", "shapely", "earthaccess", "harmony-py", "python-cmr", "pydap"
    ]
    lib_versions = {}
    for lib in lib_names:
        try:
            lib_versions[lib] = importlib.metadata.version(lib)
        except Exception:
            lib_versions[lib] = "unknown"

    datasets_prov = {}
    for k, meta in DATASETS.items():
        cube_p = meta["cube_path"]
        datasets_prov[k] = record_dataset_provenance(k, cube_p)

    report = {
        "title": "TeraTrend Multi-Dataset NASA Provenance Record",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "project": "TeraTrend (NASA Space Apps Challenge 2026)",
        "spatial_domain": {
            "extent": "India Sovereign Territory (Survey of India compliant)",
            "bounding_box_wgs84": [68.0, 6.0, 98.0, 38.0],
            "common_grid_resolution": 0.25,
            "india_grid_nc_sha256": compute_file_sha256(INDIA_GRID_NC)
        },
        "boundary_data": {
            "source": "Survey of India compliant redistribution (DataMeet maps)",
            "license": "CC-BY 2.5 / ODbL",
            "states_geojson": "data/boundaries/india_states.geojson"
        },
        "datasets": datasets_prov,
        "libraries": lib_versions
    }

    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    log.info(f"Saved complete provenance record to {out_file}")
    return report


def load_provenance(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Load existing provenance.json file if available."""
    p = path or PROVENANCE_JSON
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None
