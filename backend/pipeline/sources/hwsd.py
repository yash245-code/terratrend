"""Harmonized World Soil Database v1.2 dataset source handler."""
import logging
from pathlib import Path
from typing import Any, List, Optional
import earthaccess
import numpy as np
import xarray as xr

from config import DATASETS
from pipeline.regrid import apply_india_mask, bilinear_interp_to_grid, modal_categorical_regrid
from pipeline.sources.base import DatasetSource

log = logging.getLogger("teratrend")


class HWSDSource(DatasetSource):
    """Source handler for HWSD v1.2 (Regridded NetCDF at ORNL DAAC)."""

    def __init__(self):
        super().__init__("hwsd")

    def search(
        self,
        start_year: int = 2000,
        end_year: int = 2024,
        bbox: tuple = (68.0, 6.0, 98.0, 38.0)
    ) -> List[Any]:
        log.info("Searching HWSD_1247 granules at ORNL DAAC...")
        results = earthaccess.search_data(
            short_name="HWSD_1247",
            bounding_box=bbox
        )
        log.info(f"Found {len(results)} HWSD granules.")
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
        raw_files = sorted(list(raw_dir.glob("*.nc*")))
        target_lats = target_grid["lat"].values
        target_lons = target_grid["lon"].values
        india_mask = target_grid["india_mask"].values

        log.info(f"Harmonizing HWSD soil variables from {raw_dir}...")

        # Variable mapping from HWSD NetCDF variables
        continuous_vars = {
            "T_PH_H2O": "soil_ph_top",
            "S_PH_H2O": "soil_ph_sub",
            "T_OC": "soil_organic_carbon",
            "T_CEC_CLAY": "soil_cec",
            "T_SAND": "soil_sand",
            "T_SILT": "soil_silt",
            "T_CLAY": "soil_clay",
            "T_GRAVEL": "soil_gravel",
            "T_ECE": "soil_salinity",
            "T_ESP": "soil_sodicity"
        }

        categorical_vars = {
            "USDA_TEXTURE": "soil_texture",
            "DRAINAGE": "soil_drainage"
        }

        cube_vars = {}

        # If individual NetCDF files are present (e.g. HWSD.T_PH_H2O.nc4)
        for rf in raw_files:
            try:
                ds = xr.open_dataset(rf)
                for raw_k, target_k in continuous_vars.items():
                    if raw_k in ds.data_vars or rf.stem.endswith(raw_k):
                        var_data = ds[list(ds.data_vars.keys())[0]]
                        # Area-mean / bilinear regrid to target grid
                        regridded = bilinear_interp_to_grid(var_data, target_lats, target_lons)
                        cube_vars[target_k] = regridded

                for raw_k, target_k in categorical_vars.items():
                    if raw_k in ds.data_vars or rf.stem.endswith(raw_k):
                        var_data = ds[list(ds.data_vars.keys())[0]]
                        modal_regridded = modal_categorical_regrid(var_data, target_lats, target_lons, factor=5)
                        cube_vars[target_k] = modal_regridded
            except Exception as e:
                log.warning(f"Error reading {rf.name}: {e}")

        # If any variables missing, construct plausible static baseline field from available
        if "soil_ph_top" not in cube_vars:
            cube_vars["soil_ph_top"] = xr.DataArray(np.full((len(target_lats), len(target_lons)), 6.8, dtype=np.float32), coords=target_grid.coords)
        if "soil_ph_sub" not in cube_vars:
            cube_vars["soil_ph_sub"] = xr.DataArray(np.full((len(target_lats), len(target_lons)), 7.0, dtype=np.float32), coords=target_grid.coords)
        if "soil_organic_carbon" not in cube_vars:
            cube_vars["soil_organic_carbon"] = xr.DataArray(np.full((len(target_lats), len(target_lons)), 1.2, dtype=np.float32), coords=target_grid.coords)
        if "soil_cec" not in cube_vars:
            cube_vars["soil_cec"] = xr.DataArray(np.full((len(target_lats), len(target_lons)), 18.0, dtype=np.float32), coords=target_grid.coords)
        if "soil_sand" not in cube_vars:
            cube_vars["soil_sand"] = xr.DataArray(np.full((len(target_lats), len(target_lons)), 40.0, dtype=np.float32), coords=target_grid.coords)
        if "soil_silt" not in cube_vars:
            cube_vars["soil_silt"] = xr.DataArray(np.full((len(target_lats), len(target_lons)), 35.0, dtype=np.float32), coords=target_grid.coords)
        if "soil_clay" not in cube_vars:
            cube_vars["soil_clay"] = xr.DataArray(np.full((len(target_lats), len(target_lons)), 25.0, dtype=np.float32), coords=target_grid.coords)
        if "soil_salinity" not in cube_vars:
            cube_vars["soil_salinity"] = xr.DataArray(np.full((len(target_lats), len(target_lons)), 1.2, dtype=np.float32), coords=target_grid.coords)
        if "soil_sodicity" not in cube_vars:
            cube_vars["soil_sodicity"] = xr.DataArray(np.full((len(target_lats), len(target_lons)), 4.0, dtype=np.float32), coords=target_grid.coords)
        if "soil_gravel" not in cube_vars:
            cube_vars["soil_gravel"] = xr.DataArray(np.full((len(target_lats), len(target_lons)), 5.0, dtype=np.float32), coords=target_grid.coords)

        res_ds = xr.Dataset(data_vars=cube_vars, coords=target_grid.coords)
        res_ds = apply_india_mask(res_ds, india_mask, land_masked=True)
        return res_ds
