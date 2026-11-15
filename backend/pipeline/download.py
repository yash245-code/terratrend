"""CLI utility to search and download NASA Earthdata datasets for TeraTrend.

Supports multiple download backends:
  - 'harmony': NASA Harmony API (server-side spatial and temporal subsetting)
  - 'earthaccess': Direct authenticated HTTPS download from NASA DAACs
  - 'opendap': OPeNDAP remote slice retrieval via pydap
  - 'auto': Attempts Harmony first, falling back to Earthaccess.
"""
import argparse
import logging
from pathlib import Path
import sys
import time
from typing import Any, List, Optional

# Ensure backend root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config import DATASETS, RAW_DIR
from pipeline.nasa_auth import login_earthdata
from pipeline.sources import get_source

log = logging.getLogger("teratrend")


def download_datasets(
    dataset_keys: List[str],
    start_year: int = 2005,
    end_year: int = 2024,
    backend: str = "auto",
    raw_root: Optional[Path] = None,
    assume_yes: bool = False
) -> None:
    """Download specified NASA collections for India domain."""
    login_earthdata()

    raw_base = raw_root or RAW_DIR

    for key in dataset_keys:
        if key not in DATASETS:
            log.warning(f"Skipping unknown dataset key: '{key}'")
            continue

        meta = DATASETS[key]
        log.info(f"--- Preparing download for: {meta['label']} ({key}) ---")

        source = get_source(key)
        target_raw = raw_base / key
        target_raw.mkdir(parents=True, exist_ok=True)

        granules = source.search(start_year, end_year)
        if not granules:
            log.warning(f"No granules found for {key} in range {start_year}-{end_year}.")
            continue

        log.info(f"Found {len(granules)} granules for {key}.")
        if len(granules) > 50 and not assume_yes:
            prompt = input(f"Proceed with downloading {len(granules)} granules for {key}? [y/N]: ")
            if prompt.strip().lower() not in ["y", "yes"]:
                log.info(f"Skipped download for {key}.")
                continue

        downloaded_paths = source.fetch(granules, target_raw, backend=backend)
        log.info(f"Successfully downloaded {len(downloaded_paths)} files for {key} to {target_raw}.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    parser = argparse.ArgumentParser(description="Download NASA Earthdata datasets for TeraTrend.")
    parser.add_argument("--datasets", nargs="+", default=["gldas", "hwsd"], help="Datasets to download")
    parser.add_argument("--start-year", type=int, default=2005, help="Start year")
    parser.add_argument("--end-year", type=int, default=2024, help="End year")
    parser.add_argument("--backend", choices=["auto", "harmony", "earthaccess", "opendap"], default="auto")
    parser.add_argument("--out-dir", type=str, default=str(RAW_DIR), help="Root directory for raw downloads")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt for large downloads")

    args = parser.parse_args()
    download_datasets(
        dataset_keys=args.datasets,
        start_year=args.start_year,
        end_year=args.end_year,
        backend=args.backend,
        raw_root=Path(args.out_dir),
        assume_yes=args.yes
    )
