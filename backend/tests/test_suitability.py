"""Test suite for agricultural suitability scoring, trapezoid bounds, POOR factor caps, and outlooks."""
import numpy as np
import pytest

from teratrend.schemas import FactorReport
from teratrend.suitability import (
    compute_overall_assessment, rating_from_score, score_moisture, score_soil_ph,
    score_soil_quality, score_temperature, trapezoid_score
)


def test_trapezoid_edges():
    """Verify trapezoidal membership function at interior, bounds, exterior, and NaN."""
    # Trapezoid: abs_min=10, opt_min=20, opt_max=30, abs_max=40
    trap = (10.0, 20.0, 30.0, 40.0)

    # Optimum interior
    assert trapezoid_score(25.0, *trap) == pytest.approx(100.0)
    assert trapezoid_score(20.0, *trap) == pytest.approx(100.0)
    assert trapezoid_score(30.0, *trap) == pytest.approx(100.0)

    # Linear ramps
    assert trapezoid_score(15.0, *trap) == pytest.approx(50.0)
    assert trapezoid_score(35.0, *trap) == pytest.approx(50.0)

    # Outer bounds
    assert trapezoid_score(10.0, *trap) == pytest.approx(0.0)
    assert trapezoid_score(40.0, *trap) == pytest.approx(0.0)
    assert trapezoid_score(5.0, *trap) == pytest.approx(0.0)
    assert trapezoid_score(45.0, *trap) == pytest.approx(0.0)

    # NaN / None handling
    assert trapezoid_score(np.nan, *trap) is None
    assert trapezoid_score(None, *trap) is None


def test_ph_scoring_moderately_acidic():
    """Verify topsoil pH 5.1 scores MODERATE with accurate explanation."""
    rep = score_soil_ph(5.1, subsoil_ph=5.5)
    assert rep.rating == "MODERATE"
    assert "moderately acidic" in rep.explanation
    assert rep.values["topsoil_ph"] == 5.1


def test_poor_factor_cap_rule():
    """Verify that if ANY factor is rated POOR (< 40), overall rating is capped at MODERATE and score <= 69."""
    # 4 factors are excellent (95.0), but 1 factor (moisture) is POOR (20.0)
    factors = {
        "temperature": FactorReport("temperature", 95.0, "GOOD", {}, {}, "Good", confidence="high"),
        "moisture": FactorReport("moisture", 20.0, "POOR", {}, {}, "Severe deficit", confidence="high"),
        "soil_ph": FactorReport("soil_ph", 90.0, "GOOD", {}, {}, "Good", confidence="high"),
        "soil_quality": FactorReport("soil_quality", 90.0, "GOOD", {}, {}, "Good", confidence="high"),
        "climate": FactorReport("climate", 90.0, "GOOD", {}, {}, "Good", confidence="high"),
    }

    ov_score, ov_rating, ov_verdict, limiting, ov_conf = compute_overall_assessment(factors)

    # Uncapped weighted average would be: 0.20*95 + 0.25*20 + 0.15*90 + 0.20*90 + 0.20*90 = 73.5 (which would be GOOD)
    # But POOR cap forces score <= 69.0 and rating MODERATE
    assert ov_score <= 69.0
    assert ov_rating == "MODERATE"
    assert "moisture" in limiting


def test_irrigated_vs_rainfed_moisture():
    """Verify irrigated mode bypasses natural precipitation limits and scores 100."""
    rainfed = score_moisture(annual_rainfall_mm=300.0, root_wetness=0.15, irrigation="rainfed")
    irrigated = score_moisture(annual_rainfall_mm=300.0, root_wetness=0.15, irrigation="irrigated")

    assert rainfed.score < 50.0
    assert irrigated.score == 100.0
    assert irrigated.rating == "GOOD"
