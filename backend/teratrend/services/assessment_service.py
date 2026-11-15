"""TerraTrend Land Assessment & Crop Decision Support Service.

Orchestrates multi-dataset geospatial analysis, agronomic factor rating, crop suitability ranking,
CACP economics, trend consensus, and results caching.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from config import Config, DATASETS, INDICATORS
from db.base import get_session
from db.models.reference import District, State
from db.repositories.results_repo import ResultsRepository
from teratrend.advisor import advise
from teratrend.amendments import generate_amendments
from teratrend.climatology import compute_drought_and_wet_frequencies, compute_interannual_stats
from teratrend.consensus import consensus_for_group
from teratrend.crops import rank_crops
from teratrend.cube_store import CubeStore, get_store
from teratrend.economics import (
    compute_economics,
    rank_by_economics,
    select_balanced_crop,
)
from teratrend.geo import resolve_location
from teratrend.industry import build_industry_factors
from teratrend.regions import OutOfIndiaError
from teratrend.schemas import AssessmentReport, CropEconomicsSummary
from teratrend.services.reference_cache import get_reference_cache
from teratrend.suitability import (
    compute_overall_assessment,
    score_climate,
    score_moisture,
    score_soil_ph,
    score_soil_quality,
    score_temperature,
)
from teratrend.trend_engine import analyze_point

log = logging.getLogger("teratrend.services.assessment")


def _classify_texture(sand: float, clay: float) -> str:
    """Classify USDA soil texture from sand and clay percentages."""
    silt = max(0.0, 100.0 - sand - clay)
    if clay >= 40.0:
        if sand >= 45.0:
            return "sandy_clay"
        elif silt >= 40.0:
            return "silty_clay"
        return "clay"
    elif clay >= 27.0:
        if sand >= 45.0:
            return "sandy_clay_loam"
        elif sand < 20.0:
            return "silty_clay_loam"
        return "clay_loam"
    elif clay >= 20.0 and sand >= 45.0:
        return "sandy_clay_loam"
    elif sand >= 70.0:
        if sand >= 85.0:
            return "sand"
        return "loamy_sand"
    elif sand >= 50.0:
        return "sandy_loam"
    elif silt >= 50.0:
        return "silt_loam"
    return "loam"


def _classify_drainage(texture: str, rainfall: float) -> str:
    """Classify soil drainage from texture and local rainfall."""
    if texture in ("sand", "loamy_sand"):
        return "excessively"
    elif texture in ("clay", "silty_clay", "heavy_clay"):
        return "imperfectly" if rainfall > 1300.0 else "moderately_well"
    elif texture in ("clay_loam", "silty_clay_loam"):
        return "moderately_well"
    return "well"


class AssessmentService:
    """Service orchestrating land assessments and results caching."""

    def __init__(self, store: Optional[CubeStore] = None) -> None:
        self.store = store or get_store()

    def _build_options_hash(self, options: Dict[str, Any]) -> str:
        """Create a deterministic hash string from request options."""
        clean_opts = {
            "area_ha": float(options.get("area_ha", 1.0)),
            "tenure": str(options.get("tenure", "owned")).lower(),
            "cost_basis": str(options.get("cost_basis", "a2_fl")).lower(),
            "price_basis": str(options.get("price_basis", "market")).lower(),
            "yield_override_q_ha": options.get("yield_override_q_ha"),
            "price_override_per_q": options.get("price_override_per_q"),
        }
        encoded = json.dumps(clean_opts, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:16]

    def _build_cache_key(
        self,
        cell_lat: float,
        cell_lon: float,
        state_id: Optional[int],
        district_id: Optional[int],
        crop_key: Optional[str],
        season: str,
        irrigation: str,
        options_hash: str,
        data_version: str,
    ) -> str:
        """Generate unique SHA-256 cache key matching DB unique constraint."""
        raw = f"{cell_lat:.4f}_{cell_lon:.4f}_{state_id}_{district_id}_{crop_key}_{season}_{irrigation}_{options_hash}_{data_version}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def assess_location(
        self,
        lat: float,
        lon: float,
        crop_param: Optional[str] = None,
        season_param: str = "annual",
        irrigation_param: str = "rainfed",
        options: Optional[Dict[str, Any]] = None,
        session: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """Process full land and economics assessment with transparent DB caching."""
        t0 = time.time()
        opts = options or {}
        store = self.store

        # 1. Resolve Location & Point-in-Polygon check
        grid_point = resolve_location(lat, lon, store)
        snap_lat = grid_point.snapped_lat
        snap_lon = grid_point.snapped_lon

        # Lookup state_id and district_id from ReferenceDataCache
        ref_cache = get_reference_cache()
        state_id: Optional[int] = None
        district_id: Optional[int] = None
        if grid_point.region and grid_point.region.state:
            st_obj = ref_cache.regions.get("state_map", {}).get(grid_point.region.state)
            if st_obj:
                state_id = getattr(st_obj, "id", None) or (st_obj.get("id") if isinstance(st_obj, dict) else None)

        options_hash = self._build_options_hash(opts)
        store_ver = getattr(store, "data_version", Config.CODE_VERSION)
        data_version = f"{store_ver}_{ref_cache.reference_version}"
        cache_key = self._build_cache_key(
            snap_lat,
            snap_lon,
            state_id,
            district_id,
            crop_param,
            season_param,
            irrigation_param,
            options_hash,
            data_version,
        )

        # 2. Check Database Cache
        if Config.CACHE_ENABLED:
            try:
                if session is not None:
                    cached_data = ResultsRepository(session).get_cached(cache_key)
                else:
                    with get_session() as s:
                        cached_data = ResultsRepository(s).get_cached(cache_key)
                        s.commit()

                if cached_data:
                    query_ms = round((time.time() - t0) * 1000.0, 1)
                    if "meta" in cached_data:
                        cached_data["meta"]["query_ms"] = query_ms
                        cached_data["meta"]["cache"] = "hit"
                    return cached_data
            except Exception as exc:
                log.warning("Database cache lookup failed, falling back to on-the-fly calculation: %s", exc)

        # 3. Compute Assessment On Miss
        result_dict = self._compute_fresh_assessment(
            grid_point=grid_point,
            snap_lat=snap_lat,
            snap_lon=snap_lon,
            crop_param=crop_param,
            season_param=season_param,
            irrigation_param=irrigation_param,
            options=opts,
            t0=t0,
        )

        # 4. Store in Cache
        if Config.CACHE_ENABLED:
            try:
                if session is not None:
                    ResultsRepository(session).put_cached(
                        cache_key=cache_key,
                        cell_lat=snap_lat,
                        cell_lon=snap_lon,
                        state_id=state_id,
                        district_id=district_id,
                        crop_key=crop_param,
                        season=season_param,
                        irrigation=irrigation_param,
                        options_hash=options_hash,
                        data_version=data_version,
                        result_json=result_dict,
                    )
                else:
                    with get_session() as s:
                        ResultsRepository(s).put_cached(
                            cache_key=cache_key,
                            cell_lat=snap_lat,
                            cell_lon=snap_lon,
                            state_id=state_id,
                            district_id=district_id,
                            crop_key=crop_param,
                            season=season_param,
                            irrigation=irrigation_param,
                            options_hash=options_hash,
                            data_version=data_version,
                            result_json=result_dict,
                        )
                        s.commit()
                result_dict["meta"]["cache"] = "miss"
            except Exception as exc:
                log.warning("Failed to store assessment in database cache: %s", exc)
                result_dict["meta"]["cache"] = "bypass"
        else:
            result_dict["meta"]["cache"] = "disabled"

        return result_dict

    def _compute_fresh_assessment(
        self,
        grid_point: Any,
        snap_lat: float,
        snap_lon: float,
        crop_param: Optional[str],
        season_param: str,
        irrigation_param: str,
        options: Dict[str, Any],
        t0: float,
    ) -> Dict[str, Any]:
        """Execute pure algorithmic calculations across datasets."""
        store = self.store
        area_ha = float(options.get("area_ha", 1.0))
        tenure = str(options.get("tenure", "owned")).lower()
        cost_basis = str(options.get("cost_basis", "a2_fl")).lower()
        price_basis = str(options.get("price_basis", "market")).lower()

        # Extract Temperature
        mean_temp = 25.0
        temp_trend = None
        if store.has_dataset("gldas"):
            try:
                temp_trend = analyze_point(store, snap_lat, snap_lon, "air_temperature", source="gldas")
                mean_temp = temp_trend.recent_mean
            except Exception:
                pass

        # Extract Moisture & Rainfall
        annual_rf = 800.0
        root_wet = 0.45
        rf_trend = None
        moist_trend = None
        rf_cv = 0.20
        drought_stats = {"drought_frequency_pct": 15.0, "wet_frequency_pct": 10.0}

        if store.has_dataset("gldas"):
            try:
                rf_trend = analyze_point(store, snap_lat, snap_lon, "rainfall", source="gldas")
                annual_rf = rf_trend.recent_mean
                rf_series = pd.Series([entry["value"] for entry in rf_trend.annual_values])
                stats = compute_interannual_stats(rf_series)
                rf_cv = stats["cv"]
                drought_stats = compute_drought_and_wet_frequencies(rf_series)
            except Exception:
                pass

            try:
                moist_trend = analyze_point(store, snap_lat, snap_lon, "root_moisture", source="gldas")
                if store.has_dataset("merra2"):
                    m2_trend = analyze_point(store, snap_lat, snap_lon, "root_moisture", source="merra2")
                    root_wet = float(np.clip(m2_trend.recent_mean, 0.0, 1.0))
                else:
                    root_wet = float(np.clip(moist_trend.recent_mean / 200.0, 0.05, 0.95))
            except Exception:
                pass

        # Soil Properties from HWSD
        top_ph = 6.8
        sub_ph = 7.0
        oc_pct = 1.2
        cec_val = 18.0
        tex_str = "loam"
        drain_str = "well"
        sal_ece = 1.2
        sod_esp = 4.0
        gravel = 5.0
        sand_pct = 40.0
        clay_pct = 25.0

        if store.has_dataset("hwsd"):
            hwsd_ds = store.get("hwsd")
            pt_soil = hwsd_ds.sel(lat=snap_lat, lon=snap_lon, method="nearest")
            top_ph = float(pt_soil.get("soil_ph_top", 6.8).values)
            if math.isnan(top_ph):
                top_ph = 6.8
            sub_ph = float(pt_soil.get("soil_ph_sub", top_ph).values)
            if math.isnan(sub_ph):
                sub_ph = top_ph
            oc_pct = float(pt_soil.get("soil_organic_carbon", 1.2).values)
            if math.isnan(oc_pct):
                oc_pct = 1.2
            cec_val = float(pt_soil.get("soil_cec", 18.0).values)
            if math.isnan(cec_val):
                cec_val = 18.0
            sal_ece = float(pt_soil.get("soil_salinity", 1.2).values)
            if math.isnan(sal_ece):
                sal_ece = 1.2
            sod_esp = float(pt_soil.get("soil_sodicity", 4.0).values)
            if math.isnan(sod_esp):
                sod_esp = 4.0
            gravel = float(pt_soil.get("soil_gravel", 5.0).values)
            if math.isnan(gravel):
                gravel = 5.0
            sand_pct = float(pt_soil.get("soil_sand", 40.0).values)
            if math.isnan(sand_pct):
                sand_pct = 40.0
            clay_pct = float(pt_soil.get("soil_clay", 25.0).values)
            if math.isnan(clay_pct):
                clay_pct = 25.0

        # Dynamically classify texture and drainage based on physical attributes
        tex_str = _classify_texture(sand_pct, clay_pct)
        drain_str = _classify_drainage(tex_str, annual_rf)

        # Score Factors
        factor_reports = {}
        factor_reports["temperature"] = score_temperature(mean_temp, temp_trend=temp_trend)
        factor_reports["moisture"] = score_moisture(
            annual_rainfall_mm=annual_rf,
            root_wetness=root_wet,
            irrigation=irrigation_param,
            rainfall_trend=rf_trend,
            moisture_trend=moist_trend,
        )
        factor_reports["soil_ph"] = score_soil_ph(top_ph, sub_ph)
        factor_reports["soil_quality"] = score_soil_quality(
            organic_carbon_pct=oc_pct,
            texture_class=tex_str,
            cec=cec_val,
            drainage_class=drain_str,
            salinity_ece=sal_ece,
            sodicity_esp=sod_esp,
            gravel_pct=gravel,
        )

        m_temps = {m: mean_temp for m in range(1, 13)}
        m_rf = {m: annual_rf / 12.0 for m in range(1, 13)}
        m_wet = {m: root_wet for m in range(1, 13)}
        factor_reports["climate"] = score_climate(
            monthly_temps=m_temps,
            monthly_rainfall=m_rf,
            monthly_wetness=m_wet,
            rainfall_cv=rf_cv,
        )

        # Overall Verdict
        ov_score, ov_rating, ov_verdict, limiting_facs, ov_conf = compute_overall_assessment(factor_reports)

        # Crop Ranking
        loc_features = {
            "mean_temperature_c": mean_temp,
            "annual_rainfall_mm": annual_rf,
            "topsoil_ph": top_ph,
            "texture": tex_str,
            "drainage": drain_str,
            "salinity_ece": sal_ece,
            "organic_carbon": oc_pct,
            "soil_sand": sand_pct,
            "soil_clay": clay_pct,
            "soil_sodicity": sod_esp,
            "moisture_score": factor_reports["moisture"].score,
            "temperature_score": factor_reports["temperature"].score,
            "rainfall_cv": rf_cv,
        }
        suited_crops, not_rec_crops = rank_crops(loc_features, season=None, irrigation=irrigation_param)

        selected_crop_key = crop_param if crop_param else (suited_crops[0].key if suited_crops else "wheat")

        climate_stats_dict = {
            "rainfall_cv": rf_cv,
            "drought_frequency_pct": drought_stats["drought_frequency_pct"],
            "wet_frequency_pct": drought_stats["wet_frequency_pct"],
            "thermal_stress_months": factor_reports["climate"].values.get("thermal_stress_months", 2),
        }

        econ_options = {
            "area_ha": area_ha,
            "tenure": tenure,
            "cost_basis": cost_basis,
            "price_basis": price_basis,
            "yield_override_q_ha": options.get("yield_override_q_ha"),
            "price_override_per_q": options.get("price_override_per_q"),
        }

        sel_crop_score_now = ov_score
        sel_crop_score_10y = ov_score
        for sc in suited_crops:
            if sc.key == selected_crop_key:
                sel_crop_score_now = sc.score
                break

        temp_trend_outlook = factor_reports["temperature"].trend
        if temp_trend_outlook and temp_trend_outlook.get("outlook") == "WORSENING":
            sel_crop_score_10y = max(0.0, sel_crop_score_now - 8.0)
        elif temp_trend_outlook and temp_trend_outlook.get("outlook") == "IMPROVING":
            sel_crop_score_10y = min(100.0, sel_crop_score_now + 8.0)

        full_econ_report = compute_economics(
            crop=selected_crop_key,
            region=grid_point.region,
            suitability_now=sel_crop_score_now,
            suitability_10y=sel_crop_score_10y,
            climate_stats=climate_stats_dict,
            options=econ_options,
        )

        all_crop_econ_reports: Dict[str, Any] = {}
        for sc in suited_crops:
            c_rep = compute_economics(
                crop=sc.key,
                region=grid_point.region,
                suitability_now=sc.score,
                climate_stats=climate_stats_dict,
                options=econ_options,
            )
            all_crop_econ_reports[sc.key] = c_rep
            if c_rep.available:
                sc.economics_summary = CropEconomicsSummary(
                    available=True,
                    net_return_per_ha=c_rep.returns_data.get("net_return_per_ha", {}).get("chosen"),
                    roi_pct=c_rep.returns_data.get("roi_pct", {}).get("chosen"),
                    probability_of_loss_pct=c_rep.risk_data.get("probability_of_loss_pct"),
                    verdict=c_rep.verdict.get("label"),
                )
            else:
                sc.economics_summary = CropEconomicsSummary(available=False)

        rankings_by_suit = [sc.key for sc in suited_crops]
        rankings_by_profit = [r.crop for r in rank_by_economics(list(all_crop_econ_reports.values()))]
        balanced_pick = select_balanced_crop(suited_crops, all_crop_econ_reports)

        industry_block = build_industry_factors(
            crop=selected_crop_key,
            state=grid_point.region.state,
            econ_report=full_econ_report,
            crop_factor_report=factor_reports["moisture"],
            climate_stats=climate_stats_dict,
            monthly_rainfall=m_rf,
        )

        improvements = generate_amendments(loc_features)

        consensus_res = None
        if store.has_dataset("gldas") and store.has_dataset("merra2"):
            try:
                consensus_res = consensus_for_group(store, snap_lat, snap_lon, "soil_moisture")
            except Exception:
                pass

        trend_advice = advise(
            indicator="root_moisture",
            trend_result=moist_trend,
            consensus=consensus_res,
            vegetation_support=(consensus_res.vegetation_confirms if consensus_res else None),
        )

        cov_notes = []
        if grid_point.fallback_used:
            cov_notes.append(
                f"Nearest land cell fallback used ({grid_point.fallback_distance_km:.1f} km) for coastal/island land-surface fields."
            )
        for ds_name, status in grid_point.layer_status.items():
            if status == "NO_DATA":
                cov_notes.append(f"Layer '{ds_name}' unavailable for this cell.")

        query_ms = round((time.time() - t0) * 1000.0, 1)

        meta_block = {
            "datasets_used": store.available(),
            "datasets_missing": [k for k in DATASETS if not store.has_dataset(k)],
            "doi": {k: DATASETS[k]["doi"] for k in store.available() if k in DATASETS},
            "economics_as_of": full_econ_report.data_quality.get("price_as_of", "2024-06"),
            "query_ms": query_ms,
        }

        report = AssessmentReport(
            location=grid_point,
            mode={
                "crop": crop_param,
                "season": season_param,
                "irrigation": irrigation_param,
                "baseline_years": [2015, 2024],
            },
            overall={
                "score": ov_score,
                "rating": ov_rating,
                "verdict": ov_verdict,
                "limiting_factors": limiting_facs,
                "confidence": ov_conf,
            },
            factors=factor_reports,
            suited_crops=suited_crops,
            not_recommended=not_rec_crops,
            rankings={
                "by_suitability": rankings_by_suit,
                "by_profit": rankings_by_profit,
                "balanced_pick": balanced_pick,
            },
            economics=full_econ_report,
            industry_factors=industry_block,
            improvements=improvements,
            trend_advice=trend_advice,
            coverage_notes=cov_notes,
            disclaimer="TeraTrend decision support is an indicative advisory for farm planning, not a guarantee of yields or prices. Combine with local soil testing and agricultural university advice.",
            meta=meta_block,
        )

        return report.to_dict()
