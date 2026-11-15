"""Reference data repository for crops, rules, and regions."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from db.models.reference import (
    AmendmentRule,
    Crop,
    CropRequirement,
    CropSoilPreference,
    District,
    State,
    TrendRule,
)


class ReferenceRepository:
    """Access layer for reference datasets, returning pure dicts/dataclasses."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def load_crops(self) -> Dict[str, Any]:
        """Assemble all crops, requirements, and soil preferences into a pure dictionary."""
        stmt = (
            select(Crop)
            .options(
                selectinload(Crop.requirements),
                selectinload(Crop.soil_preferences),
            )
            .order_by(Crop.key)
        )
        crops = self.session.scalars(stmt).all()

        crops_dict: Dict[str, Any] = {}
        for c in crops:
            temp_trap = [10.0, 18.0, 30.0, 38.0]
            rain_trap = [300.0, 500.0, 1200.0, 2000.0]
            ph_trap = [5.5, 6.0, 7.5, 8.5]
            for r in c.requirements:
                trap = [r.abs_min, r.opt_min, r.opt_max, r.abs_max]
                if r.factor == "temperature":
                    temp_trap = trap
                elif r.factor == "rainfall":
                    rain_trap = trap
                elif r.factor == "ph":
                    ph_trap = trap

            textures = [sp.class_name for sp in c.soil_preferences if sp.kind == "texture"]
            drainage = [sp.class_name for sp in c.soil_preferences if sp.kind == "drainage"]

            crops_dict[c.key] = {
                "key": c.key,
                "name": c.name,
                "local_name": c.local_name,
                "group": c.group,
                "seasons": list(c.seasons or ["annual"]),
                "cycle_days": c.cycle_days,
                "temperature_trapezoid": temp_trap,
                "rainfall_trapezoid": rain_trap,
                "ph_trapezoid": ph_trap,
                "suitable_textures": textures,
                "suitable_drainage": drainage,
                "salinity_tolerance_ece": c.salinity_ece_max,
                "water_demand": c.water_demand,
                "base_yield_cv": c.base_yield_cv,
                "source": c.source,
                "verification_status": c.verification_status,
                "notes": c.notes,
            }

        return crops_dict

    def load_amendment_rules(self) -> List[Dict[str, Any]]:
        """Load soil amendment condition rules matching amendments.json schema."""
        stmt = select(AmendmentRule).order_by(AmendmentRule.id)
        rules = self.session.scalars(stmt).all()
        op_sym_map = {"lt": "<", "lte": "<=", "gt": ">", "gte": ">=", "between": "between", "eq": "=="}
        field_map = {
            "soil_ph_lt_5.5_0": "soil_ph_top",
            "soil_ph_gt_8.0_1": "soil_ph_top",
            "soil_quality_gt_15.0_2": "soil_sodicity",
            "soil_quality_gt_4.0_3": "soil_salinity",
            "soil_quality_lt_0.5_4": "soil_organic_carbon",
            "soil_quality_gt_70.0_5": "soil_sand",
            "soil_quality_gt_50.0_6": "soil_clay",
            "moisture_lt_40.0_7": "moisture_score",
            "temperature_lt_40.0_8": "temperature_score",
            "climate_gt_0.3_9": "rainfall_cv",
        }
        rules_list: List[Dict[str, Any]] = []
        for r in rules:
            if r.key in field_map:
                field = field_map[r.key]
            elif ":" in r.key:
                field = r.key.split(":")[0]
            elif r.factor == "soil_ph":
                field = "soil_ph_top"
            else:
                field = r.factor

            op_sym = op_sym_map.get(r.operator, r.operator)
            rules_list.append({
                "factor": r.factor,
                "issue": r.issue,
                "condition": {
                    "field": field,
                    "op": op_sym,
                    "val": r.threshold_low,
                },
                "actions": list(r.actions or []),
                "note": r.note or "Confirm with a local soil test and an agronomist before applying amendments.",
            })
        return rules_list

    def load_trend_rules(self) -> Dict[str, Any]:
        """Load trend-to-practice advisory rules keyed by indicator_direction."""
        stmt = select(TrendRule).order_by(TrendRule.id)
        rules = self.session.scalars(stmt).all()
        trend_dict: Dict[str, Any] = {}
        for r in rules:
            key = f"{r.indicator}_{r.direction}"
            trend_dict[key] = {
                "headline": f"{r.indicator.replace('_', ' ').title()} {r.direction.title()} Trend Detected",
                "message": r.confidence_note or "",
                "crops": list(r.crops or []),
                "avoid": list(r.avoid or []),
                "practices": list(r.practices or []),
            }
        return trend_dict

    def load_regions(self) -> Dict[str, Any]:
        """Load states and districts master catalogue."""
        states = self.session.scalars(
            select(State).options(selectinload(State.districts)).order_by(State.name)
        ).all()

        states_list = []
        state_map = {}
        for s in states:
            dist_list = [
                {"id": d.id, "name": d.name, "lgd_code": d.lgd_code}
                for d in s.districts
            ]
            s_dict = {
                "id": s.id,
                "code": s.code,
                "name": s.name,
                "is_union_territory": s.is_union_territory,
                "districts": dist_list,
            }
            states_list.append(s_dict)
            state_map[s.name] = s_dict

        return {"states": states_list, "state_map": state_map}

    def get_state_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Look up state by name (case-insensitive)."""
        stmt = select(State).where(State.name.ilike(name.strip()))
        state = self.session.scalars(stmt).first()
        if not state:
            return None
        return {
            "id": state.id,
            "code": state.code,
            "name": state.name,
            "is_union_territory": state.is_union_territory,
        }

    def get_district_by_name(self, state_id: int, name: str) -> Optional[Dict[str, Any]]:
        """Look up district by state_id and name."""
        stmt = select(District).where(
            District.state_id == state_id,
            District.name.ilike(name.strip())
        )
        dist = self.session.scalars(stmt).first()
        if not dist:
            return None
        return {
            "id": dist.id,
            "state_id": dist.state_id,
            "name": dist.name,
            "lgd_code": dist.lgd_code,
        }
