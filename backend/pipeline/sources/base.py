"""Abstract base class for TeraTrend dataset sources."""
from abc import ABC, abstractmethod
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import xarray as xr

from config import DATASETS

log = logging.getLogger("teratrend")


class DatasetSource(ABC):
    """Abstract dataset acquisition and cube harmonization source."""

    def __init__(self, key: str):
        self.key = key
        self.meta = DATASETS.get(key, {})

    @abstractmethod
    def search(
        self,
        start_year: int,
        end_year: int,
        bbox: tuple = (68.0, 6.0, 98.0, 38.0)
    ) -> List[Any]:
        """Query CMR/Earthaccess for granules matching temporal and spatial extent."""
        pass

    @abstractmethod
    def fetch(
        self,
        granules: List[Any],
        out_dir: Path,
        backend: str = "auto"
    ) -> List[Path]:
        """Download granules to local raw directory."""
        pass

    @abstractmethod
    def to_cube(
        self,
        raw_dir: Path,
        target_grid: xr.Dataset
    ) -> xr.Dataset:
        """Process and harmonize raw files into a standard 0.25° NetCDF dataset."""
        pass

    def describe(self) -> Dict[str, Any]:
        """Return collection metadata summary."""
        return {
            "key": self.key,
            "label": self.meta.get("label"),
            "provider": self.meta.get("provider"),
            "collection": self.meta.get("collection"),
            "version": self.meta.get("version"),
            "doi": self.meta.get("doi"),
            "native_res": self.meta.get("native_res"),
            "regrid_method": self.meta.get("regrid_method"),
            "required": self.meta.get("required"),
            "static": self.meta.get("static")
        }
