"""AIRS Level 3 Monthly Surface Temperature & Humidity source handler."""
import logging
from pathlib import Path
from typing import Any, List, Optional
import earthaccess
import numpy as np
import xarray as xr

from config import DATASETS
from pipeline.regrid import apply_india_mask, bilinear_interp_to_grid
from pipeline.sources.base import DatasetSource

log = logging.getLogger("teratrend")


class AIRSSource(DatasetSource):
    """Source handler for AIRS3STM v7.0."""

    def __init__(self):
        super().__init__("airs")

    def search(
        self,
        start_year: int,
        end_year: int,
        bbox: tuple = (68.0, 6.0, 98.0, 38.0)
    ) -> List[Any]:
        log.info(f"Searching AIRS3STM v7.0 granules ({start_year}-{end_year})...")
        results = earthaccess.search_data(
            short_name="AIRS3STM",
            version="7.0",
            temporal=(f"{start_year}-01-01", f"{end_year}-12-31"),
            bounding_box=bbox
        )
        log.info(f"Found {len(results)} AIRS granules.")
        return results

    def fetch(
        self,
        granules: List[Any],
        out_dir: Path,
        backend: str = "auto"
    ) -> List[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        downloaded = earthaccess.download(granules, str(out_dir))
        return [Path(p) for p in downloaded if Path(p).exists()]

    def to_cube(
        self,
        raw_dir: Path,
        target_grid: xr.Dataset
    ) -> xr.Dataset:
        raw_files = sorted(list(raw_dir.glob("*.hdf*")) + list(raw_dir.glob("*.nc*")))
        if not raw_files:
            raise FileNotFoundError(f"No AIRS data files found in {raw_dir}")

        target_lats = target_grid["lat"].values
        target_lons = target_grid["lon"].values
        india_mask = target_grid["india_mask"].values

        log.info(f"Harmonizing {len(raw_files)} AIRS monthly granules...")
        datasets = []
        for rf in raw_files:
            try:
                ds = xr.open_dataset(rf)
                t_asc = ds.get("SurfAirTemp_A")
                t_desc = ds.get("SurfAirTemp_D")

                if t_asc is not None and t_desc is not None:
                    # Combined mean daily surface air temperature
                    mean_t = 0.5 * (t_asc + t_desc)
                    # Mask fills
                    mean_t_clean = xr.where(mean_t < 100.0, np.nan, mean_t)
                    regridded_t = bilinear_interp_to_grid(mean_t_clean, target_lats, target_lons)
                    datasets.append(regridded_t.to_dataset(name="air_temperature"))
            except Exception as e:
                log.warning(f"Error reading AIRS file {rf.name}: {e}")

        if not datasets:
            raise ValueError(f"Could not load any valid AIRS granules from {raw_dir}")

        merged = xr.concat(datasets, dim="time").sortby("time")
        res_ds = apply_india_mask(merged, india_mask, land_masked=False)
        return res_ds
