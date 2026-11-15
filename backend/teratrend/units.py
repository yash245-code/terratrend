"""TeraTrend unit conversions and indicator metadata.

Pure numerical and time-series unit conversion functions.
Does NOT import Flask or any network library.
"""
import calendar
from typing import Any, Dict, Optional, Union
import numpy as np
import pandas as pd
import xarray as xr

from config import INDICATORS

def kelvin_to_celsius(values: Union[float, np.ndarray, pd.Series, xr.DataArray]) -> Union[float, np.ndarray, pd.Series, xr.DataArray]:
    """Convert Kelvin to Celsius (°C = K - 273.15)."""
    return values - 273.15


def celsius_to_kelvin(values: Union[float, np.ndarray, pd.Series, xr.DataArray]) -> Union[float, np.ndarray, pd.Series, xr.DataArray]:
    """Convert Celsius to Kelvin (K = °C + 273.15)."""
    return values + 273.15


def days_in_month_series(time_series: Union[pd.DatetimeIndex, xr.DataArray]) -> np.ndarray:
    """Return array of days in month for each timestamp, correctly handling leap years."""
    if isinstance(time_series, xr.DataArray):
        times = pd.to_datetime(time_series.values)
    elif isinstance(time_series, pd.DatetimeIndex):
        times = time_series
    else:
        times = pd.to_datetime(time_series)
    return np.array([calendar.monthrange(t.year, t.month)[1] for t in times], dtype=float)


def flux_to_mm_month(
    flux_values: Union[float, np.ndarray, pd.Series, xr.DataArray],
    times: Optional[Union[pd.DatetimeIndex, xr.DataArray]] = None,
    year: Optional[int] = None,
    month: Optional[int] = None
) -> Union[float, np.ndarray, pd.Series, xr.DataArray]:
    """Convert moisture flux (kg/m^2/s) to monthly total (mm/month).
    
    1 kg/m^2 of liquid water = 1 mm depth.
    Monthly mm = flux (kg/m^2/s) * seconds in that exact month.
    """
    if times is not None:
        dim = days_in_month_series(times)
        seconds_in_month = dim * 86400.0
        if isinstance(flux_values, xr.DataArray):
            sec_da = xr.DataArray(seconds_in_month, coords=flux_values.coords, dims=flux_values.dims)
            return flux_values * sec_da
        elif isinstance(flux_values, pd.Series):
            return flux_values * seconds_in_month
        else:
            return flux_values * seconds_in_month
    elif year is not None and month is not None:
        dim = calendar.monthrange(year, month)[1]
        return flux_values * (dim * 86400.0)
    else:
        # Default fallback to 30.4375 days average if no time supplied
        return flux_values * (30.4375 * 86400.0)


def mm_per_hour_to_mm_month(
    rate_values: Union[float, np.ndarray, pd.Series, xr.DataArray],
    times: Optional[Union[pd.DatetimeIndex, xr.DataArray]] = None,
    year: Optional[int] = None,
    month: Optional[int] = None
) -> Union[float, np.ndarray, pd.Series, xr.DataArray]:
    """Convert precipitation rate (mm/hr) to monthly total (mm/month).
    
    Monthly mm = rate (mm/hr) * 24 hr/day * days in that exact month.
    """
    if times is not None:
        dim = days_in_month_series(times)
        hours_in_month = dim * 24.0
        if isinstance(rate_values, xr.DataArray):
            hr_da = xr.DataArray(hours_in_month, coords=rate_values.coords, dims=rate_values.dims)
            return rate_values * hr_da
        elif isinstance(rate_values, pd.Series):
            return rate_values * hours_in_month
        else:
            return rate_values * hours_in_month
    elif year is not None and month is not None:
        dim = calendar.monthrange(year, month)[1]
        return rate_values * (dim * 24.0)
    else:
        return rate_values * (30.4375 * 24.0)


def modis_scale(values: Union[float, np.ndarray, pd.Series, xr.DataArray]) -> Union[float, np.ndarray, pd.Series, xr.DataArray]:
    """Scale MODIS vegetation index integers (scale factor 0.0001, fill -3000)."""
    if isinstance(values, (xr.DataArray, pd.Series, np.ndarray)):
        scaled = np.where(values == -3000, np.nan, values * 0.0001)
        scaled = np.where((scaled < -0.2) | (scaled > 1.0), np.nan, scaled)
        return scaled
    else:
        if values == -3000 or values < -2000:
            return np.nan
        val = values * 0.0001
        return val if -0.2 <= val <= 1.0 else np.nan


# Area and mass conversion helpers
def ha_to_acres(ha: float) -> float:
    """Convert hectares to acres (1 ha = 2.47105 acres)."""
    return ha * 2.47105


def acres_to_ha(acres: float) -> float:
    """Convert acres to hectares (1 acre = 0.404686 ha)."""
    return acres * 0.404686


def quintal_to_tonnes(quintals: float) -> float:
    """Convert quintals to metric tonnes (1 quintal = 100 kg = 0.1 tonne)."""
    return quintals * 0.10


def tonnes_to_quintals(tonnes: float) -> float:
    """Convert metric tonnes to quintals (1 tonne = 10 quintals)."""
    return tonnes * 10.0


def convert_series(
    conversion: str,
    series: Union[xr.DataArray, pd.Series, np.ndarray],
    times: Optional[Union[pd.DatetimeIndex, xr.DataArray]] = None
) -> Union[xr.DataArray, pd.Series, np.ndarray]:
    """Apply unit conversion function based on registry conversion string."""
    if conversion == "kelvin_to_celsius":
        return kelvin_to_celsius(series)
    elif conversion == "flux_to_mm_month":
        return flux_to_mm_month(series, times=times)
    elif conversion == "mm_per_hour_to_mm_month":
        return mm_per_hour_to_mm_month(series, times=times)
    elif conversion == "modis_scale":
        return modis_scale(series)
    elif conversion == "none" or not conversion:
        return series
    else:
        return series


def indicator_meta(key: str) -> Dict[str, Any]:
    """Look up metadata for a registered indicator."""
    if key in INDICATORS:
        return INDICATORS[key]
    raise KeyError(f"Unknown indicator: '{key}'. Registered: {list(INDICATORS.keys())}")
