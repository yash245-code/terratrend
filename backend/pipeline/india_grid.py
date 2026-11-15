"""Build the canonical 0.25° India analysis grid raster.

Constructs india_mask (all-touched intersection with official Survey of India boundary)
and state_id integer raster, saving to data/processed/india_grid.nc.
"""
import argparse
import json
import logging
from pathlib import Path
import sys
from typing import Dict, List, Tuple
import numpy as np
from shapely.geometry import box, shape
from shapely.strtree import STRtree
import xarray as xr

# Ensure backend root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config import GRID_RESOLUTION, INDIA_GRID_NC, INDIA_STATES_GEOJSON, PROCESSED_DIR

log = logging.getLogger("teratrend")


def build_india_grid(
    geojson_path: Optional[Path] = None,
    output_nc: Optional[Path] = None
) -> xr.Dataset:
    """Build canonical 0.25° India grid dataset and write NetCDF file."""
    in_geo = geojson_path or INDIA_STATES_GEOJSON
    out_nc = output_nc or INDIA_GRID_NC

    if not in_geo.exists():
        raise FileNotFoundError(
            f"Official boundary GeoJSON not found at: {in_geo}.\n"
            "Please ensure data/boundaries/india_states.geojson is placed before running the grid builder."
        )

    log.info(f"Loading official boundaries from {in_geo}...")
    with open(in_geo, "r", encoding="utf-8") as f:
        data = json.load(f)

    features = data.get("features", [])
    if not features:
        raise ValueError(f"GeoJSON at {in_geo} contains no features.")

    state_names = []
    state_geoms = []
    for idx, feat in enumerate(features):
        geom = shape(feat["geometry"])
        props = feat.get("properties", {})
        s_name = props.get("ST_NM") or props.get("state_name") or props.get("NAME_1") or f"State_{idx}"
        state_names.append(s_name)
        state_geoms.append(geom)

    tree = STRtree(state_geoms)

    # Common grid extent: 6.0°N to 38.0°N, 68.0°E to 98.0°E
    lats = np.arange(6.0, 38.0 + GRID_RESOLUTION, GRID_RESOLUTION)
    lons = np.arange(68.0, 98.0 + GRID_RESOLUTION, GRID_RESOLUTION)

    lon_grid, lat_grid = np.meshgrid(lons, lats)
    half_res = GRID_RESOLUTION / 2.0

    boxes = [
        box(lo - half_res, la - half_res, lo + half_res, la + half_res)
        for lo, la in zip(lon_grid.flat, lat_grid.flat)
    ]

    log.info(f"Computing all-touched intersections across {len(boxes)} grid cells...")
    idx_boxes, idx_geoms = tree.query(boxes, predicate="intersects")

    india_mask = np.zeros(len(boxes), dtype=np.int8)
    india_mask[idx_boxes] = 1
    india_mask_2d = india_mask.reshape((len(lats), len(lons)))

    # Compute primary state_id raster
    state_id_flat = np.full(len(boxes), -1, dtype=np.int16)
    for b_idx, g_idx in zip(idx_boxes, idx_geoms):
        if state_id_flat[b_idx] == -1:
            state_id_flat[b_idx] = g_idx

    state_id_2d = state_id_flat.reshape((len(lats), len(lons)))

    state_mapping = {int(i): name for i, name in enumerate(state_names)}

    ds = xr.Dataset(
        data_vars={
            "india_mask": (
                ["lat", "lon"],
                india_mask_2d,
                {
                    "long_name": "Sovereign India Territory All-Touched Mask",
                    "description": "1 if 0.25 deg grid cell box intersects Survey of India boundary, 0 otherwise",
                    "valid_range": [0, 1]
                }
            ),
            "state_id": (
                ["lat", "lon"],
                state_id_2d,
                {
                    "long_name": "State and Union Territory Identifier Code",
                    "state_mapping_json": json.dumps(state_mapping)
                }
            )
        },
        coords={
            "lat": (["lat"], lats, {"units": "degrees_north", "standard_name": "latitude"}),
            "lon": (["lon"], lons, {"units": "degrees_east", "standard_name": "longitude"})
        },
        attrs={
            "title": "TeraTrend Canonical 0.25° India Analysis Grid",
            "spatial_resolution": "0.25 degrees",
            "bounding_box": [68.0, 6.0, 98.0, 38.0],
            "boundary_source": "Survey of India compliant redistribution (DataMeet maps)",
            "boundary_license": "CC-BY 2.5 / ODbL",
            "total_cells": int(len(boxes)),
            "in_india_cells": int(np.sum(india_mask_2d))
        }
    )

    out_nc.parent.mkdir(parents=True, exist_ok=True)
    encoding = {
        "india_mask": {"zlib": True, "complevel": 4},
        "state_id": {"zlib": True, "complevel": 4}
    }
    ds.to_netcdf(out_nc, encoding=encoding)
    log.info(f"Saved canonical grid to {out_nc} ({int(np.sum(india_mask_2d))} cells inside India).")
    return ds


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    parser = argparse.ArgumentParser(description="Build canonical 0.25° India grid NetCDF file.")
    parser.add_argument("--geojson", type=str, default=str(INDIA_STATES_GEOJSON), help="Path to India states GeoJSON")
    parser.add_argument("--out", type=str, default=str(INDIA_GRID_NC), help="Output NetCDF path")
    args = parser.parse_args()

    build_india_grid(Path(args.geojson), Path(args.out))
