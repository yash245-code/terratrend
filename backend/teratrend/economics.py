"""TeraTrend agricultural economics engine.

Calculates CACP cost concepts (A2, A2+FL, C2), expected yields via suitability curves,
revenues on MSP & market bases, ROI, break-even metrics, deterministic Monte Carlo risk,
sensitivity analysis, and balanced crop selection.
Pure economic logic. Does NOT import Flask or any network library.
"""
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np

from config import (
    DEFAULT_COST_BASIS, DEFAULT_COST_CV, DEFAULT_PRICE_BASIS, DEFAULT_PRICE_CV,
    ECONOMICS_DIR, MC_DRAWS, PRICE_CV_BY_GROUP, YIELD_FACTOR_CURVE,
    YIELD_PRICE_CORRELATION
)
from teratrend.crops import load_crop_requirements
from teratrend.schemas import EconomicsReport

# In-memory economics database cache
_CROP_COSTS: Optional[List[Dict[str, Any]]] = None
_BENCHMARK_YIELDS: Optional[List[Dict[str, Any]]] = None
_PRICES: Optional[Dict[str, Any]] = None
_INPUT_REQS: Optional[Dict[str, Any]] = None
_POLICY_SUPPORT: Optional[Dict[str, Any]] = None

ECONOMICS_DISCLAIMER = (
    "Indicative economic estimates for farm planning, not financial advice. "
    "Actual net returns depend on local input costs, realized yields, market volatility, and government procurement. "
    "Check official DA&FW and Agmarknet notifications for latest rates."
)


def load_data(economics_dir: Optional[Path] = None, force_reload: bool = False) -> None:
    """Load and cache all official economics JSON files."""
    global _CROP_COSTS, _BENCHMARK_YIELDS, _PRICES, _INPUT_REQS, _POLICY_SUPPORT
    if not force_reload and _CROP_COSTS is not None:
        return

    edir = economics_dir or ECONOMICS_DIR

    with open(edir / "crop_costs.json", "r", encoding="utf-8") as f:
        _CROP_COSTS = json.load(f)

    with open(edir / "benchmark_yields.json", "r", encoding="utf-8") as f:
        _BENCHMARK_YIELDS = json.load(f)

    with open(edir / "prices.json", "r", encoding="utf-8") as f:
        _PRICES = json.load(f)

    with open(edir / "input_requirements.json", "r", encoding="utf-8") as f:
        _INPUT_REQS = json.load(f)

    with open(edir / "policy_support.json", "r", encoding="utf-8") as f:
        _POLICY_SUPPORT = json.load(f)


def set_economics_store(
    crop_costs: Optional[List[Dict[str, Any]]] = None,
    benchmark_yields: Optional[List[Dict[str, Any]]] = None,
    prices: Optional[Dict[str, Any]] = None,
    input_reqs: Optional[Dict[str, Any]] = None,
    policy_support: Optional[Dict[str, Any]] = None,
) -> None:
    """Explicitly inject in-memory economics reference data from database or repository."""
    global _CROP_COSTS, _BENCHMARK_YIELDS, _PRICES, _INPUT_REQS, _POLICY_SUPPORT
    if crop_costs is not None:
        _CROP_COSTS = crop_costs
    if benchmark_yields is not None:
        _BENCHMARK_YIELDS = benchmark_yields
    if prices is not None:
        _PRICES = prices
    if input_reqs is not None:
        _INPUT_REQS = input_reqs
    if policy_support is not None:
        _POLICY_SUPPORT = policy_support


def get_economics_store() -> Tuple[List[Dict], List[Dict], Dict, Dict, Dict]:
    """Return cached economics datasets."""
    load_data()
    assert _CROP_COSTS is not None
    assert _BENCHMARK_YIELDS is not None
    assert _PRICES is not None
    assert _INPUT_REQS is not None
    assert _POLICY_SUPPORT is not None
    return _CROP_COSTS, _BENCHMARK_YIELDS, _PRICES, _INPUT_REQS, _POLICY_SUPPORT


def interpolate_yield_factor(suitability_score: float) -> float:
    """Interpolate expected yield multiplier from crop suitability score.
    
    Piecewise linear:
      0   -> 0.40
      40  -> 0.75
      70  -> 1.00
      100 -> 1.20
    """
    score = max(0.0, min(100.0, float(suitability_score)))
    anchors = sorted(YIELD_FACTOR_CURVE.items(), key=lambda x: x[0])

    for i in range(len(anchors) - 1):
        x0, y0 = anchors[i]
        x1, y1 = anchors[i + 1]
        if x0 <= score <= x1:
            ratio = (score - x0) / (x1 - x0)
            return float(y0 + ratio * (y1 - y0))

    return 1.0


def find_benchmark_yield(crop: str, state: str, district: Optional[str] = None) -> Tuple[Optional[float], str, str]:
    """Find benchmark yield with fallback hierarchy: district -> state -> national (IN).
    
    Returns:
        (benchmark_yield_q_ha, benchmark_level, reference_period)
    """
    costs, yields, _, _, _ = get_economics_store()

    # 1. District match
    if district:
        for r in yields:
            if r["crop"] == crop and r.get("state") == state and r.get("district") == district:
                return float(r["benchmark_yield_q_ha"]), "district", r.get("reference_period", "")

    # 2. State match
    for r in yields:
        if r["crop"] == crop and r.get("state") == state and r.get("district") is None:
            return float(r["benchmark_yield_q_ha"]), "state", r.get("reference_period", "")

    # 3. National match (IN)
    for r in yields:
        if r["crop"] == crop and r.get("state") == "IN":
            return float(r["benchmark_yield_q_ha"]), "national", r.get("reference_period", "")

    return None, "none", ""


def find_crop_cost(crop: str, state: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """Find crop cost record with fallback hierarchy: state -> national (IN).
    
    Returns:
        (cost_record, cost_level)
    """
    costs, _, _, _, _ = get_economics_store()

    # 1. State match
    for r in costs:
        if r["crop"] == crop and r.get("state") == state:
            return r, "state"

    # 2. National match (IN)
    for r in costs:
        if r["crop"] == crop and r.get("state") == "IN":
            return r, "national"

    return None, "none"


def find_prices(crop: str, state: str) -> Tuple[Optional[float], Optional[float], Dict[str, Any], str]:
    """Retrieve MSP and market mandi modal price.
    
    Returns:
        (msp_per_q, market_modal_per_q, mandi_meta, price_level)
    """
    _, _, prices, _, _ = get_economics_store()

    # MSP
    msp_record = prices.get("msp", {}).get(crop, {})
    msp_val = msp_record.get("msp_per_q")

    # Mandi modal price
    mandi_dict = prices.get("mandi_modal", {})
    state_key = f"{crop}_{state}"
    nat_key = f"{crop}_IN"

    if state_key in mandi_dict:
        mandi_meta = mandi_dict[state_key]
        return msp_val, float(mandi_meta["modal_price_per_q"]), mandi_meta, "state"
    elif nat_key in mandi_dict:
        mandi_meta = mandi_dict[nat_key]
        return msp_val, float(mandi_meta["modal_price_per_q"]), mandi_meta, "national"
    else:
        # If crop has MSP but no mandi record, use MSP as market price
        if msp_val is not None:
            return msp_val, float(msp_val), {}, "msp_proxy"
        return None, None, {}, "none"


def run_monte_carlo_risk(
    expected_yield: float,
    yield_cv: float,
    chosen_price: float,
    price_cv: float,
    chosen_cost: float,
    cost_cv: float = DEFAULT_COST_CV,
    n_draws: int = MC_DRAWS,
    seed_key: int = 42
) -> Tuple[float, float, float, float, Dict[str, Any]]:
    """Run deterministic vectorised Monte Carlo simulation with correlated lognormal draws.
    
    Returns:
        (prob_loss_pct, p10_net, p50_net, p90_net, assumptions_dict)
    """
    rng = np.random.default_rng(seed_key)

    # Correlated bivariate standard normal draws for (yield, price)
    # Covariance matrix with correlation rho = -0.20
    cov = [[1.0, YIELD_PRICE_CORRELATION], [YIELD_PRICE_CORRELATION, 1.0]]
    mvn_draws = rng.multivariate_normal([0.0, 0.0], cov, size=n_draws)
    z_yield = mvn_draws[:, 0]
    z_price = mvn_draws[:, 1]

    # Convert normal to lognormal:
    # sigma_ln^2 = ln(1 + CV^2), mu_ln = ln(mean) - 0.5 * sigma_ln^2
    y_sigma_sq = math.log(1.0 + yield_cv ** 2)
    y_sigma = math.sqrt(y_sigma_sq)
    y_mu = math.log(max(expected_yield, 0.1)) - 0.5 * y_sigma_sq
    yield_draws = np.exp(y_mu + y_sigma * z_yield)

    p_sigma_sq = math.log(1.0 + price_cv ** 2)
    p_sigma = math.sqrt(p_sigma_sq)
    p_mu = math.log(max(chosen_price, 10.0)) - 0.5 * p_sigma_sq
    price_draws = np.exp(p_mu + p_sigma * z_price)

    # Cost noise (uncorrelated lognormal)
    c_sigma_sq = math.log(1.0 + cost_cv ** 2)
    c_sigma = math.sqrt(c_sigma_sq)
    c_mu = math.log(max(chosen_cost, 100.0)) - 0.5 * c_sigma_sq
    z_cost = rng.standard_normal(n_draws)
    cost_draws = np.exp(c_mu + c_sigma * z_cost)

    revenue_draws = yield_draws * price_draws
    net_draws = revenue_draws - cost_draws

    losses = net_draws < 0.0
    prob_loss_pct = float(np.mean(losses) * 100.0)

    p10_net = float(np.percentile(net_draws, 10))
    p50_net = float(np.percentile(net_draws, 50))
    p90_net = float(np.percentile(net_draws, 90))

    assumptions = {
        "draws_count": n_draws,
        "yield_distribution": "lognormal",
        "yield_cv": round(yield_cv, 3),
        "price_distribution": "lognormal",
        "price_cv": round(price_cv, 3),
        "yield_price_correlation": YIELD_PRICE_CORRELATION,
        "cost_cv": round(cost_cv, 3)
    }

    return prob_loss_pct, p10_net, p50_net, p90_net, assumptions


def compute_economics(
    crop: str,
    region: Any,
    suitability_now: float,
    suitability_10y: Optional[float] = None,
    climate_stats: Optional[Dict[str, Any]] = None,
    options: Optional[Dict[str, Any]] = None
) -> EconomicsReport:
    """Compute enterprise-level production economics report for a specific crop and location."""
    load_data()
    opts = options or {}

    area_ha = float(opts.get("area_ha", 1.0))
    tenure = str(opts.get("tenure", "owned")).lower()
    cost_basis = str(opts.get("cost_basis", DEFAULT_COST_BASIS)).lower()
    price_basis = str(opts.get("price_basis", DEFAULT_PRICE_BASIS)).lower()
    cost_multiplier = float(opts.get("cost_multiplier", 1.0))

    state_name = getattr(region, "state", "IN")
    district_name = getattr(region, "district", None)

    warnings: List[str] = []

    # 1. Fetch benchmark yield
    bench_q_ha, bench_lvl, ref_period = find_benchmark_yield(crop, state_name, district_name)
    if bench_q_ha is None:
        return EconomicsReport(
            available=False,
            crop=crop,
            reason=f"No official benchmark yield found for crop '{crop}' in state '{state_name}' or nationally.",
            disclaimer=ECONOMICS_DISCLAIMER
        )

    if bench_lvl == "national" and state_name != "IN":
        warnings.append(f"State-specific yield unavailable for {state_name}; using All-India benchmark yield.")

    # Apply user override for yield if supplied
    user_yield_override = opts.get("yield_override_q_ha")
    if user_yield_override is not None:
        expected_yield = float(user_yield_override)
        y_factor = expected_yield / bench_q_ha if bench_q_ha > 0 else 1.0
        warnings.append(f"User overridden expected yield: {expected_yield:.1f} quintals/ha.")
    else:
        y_factor = interpolate_yield_factor(suitability_now)
        expected_yield = bench_q_ha * y_factor

    # 10-year projected yield
    if suitability_10y is not None:
        y_factor_10y = interpolate_yield_factor(suitability_10y)
        expected_yield_10y = bench_q_ha * y_factor_10y
    else:
        expected_yield_10y = expected_yield

    # 2. Fetch prices (MSP & Market Modal)
    msp_val, market_val, mandi_meta, price_lvl = find_prices(crop, state_name)
    if msp_val is None and market_val is None:
        return EconomicsReport(
            available=False,
            crop=crop,
            reason=f"No official price data (MSP or Mandi) found for crop '{crop}'.",
            disclaimer=ECONOMICS_DISCLAIMER
        )

    # User price override
    user_price_override = opts.get("price_override_per_q")
    if user_price_override is not None:
        chosen_price = float(user_price_override)
        warnings.append(f"User overridden price: Rs {chosen_price:.1f}/quintal.")
    else:
        if price_basis == "msp" and msp_val is not None:
            chosen_price = float(msp_val)
        elif market_val is not None:
            chosen_price = float(market_val)
        elif msp_val is not None:
            chosen_price = float(msp_val)
            warnings.append("Market price unavailable; falling back to MSP.")
        else:
            chosen_price = 0.0

    # 3. Fetch costs
    cost_rec, cost_lvl = find_crop_cost(crop, state_name)
    if cost_rec is None:
        return EconomicsReport(
            available=False,
            crop=crop,
            reason=f"No official cost of cultivation record found for crop '{crop}'.",
            disclaimer=ECONOMICS_DISCLAIMER
        )

    if cost_lvl == "national" and state_name != "IN":
        warnings.append(f"State-specific cost of cultivation unavailable for {state_name}; using All-India average.")

    raw_components = dict(cost_rec.get("components", {}))
    # Apply cost multiplier
    components = {k: v * cost_multiplier for k, v in raw_components.items()}

    a2_cost = float(cost_rec.get("a2", 30000.0)) * cost_multiplier
    a2_fl_cost = float(cost_rec.get("a2_fl", 35000.0)) * cost_multiplier
    c2_cost = float(cost_rec.get("c2", 55000.0)) * cost_multiplier

    # Tenure adjustment:
    # Owned: imputed rent and fixed capital count only in C2.
    # Leased: rent paid is actual out-of-pocket in A2/A2+FL.
    if tenure == "leased":
        # Add leased land rent to A2 and A2+FL if not already included
        rent_paid = components.get("rent_paid_leased_land", 3000.0)
        # In standard CACP A2, rent_paid_leased_land is included in paid-out costs.
    else:
        # Owned land: rental value of owned land is in C2 only
        pass

    chosen_cost = a2_fl_cost if cost_basis == "a2_fl" else c2_cost

    # 4. Revenue calculation
    gross_rev_msp = (expected_yield * msp_val) if msp_val is not None else None
    gross_rev_market = (expected_yield * market_val) if market_val is not None else None
    gross_revenue = expected_yield * chosen_price

    # 5. Profit & Return metrics
    net_return_a2_fl = gross_revenue - a2_fl_cost
    net_return_c2 = gross_revenue - c2_cost
    chosen_net_return = gross_revenue - chosen_cost

    roi_a2_fl = (net_return_a2_fl / a2_fl_cost * 100.0) if a2_fl_cost > 0 else 0.0
    roi_c2 = (net_return_c2 / c2_cost * 100.0) if c2_cost > 0 else 0.0
    chosen_roi = (chosen_net_return / chosen_cost * 100.0) if chosen_cost > 0 else 0.0

    bcr = (gross_revenue / chosen_cost) if chosen_cost > 0 else 0.0
    be_yield = (chosen_cost / chosen_price) if chosen_price > 0 else 0.0
    be_price = (chosen_cost / expected_yield) if expected_yield > 0 else 0.0

    margin_of_safety_pct = ((expected_yield - be_yield) / expected_yield * 100.0) if expected_yield > 0 else 0.0

    # Net return per day
    crop_reqs = load_crop_requirements()
    cycle_days = crop_reqs.get(crop, {}).get("cycle_days", 120)
    net_return_per_day = chosen_net_return / cycle_days if cycle_days > 0 else 0.0

    # 10-year projected ROI
    gross_rev_10y = expected_yield_10y * chosen_price
    net_10y = gross_rev_10y - chosen_cost
    roi_10y = (net_10y / chosen_cost * 100.0) if chosen_cost > 0 else 0.0

    # 6. Monte Carlo Risk
    rf_cv = (climate_stats or {}).get("rainfall_cv", 0.20)
    crop_base_cv = crop_reqs.get(crop, {}).get("base_yield_cv", 0.18)
    yield_cv = float(np.clip(crop_base_cv + 0.4 * (rf_cv - 0.15) + 0.15 * (1.0 - suitability_now / 100.0), 0.08, 0.50))

    group = crop_reqs.get(crop, {}).get("group", "cereals")
    price_cv = float(mandi_meta.get("volatility_cv", PRICE_CV_BY_GROUP.get(group, DEFAULT_PRICE_CV)))

    # Deterministic seed based on input hash
    seed_int = abs(hash(f"{crop}_{state_name}_{expected_yield:.2f}_{chosen_price:.2f}_{chosen_cost:.2f}")) % (2**31 - 1)
    prob_loss_pct, p10_net, p50_net, p90_net, mc_assumptions = run_monte_carlo_risk(
        expected_yield=expected_yield,
        yield_cv=yield_cv,
        chosen_price=chosen_price,
        price_cv=price_cv,
        chosen_cost=chosen_cost,
        seed_key=seed_int
    )

    # 7. Sensitivity analysis (tornado: yield, price, cost +/- 10%)
    sensitivity_list = []
    for driver, d_label in [("price", "Market Price"), ("yield", "Expected Yield"), ("cost", "Cultivation Cost")]:
        for delta in [-10, 10]:
            factor = 1.0 + delta / 100.0
            if driver == "price":
                s_rev = expected_yield * (chosen_price * factor)
                s_cost = chosen_cost
            elif driver == "yield":
                s_rev = (expected_yield * factor) * chosen_price
                s_cost = chosen_cost
            else:  # cost
                s_rev = gross_revenue
                s_cost = chosen_cost * factor

            s_net = s_rev - s_cost
            s_roi = (s_net / s_cost * 100.0) if s_cost > 0 else 0.0
            sensitivity_list.append({
                "driver": driver,
                "label": d_label,
                "change_pct": delta,
                "roi_pct": round(s_roi, 1),
                "net_return_per_ha": round(s_net, 0)
            })

    # 8. Verdict determination
    # Thresholds: PROFITABLE (net > 0, ROI >= 20% and P(loss) <= 25%), MARGINAL (net > 0 otherwise), LOSS_MAKING (net <= 0)
    if chosen_net_return > 0 and chosen_roi >= 20.0 and prob_loss_pct <= 25.0:
        verdict_label = "PROFITABLE"
        verdict_text = f"Enterprise is economically viable with projected {chosen_roi:.1f}% ROI and low loss risk ({prob_loss_pct:.1f}%)."
    elif chosen_net_return > 0:
        verdict_label = "MARGINAL"
        dominant_risk = "market price volatility" if price_cv > 0.20 else ("yield risk" if yield_cv > 0.25 else "narrow margin")
        verdict_text = f"Enterprise generates positive returns ({chosen_roi:.1f}% ROI), but carries moderate financial risk dominated by {dominant_risk}."
    else:
        verdict_label = "LOSS_MAKING"
        verdict_text = f"Enterprise is projected to incur negative returns (net return -Rs {abs(chosen_net_return):.0f}/ha). Cultivation not financially viable under current assumptions."

    return EconomicsReport(
        available=True,
        crop=crop,
        currency="INR",
        area_ha=area_ha,
        tenure=tenure,
        cost_basis=cost_basis,
        price_basis=price_basis,
        yield_data={
            "benchmark_q_ha": round(bench_q_ha, 1),
            "benchmark_level": bench_lvl,
            "yield_factor": round(y_factor, 2),
            "expected_q_ha": round(expected_yield, 1),
            "expected_q_ha_in_10y": round(expected_yield_10y, 1),
            "reference_period": ref_period
        },
        price_data={
            "msp_per_q": round(msp_val, 1) if msp_val is not None else None,
            "market_modal_per_q": round(market_val, 1) if market_val is not None else None,
            "chosen_price_per_q": round(chosen_price, 1),
            "price_level": price_lvl,
            "as_of": mandi_meta.get("as_of", "2024-06")
        },
        costs_data={
            "a2_fl_per_ha": round(a2_fl_cost, 0),
            "c2_per_ha": round(c2_cost, 0),
            "chosen_cost_per_ha": round(chosen_cost, 0),
            "components": {k: round(v, 0) for k, v in components.items()},
            "level": cost_lvl,
            "reference_year": cost_rec.get("reference_year", "")
        },
        returns_data={
            "gross_revenue_per_ha": {
                "msp": round(gross_rev_msp, 2) if gross_rev_msp is not None else None,
                "market": round(gross_rev_market, 2) if gross_rev_market is not None else None,
                "chosen": round(gross_revenue, 2)
            },
            "net_return_per_ha": {
                "a2_fl": round(net_return_a2_fl, 2),
                "c2": round(net_return_c2, 2),
                "chosen": round(chosen_net_return, 2)
            },
            "roi_pct": {
                "a2_fl": round(roi_a2_fl, 1),
                "c2": round(roi_c2, 1),
                "chosen": round(chosen_roi, 1)
            },
            "benefit_cost_ratio": round(bcr, 2),
            "break_even_yield_q_ha": round(be_yield, 1),
            "break_even_price_per_q": round(be_price, 1),
            "margin_of_safety_pct": round(margin_of_safety_pct, 1),
            "net_return_per_day": round(net_return_per_day, 1),
            "roi_pct_in_10y": round(roi_10y, 1)
        },
        totals_for_area={
            "area_ha": area_ha,
            "total_production_quintals": round(expected_yield * area_ha, 1),
            "total_gross_revenue_inr": round(gross_revenue * area_ha, 0),
            "total_cost_inr": round(chosen_cost * area_ha, 0),
            "total_net_return_inr": round(chosen_net_return * area_ha, 0)
        },
        risk_data={
            "probability_of_loss_pct": round(prob_loss_pct, 1),
            "net_return_p10": round(p10_net, 0),
            "net_return_p50": round(p50_net, 0),
            "net_return_p90": round(p90_net, 0),
            "assumptions": mc_assumptions
        },
        sensitivity_data=sensitivity_list,
        verdict={"label": verdict_label, "text": verdict_text},
        data_quality={
            "benchmark_level": bench_lvl,
            "cost_level": cost_lvl,
            "price_level": price_lvl,
            "cost_reference_year": cost_rec.get("reference_year", ""),
            "price_as_of": mandi_meta.get("as_of", "2024-06")
        },
        warnings=warnings,
        disclaimer=ECONOMICS_DISCLAIMER
    )


def rank_by_economics(crop_reports: List[EconomicsReport]) -> List[EconomicsReport]:
    """Sort available crop economics reports descending by net return."""
    valid = [r for r in crop_reports if r.available]
    valid.sort(key=lambda r: r.returns_data.get("net_return_per_ha", {}).get("chosen", 0.0), reverse=True)
    return valid


def select_balanced_crop(
    scored_crops: List[Any],
    econ_reports: Dict[str, EconomicsReport]
) -> Optional[Dict[str, Any]]:
    """Select the balanced pick: highest suitability crop with positive ROI and P(loss) < 30%."""
    for cs in scored_crops:
        ck = cs.key
        if ck in econ_reports:
            er = econ_reports[ck]
            if er.available:
                roi = er.returns_data.get("roi_pct", {}).get("chosen", 0.0)
                p_loss = er.risk_data.get("probability_of_loss_pct", 100.0)
                if roi > 0.0 and p_loss < 30.0:
                    return {
                        "crop": ck,
                        "name": cs.name,
                        "suitability_score": cs.score,
                        "roi_pct": roi,
                        "probability_of_loss_pct": p_loss,
                        "net_return_per_ha": er.returns_data.get("net_return_per_ha", {}).get("chosen", 0.0),
                        "reason": f"Optimal balance of agronomic fit ({cs.score:.0f}/100) and economic resilience ({roi:.1f}% ROI, {p_loss:.1f}% loss risk)."
                    }
    return None
