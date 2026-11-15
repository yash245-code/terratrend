"""TeraTrend dataset sources registry and factory."""
from typing import Dict, Type

from .airs import AIRSSource
from .base import DatasetSource
from .gldas import GLDASSource
from .gpm import GPMSource
from .hwsd import HWSDSource
from .merra2 import MERRA2Source
from .modis import MODISSource
from .omi import OMISource

SOURCE_REGISTRY: Dict[str, Type[DatasetSource]] = {
    "gldas": GLDASSource,
    "hwsd": HWSDSource,
    "merra2": MERRA2Source,
    "gpm": GPMSource,
    "modis": MODISSource,
    "airs": AIRSSource,
    "omi": OMISource,
}


def get_source(key: str) -> DatasetSource:
    """Instantiate dataset source handler by key."""
    if key not in SOURCE_REGISTRY:
        raise KeyError(f"Unknown dataset source: '{key}'. Available: {list(SOURCE_REGISTRY.keys())}")
    return SOURCE_REGISTRY[key]()


__all__ = [
    "DatasetSource",
    "GLDASSource",
    "HWSDSource",
    "MERRA2Source",
    "GPMSource",
    "MODISSource",
    "AIRSSource",
    "OMISource",
    "get_source",
    "SOURCE_REGISTRY"
]
