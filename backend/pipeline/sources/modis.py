"""MODIS/Terra Vegetation Indices Monthly CMG 0.05° (MOD13C2 v061) source handler."""
import logging
from pathlib import Path
from typing import Any, List, Optional
import earthaccess
import numpy as np
import xarray as xr

from config import DATASETS
from pipeline.regrid import apply_india_mask, coarsen_with_valid_fraction
from pipeline.sources.base import DatasetSource

log = logging.getLogger("teratrend")


class MODISSource(DatasetSource):
    """Source handler for MOD13C2 v061."""

    def __init__(self):
        super().__init__("modis")

    def search(
        self,
        start_year: int,
        end_year: int,
        bbox: tuple = (68.0, 6.0, 98.0, 38.0)
    ) -> List[Any]:
        log.info(f"Searching MOD13C2 v061 granules ({start_year}-{end_year})...")
        results = earthaccess.search_data(
            short_name="MOD13C2",
            version="061",
            temporal=(f"{start_year}-01-01", f"{end_year}-12-31"),
            bounding_box=bbox
        )
        log.info(f"Found {len(results)} MODIS granules.")
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
            raise FileNotFoundError(f"No MODIS files found in {raw_dir}")

        target_lats = target_grid["lat"].values
        target_lons = target_grid["lon"].values
        india_mask = target_grid["india_mask"].values

        log.info(f"Processing {len(raw_files)} MODIS granules into vegetation cube...")
        datasets = []
        for rf in raw_files:
            try:
                ds = xr.open_dataset(rf)
                # Handle HDF subdataset names for NDVI / EVI
                ndvi_da = ds.get("CMG 0.05 Deg Monthly NDVI") or ds.get("NDVI")
                evi_da = ds.get("CMG 0.05 Deg Monthly EVI") or ds.get("EVI")

                if ndvi_da is not None:
                    # Scale factor 0.0001, fill -3000
                    ndvi_clean = xr.where(ndvi_da == -3000, np.nan, ndvi_da * 0.0001)
                    ndvi_coarsened = coarsen_with_valid_fraction(ndvi_clean, factor=5, min_valid_fraction=0.50)
                    datasets.append(ndvi_coarsened.to_dataset(name="ndvi"))
            except Exception as e:
                log.warning(f"Error processing MODIS file {rf.name}: {e}")

        if not datasets:
            raise ValueError(f"Could not process any valid MODIS files from {raw_dir}")

        merged = xr.concat(datasets, dim="time").sortby("time")
        # Ensure aligned with target grid
        aligned = merged.interp(lat=target_lats, lon=target_lons, method="nearest")
        res_ds = apply_india_mask(aligned, india_mask, land_masked=True)
        return res_ds
