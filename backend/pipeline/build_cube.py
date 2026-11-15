"""CLI utility to process raw granules and build standardized NetCDF cubes.

Applies zlib level 4 compression, float32 precision, standardized CF attributes,
and records SHA-256 hashes in provenance records.
"""
import argparse
from datetime import datetime, timezone
import logging
from pathlib import Path
import sys
from typing import List, Optional
import numpy as np
import xarray as xr

# Ensure backend root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config import DATASETS, INDIA_GRID_NC, PROCESSED_DIR, RAW_DIR
from pipeline.provenance import record_dataset_provenance
from pipeline.sources import get_source

log = logging.getLogger("teratrend")


def build_cubes(
    dataset_keys: List[str],
    force: bool = False,
    raw_root: Optional[Path] = None,
    processed_root: Optional[Path] = None
) -> None:
    """Build standardized 0.25° NetCDF cubes from raw granules."""
    raw_base = raw_root or RAW_DIR
    proc_base = processed_root or PROCESSED_DIR
    proc_base.mkdir(parents=True, exist_ok=True)

    # 1. Load canonical grid
    if not INDIA_GRID_NC.exists():
        raise FileNotFoundError(
            f"Canonical grid missing: {INDIA_GRID_NC}. Run 'python -m pipeline.india_grid' first."
        )
    target_grid = xr.open_dataset(INDIA_GRID_NC)

    for key in dataset_keys:
        if key not in DATASETS:
            log.warning(f"Unknown dataset key: '{key}'")
            continue

        meta = DATASETS[key]
        out_cube = meta["cube_path"]

        if out_cube.exists() and not force:
            log.info(f"Cube {out_cube.name} already exists. Use --force to overwrite. Skipping.")
            continue

        log.info(f"--- Building cube for {key} ---")
        source = get_source(key)
        raw_dir = raw_base / key

        if not raw_dir.exists():
            log.warning(f"Raw directory does not exist for {key}: {raw_dir}. Skipping.")
            continue

        try:
            cube_ds = source.to_cube(raw_dir, target_grid)

            # Global CF attributes
            cube_ds.attrs.update({
                "title": f"TeraTrend {meta['label']} Processed Analysis Cube",
                "source_dataset": meta["collection"],
                "provider": meta["provider"],
                "doi": meta.get("doi", ""),
                "spatial_resolution": "0.25 degrees",
                "bounding_box": [68.0, 6.0, 98.0, 38.0],
                "regrid_method": meta.get("regrid_method", ""),
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "institution": "TeraTrend (NASA Space Apps Challenge 2026)",
                "conventions": "CF-1.8"
            })

            # Compression encoding
            encoding = {}
            for var_name in cube_ds.data_vars:
                cube_ds[var_name] = cube_ds[var_name].astype(np.float32)
                encoding[var_name] = {"zlib": True, "complevel": 4}

            cube_ds.to_netcdf(out_cube, encoding=encoding)
            log.info(f"Successfully wrote {out_cube} ({out_cube.stat().st_size / (1024*1024):.1f} MB)")

            # Record provenance
            record_dataset_provenance(key, out_cube)

        except Exception as e:
            log.error(f"Failed to build cube for {key}: {e}", exc_info=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    parser = argparse.ArgumentParser(description="Build standardized NetCDF cubes from raw NASA granules.")
    parser.add_argument("--datasets", nargs="+", default=["gldas", "hwsd"], help="Datasets to process")
    parser.add_argument("--force", "-f", action="store_true", help="Force overwrite existing cubes")

    args = parser.parse_args()
    build_cubes(dataset_keys=args.datasets, force=args.force)
