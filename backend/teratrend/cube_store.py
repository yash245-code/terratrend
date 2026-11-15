"""TeraTrend in-memory Xarray cube store.

Preloads all NetCDF cubes and India boundary grid into RAM as float32.
Sub-millisecond access for spatial point extraction and nearest-neighbor lookups.
"""
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
import xarray as xr

from config import DATASETS, INDIA_GRID_NC, MAX_LAND_FALLBACK_KM, PROCESSED_DIR

log = logging.getLogger("teratrend")

_GLOBAL_STORE: Optional["CubeStore"] = None


class CubeStore:
    """Manages pre-loaded NetCDF datasets in system memory."""

    def __init__(self, processed_dir: Optional[Path] = None):
        self.processed_dir = processed_dir or PROCESSED_DIR
        self.cubes: Dict[str, xr.Dataset] = {}
        self.grid_ds: Optional[xr.Dataset] = None
        self._lats: Optional[np.ndarray] = None
        self._lons: Optional[np.ndarray] = None
        self._india_mask: Optional[np.ndarray] = None
        self.total_ram_mb: float = 0.0

    def load_all(self) -> None:
        """Scan disk and load all existing cube NetCDF files into RAM."""
        # 1. Load India Grid
        grid_path = self.processed_dir / "india_grid.nc"
        if grid_path.exists():
            try:
                self.grid_ds = xr.open_dataset(grid_path).load()
                self._lats = self.grid_ds["lat"].values
                self._lons = self.grid_ds["lon"].values
                if "india_mask" in self.grid_ds:
                    self._india_mask = self.grid_ds["india_mask"].values.astype(bool)
                log.info(f"Loaded india_grid.nc with shape ({len(self._lats)}, {len(self._lons)})")
            except Exception as e:
                log.error(f"Failed to load {grid_path}: {e}")

        # 2. Load Dataset Cubes
        for key, meta in DATASETS.items():
            cube_file = self.processed_dir / f"{key}_cube.nc"
            if cube_file.exists():
                try:
                    ds = xr.open_dataset(cube_file).load()
                    # Cast floats to float32 to conserve RAM
                    float_vars = [v for v in ds.data_vars if ds[v].dtype in [np.float64, np.float32]]
                    for fv in float_vars:
                        ds[fv] = ds[fv].astype(np.float32)

                    self.cubes[key] = ds
                    sz_mb = ds.nbytes / (1024.0 * 1024.0)
                    self.total_ram_mb += sz_mb
                    log.info(f"Loaded {key}_cube.nc ({sz_mb:.1f} MB) in RAM.")
                except Exception as e:
                    log.error(f"Error loading {cube_file}: {e}")

        log.info(f"CubeStore initialization complete. Total preloaded RAM: {self.total_ram_mb:.1f} MB.")

    def has_dataset(self, key: str) -> bool:
        """Check if dataset key is loaded."""
        return key in self.cubes

    def get(self, key: str) -> xr.Dataset:
        """Get dataset xarray cube."""
        if key not in self.cubes:
            raise KeyError(f"Dataset '{key}' is not loaded. Available: {list(self.cubes.keys())}")
        return self.cubes[key]

    def available(self) -> List[str]:
        """Return list of loaded dataset keys."""
        return list(self.cubes.keys())

    def is_operational(self) -> Tuple[bool, List[str]]:
        """Check if minimum required datasets (gldas, hwsd, india_grid) are present."""
        missing = []
        if self._india_mask is None:
            missing.append("india_grid")
        if "gldas" not in self.cubes:
            missing.append("gldas")
        if "hwsd" not in self.cubes:
            missing.append("hwsd")
        return (len(missing) == 0), missing

    def get_lats(self) -> np.ndarray:
        """Return latitude array."""
        if self._lats is not None:
            return self._lats
        # Generate default grid if not loaded
        return np.arange(6.0, 38.0 + 0.25, 0.25)

    def get_lons(self) -> np.ndarray:
        """Return longitude array."""
        if self._lons is not None:
            return self._lons
        return np.arange(68.0, 98.0 + 0.25, 0.25)

    def get_india_mask(self) -> np.ndarray:
        """Return 2D boolean india_mask array."""
        if self._india_mask is not None:
            return self._india_mask
        lats = self.get_lats()
        lons = self.get_lons()
        return np.ones((len(lats), len(lons)), dtype=bool)

    def coverage(self, key: str) -> Dict[str, Any]:
        """Return metadata coverage summary for a dataset."""
        if key not in self.cubes:
            return {"loaded": False}
        ds = self.cubes[key]
        times = ds["time"].values if "time" in ds else []
        return {
            "loaded": True,
            "variables": list(ds.data_vars.keys()),
            "start_time": str(times[0]) if len(times) > 0 else None,
            "end_time": str(times[-1]) if len(times) > 0 else None,
            "time_steps": len(times),
            "ram_mb": round(ds.nbytes / (1024.0 * 1024.0), 2)
        }

    def check_cell_valid(self, dataset: str, lat: float, lon: float) -> bool:
        """Check if grid cell has non-NaN values for dataset."""
        if dataset not in self.cubes:
            return False
        ds = self.cubes[dataset]
        # Snap to nearest coordinate
        sample_var = list(ds.data_vars.keys())[0]
        da = ds[sample_var].sel(lat=lat, lon=lon, method="nearest")
        if "time" in da.dims:
            vals = da.values
            return bool(np.any(~np.isnan(vals)))
        else:
            return bool(~np.isnan(da.values))

    def find_nearest_valid_land_cell(
        self,
        dataset: str,
        lat: float,
        lon: float,
        max_km: float = MAX_LAND_FALLBACK_KM
    ) -> Tuple[Optional[Tuple[float, float]], float]:
        """Find the nearest valid land cell for a land-surface model within max_km distance."""
        from teratrend.geo import haversine_distance_km
        if dataset not in self.cubes:
            return None, float("inf")

        ds = self.cubes[dataset]
        sample_var = list(ds.data_vars.keys())[0]
        da = ds[sample_var]

        # Valid 2D mask
        if "time" in da.dims:
            valid_2d = np.any(~np.isnan(da.values), axis=0)
        else:
            valid_2d = ~np.isnan(da.values)

        if not np.any(valid_2d):
            return None, float("inf")

        lats = ds["lat"].values
        lons = ds["lon"].values

        # Only inspect coordinates within a reasonable degree window (~0.5 deg around max_km)
        deg_pad = (max_km / 111.0) * 1.5
        lat_mask = (lats >= lat - deg_pad) & (lats <= lat + deg_pad)
        lon_mask = (lons >= lon - deg_pad) & (lons <= lon + deg_pad)

        candidate_lats = lats[lat_mask]
        candidate_lons = lons[lon_mask]

        best_coord = None
        best_dist = float("inf")

        for clat in candidate_lats:
            for clon in candidate_lons:
                lat_i = int(np.where(lats == clat)[0][0])
                lon_i = int(np.where(lons == clon)[0][0])
                if valid_2d[lat_i, lon_i]:
                    dist = haversine_distance_km(lat, lon, clat, clon)
                    if dist < best_dist:
                        best_dist = dist
                        best_coord = (float(clat), float(clon))

        if best_dist <= max_km:
            return best_coord, best_dist
        return None, best_dist

    def extract_monthly_series(
        self,
        dataset: str,
        var_name: str,
        lat: float,
        lon: float
    ) -> pd.Series:
        """Extract 1D monthly time series at coordinate."""
        if dataset not in self.cubes:
            return pd.Series(dtype=float)
        ds = self.cubes[dataset]

        # Check variable name directly or map from raw
        target_var = var_name
        if target_var not in ds.data_vars:
            # Check if mapped name exists
            ds_vars = DATASETS.get(dataset, {}).get("variables", {})
            for rk, rmeta in ds_vars.items():
                if rk == var_name or rmeta.get("name") == var_name:
                    if rmeta.get("name") in ds.data_vars:
                        target_var = rmeta.get("name")
                        break
                    elif rk in ds.data_vars:
                        target_var = rk
                        break

        if target_var not in ds.data_vars:
            log.warning(f"Variable '{var_name}' not found in dataset '{dataset}'. Available: {list(ds.data_vars.keys())}")
            return pd.Series(dtype=float)

        da = ds[target_var].sel(lat=lat, lon=lon, method="nearest")
        if "time" not in da.dims:
            return pd.Series(dtype=float)

        times = pd.to_datetime(da["time"].values)
        vals = da.values.astype(float)
        return pd.Series(vals, index=times, name=target_var)


def get_store(processed_dir: Optional[Path] = None) -> CubeStore:
    """Retrieve or initialize singleton CubeStore."""
    global _GLOBAL_STORE
    if _GLOBAL_STORE is None:
        _GLOBAL_STORE = CubeStore(processed_dir)
        _GLOBAL_STORE.load_all()
    return _GLOBAL_STORE
