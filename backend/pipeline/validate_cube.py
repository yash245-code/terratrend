"""Validation suite for processed NetCDF cubes and multi-dataset cross-consistency."""
import argparse
import logging
from pathlib import Path
import sys
from typing import Dict, List, Optional
import numpy as np
import xarray as xr

# Ensure backend root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config import DATASETS, INDIA_GRID_NC, PROCESSED_DIR
from pipeline.provenance import compute_file_sha256, load_provenance

log = logging.getLogger("teratrend")


def validate_cube_file(cube_path: Path, dataset_key: str, target_grid: xr.Dataset) -> List[str]:
    """Validate single NetCDF cube against structural and integrity standards."""
    errors: List[str] = []

    if not cube_path.exists():
        errors.append(f"Cube file not found: {cube_path}")
        return errors

    try:
        ds = xr.open_dataset(cube_path)
    except Exception as e:
        errors.append(f"Failed to open NetCDF cube: {e}")
        return errors

    # 1. Coordinates check
    grid_lats = target_grid["lat"].values
    grid_lons = target_grid["lon"].values

    if not np.allclose(ds["lat"].values, grid_lats, atol=1e-4):
        errors.append(f"Latitude coordinate mismatch with canonical India grid ({len(ds['lat'])} vs {len(grid_lats)})")

    if not np.allclose(ds["lon"].values, grid_lons, atol=1e-4):
        errors.append(f"Longitude coordinate mismatch with canonical India grid ({len(ds['lon'])} vs {len(grid_lons)})")

    # 2. Time coordinate check (for dynamic sets)
    meta = DATASETS.get(dataset_key, {})
    if not meta.get("static", False):
        if "time" not in ds.coords and "time" not in ds.dims:
            errors.append("Dynamic dataset missing 'time' coordinate")
        else:
            times = ds["time"].values
            if len(times) < 12:
                errors.append(f"Time steps ({len(times)}) less than 1 year (12 months)")

    # 3. Check plausible values and NaN fraction inside India mask
    india_mask = target_grid["india_mask"].values.astype(bool)
    in_india_count = int(np.sum(india_mask))

    for var_name in ds.data_vars:
        da = ds[var_name]
        vals = da.values
        if "time" in da.dims:
            # Check last time slice
            slice_vals = vals[-1]
        else:
            slice_vals = vals

        in_vals = slice_vals[india_mask]
        nan_fraction = np.sum(np.isnan(in_vals)) / in_india_count

        if meta.get("land_masked", True):
            # Land surface models (GLDAS, HWSD) have NaNs over small islands and water bodies
            if nan_fraction > 0.60:
                errors.append(f"Variable '{var_name}' has excessive NaN fraction inside India: {nan_fraction:.1%}")
        else:
            # Atmospheric sets (MERRA-2, GPM) should have very low NaNs inside India
            if nan_fraction > 0.20:
                errors.append(f"Atmospheric variable '{var_name}' has unexpected NaNs inside India: {nan_fraction:.1%}")

    # Specific sanity checks for soil
    if dataset_key == "hwsd":
        if "soil_ph_top" in ds:
            ph = ds["soil_ph_top"].values
            valid_ph = ph[~np.isnan(ph)]
            if len(valid_ph) > 0 and (np.min(valid_ph) < 3.0 or np.max(valid_ph) > 10.5):
                errors.append(f"HWSD topsoil pH outside plausible terrestrial bounds (3.0-10.5): min={np.min(valid_ph):.1f}, max={np.max(valid_ph):.1f}")
        if "soil_organic_carbon" in ds:
            oc = ds["soil_organic_carbon"].values
            valid_oc = oc[~np.isnan(oc)]
            if len(valid_oc) > 0 and np.min(valid_oc) < 0.0:
                errors.append(f"HWSD organic carbon contains negative values: min={np.min(valid_oc):.2f}")

    return errors


def run_cross_dataset_sanity(processed_dir: Path) -> List[str]:
    """Perform cross-dataset physical consistency checks."""
    warnings: List[str] = []

    gldas_path = processed_dir / "gldas_cube.nc"
    merra2_path = processed_dir / "merra2_cube.nc"
    gpm_path = processed_dir / "gpm_cube.nc"

    # 1. Temperature sanity (GLDAS vs MERRA-2)
    if gldas_path.exists() and merra2_path.exists():
        try:
            ds_g = xr.open_dataset(gldas_path)
            ds_m = xr.open_dataset(merra2_path)
            if "air_temperature" in ds_g and "air_temperature" in ds_m:
                t_g = float(ds_g["air_temperature"].mean().values)
                t_m = float(ds_m["air_temperature"].mean().values)
                diff = abs(t_g - t_m)
                if diff > 10.0:
                    warnings.append(f"Large temperature divergence between GLDAS and MERRA-2: {diff:.1f} K difference.")
                else:
                    log.info(f"Cross-check GLDAS vs MERRA-2 temperature: within {diff:.1f} K (Pass).")
        except Exception as e:
            warnings.append(f"Temperature cross-validation error: {e}")

    # 2. Rainfall sanity (GLDAS vs GPM)
    if gldas_path.exists() and gpm_path.exists():
        try:
            ds_g = xr.open_dataset(gldas_path)
            ds_p = xr.open_dataset(gpm_path)
            if "rainfall" in ds_g and "rainfall" in ds_p:
                rf_g = float(ds_g["rainfall"].mean().values)
                rf_p = float(ds_p["rainfall"].mean().values)
                log.info(f"Cross-check GLDAS vs GPM rainfall comparison: GLDAS={rf_g:.1f}, GPM={rf_p:.1f}")
        except Exception as e:
            warnings.append(f"Rainfall cross-validation error: {e}")

    return warnings


def validate_all(processed_dir: Optional[Path] = None) -> bool:
    """Run full validation across all generated cubes."""
    p_dir = processed_dir or PROCESSED_DIR
    grid_path = p_dir / "india_grid.nc"

    if not grid_path.exists():
        log.error(f"Cannot validate without canonical grid: {grid_path}")
        return False

    target_grid = xr.open_dataset(grid_path)
    all_passed = True

    for key, meta in DATASETS.items():
        cube_p = meta["cube_path"]
        if not cube_p.exists():
            if meta.get("required", False):
                log.error(f"Required cube missing: {cube_p.name}")
                all_passed = False
            else:
                log.info(f"Optional cube not present: {cube_p.name} (Skipped)")
            continue

        log.info(f"Validating {cube_p.name}...")
        errs = validate_cube_file(cube_p, key, target_grid)
        if errs:
            for er in errs:
                log.error(f"[{key}] {er}")
            all_passed = False
        else:
            log.info(f"[{key}] Validation PASSED.")

    # Cross-dataset sanity
    cross_warns = run_cross_dataset_sanity(p_dir)
    for w in cross_warns:
        log.warning(f"[Cross-Dataset Sanity] {w}")

    return all_passed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    passed = validate_all()
    sys.exit(0 if passed else 1)
