"""Test suite for unit conversions and indicator metadata."""
import calendar
import numpy as np
import pandas as pd
import pytest
import xarray as xr

from teratrend.units import (
    acres_to_ha, celsius_to_kelvin, convert_series, flux_to_mm_month,
    ha_to_acres, indicator_meta, kelvin_to_celsius, mm_per_hour_to_mm_month,
    modis_scale, quintal_to_tonnes, tonnes_to_quintals
)


def test_temperature_conversions():
    """Verify Kelvin <-> Celsius conversions."""
    assert kelvin_to_celsius(273.15) == pytest.approx(0.0)
    assert kelvin_to_celsius(300.0) == pytest.approx(26.85)
    assert celsius_to_kelvin(0.0) == pytest.approx(273.15)
    assert celsius_to_kelvin(25.0) == pytest.approx(298.15)


def test_flux_conversion_leap_february():
    """Verify moisture flux conversion uses real month seconds (leap Feb 2024 vs non-leap Feb 2023)."""
    flux = 1.0e-5  # kg/m^2/s

    # 2024 is a leap year -> 29 days = 29 * 86400 = 2,505,600 s
    mm_feb_2024 = flux_to_mm_month(flux, year=2024, month=2)
    expected_2024 = flux * 29 * 86400.0
    assert mm_feb_2024 == pytest.approx(expected_2024)

    # 2023 is non-leap -> 28 days = 28 * 86400 = 2,419,200 s
    mm_feb_2023 = flux_to_mm_month(flux, year=2023, month=2)
    expected_2023 = flux * 28 * 86400.0
    assert mm_feb_2023 == pytest.approx(expected_2023)

    # Vectorized timestamp test
    t_idx = pd.to_datetime(["2024-02-15", "2023-02-15"])
    arr = np.array([flux, flux])
    res = flux_to_mm_month(arr, times=t_idx)
    assert res[0] == pytest.approx(expected_2024)
    assert res[1] == pytest.approx(expected_2023)


def test_imerg_rate_conversion():
    """Verify IMERG precipitation rate (mm/hr) to monthly depth (mm/month)."""
    rate = 0.10  # mm/hr
    # January has 31 days = 744 hours
    mm_jan = mm_per_hour_to_mm_month(rate, year=2023, month=1)
    assert mm_jan == pytest.approx(rate * 31 * 24.0)


def test_modis_scaling_and_fill():
    """Verify MODIS 0.0001 scale factor and -3000 fill value handling."""
    assert modis_scale(5000) == pytest.approx(0.50)
    assert np.isnan(modis_scale(-3000))
    assert np.isnan(modis_scale(15000))  # Out of range (>1.0)


def test_land_and_mass_helpers():
    """Verify ha/acre and quintal/tonne conversions."""
    # 1 ha = 2.47105 acres
    assert ha_to_acres(10.0) == pytest.approx(24.7105)
    assert acres_to_ha(24.7105) == pytest.approx(10.0)

    # 1 quintal = 100 kg = 0.1 tonne
    assert quintal_to_tonnes(50.0) == pytest.approx(5.0)
    assert tonnes_to_quintals(5.0) == pytest.approx(50.0)


def test_indicator_meta_lookup():
    """Verify indicator registry metadata retrieval."""
    meta = indicator_meta("air_temperature")
    assert meta["unit"] == "degC"
    assert meta["primary_source"] == "gldas"

    with pytest.raises(KeyError):
        indicator_meta("non_existent_indicator")
