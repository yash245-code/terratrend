"""TeraTrend crop suitability scoring and ranking.

Evaluates 20 principal Indian crops against location environmental features using
geometric-mean scoring with worst-factor + 30 caps.
Pure agronomic logic. Does NOT import Flask or any network library.
"""
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import CROPS_DIR
from teratrend.schemas import CropScore
from teratrend.suitability import rating_from_score, trapezoid_score

_CROP_REQUIREMENTS_CACHE: Optional[Dict[str, Any]] = None


def set_crop_requirements(requirements: Dict[str, Any]) -> None:
    """Explicitly inject crop requirements database from repository or cache."""
    global _CROP_REQUIREMENTS_CACHE
    _CROP_REQUIREMENTS_CACHE = dict(requirements)


def load_crop_requirements(path: Optional[Path] = None, force_reload: bool = False) -> Dict[str, Any]:
    """Load crop requirements database from JSON."""
    global _CROP_REQUIREMENTS_CACHE
    if not force_reload and _CROP_REQUIREMENTS_CACHE is not None:
        return _CROP_REQUIREMENTS_CACHE

    target_path = path or (CROPS_DIR / "crop_requirements.json")
    if not target_path.exists():
        raise FileNotFoundError(f"Crop requirements database missing: {target_path}")

    with open(target_path, "r", encoding="utf-8") as f:
        _CROP_REQUIREMENTS_CACHE = json.load(f)

    return _CROP_REQUIREMENTS_CACHE


def score_single_crop(
    crop_spec: Dict[str, Any],
    location_features: Dict[str, Any],
    season: Optional[str] = None,
    irrigation: str = "rainfed"
) -> CropScore:
    """Score a single crop against location environmental features.
    
    Factors evaluated:
    - Temperature (seasonal mean)
    - Rainfall / Moisture (seasonal sum)
    - Soil pH (topsoil)
    - Soil physical suitability (texture + drainage)
    - Salinity tolerance
    
    Overall score is geometric mean of factor scores, capped at worst_factor + 30.
    """
    key = crop_spec["key"]
    name = crop_spec["name"]
    local_name = crop_spec.get("local_name", "")
    group = crop_spec.get("group", "general")
    allowed_seasons = crop_spec.get("seasons", ["kharif"])

    # Determine evaluation season
    eval_season = season if (season and season in allowed_seasons) else allowed_seasons[0]

    # 1. Temperature score
    # Look for season-specific temp, fallback to annual mean temp
    seasonal_temps = location_features.get("seasonal_temperatures", {})
    crop_temp = seasonal_temps.get(eval_season, location_features.get("mean_temperature_c", 25.0))
    t_trap = crop_spec.get("temperature_trapezoid", [10, 18, 30, 38])
    temp_score = trapezoid_score(crop_temp, *t_trap) or 0.0

    # 2. Moisture / Rainfall score
    if irrigation == "irrigated":
        rf_score = 100.0
    else:
        seasonal_rf = location_features.get("seasonal_rainfall", {})
        crop_rf = seasonal_rf.get(eval_season, location_features.get("annual_rainfall_mm", 800.0))
        rf_trap = crop_spec.get("rainfall_trapezoid", [300, 600, 1200, 1800])
        rf_score = trapezoid_score(crop_rf, *rf_trap) or 0.0

    # 3. pH score
    top_ph = location_features.get("topsoil_ph", 7.0)
    ph_trap = crop_spec.get("ph_trapezoid", [5.5, 6.0, 7.5, 8.5])
    ph_score = trapezoid_score(top_ph, *ph_trap) or 0.0

    # 4. Soil texture and drainage
    loc_texture = str(location_features.get("texture", "loam")).lower().replace(" ", "_")
    pref_tex = [t.lower().replace(" ", "_") for t in crop_spec.get("preferred_textures", [])]
    tol_tex = [t.lower().replace(" ", "_") for t in crop_spec.get("tolerated_textures", [])]

    if loc_texture in pref_tex:
        tex_score = 100.0
    elif loc_texture in tol_tex:
        tex_score = 75.0
    else:
        tex_score = 35.0

    loc_drainage = str(location_features.get("drainage", "well")).lower().replace(" ", "_")
    pref_drain = [d.lower().replace(" ", "_") for d in crop_spec.get("preferred_drainage", [])]
    drain_score = 100.0 if loc_drainage in pref_drain else 60.0

    soil_score = 0.6 * tex_score + 0.4 * drain_score

    # 5. Salinity tolerance
    loc_salinity = location_features.get("salinity_ece", 1.0)
    tol_salinity = crop_spec.get("salinity_tolerance_ece", 4.0)

    if loc_salinity <= tol_salinity:
        sal_score = 100.0
    elif loc_salinity >= 2.0 * tol_salinity:
        sal_score = 0.0
    else:
        sal_score = float((2.0 * tol_salinity - loc_salinity) / tol_salinity * 100.0)

    factor_scores = {
        "temperature": temp_score,
        "moisture": rf_score,
        "soil_ph": ph_score,
        "soil": soil_score,
        "salinity": sal_score
    }

    # Minimum factor and limiting factor identification
    worst_factor = min(factor_scores, key=factor_scores.get)
    worst_score = factor_scores[worst_factor]

    # Geometric mean: exp(1/N * sum(ln(max(s, 1.0))))
    log_sum = sum(math.log(max(s, 1.0)) for s in factor_scores.values())
    raw_geom_mean = math.exp(log_sum / len(factor_scores))

    # Cap rule: geometric mean capped at worst factor score + 30
    capped_score = min(raw_geom_mean, worst_score + 30.0)
    final_score = max(0.0, min(100.0, capped_score))
    rating = rating_from_score(final_score)

    reason = f"Scored {final_score:.0f}/100 in {eval_season} season. "
    if worst_score < 50.0:
        reason += f"Constrained primarily by {worst_factor} ({worst_score:.0f}/100)."
    else:
        reason += "Well-balanced conditions across all agronomic parameters."

    return CropScore(
        key=key,
        name=name,
        local_name=local_name,
        group=group,
        score=round(final_score, 1),
        rating=rating,
        limiting_factor=worst_factor,
        season=eval_season,
        reason=reason
    )


def rank_crops(
    location_features: Dict[str, Any],
    season: Optional[str] = None,
    irrigation: str = "rainfed",
    crop_requirements_path: Optional[Path] = None,
    crops_data: Optional[Dict[str, Any]] = None,
) -> Tuple[List[CropScore], List[CropScore]]:
    """Rank all registered crops for a location and return suited crops and not recommended crops.
    
    Returns:
        (suited_crops_top8, not_recommended_up_to_5)
    """
    reqs = crops_data if crops_data is not None else load_crop_requirements(crop_requirements_path)
    scored_crops: List[CropScore] = []

    for crop_key, crop_spec in reqs.items():
        cs = score_single_crop(crop_spec, location_features, season=season, irrigation=irrigation)
        scored_crops.append(cs)

    # Sort descending by score
    scored_crops.sort(key=lambda c: c.score, reverse=True)

    # Top 8 suited crops
    suited_crops = [c for c in scored_crops if c.score >= 40.0][:8]
    if not suited_crops:
        # If none >= 40, return top 3 highest scoring
        suited_crops = scored_crops[:3]

    # Misfits: score < 40 or rated POOR
    misfits = [c for c in scored_crops if c.score < 40.0]
    misfits.sort(key=lambda c: c.score)  # Lowest score first
    not_recommended = misfits[:5]

    return suited_crops, not_recommended
