"""TerraTrend Database Seeder.

Idempotently imports official agronomic, boundary, and CACP economic reference JSON datasets
into the database within a single transaction with strict validation.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import Config, BOUNDARIES_DIR, SEED_DIR
from db.base import upsert
from db.models.reference import (
    AmendmentRule,
    Crop,
    CropRequirement,
    CropSoilPreference,
    District,
    State,
    TrendRule,
)
from db.models.economics import (
    BenchmarkYield,
    CropCost,
    InputRequirement,
    MandiPrice,
    Msp,
    PolicyScheme,
)

log = logging.getLogger("teratrend.db.seed")

# Mapping operators in amendment rules to canonical enums
OP_MAP = {
    "<": "lt",
    "<=": "lte",
    ">": "gt",
    ">=": "gte",
    "between": "between",
    "==": "eq",
    "=": "eq",
}


def _clean_op(op_str: str) -> str:
    """Normalize operator string to canonical enum value."""
    op_clean = op_str.strip().lower()
    return OP_MAP.get(op_clean, "lt")


def seed_database(
    session: Session,
    from_dir: Optional[Path] = None,
    only: Optional[str] = None,
    skip_invalid: bool = False,
) -> Dict[str, Any]:
    """Import seed JSON files into database within current session transaction.
    
    Args:
        session: Active SQLAlchemy Session (caller commits or rolls back)
        from_dir: Root directory of seed data (defaults to Config.DATA_DIR / 'seed')
        only: Optional filter: 'regions', 'crops', 'rules', or 'economics'
        skip_invalid: If True, log and skip invalid rows; if False, raise ValueError
    """
    root_seed = from_dir or Config.DATA_DIR / "seed"
    stats: Dict[str, Dict[str, int]] = {}

    def log_stat(category: str, status: str) -> None:
        if category not in stats:
            stats[category] = {"inserted": 0, "updated": 0, "rejected": 0}
        stats[category][status] += 1

    def handle_rejection(category: str, msg: str) -> None:
        log_stat(category, "rejected")
        if not skip_invalid:
            raise ValueError(f"[{category}] Validation failed: {msg}")
        log.warning(f"[{category}] Rejected record: {msg}")

    # 1. SEED REGIONS
    if only is None or only == "regions":
        stats["regions"] = {"inserted": 0, "updated": 0, "rejected": 0}
        geojson_path = BOUNDARIES_DIR / "india_states.geojson"
        if not geojson_path.exists():
            geojson_path = Config.DATA_DIR / "boundaries" / "india_states.geojson"

        if geojson_path.exists():
            with open(geojson_path, "r", encoding="utf-8") as f:
                geo = json.load(f)

            ut_keywords = {
                "andaman & nicobar", "chandigarh", "dadara", "daman & diu",
                "delhi", "jammu & kashmir", "ladakh", "lakshadweep", "puducherry"
            }

            state_code_map = {
                "andaman & nicobar island": "AN",
                "andhra pradesh": "AP",
                "arunanchal pradesh": "AR",
                "arunachal pradesh": "AR",
                "assam": "AS",
                "bihar": "BR",
                "chandigarh": "CH",
                "chhattisgarh": "CT",
                "dadara & nagar havelli": "DN",
                "dadra and nagar haveli and daman and diu": "DH",
                "daman & diu": "DD",
                "goa": "GA",
                "gujarat": "GJ",
                "haryana": "HR",
                "himachal pradesh": "HP",
                "jammu & kashmir": "JK",
                "jharkhand": "JH",
                "karnataka": "KA",
                "kerala": "KL",
                "ladakh": "LA",
                "lakshadweep": "LD",
                "madhya pradesh": "MP",
                "maharashtra": "MH",
                "manipur": "MN",
                "meghalaya": "ML",
                "mizoram": "MZ",
                "nagaland": "NL",
                "nct of delhi": "DL",
                "delhi": "DL",
                "odisha": "OR",
                "puducherry": "PY",
                "punjab": "PB",
                "rajasthan": "RJ",
                "sikkim": "SK",
                "tamil nadu": "TN",
                "telangana": "TG",
                "tripura": "TR",
                "uttar pradesh": "UP",
                "uttarakhand": "UT",
                "west bengal": "WB",
            }

            existing_states = {s.name: s for s in session.scalars(select(State)).all()}
            used_codes = {s.code for s in existing_states.values()}

            for feat in geo.get("features", []):
                st_name = feat.get("properties", {}).get("ST_NM")
                if not st_name:
                    continue
                st_name = st_name.strip()
                norm_name = st_name.lower()
                is_ut = any(k in norm_name for k in ut_keywords)

                existing = existing_states.get(st_name)
                if existing:
                    existing.is_union_territory = is_ut
                    log_stat("regions", "updated")
                else:
                    code = state_code_map.get(norm_name)
                    if not code or code in used_codes:
                        prefix = "".join(w[0] for w in st_name.split() if w[0].isalnum()).upper()[:2]
                        if len(prefix) < 2:
                            prefix = st_name[:2].upper()
                        code = prefix
                        counter = 1
                        while code in used_codes:
                            code = f"{prefix[:1]}{counter:02d}"
                            counter += 1

                    used_codes.add(code)
                    st = State(code=code, name=st_name, is_union_territory=is_ut)
                    session.add(st)
                    existing_states[st_name] = st
                    log_stat("regions", "inserted")
            session.flush()

    # 2. SEED CROPS & REQUIREMENTS
    if only is None or only == "crops":
        stats["crops"] = {"inserted": 0, "updated": 0, "rejected": 0}
        crops_file = root_seed / "crops" / "crop_requirements.json"
        if not crops_file.exists():
            crops_file = Config.DATA_DIR / "crops" / "crop_requirements.json"

        if crops_file.exists():
            with open(crops_file, "r", encoding="utf-8") as f:
                c_data = json.load(f)

            # Dictionary of crops
            crop_items = c_data.get("crops", c_data)
            for key, val in crop_items.items():
                if not isinstance(val, dict):
                    continue

                c_key = val.get("key", key)
                name = val.get("name")
                group = val.get("group", "other")
                source = val.get("source")
                cycle_days = val.get("cycle_days", 120)
                water_demand = val.get("water_demand", "medium")
                base_yield_cv = float(val.get("base_yield_cv", 0.15))
                salinity_ece_max = float(val.get("salinity_tolerance_ece", val.get("salinity_ece_max", 4.0)))

                if not name or not source:
                    handle_rejection("crops", f"Crop '{c_key}' missing required name or source")
                    continue

                existing_crop = session.scalars(select(Crop).where(Crop.key == c_key)).first()
                if existing_crop:
                    existing_crop.name = name
                    existing_crop.local_name = val.get("local_name")
                    existing_crop.group = group
                    existing_crop.seasons = list(val.get("seasons", ["annual"]))
                    existing_crop.cycle_days = cycle_days
                    existing_crop.water_demand = water_demand
                    existing_crop.base_yield_cv = base_yield_cv
                    existing_crop.salinity_ece_max = salinity_ece_max
                    existing_crop.notes = val.get("notes")
                    existing_crop.source = source
                    existing_crop.verification_status = val.get("verification_status", "verified")
                    crop_obj = existing_crop
                    log_stat("crops", "updated")
                else:
                    crop_obj = Crop(
                        key=c_key,
                        name=name,
                        local_name=val.get("local_name"),
                        group=group,
                        seasons=list(val.get("seasons", ["annual"])),
                        cycle_days=cycle_days,
                        water_demand=water_demand,
                        base_yield_cv=base_yield_cv,
                        salinity_ece_max=salinity_ece_max,
                        notes=val.get("notes"),
                        source=source,
                        verification_status=val.get("verification_status", "verified"),
                    )
                    session.add(crop_obj)
                    session.flush()
                    log_stat("crops", "inserted")

                # Requirements
                trapezoid_map = {
                    "temperature": val.get("temperature_trapezoid"),
                    "rainfall": val.get("rainfall_trapezoid"),
                    "ph": val.get("ph_trapezoid"),
                }
                for factor, trap in trapezoid_map.items():
                    if not trap or len(trap) != 4:
                        continue
                    abs_min, opt_min, opt_max, abs_max = [float(x) for x in trap]
                    if not (abs_min <= opt_min <= opt_max <= abs_max):
                        handle_rejection(
                            "crops",
                            f"Unordered trapezoid {trap} for crop {c_key} factor {factor}"
                        )
                        continue

                    req = session.scalars(
                        select(CropRequirement).where(
                            CropRequirement.crop_id == crop_obj.id,
                            CropRequirement.factor == factor,
                            CropRequirement.season.is_(None),
                        )
                    ).first()
                    if req:
                        req.abs_min = abs_min
                        req.opt_min = opt_min
                        req.opt_max = opt_max
                        req.abs_max = abs_max
                    else:
                        req = CropRequirement(
                            crop_id=crop_obj.id,
                            factor=factor,
                            season=None,
                            abs_min=abs_min,
                            opt_min=opt_min,
                            opt_max=opt_max,
                            abs_max=abs_max,
                        )
                        session.add(req)

                # Soil preferences
                for pref_tex in val.get("preferred_textures", []):
                    sp = session.scalars(
                        select(CropSoilPreference).where(
                            CropSoilPreference.crop_id == crop_obj.id,
                            CropSoilPreference.kind == "texture",
                            CropSoilPreference.class_name == pref_tex,
                        )
                    ).first()
                    if not sp:
                        session.add(
                            CropSoilPreference(
                                crop_id=crop_obj.id,
                                kind="texture",
                                class_name=pref_tex,
                                level="preferred",
                            )
                        )

                for tol_tex in val.get("tolerated_textures", []):
                    sp = session.scalars(
                        select(CropSoilPreference).where(
                            CropSoilPreference.crop_id == crop_obj.id,
                            CropSoilPreference.kind == "texture",
                            CropSoilPreference.class_name == tol_tex,
                        )
                    ).first()
                    if not sp:
                        session.add(
                            CropSoilPreference(
                                crop_id=crop_obj.id,
                                kind="texture",
                                class_name=tol_tex,
                                level="tolerated",
                            )
                        )

                for pref_drn in val.get("preferred_drainage", []):
                    sp = session.scalars(
                        select(CropSoilPreference).where(
                            CropSoilPreference.crop_id == crop_obj.id,
                            CropSoilPreference.kind == "drainage",
                            CropSoilPreference.class_name == pref_drn,
                        )
                    ).first()
                    if not sp:
                        session.add(
                            CropSoilPreference(
                                crop_id=crop_obj.id,
                                kind="drainage",
                                class_name=pref_drn,
                                level="preferred",
                            )
                        )
            session.flush()

    # 3. SEED RULES
    if only is None or only == "rules":
        stats["rules"] = {"inserted": 0, "updated": 0, "rejected": 0}
        amendments_file = root_seed / "rules" / "amendments.json"
        if not amendments_file.exists():
            amendments_file = Config.DATA_DIR / "rules" / "amendments.json"

        if amendments_file.exists():
            with open(amendments_file, "r", encoding="utf-8") as f:
                am_data = json.load(f)

            for i, rule in enumerate(am_data):
                cond = rule.get("condition", {})
                factor = rule.get("factor", "soil")
                issue = rule.get("issue", "Soil amendment needed")
                raw_op = cond.get("op", "<")
                op_enum = _clean_op(raw_op)
                val = cond.get("val", 0.0)
                val2 = cond.get("val2")
                r_key = rule.get("key", f"{factor}_{op_enum}_{val}_{i}")

                existing_rule = session.scalars(
                    select(AmendmentRule).where(AmendmentRule.key == r_key)
                ).first()
                if existing_rule:
                    existing_rule.factor = factor
                    existing_rule.operator = op_enum
                    existing_rule.threshold_low = float(val) if isinstance(val, (int, float)) else 0.0
                    existing_rule.threshold_high = float(val2) if val2 is not None else None
                    existing_rule.issue = issue
                    existing_rule.actions = list(rule.get("actions", []))
                    existing_rule.note = rule.get("note")
                    log_stat("rules", "updated")
                else:
                    session.add(
                        AmendmentRule(
                            key=r_key,
                            factor=factor,
                            operator=op_enum,
                            threshold_low=float(val) if isinstance(val, (int, float)) else 0.0,
                            threshold_high=float(val2) if val2 is not None else None,
                            issue=issue,
                            actions=list(rule.get("actions", [])),
                            note=rule.get("note"),
                        )
                    )
                    log_stat("rules", "inserted")

        # Trend rules
        crop_rules_file = root_seed / "crops" / "crop_rules.json"
        if not crop_rules_file.exists():
            crop_rules_file = Config.DATA_DIR / "crops" / "crop_rules.json"

        if crop_rules_file.exists():
            with open(crop_rules_file, "r", encoding="utf-8") as f:
                cr_data = json.load(f)

            for rule_key, r_spec in cr_data.items():
                if not isinstance(r_spec, dict):
                    continue

                # split indicator and direction: e.g. root_moisture_decreasing
                parts = rule_key.rsplit("_", 1)
                if len(parts) == 2 and parts[1] in ("increasing", "decreasing"):
                    ind, direction = parts[0], parts[1]
                else:
                    ind, direction = rule_key, "increasing"

                existing_tr = session.scalars(
                    select(TrendRule).where(
                        TrendRule.indicator == ind,
                        TrendRule.direction == direction,
                    )
                ).first()
                if existing_tr:
                    existing_tr.crops = list(r_spec.get("crops", []))
                    existing_tr.avoid = list(r_spec.get("avoid", []))
                    existing_tr.practices = list(r_spec.get("practices", []))
                    existing_tr.confidence_note = r_spec.get("message")
                    log_stat("rules", "updated")
                else:
                    session.add(
                        TrendRule(
                            indicator=ind,
                            direction=direction,
                            crops=list(r_spec.get("crops", [])),
                            avoid=list(r_spec.get("avoid", [])),
                            practices=list(r_spec.get("practices", [])),
                            confidence_note=r_spec.get("message"),
                        )
                    )
                    log_stat("rules", "inserted")
        session.flush()

    # 4. SEED ECONOMICS
    if only is None or only == "economics":
        stats["economics"] = {"inserted": 0, "updated": 0, "rejected": 0}
        crops_map = {c.key: c.id for c in session.scalars(select(Crop)).all()}
        states_map = {s.name.lower(): s.id for s in session.scalars(select(State)).all()}

        # 4a. Crop Costs
        costs_file = root_seed / "economics" / "crop_costs.json"
        if not costs_file.exists():
            costs_file = Config.DATA_DIR / "economics" / "crop_costs.json"

        if costs_file.exists():
            with open(costs_file, "r", encoding="utf-8") as f:
                cost_rows = json.load(f)

            for row in cost_rows:
                crop_k = row.get("crop")
                if crop_k not in crops_map:
                    handle_rejection("economics", f"Unknown crop '{crop_k}' in crop_costs")
                    continue

                source = row.get("source")
                ref_year = str(row.get("reference_year", ""))
                if not source or not ref_year:
                    handle_rejection("economics", f"Missing source or reference_year in crop_costs: {row}")
                    continue

                st_k = row.get("state")
                st_id = states_map.get(st_k.lower()) if st_k and st_k != "IN" else None

                existing_cost = session.scalars(
                    select(CropCost).where(
                        CropCost.crop_id == crops_map[crop_k],
                        CropCost.state_id == st_id,
                        CropCost.reference_year == ref_year,
                    )
                ).first()

                if existing_cost:
                    existing_cost.cost_a2 = float(row.get("a2", 0.0))
                    existing_cost.cost_a2_fl = float(row.get("a2_fl", 0.0))
                    existing_cost.cost_c2 = float(row.get("c2", 0.0))
                    existing_cost.components = dict(row.get("components", {}))
                    existing_cost.yield_reference_q_ha = float(row.get("yield_reference_q_ha", 0.0))
                    existing_cost.source = source
                    existing_cost.source_url = row.get("source_url")
                    existing_cost.verification_status = row.get("verification_status", "verified")
                    log_stat("economics", "updated")
                else:
                    session.add(
                        CropCost(
                            crop_id=crops_map[crop_k],
                            state_id=st_id,
                            reference_year=ref_year,
                            cost_a2=float(row.get("a2", 0.0)),
                            cost_a2_fl=float(row.get("a2_fl", 0.0)),
                            cost_c2=float(row.get("c2", 0.0)),
                            components=dict(row.get("components", {})),
                            yield_reference_q_ha=float(row.get("yield_reference_q_ha", 0.0)),
                            source=source,
                            source_url=row.get("source_url"),
                            verification_status=row.get("verification_status", "verified"),
                        )
                    )
                    log_stat("economics", "inserted")

        # 4b. Benchmark Yields
        yields_file = root_seed / "economics" / "benchmark_yields.json"
        if not yields_file.exists():
            yields_file = Config.DATA_DIR / "economics" / "benchmark_yields.json"

        if yields_file.exists():
            with open(yields_file, "r", encoding="utf-8") as f:
                yield_rows = json.load(f)

            for row in yield_rows:
                crop_k = row.get("crop")
                if crop_k not in crops_map:
                    handle_rejection("economics", f"Unknown crop '{crop_k}' in benchmark_yields")
                    continue

                source = row.get("source")
                yield_val = float(row.get("benchmark_yield_q_ha", row.get("yield_q_ha", 0.0)))
                if yield_val <= 0 or not source:
                    handle_rejection("economics", f"Invalid yield value or missing source in benchmark_yields: {row}")
                    continue

                st_k = row.get("state")
                st_id = states_map.get(st_k.lower()) if st_k and st_k != "IN" else None

                # Parse years from reference_period if present
                ref_period = str(row.get("reference_period", ""))
                years = [int(y) for y in re.findall(r"\b(20\d\d)\b", ref_period)]
                p_start = years[0] if years else row.get("period_start", 2021)
                p_end = years[-1] if len(years) > 1 else row.get("period_end", 2024)

                session.add(
                    BenchmarkYield(
                        crop_id=crops_map[crop_k],
                        state_id=st_id,
                        district_id=None,
                        yield_q_ha=yield_val,
                        period_start=p_start,
                        period_end=p_end,
                        source=source,
                        source_url=row.get("source_url"),
                        verification_status=row.get("verification_status", "verified"),
                    )
                )
                log_stat("economics", "inserted")

        # 4c. MSP & Mandi Prices
        prices_file = root_seed / "economics" / "prices.json"
        if not prices_file.exists():
            prices_file = Config.DATA_DIR / "economics" / "prices.json"

        if prices_file.exists():
            with open(prices_file, "r", encoding="utf-8") as f:
                p_data = json.load(f)

            # MSP
            for crop_k, msp_info in p_data.get("msp", {}).items():
                if crop_k not in crops_map or not isinstance(msp_info, dict):
                    continue
                msp_val = msp_info.get("msp_per_q")
                if msp_val is None or float(msp_val) <= 0:
                    continue

                season_label = str(msp_info.get("marketing_season", "2024-25"))
                source = str(msp_info.get("source", "DA&FW MSP"))
                is_frp = bool("FRP" in season_label.upper())

                existing_msp = session.scalars(
                    select(Msp).where(
                        Msp.crop_id == crops_map[crop_k],
                        Msp.marketing_year == season_label,
                    )
                ).first()

                if existing_msp:
                    existing_msp.msp_per_q = float(msp_val)
                    existing_msp.is_frp = is_frp
                    existing_msp.source = source
                    existing_msp.source_url = msp_info.get("source_url")
                    existing_msp.verification_status = msp_info.get("verification_status", "verified")
                    log_stat("economics", "updated")
                else:
                    session.add(
                        Msp(
                            crop_id=crops_map[crop_k],
                            marketing_year=season_label,
                            msp_per_q=float(msp_val),
                            is_frp=is_frp,
                            source=source,
                            source_url=msp_info.get("source_url"),
                            verification_status=msp_info.get("verification_status", "verified"),
                        )
                    )
                    log_stat("economics", "inserted")

            # Mandi Prices
            for item_key, m_info in p_data.get("mandi_prices", {}).items():
                if not isinstance(m_info, dict):
                    continue
                crop_k = m_info.get("crop")
                st_k = m_info.get("state")
                if crop_k not in crops_map or not st_k:
                    continue

                st_id = states_map.get(st_k.lower())
                if not st_id:
                    continue

                as_of = str(m_info.get("as_of", "2024-06"))
                source = str(m_info.get("source", "Agmarknet"))

                modal_p = float(m_info.get("modal_price_per_q", m_info.get("trailing_avg_modal_per_q", 0.0)))
                existing_mandi = session.scalars(
                    select(MandiPrice).where(
                        MandiPrice.crop_id == crops_map[crop_k],
                        MandiPrice.state_id == st_id,
                        MandiPrice.as_of == as_of,
                    )
                ).first()

                if existing_mandi:
                    existing_mandi.trailing_avg_modal_per_q = modal_p
                    existing_mandi.yoy_change_pct = float(m_info.get("yoy_change_pct", 0.0))
                    existing_mandi.price_cv = float(m_info.get("volatility_cv", m_info.get("price_cv", 0.15)))
                    existing_mandi.seasonal_index = list(m_info.get("seasonal_index", [1.0] * 12))
                    existing_mandi.source = source
                    existing_mandi.source_url = m_info.get("source_url")
                    existing_mandi.verification_status = m_info.get("verification_status", "verified")
                    log_stat("economics", "updated")
                else:
                    session.add(
                        MandiPrice(
                            crop_id=crops_map[crop_k],
                            state_id=st_id,
                            as_of=as_of,
                            trailing_avg_modal_per_q=modal_p,
                            yoy_change_pct=float(m_info.get("yoy_change_pct", 0.0)),
                            price_cv=float(m_info.get("volatility_cv", m_info.get("price_cv", 0.15))),
                            seasonal_index=list(m_info.get("seasonal_index", [1.0] * 12)),
                            source=source,
                            source_url=m_info.get("source_url"),
                            verification_status=m_info.get("verification_status", "verified"),
                        )
                    )
                    log_stat("economics", "inserted")

        # 4d. Input Requirements
        inp_file = root_seed / "economics" / "input_requirements.json"
        if not inp_file.exists():
            inp_file = Config.DATA_DIR / "economics" / "input_requirements.json"

        if inp_file.exists():
            with open(inp_file, "r", encoding="utf-8") as f:
                input_data = json.load(f)

            for crop_k, req in input_data.items():
                if crop_k not in crops_map or not isinstance(req, dict):
                    continue

                source = str(req.get("source", "CACP / ICAR Recommendations"))
                npk_raw = req.get("npk_kg_ha", {})
                if isinstance(npk_raw, list):
                    npk_val = {
                        "N": float(npk_raw[0]) if len(npk_raw) > 0 else 0.0,
                        "P": float(npk_raw[1]) if len(npk_raw) > 1 else 0.0,
                        "K": float(npk_raw[2]) if len(npk_raw) > 2 else 0.0,
                    }
                elif isinstance(npk_raw, dict):
                    npk_val = {str(k): float(v) for k, v in npk_raw.items()}
                else:
                    npk_val = {}

                water_mm = float(req.get("season_water_mm") or req.get("season_water_requirement_mm") or 0.0)
                man_days = float(req.get("man_days_ha") or req.get("labour_man_days_ha") or 0.0)
                sprays_cnt = int(req.get("sprays") or req.get("plant_protection_sprays") or 0)

                existing_inp = session.scalars(
                    select(InputRequirement).where(
                        InputRequirement.crop_id == crops_map[crop_k]
                    )
                ).first()

                if existing_inp:
                    existing_inp.seed_rate_kg_ha = float(req.get("seed_rate_kg_ha", 0.0))
                    existing_inp.npk_kg_ha = npk_val
                    existing_inp.irrigation_count = int(req.get("irrigation_count", 0))
                    existing_inp.season_water_mm = water_mm
                    existing_inp.man_days_ha = man_days
                    existing_inp.sprays = sprays_cnt
                    existing_inp.source = source
                    existing_inp.source_url = req.get("source_url")
                    existing_inp.verification_status = req.get("verification_status", "verified")
                    log_stat("economics", "updated")
                else:
                    session.add(
                        InputRequirement(
                            crop_id=crops_map[crop_k],
                            seed_rate_kg_ha=float(req.get("seed_rate_kg_ha", 0.0)),
                            npk_kg_ha=npk_val,
                            irrigation_count=int(req.get("irrigation_count", 0)),
                            season_water_mm=water_mm,
                            man_days_ha=man_days,
                            sprays=sprays_cnt,
                            source=source,
                            source_url=req.get("source_url"),
                            verification_status=req.get("verification_status", "verified"),
                        )
                    )
                    log_stat("economics", "inserted")

        # 4e. Policy Support
        pol_file = root_seed / "economics" / "policy_support.json"
        if not pol_file.exists():
            pol_file = Config.DATA_DIR / "economics" / "policy_support.json"

        if pol_file.exists():
            with open(pol_file, "r", encoding="utf-8") as f:
                pol_data = json.load(f)

            for pol_k, p_info in pol_data.items():
                if not isinstance(p_info, dict):
                    continue

                source = str(p_info.get("source", "Government Scheme Portal"))
                as_of = str(p_info.get("as_of", "2024-06"))

                existing_pol = session.scalars(
                    select(PolicyScheme).where(PolicyScheme.key == pol_k)
                ).first()

                if existing_pol:
                    existing_pol.name = str(p_info.get("name", pol_k))
                    existing_pol.details = dict(p_info.get("details", p_info))
                    existing_pol.as_of = as_of
                    existing_pol.source = source
                    existing_pol.source_url = p_info.get("source_url")
                    existing_pol.verify_before_use = bool(p_info.get("verify_before_use", True))
                    existing_pol.verification_status = p_info.get("verification_status", "verified")
                    log_stat("economics", "updated")
                else:
                    session.add(
                        PolicyScheme(
                            key=pol_k,
                            name=str(p_info.get("name", pol_k)),
                            details=dict(p_info.get("details", p_info)),
                            as_of=as_of,
                            source=source,
                            source_url=p_info.get("source_url"),
                            verify_before_use=bool(p_info.get("verify_before_use", True)),
                            verification_status=p_info.get("verification_status", "verified"),
                        )
                    )
                    log_stat("economics", "inserted")
        session.flush()

    return stats
