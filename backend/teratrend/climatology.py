"""TeraTrend climatological statistics, annual aggregations, and seasonal window calculations.

Pure numerical functions.
Does NOT import Flask or any network library.
"""
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
import xarray as xr

# Seasonal definitions (month numbers 1-12)
SEASON_MONTHS = {
    "kharif": [6, 7, 8, 9, 10],       # June to October
    "rabi": [11, 12, 1, 2, 3],        # November to March (crosses calendar year boundary)
    "zaid": [3, 4, 5, 6],             # March to June
    "annual": list(range(1, 13))       # January to December
}


def compute_monthly_climatology(series: pd.Series) -> Dict[int, float]:
    """Compute 12-month baseline climatology (mean for each month 1-12)."""
    if series.empty:
        return {m: 0.0 for m in range(1, 13)}
    grouped = series.groupby(series.index.month).mean()
    result = {}
    for m in range(1, 13):
        val = grouped.get(m, np.nan)
        result[m] = float(val) if not np.isnan(val) else 0.0
    return result


def aggregate_annual_series(
    monthly_series: pd.Series,
    method: str = "mean",
    min_valid_months: int = 12
) -> pd.Series:
    """Aggregate monthly time series to annual series.
    
    Args:
        monthly_series: pd.Series with DatetimeIndex
        method: "mean" or "sum"
        min_valid_months: Minimum required valid non-NaN months in a year (default 12)
    """
    if monthly_series.empty:
        return pd.Series(dtype=float)

    # Group by year
    years = monthly_series.index.year.unique()
    annual_vals = {}

    for yr in sorted(years):
        yr_data = monthly_series[monthly_series.index.year == yr].dropna()
        if len(yr_data) >= min_valid_months:
            if method == "sum":
                annual_vals[pd.Timestamp(year=yr, month=12, day=31)] = float(yr_data.sum())
            else:
                annual_vals[pd.Timestamp(year=yr, month=12, day=31)] = float(yr_data.mean())

    if not annual_vals:
        return pd.Series(dtype=float)

    idx = pd.DatetimeIndex(list(annual_vals.keys()))
    return pd.Series(list(annual_vals.values()), index=idx, name=monthly_series.name)


def aggregate_anomaly_series(
    monthly_series: pd.Series,
    min_valid_months: int = 9
) -> pd.Series:
    """Aggregate gappy monthly series to annual by averaging monthly anomalies.
    
    Prevents seasonal sampling bias when certain calendar months are missing.
    """
    if monthly_series.empty:
        return pd.Series(dtype=float)

    # 1. Monthly climatology
    clim = monthly_series.groupby(monthly_series.index.month).mean()
    # 2. Monthly anomaly
    anomalies = monthly_series.copy()
    for m, clim_val in clim.items():
        mask = anomalies.index.month == m
        anomalies[mask] = anomalies[mask] - clim_val

    # 3. Average anomalies per year requiring at least min_valid_months
    years = anomalies.index.year.unique()
    annual_anom = {}
    overall_mean = float(monthly_series.mean())

    for yr in sorted(years):
        yr_anom = anomalies[anomalies.index.year == yr].dropna()
        if len(yr_anom) >= min_valid_months:
            # Reconstruct annual absolute by adding overall mean
            annual_anom[pd.Timestamp(year=yr, month=12, day=31)] = float(yr_anom.mean() + overall_mean)

    if not annual_anom:
        return pd.Series(dtype=float)

    idx = pd.DatetimeIndex(list(annual_anom.keys()))
    return pd.Series(list(annual_anom.values()), index=idx, name=monthly_series.name)


def compute_interannual_stats(annual_series: pd.Series) -> Dict[str, float]:
    """Compute mean, standard deviation, and coefficient of variation (CV) of annual series."""
    clean = annual_series.dropna()
    if clean.empty or len(clean) < 2:
        return {"mean": float(clean.mean()) if len(clean) == 1 else 0.0, "std": 0.0, "cv": 0.0}

    mean_val = float(clean.mean())
    std_val = float(clean.std(ddof=1))
    cv_val = float(std_val / mean_val) if mean_val > 1e-6 else 0.0

    return {
        "mean": mean_val,
        "std": std_val,
        "cv": cv_val
    }


def compute_drought_and_wet_frequencies(annual_rainfall_series: pd.Series) -> Dict[str, float]:
    """Calculate historical frequency of drought years (<75% mean) and wet years (>125% mean).
    
    Based on India Meteorological Department (IMD) standard classification:
    - Moderate drought: annual rainfall deficiency between 26% and 50% (rainfall < 75% normal)
    - Excess / flood: annual rainfall > 125% normal
    """
    clean = annual_rainfall_series.dropna()
    if len(clean) < 5:
        return {"drought_frequency_pct": 0.0, "wet_frequency_pct": 0.0, "total_years": len(clean)}

    mean_rf = float(clean.mean())
    if mean_rf < 1.0:
        return {"drought_frequency_pct": 0.0, "wet_frequency_pct": 0.0, "total_years": len(clean)}

    drought_years = clean[clean < 0.75 * mean_rf]
    wet_years = clean[clean > 1.25 * mean_rf]

    return {
        "drought_frequency_pct": round(float(len(drought_years) / len(clean) * 100.0), 1),
        "wet_frequency_pct": round(float(len(wet_years) / len(clean) * 100.0), 1),
        "total_years": len(clean)
    }


def extract_seasonal_window(
    monthly_series: pd.Series,
    season: str = "annual",
    method: str = "sum"
) -> pd.Series:
    """Extract and aggregate a seasonal window across years, handling cross-year boundary (rabi).
    
    Args:
        monthly_series: Monthly series with DatetimeIndex
        season: "kharif", "rabi", "zaid", "annual"
        method: "sum" (for rainfall) or "mean" (for temp/moisture)
    """
    if monthly_series.empty or season not in SEASON_MONTHS:
        return pd.Series(dtype=float)

    months = SEASON_MONTHS[season]
    years = sorted(monthly_series.index.year.unique())
    seasonal_data = {}

    if season == "rabi":
        # Rabi spans Nov-Dec of year Y-1 and Jan-Feb-Mar of year Y
        for yr in years:
            prev_yr = yr - 1
            pts = []
            # Nov, Dec of prev_yr
            pts.extend(monthly_series[(monthly_series.index.year == prev_yr) & (monthly_series.index.month.isin([11, 12]))].values)
            # Jan, Feb, Mar of yr
            pts.extend(monthly_series[(monthly_series.index.year == yr) & (monthly_series.index.month.isin([1, 2, 3]))].values)
            if len(pts) >= 4:  # At least 4 of 5 months
                val = float(np.sum(pts)) if method == "sum" else float(np.mean(pts))
                seasonal_data[pd.Timestamp(year=yr, month=4, day=1)] = val
    else:
        for yr in years:
            pts = monthly_series[(monthly_series.index.year == yr) & (monthly_series.index.month.isin(months))].values
            req = len(months) - 1 if len(months) > 2 else len(months)
            if len(pts) >= req:
                val = float(np.sum(pts)) if method == "sum" else float(np.mean(pts))
                seasonal_data[pd.Timestamp(year=yr, month=12, day=31)] = val

    if not seasonal_data:
        return pd.Series(dtype=float)

    idx = pd.DatetimeIndex(list(seasonal_data.keys()))
    return pd.Series(list(seasonal_data.values()), index=idx, name=f"{monthly_series.name}_{season}")
