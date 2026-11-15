"""TerraTrend Database Exporter.

Exports database records back to JSON format matching the exact structure of data/seed/ files.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import Config
from db.models.economics import (
    BenchmarkYield,
    CropCost,
    InputRequirement,
    MandiPrice,
    Msp,
    PolicyScheme,
)
from db.models.reference import (
    AmendmentRule,
    Crop,
    CropRequirement,
    CropSoilPreference,
    State,
    TrendRule,
)


def export_database(session: Session, to_dir: Optional[Path] = None) -> Dict[str, int]:
    """Export database reference and economics tables to JSON files."""
    out_dir = to_dir or Config.DATA_DIR / "seed"
    crops_dir = out_dir / "crops"
    rules_dir = out_dir / "rules"
    econ_dir = out_dir / "economics"

    crops_dir.mkdir(parents=True, exist_ok=True)
    rules_dir.mkdir(parents=True, exist_ok=True)
    econ_dir.mkdir(parents=True, exist_ok=True)

    counts = {}

    # 1. Export Crops
    crops = session.scalars(select(Crop).order_by(Crop.key)).all()
    crops_dict = {}
    for c in crops:
        temp_trap = [0.0, 0.0, 0.0, 0.0]
        rain_trap = [0.0, 0.0, 0.0, 0.0]
        ph_trap = [0.0, 0.0, 0.0, 0.0]

        for req in c.requirements:
            t = [req.abs_min, req.opt_min, req.opt_max, req.abs_max]
            if req.factor == "temperature":
                temp_trap = t
            elif req.factor == "rainfall":
                rain_trap = t
            elif req.factor == "ph":
                ph_trap = t

        pref_tex = [sp.class_name for sp in c.soil_preferences if sp.kind == "texture" and sp.level == "preferred"]
        tol_tex = [sp.class_name for sp in c.soil_preferences if sp.kind == "texture" and sp.level == "tolerated"]
        pref_drn = [sp.class_name for sp in c.soil_preferences if sp.kind == "drainage" and sp.level == "preferred"]

        crops_dict[c.key] = {
            "key": c.key,
            "name": c.name,
            "local_name": c.local_name,
            "group": c.group,
            "seasons": list(c.seasons or []),
            "cycle_days": c.cycle_days,
            "temperature_trapezoid": temp_trap,
            "rainfall_trapezoid": rain_trap,
            "ph_trapezoid": ph_trap,
            "preferred_textures": pref_tex,
            "tolerated_textures": tol_tex,
            "preferred_drainage": pref_drn,
            "salinity_tolerance_ece": c.salinity_ece_max,
            "water_demand": c.water_demand,
            "base_yield_cv": c.base_yield_cv,
            "notes": c.notes,
            "source": c.source,
            "verification_status": c.verification_status,
        }

    with open(crops_dir / "crop_requirements.json", "w", encoding="utf-8") as f:
        json.dump(crops_dict, f, indent=2)
    counts["crops"] = len(crops_dict)

    # 2. Export Amendments
    amendments = session.scalars(select(AmendmentRule).order_by(AmendmentRule.id)).all()
    amend_list = []
    for a in amendments:
        amend_list.append({
            "key": a.key,
            "factor": a.factor,
            "issue": a.issue,
            "condition": {
                "field": f"{a.factor}_val",
                "op": "<" if a.operator == "lt" else (">" if a.operator == "gt" else a.operator),
                "val": a.threshold_low,
                "val2": a.threshold_high,
            },
            "actions": list(a.actions or []),
            "note": a.note,
        })

    with open(rules_dir / "amendments.json", "w", encoding="utf-8") as f:
        json.dump(amend_list, f, indent=2)
    counts["amendments"] = len(amend_list)

    # 3. Export Trend Rules
    trend_rules = session.scalars(select(TrendRule).order_by(TrendRule.id)).all()
    trend_dict = {}
    for tr in trend_rules:
        k = f"{tr.indicator}_{tr.direction}"
        trend_dict[k] = {
            "headline": f"{tr.indicator.replace('_', ' ').title()} {tr.direction.title()} Detected",
            "message": tr.confidence_note or "",
            "crops": list(tr.crops or []),
            "avoid": list(tr.avoid or []),
            "practices": list(tr.practices or []),
        }

    with open(crops_dir / "crop_rules.json", "w", encoding="utf-8") as f:
        json.dump(trend_dict, f, indent=2)
    counts["trend_rules"] = len(trend_dict)

    # 4. Export Economics: Crop Costs
    crops_lookup = {c.id: c.key for c in crops}
    states_lookup = {s.id: s.name for s in session.scalars(select(State)).all()}

    cost_rows = session.scalars(select(CropCost)).all()
    costs_list = []
    for c in cost_rows:
        costs_list.append({
            "crop": crops_lookup.get(c.crop_id, ""),
            "state": states_lookup.get(c.state_id, "IN") if c.state_id else "IN",
            "a2": c.cost_a2,
            "a2_fl": c.cost_a2_fl,
            "c2": c.cost_c2,
            "reference_year": c.reference_year,
            "components": dict(c.components or {}),
            "source": c.source,
            "source_url": c.source_url,
            "verification_status": c.verification_status,
        })

    with open(econ_dir / "crop_costs.json", "w", encoding="utf-8") as f:
        json.dump(costs_list, f, indent=2)
    counts["crop_costs"] = len(costs_list)

    # 5. Benchmark Yields
    yield_rows = session.scalars(select(BenchmarkYield)).all()
    yields_list = []
    for y in yield_rows:
        yields_list.append({
            "crop": crops_lookup.get(y.crop_id, ""),
            "state": states_lookup.get(y.state_id, "IN") if y.state_id else "IN",
            "district": None,
            "benchmark_yield_q_ha": y.yield_q_ha,
            "reference_period": f"{y.period_start}-{y.period_end}",
            "source": y.source,
            "source_url": y.source_url,
            "verification_status": y.verification_status,
        })

    with open(econ_dir / "benchmark_yields.json", "w", encoding="utf-8") as f:
        json.dump(yields_list, f, indent=2)
    counts["benchmark_yields"] = len(yields_list)

    # 6. Prices (MSP and Mandi)
    msp_dict = {}
    for m in session.scalars(select(Msp)).all():
        crop_k = crops_lookup.get(m.crop_id, "")
        msp_dict[crop_k] = {
            "crop": crop_k,
            "msp_per_q": m.msp_per_q,
            "marketing_season": m.marketing_year,
            "source": m.source,
            "source_url": m.source_url,
            "verification_status": m.verification_status,
        }

    mandi_dict = {}
    for mp in session.scalars(select(MandiPrice)).all():
        crop_k = crops_lookup.get(mp.crop_id, "")
        st_name = states_lookup.get(mp.state_id, "IN")
        item_k = f"{crop_k}_{st_name}"
        mandi_dict[item_k] = {
            "crop": crop_k,
            "state": st_name,
            "modal_price_per_q": mp.trailing_avg_modal_per_q,
            "trailing_12m_avg": mp.trailing_avg_modal_per_q,
            "yoy_change_pct": mp.yoy_change_pct,
            "volatility_cv": mp.price_cv,
            "seasonal_index": list(mp.seasonal_index or []),
            "as_of": mp.as_of,
            "source": mp.source,
            "source_url": mp.source_url,
            "verification_status": mp.verification_status,
        }

    prices_export = {"msp": msp_dict, "mandi_prices": mandi_dict}
    with open(econ_dir / "prices.json", "w", encoding="utf-8") as f:
        json.dump(prices_export, f, indent=2)
    counts["msp"] = len(msp_dict)
    counts["mandi_prices"] = len(mandi_dict)

    # 7. Input Requirements
    inp_dict = {}
    for ir in session.scalars(select(InputRequirement)).all():
        crop_k = crops_lookup.get(ir.crop_id, "")
        inp_dict[crop_k] = {
            "seed_rate_kg_ha": ir.seed_rate_kg_ha,
            "npk_kg_ha": dict(ir.npk_kg_ha or {}),
            "irrigation_count": ir.irrigation_count,
            "season_water_mm": ir.season_water_mm,
            "man_days_ha": ir.man_days_ha,
            "sprays": ir.sprays,
            "source": ir.source,
            "source_url": ir.source_url,
            "verification_status": ir.verification_status,
        }

    with open(econ_dir / "input_requirements.json", "w", encoding="utf-8") as f:
        json.dump(inp_dict, f, indent=2)
    counts["input_requirements"] = len(inp_dict)

    # 8. Policy Support
    pol_dict = {}
    for ps in session.scalars(select(PolicyScheme)).all():
        pol_dict[ps.key] = {
            "name": ps.name,
            "details": dict(ps.details or {}),
            "as_of": ps.as_of,
            "source": ps.source,
            "source_url": ps.source_url,
            "verify_before_use": ps.verify_before_use,
            "verification_status": ps.verification_status,
        }

    with open(econ_dir / "policy_support.json", "w", encoding="utf-8") as f:
        json.dump(pol_dict, f, indent=2)
    counts["policy_schemes"] = len(pol_dict)

    return counts
