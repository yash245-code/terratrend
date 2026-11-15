"""TeraTrend agricultural industry and production driver factors.

Constructs comprehensive industry intelligence across market, inputs, water (USDA-SCS effective rainfall),
climate risk, policy support, and post-harvest logistics.
Pure logic. Does NOT import Flask or any network library.
"""
import math
from typing import Any, Dict, List, Optional

from config import CLIMATE_WEIGHTS
from teratrend.climatology import SEASON_MONTHS
from teratrend.crops import load_crop_requirements
from teratrend.economics import get_economics_store
from teratrend.schemas import EconomicsReport, IndustryFactors

# Post-harvest loss and perishability guidelines by crop group (ICAR-CIPHET post-harvest study)
GROUP_LOGISTICS = {
    "cereals": {"loss_pct_range": [3.5, 6.0], "perishability": "low", "storage_months": 12},
    "pulses": {"loss_pct_range": [5.0, 8.5], "perishability": "low", "storage_months": 10},
    "oilseeds": {"loss_pct_range": [4.5, 7.0], "perishability": "low", "storage_months": 8},
    "fibre": {"loss_pct_range": [2.5, 4.5], "perishability": "low", "storage_months": 18},
    "commercial": {"loss_pct_range": [8.0, 15.0], "perishability": "moderate", "storage_months": 2},
    "vegetables": {"loss_pct_range": [14.0, 26.0], "perishability": "high", "storage_months": 1}
}


def compute_usda_effective_rainfall(monthly_rainfall: Dict[int, float], season: str = "annual") -> Tuple[float, float]:
    """Compute effective rainfall using USDA-SCS method across season months.
    
    Formula:
      For monthly P <= 250 mm:
        Peff = P * (125.0 - 0.2 * P) / 125.0
      For monthly P > 250 mm:
        Peff = 125.0 + 0.1 * P
    
    Returns:
        (total_season_rainfall_mm, total_effective_rainfall_mm)
    """
    season_months = SEASON_MONTHS.get(season, list(range(1, 13)))
    total_rf = 0.0
    total_peff = 0.0

    for m in season_months:
        p = float(monthly_rainfall.get(m, 0.0))
        total_rf += p
        if p <= 250.0:
            peff = p * (125.0 - 0.2 * p) / 125.0
        else:
            peff = 125.0 + 0.1 * p
        total_peff += max(0.0, peff)

    return total_rf, total_peff


def build_industry_factors(
    crop: str,
    state: str,
    econ_report: EconomicsReport,
    crop_factor_report: Optional[Any] = None,
    climate_stats: Optional[Dict[str, Any]] = None,
    monthly_rainfall: Optional[Dict[int, float]] = None
) -> IndustryFactors:
    """Build structured industry factors block for decision support."""
    _, _, prices, input_reqs, policy_support = get_economics_store()
    crop_reqs = load_crop_requirements()
    crop_spec = crop_reqs.get(crop, {})
    group = crop_spec.get("group", "cereals")

    # 1. MARKET
    mandi_meta = econ_report.price_data.get("as_of", "")
    s_idx = [1.0] * 12
    mandi_dict = prices.get("mandi_modal", {})
    state_key = f"{crop}_{state}"
    nat_key = f"{crop}_IN"
    record = mandi_dict.get(state_key) or mandi_dict.get(nat_key, {})
    if record and "seasonal_index" in record:
        s_idx = record["seasonal_index"]

    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    best_months = [month_names[i] for i, idx_val in enumerate(s_idx) if idx_val > 1.03]

    market_block = {
        "msp_available": econ_report.price_data.get("msp_per_q") is not None,
        "msp_per_q": econ_report.price_data.get("msp_per_q"),
        "mandi_modal_per_q": econ_report.price_data.get("market_modal_per_q"),
        "trailing_mandi_yoy_change_pct": record.get("yoy_change_pct"),
        "mandi_volatility_cv": record.get("volatility_cv"),
        "best_selling_months": best_months or ["Post-harvest peak"],
        "seasonal_price_index": s_idx
    }

    # 2. INPUTS
    inp = input_reqs.get(crop, {})
    cost_comps = econ_report.costs_data.get("components", {})
    total_cost = sum(cost_comps.values()) if cost_comps else 1.0

    human_labour = cost_comps.get("human_labour_hired", 0.0) + cost_comps.get("human_labour_family", 0.0)
    machine_labour = cost_comps.get("bullock_machine_labour", 0.0)
    fertilizer = cost_comps.get("fertilizer_manure", 0.0)
    seed_cost = cost_comps.get("seed", 0.0)
    irrigation_cost = cost_comps.get("irrigation", 0.0)

    inputs_block = {
        "seed_rate_kg_ha": inp.get("seed_rate_kg_ha"),
        "recommended_npk_kg_ha": inp.get("npk_kg_ha", [100, 50, 50]),
        "labour_man_days_ha": inp.get("labour_man_days_ha"),
        "plant_protection_sprays_count": inp.get("plant_protection_sprays", 2),
        "cost_shares_pct": {
            "human_labour": round(human_labour / total_cost * 100.0, 1),
            "machinery": round(machine_labour / total_cost * 100.0, 1),
            "fertilizer_and_manure": round(fertilizer / total_cost * 100.0, 1),
            "seed": round(seed_cost / total_cost * 100.0, 1),
            "irrigation": round(irrigation_cost / total_cost * 100.0, 1)
        }
    }

    # 3. WATER & IRRIGATION GAP
    eval_season = crop_spec.get("seasons", ["kharif"])[0]
    water_req_mm = float(inp.get("season_water_requirement_mm", 500.0))
    m_rf = monthly_rainfall or {m: 60.0 for m in range(1, 13)}

    total_season_rf, peff_mm = compute_usda_effective_rainfall(m_rf, season=eval_season)
    irrigation_gap_mm = max(0.0, water_req_mm - peff_mm)
    # Typical irrigation depth per event is 60 mm
    suggested_irrigations = int(math.ceil(irrigation_gap_mm / 60.0)) if irrigation_gap_mm > 0 else 0

    water_block = {
        "season_water_requirement_mm": water_req_mm,
        "effective_rainfall_usda_scs_mm": round(peff_mm, 1),
        "total_season_rainfall_mm": round(total_season_rf, 1),
        "irrigation_gap_mm": round(irrigation_gap_mm, 1),
        "suggested_irrigation_events": suggested_irrigations,
        "water_demand_tier": crop_spec.get("water_demand", "medium")
    }

    # 4. CLIMATE RISK
    c_stats = climate_stats or {}
    limiting_fac = getattr(crop_factor_report, "limiting_factor", "moisture") if crop_factor_report else "moisture"
    outlook_str = "STABLE"
    if crop_factor_report and hasattr(crop_factor_report, "trend") and crop_factor_report.trend:
        outlook_str = crop_factor_report.trend.get("outlook", "STABLE")

    climate_risk_block = {
        "rainfall_cv": c_stats.get("rainfall_cv", 0.20),
        "drought_frequency_pct": c_stats.get("drought_frequency_pct", 15.0),
        "wet_frequency_pct": c_stats.get("wet_frequency_pct", 10.0),
        "thermal_stress_months": c_stats.get("thermal_stress_months", 2),
        "primary_limiting_factor": limiting_fac,
        "10y_trend_outlook": outlook_str
    }

    # 5. POLICY SUPPORT
    pmfby_info = policy_support.get("pmfby", {})
    farmer_rates = pmfby_info.get("farmer_premium_rates", {})

    if group in ["cereals", "pulses", "oilseeds"]:
        rate_pct = farmer_rates.get("rabi_food_and_oilseeds_pct", 1.5) if eval_season == "rabi" else farmer_rates.get("kharif_food_and_oilseeds_pct", 2.0)
    else:
        rate_pct = farmer_rates.get("annual_commercial_and_horticultural_pct", 5.0)

    policy_block = {
        "pmfby_scheme": {
            "applicable_premium_rate_pct": rate_pct,
            "sum_insured_note": pmfby_info.get("sum_insured_note"),
            "as_of": pmfby_info.get("as_of"),
            "verify_before_use": True
        },
        "kcc_credit": policy_support.get("kcc", {}),
        "pm_kisan": policy_support.get("pm_kisan", {}),
        "msp_procurement": policy_support.get("msp_procurement", {}),
        "input_subsidies": policy_support.get("input_subsidies", {})
    }

    # 6. LOGISTICS
    logistics_meta = GROUP_LOGISTICS.get(group, GROUP_LOGISTICS["cereals"])
    logistics_block = {
        "crop_group": group,
        "typical_post_harvest_loss_pct": logistics_meta["loss_pct_range"],
        "perishability_tier": logistics_meta["perishability"],
        "ambient_storage_potential_months": logistics_meta["storage_months"],
        "source": "ICAR-CIPHET National Post-Harvest Loss Assessment",
        "verified": True
    }

    return IndustryFactors(
        market=market_block,
        inputs=inputs_block,
        water=water_block,
        climate_risk=climate_risk_block,
        policy_support=policy_block,
        logistics=logistics_block
    )
