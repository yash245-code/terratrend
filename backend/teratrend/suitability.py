"""TeraTrend agricultural land suitability scoring engine.

Evaluates 5 primary agronomic factors (temperature, moisture, soil pH, soil quality, climate)
using smooth trapezoidal scoring, factor breakdowns, dynamic 10-year outlooks, and POOR factor caps.
Pure agronomic logic. Does NOT import Flask or any network library.
"""
import math
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np

from config import (
    CLIMATE_WEIGHTS, DRAINAGE_SCORES, FACTOR_WEIGHTS, OUTLOOK_YEARS,
    POOR_SCORE_CAP, RATING_GOOD_THRESHOLD, RATING_MODERATE_THRESHOLD,
    SOIL_QUALITY_WEIGHTS, TEXTURE_SCORES, TRAPEZOIDS
)
from teratrend.schemas import FactorReport


def trapezoid_score(
    x: Optional[float],
    abs_min: float,
    opt_min: float,
    opt_max: float,
    abs_max: float
) -> Optional[float]:
    """Compute 0-100 score using a trapezoidal membership function.
    
    Returns 100 inside [opt_min, opt_max], linear ramp from 0 at bounds, 0 outside.
    Returns None if x is None or NaN.
    """
    if x is None or math.isnan(x):
        return None

    if x < abs_min or x > abs_max:
        return 0.0

    if opt_min <= x <= opt_max:
        return 100.0

    if abs_min <= x < opt_min:
        if opt_min == abs_min:
            return 100.0
        return float(((x - abs_min) / (opt_min - abs_min)) * 100.0)

    if opt_max < x <= abs_max:
        if abs_max == opt_max:
            return 100.0
        return float(((abs_max - x) / (abs_max - opt_max)) * 100.0)

    return 0.0


def rating_from_score(score: Optional[float]) -> str:
    """Classify 0-100 score into GOOD, MODERATE, POOR, or NO_DATA."""
    if score is None or math.isnan(score):
        return "NO_DATA"
    if score >= RATING_GOOD_THRESHOLD:
        return "GOOD"
    if score >= RATING_MODERATE_THRESHOLD:
        return "MODERATE"
    return "POOR"


def score_temperature(
    mean_temp_c: float,
    temp_trend: Optional[Any] = None,
    trapezoid: Optional[Tuple[float, float, float, float]] = None
) -> FactorReport:
    """Score temperature factor."""
    trap = trapezoid or TRAPEZOIDS["temperature"]
    score = trapezoid_score(mean_temp_c, *trap) or 0.0
    rating = rating_from_score(score)

    explanation = (
        f"Annual mean temperature is {mean_temp_c:.1f}°C. "
        f"The optimal agronomic range is {trap[1]:.0f}–{trap[2]:.0f}°C (tolerated {trap[0]:.0f}–{trap[3]:.0f}°C)."
    )
    if rating == "GOOD":
        explanation += " Thermal regime is highly favorable for principal seasonal crops."
    elif rating == "MODERATE":
        explanation += " Thermal regime is acceptable but may restrict heat- or chill-sensitive crop stages."
    else:
        explanation += " Thermal regime imposes significant heat or cold stress on crops."

    trend_block = None
    if temp_trend is not None and getattr(temp_trend, "significant", False):
        slope_decade = getattr(temp_trend, "sens_slope_per_decade", 0.0)
        proj_val = mean_temp_c + (slope_decade * (OUTLOOK_YEARS / 10.0))
        proj_score = trapezoid_score(proj_val, *trap) or 0.0
        score_diff = proj_score - score
        outlook = "IMPROVING" if score_diff >= 5.0 else ("WORSENING" if score_diff <= -5.0 else "STABLE")

        trend_block = {
            "direction": temp_trend.direction,
            "significant": True,
            "p_value": round(float(temp_trend.p_value), 4),
            "sens_slope_per_decade": round(float(slope_decade), 2),
            "projected_value": round(float(proj_val), 1),
            "score_in_10y": round(float(proj_score), 1),
            "outlook": outlook
        }
    elif temp_trend is not None:
        trend_block = {
            "direction": "no_trend",
            "significant": False,
            "p_value": round(float(temp_trend.p_value), 4) if getattr(temp_trend, "p_value", None) is not None else None,
            "sens_slope_per_decade": 0.0,
            "projected_value": round(float(mean_temp_c), 1),
            "score_in_10y": round(float(score), 1),
            "outlook": "STABLE"
        }

    return FactorReport(
        factor="temperature",
        score=round(score, 1),
        rating=rating,
        values={"mean_temperature_c": round(mean_temp_c, 1)},
        ideal={"optimal_min_c": trap[1], "optimal_max_c": trap[2], "tolerated_min_c": trap[0], "tolerated_max_c": trap[3]},
        explanation=explanation,
        trend=trend_block,
        sources=["gldas"],
        confidence="high"
    )


def score_moisture(
    annual_rainfall_mm: float,
    root_wetness: float,
    irrigation: str = "rainfed",
    rainfall_trend: Optional[Any] = None,
    moisture_trend: Optional[Any] = None,
    rainfall_trap: Optional[Tuple[float, float, float, float]] = None
) -> FactorReport:
    """Score moisture factor."""
    if irrigation == "irrigated":
        return FactorReport(
            factor="moisture",
            score=100.0,
            rating="GOOD",
            values={"annual_rainfall_mm": round(annual_rainfall_mm, 0), "root_wetness": round(root_wetness, 2), "irrigation_mode": "irrigated"},
            ideal={"rainfall_mm": "Assured irrigation source", "root_wetness": "Managed via irrigation"},
            explanation="Field has assured irrigation. Natural precipitation and soil wetness constraints are bypassed, contingent on reliable water supply.",
            trend={"direction": "managed", "significant": False, "outlook": "STABLE"},
            sources=["user_option", "gldas"],
            confidence="high"
        )

    rf_trap = rainfall_trap or TRAPEZOIDS["rainfall"]
    rw_trap = TRAPEZOIDS["root_wetness"]

    rf_score = trapezoid_score(annual_rainfall_mm, *rf_trap) or 0.0
    rw_score = trapezoid_score(root_wetness, *rw_trap) or 0.0

    score = 0.5 * rf_score + 0.5 * rw_score
    rating = rating_from_score(score)

    explanation = (
        f"Annual rainfall is {annual_rainfall_mm:.0f} mm (optimal {rf_trap[1]:.0f}–{rf_trap[2]:.0f} mm) "
        f"and root-zone wetness is {root_wetness:.2f} (optimal {rw_trap[1]:.2f}–{rw_trap[2]:.2f})."
    )
    if rating == "GOOD":
        explanation += " Moisture regime is well-suited for rainfed crop cycles."
    elif rating == "MODERATE":
        explanation += " Moisture is moderately limiting; supplemental protective irrigation recommended during dry spells."
    else:
        explanation += " Severe moisture deficit or waterlogging risk; requires micro-irrigation or drainage."

    trend_block = None
    active_trend = moisture_trend if (moisture_trend and getattr(moisture_trend, "significant", False)) else rainfall_trend
    if active_trend is not None and getattr(active_trend, "significant", False):
        slope_decade = getattr(active_trend, "sens_slope_per_decade", 0.0)
        proj_rf = annual_rainfall_mm + (slope_decade * (OUTLOOK_YEARS / 10.0))
        proj_score = (0.5 * (trapezoid_score(proj_rf, *rf_trap) or 0.0) + 0.5 * rw_score)
        score_diff = proj_score - score
        outlook = "IMPROVING" if score_diff >= 5.0 else ("WORSENING" if score_diff <= -5.0 else "STABLE")

        trend_block = {
            "direction": active_trend.direction,
            "significant": True,
            "p_value": round(float(active_trend.p_value), 4),
            "sens_slope_per_decade": round(float(slope_decade), 2),
            "projected_value": round(float(proj_rf), 0),
            "score_in_10y": round(float(proj_score), 1),
            "outlook": outlook
        }
    else:
        trend_block = {
            "direction": "no_trend",
            "significant": False,
            "sens_slope_per_decade": 0.0,
            "projected_value": round(float(annual_rainfall_mm), 0),
            "score_in_10y": round(float(score), 1),
            "outlook": "STABLE"
        }

    return FactorReport(
        factor="moisture",
        score=round(score, 1),
        rating=rating,
        values={"annual_rainfall_mm": round(annual_rainfall_mm, 0), "root_wetness": round(root_wetness, 2)},
        ideal={"optimal_rainfall_mm": [rf_trap[1], rf_trap[2]], "optimal_root_wetness": [rw_trap[1], rw_trap[2]]},
        explanation=explanation,
        trend=trend_block,
        components={"rainfall_score": round(rf_score, 1), "root_wetness_score": round(rw_score, 1)},
        sources=["gldas"],
        confidence="high"
    )


def score_soil_ph(
    topsoil_ph: float,
    subsoil_ph: Optional[float] = None,
    ph_trap: Optional[Tuple[float, float, float, float]] = None
) -> FactorReport:
    """Score soil pH factor (static, no trend)."""
    trap = ph_trap or TRAPEZOIDS["soil_ph"]
    sub_ph = subsoil_ph if (subsoil_ph is not None and not math.isnan(subsoil_ph)) else topsoil_ph

    top_score = trapezoid_score(topsoil_ph, *trap) or 0.0
    sub_score = trapezoid_score(sub_ph, *trap) or 0.0

    score = 0.8 * top_score + 0.2 * sub_score
    rating = rating_from_score(score)

    if topsoil_ph < 5.0:
        ph_desc = "strongly acidic"
    elif topsoil_ph < 6.5:
        ph_desc = "moderately acidic"
    elif topsoil_ph <= 7.5:
        ph_desc = "neutral (ideal for most crops)"
    elif topsoil_ph <= 8.5:
        ph_desc = "moderately alkaline / calcareous"
    else:
        ph_desc = "strongly alkaline / sodic"

    explanation = (
        f"Topsoil pH is {topsoil_ph:.1f} ({ph_desc}); subsoil pH is {sub_ph:.1f}. "
        f"Most crops prefer 6.0–7.5 (tolerated {trap[0]:.1f}–{trap[3]:.1f})."
    )

    return FactorReport(
        factor="soil_ph",
        score=round(score, 1),
        rating=rating,
        values={"topsoil_ph": round(topsoil_ph, 2), "subsoil_ph": round(sub_ph, 2)},
        ideal={"optimal_ph_min": trap[1], "optimal_ph_max": trap[2], "tolerated_ph_min": trap[0], "tolerated_ph_max": trap[3]},
        explanation=explanation,
        trend={"direction": "static", "significant": False, "outlook": "STATIC"},
        components={"topsoil_score": round(top_score, 1), "subsoil_score": round(sub_score, 1)},
        sources=["hwsd"],
        confidence="high"
    )


def score_soil_quality(
    organic_carbon_pct: float,
    texture_class: str,
    cec: float,
    drainage_class: str,
    salinity_ece: float,
    sodicity_esp: float,
    gravel_pct: float = 0.0
) -> FactorReport:
    """Score multi-component soil quality (static soil layer)."""
    # 1. Organic carbon score
    oc_trap = TRAPEZOIDS["soil_oc"]
    oc_score = trapezoid_score(organic_carbon_pct, *oc_trap) or 0.0

    # 2. Texture score
    tex_clean = str(texture_class).lower().replace(" ", "_")
    tex_score = TEXTURE_SCORES.get(tex_clean, 70.0)

    # 3. CEC score
    cec_trap = TRAPEZOIDS["soil_cec"]
    cec_score = trapezoid_score(cec, *cec_trap) or 0.0

    # 4. Drainage score
    dr_clean = str(drainage_class).lower().replace(" ", "_")
    dr_score = DRAINAGE_SCORES.get(dr_clean, 75.0)

    # 5. Salinity score (100 at ECe <= 2 dS/m, 0 at >= 16 dS/m)
    if salinity_ece <= 2.0:
        sal_score = 100.0
    elif salinity_ece >= 16.0:
        sal_score = 0.0
    else:
        sal_score = float((16.0 - salinity_ece) / (16.0 - 2.0) * 100.0)

    # 6. Sodicity score (100 at ESP <= 6%, 0 at >= 25%)
    if sodicity_esp <= 6.0:
        sod_score = 100.0
    elif sodicity_esp >= 25.0:
        sod_score = 0.0
    else:
        sod_score = float((25.0 - sodicity_esp) / (25.0 - 6.0) * 100.0)

    # Weighted mean of components
    raw_score = (
        SOIL_QUALITY_WEIGHTS["organic_carbon"] * oc_score +
        SOIL_QUALITY_WEIGHTS["texture"] * tex_score +
        SOIL_QUALITY_WEIGHTS["cec"] * cec_score +
        SOIL_QUALITY_WEIGHTS["drainage"] * dr_score +
        SOIL_QUALITY_WEIGHTS["salinity"] * sal_score +
        SOIL_QUALITY_WEIGHTS["sodicity"] * sod_score
    )

    # Gravel penalty
    gravel_factor = max(0.0, 1.0 - (gravel_pct / 100.0))
    final_score = raw_score * gravel_factor
    rating = rating_from_score(final_score)

    explanation = (
        f"Soil texture is {tex_clean.replace('_', ' ')} with organic carbon {organic_carbon_pct:.2f}%, "
        f"CEC {cec:.1f} cmol/kg, and {dr_clean.replace('_', ' ')} drainage."
    )
    if salinity_ece > 4.0:
        explanation += f" Elevated salinity (ECe {salinity_ece:.1f} dS/m) restricts sensitive crops."
    if sodicity_esp > 15.0:
        explanation += f" Elevated sodicity (ESP {sodicity_esp:.1f}%) impairs soil permeability."

    return FactorReport(
        factor="soil_quality",
        score=round(final_score, 1),
        rating=rating,
        values={
            "organic_carbon_pct": round(organic_carbon_pct, 2),
            "texture": tex_clean,
            "cec_cmol_kg": round(cec, 1),
            "drainage": dr_clean,
            "salinity_ece_ds_m": round(salinity_ece, 2),
            "sodicity_esp_pct": round(sodicity_esp, 1),
            "gravel_pct": round(gravel_pct, 1)
        },
        ideal={
            "organic_carbon_pct": [0.8, 4.0],
            "salinity_ece_max": 2.0,
            "sodicity_esp_max": 6.0
        },
        explanation=explanation,
        trend={"direction": "static", "significant": False, "outlook": "STATIC"},
        components={
            "organic_carbon_score": round(oc_score, 1),
            "texture_score": round(tex_score, 1),
            "cec_score": round(cec_score, 1),
            "drainage_score": round(dr_score, 1),
            "salinity_score": round(sal_score, 1),
            "sodicity_score": round(sod_score, 1),
            "gravel_factor": round(gravel_factor, 2)
        },
        sources=["hwsd"],
        confidence="high"
    )


def score_climate(
    monthly_temps: Dict[int, float],
    monthly_rainfall: Dict[int, float],
    monthly_wetness: Dict[int, float],
    rainfall_cv: float,
    ndvi_percentile: Optional[float] = None
) -> FactorReport:
    """Score multi-component climate and growing season factor."""
    # 1. Growing months count
    growing_months = 0
    thermal_stress_months = 0
    dry_months = 0
    monsoon_rf = 0.0
    total_rf = sum(monthly_rainfall.values())

    for m in range(1, 13):
        t = monthly_temps.get(m, 25.0)
        p = monthly_rainfall.get(m, 50.0)
        w = monthly_wetness.get(m, 0.4)

        if m in [6, 7, 8, 9]:
            monsoon_rf += p

        if p < 30.0:
            dry_months += 1

        if t > 32.0 or t < 5.0:
            thermal_stress_months += 1

        if (10.0 <= t <= 32.0) and (p >= 50.0 or w >= 0.30):
            growing_months += 1

    gm_trap = TRAPEZOIDS["growing_months"]
    gm_score = trapezoid_score(float(growing_months), *gm_trap) or 0.0

    # 2. Rainfall reliability score (100 at CV <= 15%, 0 at >= 40%)
    if rainfall_cv <= 0.15:
        rel_score = 100.0
    elif rainfall_cv >= 0.40:
        rel_score = 0.0
    else:
        rel_score = float((0.40 - rainfall_cv) / (0.40 - 0.15) * 100.0)

    # 3. Thermal stress score (penalty for stressed months)
    thermal_score = max(0.0, float(100.0 - (thermal_stress_months / 12.0 * 100.0)))

    # 4. Vegetation productivity (MODIS NDVI percentile within India)
    if ndvi_percentile is not None and not math.isnan(ndvi_percentile):
        veg_score = float(ndvi_percentile)
        weights = CLIMATE_WEIGHTS
    else:
        # Renormalize weights without vegetation
        veg_score = None
        weights = {
            "growing_months": 0.40,
            "rainfall_reliability": 0.35,
            "thermal_stress": 0.25
        }

    if veg_score is not None:
        score = (
            weights["growing_months"] * gm_score +
            weights["rainfall_reliability"] * rel_score +
            weights["thermal_stress"] * thermal_score +
            weights["vegetation_productivity"] * veg_score
        )
    else:
        score = (
            weights["growing_months"] * gm_score +
            weights["rainfall_reliability"] * rel_score +
            weights["thermal_stress"] * thermal_score
        )

    rating = rating_from_score(score)
    monsoon_pct = (monsoon_rf / total_rf * 100.0) if total_rf > 0 else 0.0

    explanation = (
        f"Favorable crop growing season spans {growing_months} months/year. "
        f"Monsoon rainfall provides {monsoon_pct:.0f}% of annual precipitation with rainfall CV of {rainfall_cv:.2f}."
    )

    return FactorReport(
        factor="climate",
        score=round(score, 1),
        rating=rating,
        values={
            "growing_months": growing_months,
            "rainfall_cv": round(rainfall_cv, 2),
            "thermal_stress_months": thermal_stress_months,
            "dry_months": dry_months,
            "monsoon_share_pct": round(monsoon_pct, 1)
        },
        ideal={"optimal_growing_months": [gm_trap[1], gm_trap[2]], "max_rainfall_cv": 0.15},
        explanation=explanation,
        trend={"direction": "variable", "significant": False, "outlook": "STABLE"},
        components={
            "growing_months_score": round(gm_score, 1),
            "rainfall_reliability_score": round(rel_score, 1),
            "thermal_stress_score": round(thermal_score, 1),
            "vegetation_score": round(veg_score, 1) if veg_score is not None else None
        },
        context={
            "dry_months": dry_months,
            "monsoon_share_pct": round(monsoon_pct, 1)
        },
        sources=["gldas", "modis"] if veg_score is not None else ["gldas"],
        confidence="high"
    )


def compute_overall_assessment(
    factors: Dict[str, FactorReport]
) -> Tuple[float, str, str, List[str], str]:
    """Compute overall weighted land score, POOR factor cap, limiting factors, verdict, and confidence.
    
    Hard Rule: If ANY factor is rated POOR (< 40), the overall rating is capped at MODERATE
    and the score is capped at 69.0.
    
    Returns:
        (overall_score, overall_rating, verdict_text, limiting_factors, confidence)
    """
    total_weight = 0.0
    weighted_sum = 0.0
    has_poor = False
    limiting = []

    for name, w in FACTOR_WEIGHTS.items():
        if name in factors:
            f = factors[name]
            if f.score is not None and not math.isnan(f.score):
                weighted_sum += w * f.score
                total_weight += w
                if f.score < RATING_MODERATE_THRESHOLD:
                    has_poor = True
                    limiting.append(name)
                elif f.score < RATING_GOOD_THRESHOLD:
                    limiting.append(name)

    if total_weight > 0:
        base_score = weighted_sum / total_weight
    else:
        base_score = 0.0

    if has_poor:
        final_score = min(base_score, POOR_SCORE_CAP)
        final_rating = "MODERATE" if final_score >= RATING_MODERATE_THRESHOLD else "POOR"
    else:
        final_score = base_score
        final_rating = rating_from_score(final_score)

    # Verdict construction
    if final_rating == "GOOD":
        verdict = f"Land is well-suited for agriculture with an overall score of {final_score:.1f}/100. Environmental factors support strong productive potential."
    elif final_rating == "MODERATE":
        if has_poor:
            verdict = (
                f"Conditions are generally moderate ({final_score:.1f}/100), but overall capability is constrained "
                f"by a severe limiting factor ({', '.join(limiting)})."
            )
        else:
            verdict = f"Land has moderate suitability ({final_score:.1f}/100). Targeted soil and water management can optimize yields."
    else:
        verdict = f"Land conditions are marginal for rainfed cultivation ({final_score:.1f}/100) due to multiple constraints ({', '.join(limiting)})."

    confidence = "high"
    return round(final_score, 1), final_rating, verdict, limiting, confidence
