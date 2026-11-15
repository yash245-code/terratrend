"""TeraTrend scientific trend engine.

Applies the Hamed-Rao Modified Mann-Kendall test for serially correlated time series
paired with Sen's non-parametric slope estimator.
Pure scientific logic. Does NOT import Flask or any network library.
"""
import math
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
import pymannkendall as pmk

from config import ALPHA, DATASETS, INDICATORS, MIN_YEARS_FOR_TREND, TREND_PER_YEARS
from teratrend.climatology import aggregate_anomaly_series, aggregate_annual_series
from teratrend.schemas import TrendResult
from teratrend.units import convert_series


class InsufficientDataError(Exception):
    """Exception raised when an indicator has fewer valid years than MIN_YEARS_FOR_TREND."""
    def __init__(self, message: str = "Insufficient data points to compute statistically valid trend", code: str = "INSUFFICIENT_DATA"):
        super().__init__(message)
        self.message = message
        self.code = code


def run_hamed_rao_trend(
    years: np.ndarray,
    values: np.ndarray,
    indicator_name: str = "",
    source_name: str = ""
) -> TrendResult:
    """Run Hamed-Rao Modified Mann-Kendall test on annual values array."""
    # Check length
    valid_mask = ~np.isnan(values)
    v_years = years[valid_mask]
    v_values = values[valid_mask]

    n_years = len(v_values)
    if n_years < MIN_YEARS_FOR_TREND:
        raise InsufficientDataError(
            f"Only {n_years} valid annual points available for {indicator_name} from {source_name}. "
            f"Minimum {MIN_YEARS_FOR_TREND} years required for modified Mann-Kendall trend testing."
        )

    # Check for constant series
    if np.all(v_values == v_values[0]) or np.std(v_values) == 0:
        raise InsufficientDataError(
            f"Series for {indicator_name} from {source_name} is constant across all years."
        )

    # Run Hamed-Rao test
    # pymannkendall hamed_rao_modification_test handles lag-1 to lag-k autocorrelation
    res = pmk.hamed_rao_modification_test(v_values, alpha=ALPHA)

    # Extract test attributes
    p_val = float(res.p)
    slope = float(res.slope)
    intercept = float(res.intercept)
    tau = float(res.Tau)
    trend_str = str(res.trend).lower()  # "increasing", "decreasing", "no trend"

    # Direction
    if p_val < ALPHA:
        if slope > 0:
            direction = "increasing"
        elif slope < 0:
            direction = "decreasing"
        else:
            direction = "no_trend"
    else:
        direction = "no_trend"

    sens_slope_per_year = slope
    sens_slope_per_decade = slope * float(TREND_PER_YEARS)

    # Baseline calculations
    start_year = int(v_years[0])
    end_year = int(v_years[-1])

    # Baseline mean from first 5 annual values
    baseline_window = min(5, n_years)
    baseline_mean = float(np.mean(v_values[:baseline_window]))
    recent_mean = float(np.mean(v_values[-baseline_window:]))

    # Total change percentage: slope * (n_years - 1) / baseline_mean * 100
    total_change_pct = None
    note = None
    if abs(baseline_mean) > 1e-4:
        total_change_pct = float(slope * (n_years - 1) / baseline_mean * 100.0)
    else:
        note = "Baseline mean near zero; percentage change undefined."

    # Standardized change: total change / interannual std
    interannual_std = float(np.std(v_values, ddof=1))
    standardized_change = None
    if interannual_std > 1e-6:
        standardized_change = float((slope * (n_years - 1)) / interannual_std)

    # Construct annual values and fitted trend line points
    annual_values_list = []
    trend_line_list = []
    for yr, val in zip(v_years, v_values):
        yr_int = int(yr)
        annual_values_list.append({"year": yr_int, "value": round(float(val), 4)})
        # pymannkendall intercept is relative to index 0..n-1
        idx_offset = yr_int - start_year
        fitted_val = intercept + slope * idx_offset
        trend_line_list.append({"year": yr_int, "fitted": round(float(fitted_val), 4)})

    return TrendResult(
        indicator=indicator_name,
        source=source_name,
        n_years=n_years,
        start_year=start_year,
        end_year=end_year,
        p_value=p_val,
        significant=(p_val < ALPHA),
        direction=direction,
        sens_slope_per_year=sens_slope_per_year,
        sens_slope_per_decade=sens_slope_per_decade,
        total_change_pct=total_change_pct,
        standardized_change=standardized_change,
        tau=tau,
        intercept=intercept,
        baseline_mean=baseline_mean,
        recent_mean=recent_mean,
        annual_values=annual_values_list,
        trend_line=trend_line_list,
        note=note
    )


def analyze_point(
    store: Any,
    lat: float,
    lon: float,
    indicator: str,
    source: Optional[str] = None
) -> TrendResult:
    """Extract time series for indicator and coordinate from CubeStore, aggregate to annual, and run trend test."""
    if indicator not in INDICATORS:
        raise KeyError(f"Unknown indicator '{indicator}'. Registered: {list(INDICATORS.keys())}")

    ind_spec = INDICATORS[indicator]
    source_key = source or ind_spec["primary_source"]

    if not store.has_dataset(source_key):
        raise KeyError(f"Source dataset '{source_key}' is not available in CubeStore.")

    # Find the right raw variable and conversion from indicator spec
    matched_src = None
    for s_entry in ind_spec["sources"]:
        if s_entry["dataset"] == source_key:
            matched_src = s_entry
            break

    if not matched_src:
        raise KeyError(f"Source '{source_key}' has no registered variable mapping for indicator '{indicator}'.")

    raw_var = matched_src["raw_var"]
    conversion = matched_src.get("conversion", "none")

    # Extract monthly time series from CubeStore
    monthly_series = store.extract_monthly_series(source_key, raw_var, lat, lon)
    if monthly_series.empty:
        raise InsufficientDataError(f"No valid monthly time series extracted for {indicator} at ({lat}, {lon}).")

    # Apply registered unit conversion
    converted_series = convert_series(conversion, monthly_series, times=monthly_series.index)
    if isinstance(converted_series, np.ndarray):
        converted_series = pd.Series(converted_series, index=monthly_series.index, name=indicator)

    # Determine aggregation method
    ds_meta = DATASETS.get(source_key, {})
    annual_method = ds_meta.get("annual_method", "standard")
    min_months = ds_meta.get("min_valid_months", 12)
    agg_op = ind_spec.get("aggregation", "mean")

    if annual_method == "anomaly":
        annual_series = aggregate_anomaly_series(converted_series, min_valid_months=min_months)
    else:
        annual_series = aggregate_annual_series(converted_series, method=agg_op, min_valid_months=min_months)

    if annual_series.empty:
        raise InsufficientDataError(f"No valid annual points could be constructed for {indicator} from {source_key}.")

    years = np.array(annual_series.index.year, dtype=int)
    values = annual_series.values.astype(float)

    return run_hamed_rao_trend(
        years=years,
        values=values,
        indicator_name=indicator,
        source_name=source_key
    )
