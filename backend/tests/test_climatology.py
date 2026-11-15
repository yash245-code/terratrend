"""Test suite for climatological aggregates, CV, drought frequencies, and seasonal windows."""
import numpy as np
import pandas as pd
import pytest

from teratrend.climatology import (
    aggregate_annual_series, compute_drought_and_wet_frequencies,
    compute_interannual_stats, compute_monthly_climatology,
    extract_seasonal_window
)


def test_monthly_climatology():
    """Verify 12-month baseline climatology computation."""
    times = pd.date_range("2010-01-01", "2019-12-31", freq="MS")
    # Sine wave with base 20.0 and amplitude 10.0
    vals = 20.0 + 10.0 * np.sin(2 * np.pi * (times.month - 1) / 12)
    s = pd.Series(vals, index=times)

    clim = compute_monthly_climatology(s)
    assert len(clim) == 12
    assert clim[1] == pytest.approx(20.0)  # January (sin(0) = 0)
    assert clim[4] == pytest.approx(30.0)  # April (sin(pi/2) = 1)


def test_interannual_cv():
    """Verify mean, std, and coefficient of variation (CV)."""
    # 10 years of annual values with mean 1000 and std 200 -> CV = 0.20
    vals = np.array([1000.0, 1200.0, 800.0, 1100.0, 900.0, 1050.0, 950.0, 1150.0, 850.0, 1000.0])
    idx = pd.date_range("2010-12-31", periods=10, freq="YE")
    s = pd.Series(vals, index=idx)

    stats = compute_interannual_stats(s)
    assert stats["mean"] == pytest.approx(1000.0)
    assert stats["cv"] == pytest.approx(float(np.std(vals, ddof=1) / 1000.0))


def test_drought_and_wet_frequencies():
    """Verify IMD standard drought (<75% mean) and wet (>125% mean) year frequencies."""
    # Mean = 1000. Thresholds: drought < 750, wet > 1250
    # Out of 10 years: 2 drought years (600, 700) -> 20%, 1 wet year (1400) -> 10%
    vals = np.array([1000.0, 1400.0, 600.0, 1000.0, 700.0, 1000.0, 1000.0, 1000.0, 1100.0, 1200.0])
    s = pd.Series(vals, index=pd.date_range("2010-12-31", periods=10, freq="YE"))

    res = compute_drought_and_wet_frequencies(s)
    assert res["drought_frequency_pct"] == pytest.approx(20.0)
    assert res["wet_frequency_pct"] == pytest.approx(10.0)


def test_rabi_seasonal_window_wraparound():
    """Verify rabi window (Nov, Dec of year Y-1 and Jan, Feb, Mar of year Y) aggregates across calendar years."""
    times = pd.date_range("2020-01-01", "2023-12-31", freq="MS")
    # Assign known constant per month
    s = pd.Series(times.month.astype(float), index=times)

    # Rabi sum for year 2021 = Nov 2020 (11) + Dec 2020 (12) + Jan 2021 (1) + Feb 2021 (2) + Mar 2021 (3) = 29
    rabi_series = extract_seasonal_window(s, season="rabi", method="sum")
    assert pd.Timestamp("2021-04-01") in rabi_series.index
    val_2021 = rabi_series.loc[pd.Timestamp("2021-04-01")]
    assert val_2021 == pytest.approx(11 + 12 + 1 + 2 + 3)
