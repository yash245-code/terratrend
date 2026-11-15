"""TerraTrend Reference Data Cache.

Loads official agronomic, boundary, and CACP economic reference data from the database into RAM once
at application startup, ensuring pure business logic modules operate entirely in-memory without
hitting database tables per request.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config import Config
from db.base import get_session
from db.models.economics import BenchmarkYield, CropCost, MandiPrice, Msp
from db.models.reference import AmendmentRule, Crop, CropRequirement, District, State, TrendRule
from db.repositories.economics_repo import EconomicsData, EconomicsRepository
from db.repositories.reference_repo import ReferenceRepository
from db.seed import seed_database
from teratrend.advisor import set_crop_rules
from teratrend.amendments import set_amendment_rules
from teratrend.crops import set_crop_requirements
from teratrend.economics import set_economics_store

log = logging.getLogger("teratrend.services.reference_cache")

_INSTANCE: Optional["ReferenceDataCache"] = None


class ReferenceDataCache:
    """In-memory cache for all agronomic reference and baseline economics data."""

    def __init__(self) -> None:
        self.crops: Dict[str, Any] = {}
        self.amendments: List[Dict[str, Any]] = []
        self.trend_rules: Dict[str, Any] = {}
        self.regions: Dict[str, Any] = {}
        self.economics: Optional[EconomicsData] = None
        self.reference_version: str = "v1.0.0"
        self.loaded_at: Optional[datetime] = None
        self.counts: Dict[str, int] = {}

    def load(self, fail_fast: bool = True) -> "ReferenceDataCache":
        """Load or reload all reference datasets from the database into memory."""
        log.info("Loading reference data from database into RAM...")
        with get_session() as session:
            # Check if database has crops
            crop_count = session.scalar(select(func.count(Crop.id))) or 0
            if crop_count == 0:
                if Config.AUTO_CREATE_DB:
                    log.info("Reference tables are empty and AUTO_CREATE_DB is enabled. Running auto-seed...")
                    seed_database(session)
                    session.commit()
                elif fail_fast:
                    raise RuntimeError(
                        "TerraTrend reference database is unseeded. "
                        "Please run: python -m db.cli init && python -m db.cli seed"
                    )

            ref_repo = ReferenceRepository(session)
            econ_repo = EconomicsRepository(session)

            self.crops = ref_repo.load_crops()
            self.amendments = ref_repo.load_amendment_rules()
            self.trend_rules = ref_repo.load_trend_rules()
            self.regions = ref_repo.load_regions()
            self.economics = econ_repo.load_economics_data()

            # Row counts
            self.counts = {
                "crops": len(self.crops),
                "amendments": len(self.amendments),
                "trend_rules": len(self.trend_rules),
                "states": len(self.regions.get("states", [])),
                "districts": len(self.regions.get("districts", [])),
                "crop_costs": len(self.economics.crop_costs),
                "benchmark_yields": len(self.economics.benchmark_yields),
                "msp": len(self.economics.prices.get("msp", {})),
                "mandi_prices": len(self.economics.prices.get("mandi_prices", {})),
            }

            # Derive deterministic reference_version hash from max updated_at and counts
            hasher = hashlib.sha256()
            hasher.update(str(self.counts).encode("utf-8"))
            for model in [Crop, AmendmentRule, TrendRule, CropCost, BenchmarkYield]:
                max_ts = session.scalar(select(func.max(model.updated_at)))
                if max_ts:
                    hasher.update(str(max_ts).encode("utf-8"))
            self.reference_version = hasher.hexdigest()[:16]
            self.loaded_at = datetime.now(timezone.utc)

        # Hydrate pure modules in RAM
        set_crop_requirements(self.crops)
        set_amendment_rules(self.amendments)
        set_crop_rules(self.trend_rules)
        set_economics_store(
            crop_costs=self.economics.crop_costs,
            benchmark_yields=self.economics.benchmark_yields,
            prices=self.economics.prices,
            input_reqs=self.economics.input_requirements.get("input_requirements", {}),
            policy_support=self.economics.policy_support.get("policy_support", {}),
        )

        log.info(
            "Reference data loaded successfully (version: %s, crops: %d, rules: %d, costs: %d)",
            self.reference_version,
            self.counts.get("crops", 0),
            self.counts.get("amendments", 0),
            self.counts.get("crop_costs", 0),
        )
        return self

    def reload(self) -> "ReferenceDataCache":
        """Hot-reload cache from DB while keeping existing instance."""
        return self.load(fail_fast=True)

    def snapshot(self) -> Dict[str, Any]:
        """Return diagnostic snapshot of loaded reference datasets."""
        return {
            "reference_version": self.reference_version,
            "loaded_at": self.loaded_at.isoformat() if self.loaded_at else None,
            "counts": self.counts,
            "status": "ready" if self.counts.get("crops", 0) > 0 else "empty",
        }


def get_reference_cache() -> ReferenceDataCache:
    """Retrieve global singleton instance of ReferenceDataCache."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = ReferenceDataCache()
        _INSTANCE.load()
    return _INSTANCE
