"""Test suite for climate trend adaptation advisor."""
import pytest
from teratrend.advisor import advise
from teratrend.schemas import ConsensusResult, TrendResult


def test_significance_gate_p_value_threshold():
    """Verify strict significance gate:
    p = 0.049 (< 0.05) triggers SIGNIFICANT_DECREASE advisory.
    p = 0.050 (>= 0.05) returns STABLE_BASELINE (maintain rotations, no crop changes).
    """
    # Case A: p = 0.049 (Significant)
    tr_sig = TrendResult(
        indicator="root_moisture",
        source="gldas",
        n_years=15,
        start_year=2010,
        end_year=2024,
        p_value=0.049,
        significant=True,
        direction="decreasing",
        sens_slope_per_year=-1.5,
        sens_slope_per_decade=-15.0,
        total_change_pct=-12.0,
        standardized_change=-0.8,
        tau=-0.35,
        intercept=120.0,
        baseline_mean=180.0,
        recent_mean=158.0
    )

    adv_sig = advise("root_moisture", tr_sig)
    assert adv_sig.status == "SIGNIFICANT_DECREASE"
    assert len(adv_sig.crops) > 0  # Recommend drought-hardy crops (pearl millet, sorghum)
    assert "pearl_millet" in adv_sig.crops
    assert "rice" in adv_sig.avoid

    # Case B: p = 0.050 (Non-significant, fail gate)
    tr_nonsig = TrendResult(
        indicator="root_moisture",
        source="gldas",
        n_years=15,
        start_year=2010,
        end_year=2024,
        p_value=0.050,
        significant=False,
        direction="no_trend",
        sens_slope_per_year=-1.0,
        sens_slope_per_decade=-10.0,
        total_change_pct=-8.0,
        standardized_change=-0.5,
        tau=-0.20,
        intercept=120.0,
        baseline_mean=180.0,
        recent_mean=165.0
    )

    adv_nonsig = advise("root_moisture", tr_nonsig)
    assert adv_nonsig.status == "STABLE_BASELINE"
    assert len(adv_nonsig.crops) == 0
    assert len(adv_nonsig.avoid) == 0
    assert "maintain established crop rotations" in adv_nonsig.message.lower()


def test_air_quality_never_produces_crop_swap():
    """Verify atmospheric NO2 and Ozone trends never recommend changing crops."""
    tr_no2 = TrendResult(
        indicator="no2",
        source="omi",
        n_years=15,
        start_year=2010,
        end_year=2024,
        p_value=0.01,
        significant=True,
        direction="increasing",
        sens_slope_per_year=0.1,
        sens_slope_per_decade=1.0,
        total_change_pct=25.0,
        standardized_change=1.2,
        tau=0.45,
        intercept=2.0,
        baseline_mean=2.2,
        recent_mean=2.8
    )

    adv_no2 = advise("no2", tr_no2)
    assert len(adv_no2.crops) == 0
    assert len(adv_no2.avoid) == 0
    assert "air quality context only" in adv_no2.message.lower()
