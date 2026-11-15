"""Test suite for Hamed-Rao modified Mann-Kendall trend detection and Sen's slope."""
import numpy as np
import pandas as pd
import pytest

from teratrend.climatology import aggregate_anomaly_series
from teratrend.trend_engine import (
    InsufficientDataError, run_hamed_rao_trend
)


def test_known_downward_trend():
    """Verify known downward trend yields statistically significant p < 0.05 and negative Sen's slope."""
    years = np.arange(2000, 2020)  # 20 years
    # Strong downward slope: -1.5 per year + small noise
    rng = np.random.default_rng(42)
    values = 100.0 - 1.5 * (years - 2000) + rng.normal(0, 0.5, len(years))

    res = run_hamed_rao_trend(years, values, indicator_name="root_moisture", source_name="gldas")
    assert res.significant is True
    assert res.p_value < 0.05
    assert res.direction == "decreasing"
    assert res.sens_slope_per_year < 0.0
    assert res.sens_slope_per_decade == pytest.approx(res.sens_slope_per_year * 10.0)
    assert res.total_change_pct < 0.0


def test_random_noise_no_trend():
    """Verify purely random noise yields p >= 0.05 and direction 'no_trend'."""
    years = np.arange(2000, 2020)
    rng = np.random.default_rng(123)
    values = rng.normal(50.0, 5.0, len(years))

    res = run_hamed_rao_trend(years, values, indicator_name="rainfall", source_name="merra2")
    assert res.significant is False
    assert res.direction == "no_trend"


def test_short_series_raises_error():
    """Verify time series shorter than MIN_YEARS_FOR_TREND (10 years) raises InsufficientDataError."""
    years = np.arange(2015, 2020)  # 5 years
    values = np.array([10.0, 11.0, 12.0, 13.0, 14.0])

    with pytest.raises(InsufficientDataError) as exc_info:
        run_hamed_rao_trend(years, values, indicator_name="air_temperature", source_name="airs")
    assert "Minimum 10 years required" in exc_info.value.message


def test_anomaly_aggregation_unbiased():
    """Verify anomaly aggregation avoids seasonal sampling bias when different months are missing."""
    times = pd.date_range("2010-01-01", "2020-12-31", freq="MS")
    # Base seasonal cycle: hot May (35°C), cold January (15°C)
    base_t = 25.0 + 10.0 * np.sin(2 * np.pi * (times.month - 2) / 12)
    s = pd.Series(base_t, index=times)

    # In year 2015, drop peak summer months (May, June)
    s_gappy = s.copy()
    s_gappy[(s_gappy.index.year == 2015) & (s_gappy.index.month.isin([5, 6]))] = np.nan

    # Standard mean would drop significantly in 2015 due to missing summer months
    anom_res = aggregate_anomaly_series(s_gappy, min_valid_months=9)

    # In 2015, anomaly-based annual mean should remain near overall mean (~25.0), within 0.5°C
    val_2015 = anom_res[anom_res.index.year == 2015].values[0]
    val_2014 = anom_res[anom_res.index.year == 2014].values[0]
    assert abs(val_2015 - val_2014) < 0.5
