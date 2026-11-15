"""MERRA-2 Monthly Atmospheric & Land Assimilation source handler."""
import logging
from pathlib import Path
from typing import Any, List, Optional
import earthaccess
import xarray as xr

from config import DATASETS
from pipeline.regrid import apply_india_mask, bilinear_interp_to_grid
from pipeline.sources.base import DatasetSource

log = logging.getLogger("teratrend")


class MERRA2Source(DatasetSource):
    """Source handler for MERRA-2 (M2TMNXSLV, M2TMNXFLX, M2TMNXLND)."""

    def __init__(self):
        super().__init__("merra2")

    def search(
        self,
        start_year: int,
        end_year: int,
        bbox: tuple = (68.0, 6.0, 98.0, 38.0)
    ) -> List[Any]:
        log.info(f"Searching MERRA-2 collections ({start_year}-{end_year})...")
        collections = ["M2TMNXSLV", "M2TMNXFLX", "M2TMNXLND"]
        all_granules = []
        for coll in collections:
            res = earthaccess.search_data(
                short_name=coll,
                temporal=(f"{start_year}-01-01", f"{end_year}-12-31"),
                bounding_box=bbox
            )
            all_granules.extend(res)
        log.info(f"Found total {len(all_granules)} MERRA-2 granules across 3 collections.")
        return all_granules

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
        raw_files = sorted(list(raw_dir.glob("*.nc*")))
        if not raw_files:
            raise FileNotFoundError(f"No NetCDF files found in MERRA-2 raw directory: {raw_dir}")

        target_lats = target_grid["lat"].values
        target_lons = target_grid["lon"].values
        india_mask = target_grid["india_mask"].values

        log.info(f"Merging and regridding {len(raw_files)} MERRA-2 files...")
        datasets = []
        for rf in raw_files:
            try:
                ds = xr.open_dataset(rf)
                datasets.append(ds)
            except Exception as e:
                log.warning(f"Error reading {rf.name}: {e}")

        if not datasets:
            raise ValueError(f"Could not read any valid MERRA-2 files from {raw_dir}")

        merged = xr.combine_by_coords(datasets, combine_attrs="override")

        # Map variables
        var_map = {
            "T2M": "air_temperature",
            "PRECTOTCORR": "rainfall",
            "EVAP": "evapotranspiration",
            "GWETROOT": "root_moisture",
            "GWETTOP": "surface_moisture"
        }

        cube_vars = {}
        for rk, tk in var_map.items():
            if rk in merged.data_vars:
                regridded = bilinear_interp_to_grid(merged[rk], target_lats, target_lons)
                cube_vars[tk] = regridded

        res_ds = xr.Dataset(data_vars=cube_vars, coords=target_grid.coords)
        # Apply India mask without land-masking (atmospheric sets cover coasts/islands)
        res_ds = apply_india_mask(res_ds, india_mask, land_masked=False)
        return res_ds
