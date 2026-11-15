"""GPM IMERG Final Monthly Precipitation v07 source handler."""
import logging
from pathlib import Path
from typing import Any, List, Optional
import earthaccess
import xarray as xr

from config import DATASETS
from pipeline.regrid import apply_india_mask, bilinear_interp_to_grid
from pipeline.sources.base import DatasetSource

log = logging.getLogger("teratrend")


class GPMSource(DatasetSource):
    """Source handler for GPM_3IMERGM v07."""

    def __init__(self):
        super().__init__("gpm")

    def search(
        self,
        start_year: int,
        end_year: int,
        bbox: tuple = (68.0, 6.0, 98.0, 38.0)
    ) -> List[Any]:
        log.info(f"Searching GPM_3IMERGM granules ({start_year}-{end_year})...")
        results = earthaccess.search_data(
            short_name="GPM_3IMERGM",
            version="07",
            temporal=(f"{start_year}-01-01", f"{end_year}-12-31"),
            bounding_box=bbox
        )
        log.info(f"Found {len(results)} GPM granules.")
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
        raw_files = sorted(list(raw_dir.glob("*.nc*")) + list(raw_dir.glob("*.HDF5*")))
        if not raw_files:
            raise FileNotFoundError(f"No GPM data files found in {raw_dir}")

        target_lats = target_grid["lat"].values
        target_lons = target_grid["lon"].values
        india_mask = target_grid["india_mask"].values

        log.info(f"Processing {len(raw_files)} GPM granules into rainfall cube...")
        datasets = []
        for rf in raw_files:
            try:
                ds = xr.open_dataset(rf)
                # GPM coordinates can be 'lat'/'lon' or 'latitude'/'longitude'
                lat_k = "lat" if "lat" in ds.coords else "latitude"
                lon_k = "lon" if "lon" in ds.coords else "longitude"
                ds = ds.rename({lat_k: "lat", lon_k: "lon"})
                datasets.append(ds)
            except Exception as e:
                log.warning(f"Error reading GPM file {rf.name}: {e}")

        if not datasets:
            raise ValueError(f"Could not read any valid GPM files from {raw_dir}")

        merged = xr.concat(datasets, dim="time").sortby("time")
        precip_da = merged.get("precipitation") or merged.get("precipitationCal")

        if precip_da is None:
            raise KeyError(f"No precipitation variable found in GPM dataset. Available: {list(merged.data_vars.keys())}")

        regridded = bilinear_interp_to_grid(precip_da, target_lats, target_lons)
        res_ds = xr.Dataset(data_vars={"rainfall": regridded}, coords=target_grid.coords)
        res_ds = apply_india_mask(res_ds, india_mask, land_masked=False)
        return res_ds
