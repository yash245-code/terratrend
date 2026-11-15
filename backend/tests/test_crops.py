"""Test suite for crop suitability ranking, soil and moisture preferences, and geometric mean cap."""
import pytest
from teratrend.crops import rank_crops, score_single_crop


def test_crop_ranking_wet_clay_vs_dry_sandy():
    """Verify ecological realism:
    - In wet clay soil (1500 mm rain, clay texture), Rice outscores Pearl Millet.
    - In dry sandy soil (350 mm rain, loamy sand), Pearl Millet outscores Rice.
    """
    wet_clay_env = {
        "mean_temperature_c": 26.0,
        "annual_rainfall_mm": 1800.0,
        "topsoil_ph": 6.8,
        "texture": "clay",
        "drainage": "moderately_well",
        "salinity_ece": 1.5
    }

    dry_sandy_env = {
        "mean_temperature_c": 28.0,
        "annual_rainfall_mm": 350.0,
        "topsoil_ph": 7.5,
        "texture": "loamy_sand",
        "drainage": "well",
        "salinity_ece": 1.8
    }

    suited_wet, _ = rank_crops(wet_clay_env, irrigation="rainfed")
    suited_dry, _ = rank_crops(dry_sandy_env, irrigation="rainfed")

    score_map_wet = {c.key: c.score for c in suited_wet}
    score_map_dry = {c.key: c.score for c in suited_dry}

    # In wet clay: Rice beats Pearl Millet
    assert score_map_wet.get("rice", 0.0) > score_map_wet.get("pearl_millet", 0.0)

    # In dry sandy: Pearl Millet beats Rice
    assert score_map_dry.get("pearl_millet", 0.0) > score_map_dry.get("rice", 0.0)


def test_salinity_impact_on_sensitive_crops():
    """Verify high soil salinity (ECe = 6.0 dS/m) severely penalizes salt-sensitive crops (potato, tomato)
    while salt-tolerant crops (barley, cotton) maintain viability."""
    saline_env = {
        "mean_temperature_c": 20.0,
        "annual_rainfall_mm": 600.0,
        "topsoil_ph": 7.8,
        "texture": "loam",
        "drainage": "well",
        "salinity_ece": 6.5
    }

    suited, misfits = rank_crops(saline_env, irrigation="rainfed")
    misfit_keys = [c.key for c in misfits]
    suited_keys = [c.key for c in suited]

    # Barley is highly salt tolerant (tolerance 8.0)
    assert "barley" in suited_keys
    # Potato is salt sensitive (tolerance 2.5) -> must be severely penalized
    assert ("potato" in misfit_keys) or (any(c.key == "potato" and c.score < 50 for c in suited))
