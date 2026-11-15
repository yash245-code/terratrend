"""Economics repository for CACP costs, benchmark yields, prices, and policies."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.base import upsert
from db.models.economics import (
    BenchmarkYield,
    CropCost,
    InputRequirement,
    MandiPrice,
    Msp,
    PolicyScheme,
)
from db.models.reference import Crop, District, State


@dataclass
class EconomicsData:
    """Pure dataclass holding complete agricultural economics memory structures."""
    crop_costs: List[Dict[str, Any]]
    benchmark_yields: List[Dict[str, Any]]
    prices: Dict[str, Any]
    input_requirements: Dict[str, Any]
    policy_support: Dict[str, Any]


class EconomicsRepository:
    """Access layer for agricultural economics records."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def load_economics_data(self) -> EconomicsData:
        """Load and assemble all economics data into a pure EconomicsData dataclass."""
        # 1. State and Crop name lookups
        crops = {c.id: c.key for c in self.session.scalars(select(Crop)).all()}
        states = {s.id: s.name for s in self.session.scalars(select(State)).all()}
        districts = {d.id: d.name for d in self.session.scalars(select(District)).all()}

        # 2. Crop Costs
        cost_rows = self.session.scalars(select(CropCost)).all()
        crop_costs: List[Dict[str, Any]] = []
        for r in cost_rows:
            crop_key = crops.get(r.crop_id, "unknown")
            state_name = states.get(r.state_id, "IN") if r.state_id else "IN"
            crop_costs.append({
                "crop": crop_key,
                "state": state_name,
                "a2": r.cost_a2,
                "a2_fl": r.cost_a2_fl,
                "c2": r.cost_c2,
                "reference_year": r.reference_year,
                "yield_reference_q_ha": r.yield_reference_q_ha,
                "components": dict(r.components or {}),
                "source": r.source,
                "source_url": r.source_url,
                "verification_status": r.verification_status,
            })

        # 3. Benchmark Yields
        yield_rows = self.session.scalars(select(BenchmarkYield)).all()
        benchmark_yields: List[Dict[str, Any]] = []
        for r in yield_rows:
            crop_key = crops.get(r.crop_id, "unknown")
            state_name = states.get(r.state_id) if r.state_id else None
            dist_name = districts.get(r.district_id) if r.district_id else None
            period_str = f"{r.period_start}-{r.period_end}" if r.period_start and r.period_end else "Historical average"
            benchmark_yields.append({
                "crop": crop_key,
                "state": state_name or "IN",
                "district": dist_name,
                "benchmark_yield_q_ha": r.yield_q_ha,
                "reference_period": period_str,
                "period_start": r.period_start,
                "period_end": r.period_end,
                "source": r.source,
                "source_url": r.source_url,
                "verification_status": r.verification_status,
            })

        # 4. MSP & Mandi Prices
        msp_rows = self.session.scalars(select(Msp)).all()
        msp_dict: Dict[str, Any] = {}
        for r in msp_rows:
            crop_key = crops.get(r.crop_id, "unknown")
            msp_dict[crop_key] = {
                "crop": crop_key,
                "msp_per_q": r.msp_per_q,
                "marketing_season": r.marketing_year,
                "is_frp": r.is_frp,
                "source": r.source,
                "source_url": r.source_url,
                "verification_status": r.verification_status,
            }

        mandi_rows = self.session.scalars(select(MandiPrice)).all()
        mandi_dict: Dict[str, Any] = {}
        for r in mandi_rows:
            crop_key = crops.get(r.crop_id, "unknown")
            state_name = states.get(r.state_id, "IN")
            key = f"{crop_key}_{state_name}"
            mandi_dict[key] = {
                "crop": crop_key,
                "state": state_name,
                "modal_price_per_q": r.trailing_avg_modal_per_q,
                "trailing_12m_avg": r.trailing_avg_modal_per_q,
                "yoy_change_pct": r.yoy_change_pct,
                "volatility_cv": r.price_cv,
                "seasonal_index": list(r.seasonal_index or []),
                "as_of": r.as_of,
                "source": r.source,
                "source_url": r.source_url,
                "verification_status": r.verification_status,
            }

        prices_dict = {
            "msp": msp_dict,
            "mandi_prices": mandi_dict,
        }

        # 5. Input Requirements
        input_rows = self.session.scalars(select(InputRequirement)).all()
        input_reqs_dict: Dict[str, Any] = {}
        for r in input_rows:
            crop_key = crops.get(r.crop_id, "unknown")
            input_reqs_dict[crop_key] = {
                "seed_rate_kg_ha": r.seed_rate_kg_ha,
                "npk_kg_ha": dict(r.npk_kg_ha or {}),
                "irrigation_count": r.irrigation_count,
                "season_water_mm": r.season_water_mm,
                "man_days_ha": r.man_days_ha,
                "sprays": r.sprays,
                "source": r.source,
                "source_url": r.source_url,
                "verification_status": r.verification_status,
            }
        final_inputs = {"input_requirements": input_reqs_dict}

        # 6. Policy Schemes
        policy_rows = self.session.scalars(select(PolicyScheme)).all()
        policy_dict: Dict[str, Any] = {}
        for r in policy_rows:
            policy_dict[r.key] = {
                "name": r.name,
                "details": dict(r.details or {}),
                "as_of": r.as_of,
                "source": r.source,
                "source_url": r.source_url,
                "verify_before_use": r.verify_before_use,
                "verification_status": r.verification_status,
            }
        final_policy = {"policy_support": policy_dict}

        return EconomicsData(
            crop_costs=crop_costs,
            benchmark_yields=benchmark_yields,
            prices=prices_dict,
            input_requirements=final_inputs,
            policy_support=final_policy,
        )

    def coverage_matrix(self) -> Dict[str, Any]:
        """Produce a coverage and staleness analysis across all crops and states."""
        all_crops = self.session.scalars(select(Crop.key).order_by(Crop.key)).all()
        all_states = self.session.scalars(select(State.name).order_by(State.name)).all()

        crop_costs_count = self.session.scalar(select(func.count(CropCost.id))) or 0
        benchmark_yields_count = self.session.scalar(select(func.count(BenchmarkYield.id))) or 0
        msp_count = self.session.scalar(select(func.count(Msp.id))) or 0
        mandi_count = self.session.scalar(select(func.count(MandiPrice.id))) or 0

        # Unverified records
        unverified_costs = self.session.scalar(
            select(func.count(CropCost.id)).where(CropCost.verification_status != "verified")
        ) or 0
        unverified_yields = self.session.scalar(
            select(func.count(BenchmarkYield.id)).where(BenchmarkYield.verification_status != "verified")
        ) or 0

        # Check crops missing costs
        crops_with_costs = set(
            self.session.scalars(
                select(Crop.key).join(CropCost, Crop.id == CropCost.crop_id).distinct()
            ).all()
        )
        crops_with_yields = set(
            self.session.scalars(
                select(Crop.key).join(BenchmarkYield, Crop.id == BenchmarkYield.crop_id).distinct()
            ).all()
        )
        crops_with_msp = set(
            self.session.scalars(
                select(Crop.key).join(Msp, Crop.id == Msp.crop_id).distinct()
            ).all()
        )
        crops_with_mandi = set(
            self.session.scalars(
                select(Crop.key).join(MandiPrice, Crop.id == MandiPrice.crop_id).distinct()
            ).all()
        )
        crops_with_inputs = set(
            self.session.scalars(
                select(Crop.key).join(InputRequirement, Crop.id == InputRequirement.crop_id).distinct()
            ).all()
        )

        missing_cost_crops = [c for c in all_crops if c not in crops_with_costs]

        by_crop = {}
        for c_k in all_crops:
            by_crop[c_k] = {
                "has_costs": c_k in crops_with_costs,
                "has_benchmark_yield": c_k in crops_with_yields,
                "has_msp": c_k in crops_with_msp,
                "has_mandi": c_k in crops_with_mandi,
                "has_inputs": c_k in crops_with_inputs,
            }

        return {
            "total_crops": len(all_crops),
            "total_states": len(all_states),
            "crop_costs_records": crop_costs_count,
            "benchmark_yields_records": benchmark_yields_count,
            "msp_records": msp_count,
            "mandi_price_records": mandi_count,
            "unverified_records": {
                "costs": unverified_costs,
                "yields": unverified_yields,
            },
            "missing_cost_crops": missing_cost_crops,
            "national_fallback_active": True,
            "status": "complete" if not missing_cost_crops else "has_gaps",
            "by_crop": by_crop,
        }

    def upsert_mandi_prices(self, rows: List[Dict[str, Any]]) -> int:
        """Upsert dynamic mandi prices from external feed or API."""
        if not rows:
            return 0

        crops_map = {c.key: c.id for c in self.session.scalars(select(Crop)).all()}
        states_map = {s.name: s.id for s in self.session.scalars(select(State)).all()}

        count = 0
        for r in rows:
            crop_key = r.get("crop")
            state_name = r.get("state")
            if crop_key not in crops_map or state_name not in states_map:
                continue

            values = {
                "crop_id": crops_map[crop_key],
                "state_id": states_map[state_name],
                "as_of": str(r.get("as_of", datetime.now(timezone.utc).strftime("%Y-%m-%d"))),
                "trailing_avg_modal_per_q": float(r.get("modal_price_per_q", r.get("trailing_avg_modal_per_q", 0.0))),
                "yoy_change_pct": float(r.get("yoy_change_pct", 0.0)),
                "price_cv": float(r.get("volatility_cv", r.get("price_cv", 0.15))),
                "seasonal_index": list(r.get("seasonal_index", [1.0] * 12)),
                "source": str(r.get("source", "Agmarknet")),
                "source_url": r.get("source_url"),
                "verification_status": str(r.get("verification_status", "verified")),
                "updated_at": datetime.now(timezone.utc),
            }

            upsert(
                self.session,
                MandiPrice,
                values,
                conflict_cols=["crop_id", "state_id", "as_of"],
                update_cols=[
                    "trailing_avg_modal_per_q",
                    "yoy_change_pct",
                    "price_cv",
                    "seasonal_index",
                    "source",
                    "source_url",
                    "verification_status",
                    "updated_at",
                ],
            )
            count += 1

        return count
