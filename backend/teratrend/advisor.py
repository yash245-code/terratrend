"""TeraTrend climate trend adaptation advisor.

Strictly gated by statistical significance (p < ALPHA). Evaluates multi-dataset consensus
and provides evidence-backed adaptation practices.
Pure agronomic logic. Does NOT import Flask or any network library.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import ALPHA, CROPS_DIR
from teratrend.schemas import Advice, ConsensusResult, TrendResult

_CROP_RULES_CACHE: Optional[Dict[str, Any]] = None


def set_crop_rules(rules: Dict[str, Any]) -> None:
    """Explicitly inject crop advisory rules from repository or cache."""
    global _CROP_RULES_CACHE
    _CROP_RULES_CACHE = dict(rules)

DISCLAIMER_TEXT = (
    "TeraTrend decision support is based on ~27 km satellite and reanalysis grid cell averages. "
    "Always combine with a local soil test and district agronomic extension advisory."
)


def load_crop_rules(path: Optional[Path] = None, force_reload: bool = False) -> Dict[str, Any]:
    """Load crop trend advisory rules from JSON."""
    global _CROP_RULES_CACHE
    if not force_reload and _CROP_RULES_CACHE is not None:
        return _CROP_RULES_CACHE

    target_path = path or (CROPS_DIR / "crop_rules.json")
    if not target_path.exists():
        raise FileNotFoundError(f"Crop advisory rules file missing: {target_path}")

    with open(target_path, "r", encoding="utf-8") as f:
        _CROP_RULES_CACHE = json.load(f)

    return _CROP_RULES_CACHE


def advise(
    indicator: str,
    trend_result: Optional[TrendResult],
    consensus: Optional[ConsensusResult] = None,
    vegetation_support: Optional[bool] = None,
    rules_path: Optional[Path] = None,
    rules_data: Optional[Dict[str, Any]] = None,
) -> Advice:
    """Generate trend-based agronomic advisory.
    
    Strict Significance Gate:
    If primary source p >= ALPHA (p >= 0.05) or trend is not significant,
    returns STABLE_BASELINE (maintain established rotations, do not react to noise).
    """
    # Strict gate: if no trend or p >= ALPHA
    if trend_result is None or not trend_result.significant or trend_result.direction == "no_trend":
        return Advice(
            status="STABLE_BASELINE",
            evidence_confidence="high" if (consensus and consensus.consensus_level == "STRONG") else "medium",
            headline="Conditions Stable (No Significant Trend)",
            message=(
                f"Multi-decadal satellite observation of {indicator} shows no statistically significant trend (p = "
                f"{trend_result.p_value:.3f} >= {ALPHA}). Maintain established crop rotations and avoid premature adaptations to short-term noise."
                if trend_result else f"Insufficient multi-year data to establish a trend for {indicator}. Maintain standard crop practices."
            ),
            crops=[],
            avoid=[],
            practices=["Maintain existing crop calendar and soil fertility management."],
            disclaimer=DISCLAIMER_TEXT
        )

    # If significant trend detected
    rules = rules_data if rules_data is not None else load_crop_rules(rules_path)
    rule_key = f"{indicator}_{trend_result.direction}"
    rule_data = rules.get(rule_key, {})

    status_str = "SIGNIFICANT_INCREASE" if trend_result.direction == "increasing" else "SIGNIFICANT_DECREASE"

    # Determine evidence confidence from consensus level
    c_level = consensus.consensus_level if consensus else "SINGLE_SOURCE"
    if c_level == "STRONG":
        evidence_confidence = "high"
    elif c_level in ["MODERATE", "SINGLE_SOURCE"]:
        evidence_confidence = "medium"
    else:  # WEAK or CONFLICTING
        evidence_confidence = "low"

    headline = rule_data.get("headline", f"Significant {indicator.replace('_', ' ').title()} Trend Detected")
    message = rule_data.get("message", f"Observed statistically significant {trend_result.direction} trend over {trend_result.n_years} years.")

    if c_level == "CONFLICTING":
        message += " WARNING: Independent satellite / reanalysis datasets disagree on the trend direction. Verify locally before taking action."

    if vegetation_support is True:
        message += " Independent MODIS satellite vegetation trends confirm declining vegetative productivity, reinforcing this trend advisory."

    crops = list(rule_data.get("crops", []))
    avoid = list(rule_data.get("avoid", []))
    practices = list(rule_data.get("practices", []))

    # Air quality indicators must never produce a crop swap
    if indicator in ["no2", "ozone"]:
        crops = []
        avoid = []
        message += " Note: Air quality context only. Satellite atmospheric indicators do not warrant changes to crop selection."

    return Advice(
        status=status_str,
        evidence_confidence=evidence_confidence,
        headline=headline,
        message=message,
        crops=crops,
        avoid=avoid,
        practices=practices,
        disclaimer=DISCLAIMER_TEXT
    )
