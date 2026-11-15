"""TeraTrend REST API Blueprint.

Serves all geospatial assessment, trend analysis, crop ranking,
and enterprise agricultural economics endpoints.
"""
import json
import logging
import math
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
from flask import Blueprint, current_app, jsonify, request

from config import (
    BASELINE_YEARS, DATASETS, INDICATORS, PROVENANCE_JSON, RATING_GOOD_THRESHOLD,
    RATING_MODERATE_THRESHOLD
)
from teratrend.advisor import advise
from teratrend.amendments import generate_amendments
from teratrend.climatology import compute_drought_and_wet_frequencies, compute_interannual_stats, extract_seasonal_window
from teratrend.consensus import CONSENSUS_GROUPS, consensus_for_group
from teratrend.crops import load_crop_requirements, rank_crops, score_single_crop
from teratrend.cube_store import CubeStore, get_store
from teratrend.economics import (
    compute_economics, get_economics_store, load_data as load_economics_data,
    rank_by_economics, select_balanced_crop
)
from teratrend.geo import resolve_location
from teratrend.geocode import geocode as run_geocode
from teratrend.industry import build_industry_factors
from teratrend.regions import OutOfIndiaError, locate
from teratrend.schemas import AssessmentReport, CropEconomicsSummary
from teratrend.soilgrids import fetch_soilgrids_supplement
from teratrend.suitability import (
    compute_overall_assessment, score_climate, score_moisture, score_soil_ph,
    score_soil_quality, score_temperature
)
from teratrend.trend_engine import InsufficientDataError, analyze_point
from db.base import get_session
from db.repositories.results_repo import ResultsRepository
from teratrend.services.assessment_service import AssessmentService

log = logging.getLogger("teratrend")
api_bp = Blueprint("api", __name__, url_prefix="/api")

# In-memory query cache
_ASSESS_CACHE: Dict[str, Dict[str, Any]] = {}


def _get_active_store() -> CubeStore:
    """Retrieve CubeStore from Flask extension or singleton."""
    if current_app and "cubes" in current_app.extensions:
        return current_app.extensions["cubes"]
    return get_store()


@api_bp.route("/health")
def health():
    """System health and operational status check."""
    store = _get_active_store()
    operational, missing = store.is_operational()
    return jsonify({
        "status": "healthy" if operational else "degraded",
        "operational": operational,
        "missing_required_layers": missing,
        "loaded_cubes": store.available(),
        "total_ram_mb": round(store.total_ram_mb, 1),
        "app": "TeraTrend",
        "scope": "India (Government of India Official Territory)"
    }), (200 if operational else 503)


@api_bp.route("/datasets")
def list_datasets():
    """List registered NASA & soil datasets and their loaded status."""
    store = _get_active_store()
    results = {}
    for k, meta in DATASETS.items():
        results[k] = {
            "label": meta["label"],
            "provider": meta["provider"],
            "collection": meta["collection"],
            "version": meta["version"],
            "doi": meta["doi"],
            "required": meta["required"],
            "static": meta["static"],
            "loaded": store.has_dataset(k),
            "coverage": store.coverage(k)
        }
    return jsonify(results)


@api_bp.route("/indicators")
def list_indicators():
    """List registered agricultural and climate indicators."""
    return jsonify(INDICATORS)


@api_bp.route("/provenance")
def get_provenance():
    """Return data provenance records if available."""
    if PROVENANCE_JSON.exists():
        with open(PROVENANCE_JSON, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    return jsonify({"provenance_available": False, "note": "Run pipeline to generate complete provenance.json"})


@api_bp.route("/region")
def lookup_region():
    """Lookup state and district for Indian coordinates."""
    lat_str = request.args.get("lat")
    lon_str = request.args.get("lon")
    if not lat_str or not lon_str:
        return jsonify({"error": "Missing required query parameters: 'lat' and 'lon'", "code": "BAD_REQUEST"}), 400

    try:
        lat = float(lat_str)
        lon = float(lon_str)
        reg = locate(lat, lon)
        return jsonify(reg.to_dict())
    except OutOfIndiaError as e:
        return jsonify({"error": str(e), "code": "OUT_OF_INDIA"}), 422
    except ValueError:
        return jsonify({"error": "Latitude and longitude must be valid floating point numbers", "code": "BAD_REQUEST"}), 400


@api_bp.route("/geocode")
def geocode_endpoint():
    """Resolve Indian place name to coordinates."""
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "Missing required parameter 'q'", "code": "BAD_REQUEST"}), 400

    q_norm = q.lower()
    try:
        with get_session() as session:
            repo = ResultsRepository(session)
            cached_res = repo.get_geocode(q_norm)
            if cached_res is not None:
                return jsonify(cached_res)
    except Exception:
        pass

    res = run_geocode(q)
    try:
        with get_session() as session:
            repo = ResultsRepository(session)
            repo.put_geocode(q_norm, res)
            session.commit()
    except Exception:
        pass

    return jsonify(res)


@api_bp.route("/crops")
def list_crops():
    """List all registered crops and their agronomic requirements."""
    reqs = load_crop_requirements()
    return jsonify(reqs)


@api_bp.route("/economics/coverage")
def economics_coverage():
    """Return crop x state coverage and data freshness report for official economics."""
    load_economics_data()
    costs, yields, prices, inps, policy = get_economics_store()

    crop_state_matrix: Dict[str, List[str]] = {}
    for r in costs:
        crop_state_matrix.setdefault(r["crop"], []).append(r["state"])

    return jsonify({
        "total_cost_records": len(costs),
        "total_yield_records": len(yields),
        "crops_count": len(crop_state_matrix),
        "coverage_matrix": crop_state_matrix,
        "as_of": "2024-06",
        "staleness": "All records reference official CACP / DES publications within 24 months."
    })


@api_bp.route("/assess")
def assess():
    """Primary TeraTrend land assessment and crop decision-support endpoint."""
    t0 = time.time()
    store = _get_active_store()

    operational, missing = store.is_operational()
    if not operational:
        return jsonify({
            "error": f"Required data layers missing: {', '.join(missing)}. TeraTrend cannot process assessments.",
            "code": "REQUIRED_LAYERS_MISSING"
        }), 503

    # Parse arguments
    lat_str = request.args.get("lat")
    lon_str = request.args.get("lon")
    if not lat_str or not lon_str:
        return jsonify({"error": "Missing required parameters: 'lat' and 'lon'", "code": "BAD_REQUEST"}), 400

    try:
        lat = float(lat_str)
        lon = float(lon_str)
    except ValueError:
        return jsonify({"error": "Latitude and longitude must be valid numbers", "code": "BAD_REQUEST"}), 400

    crop_param = request.args.get("crop")
    season_param = request.args.get("season", "annual").lower()
    irrigation_param = request.args.get("irrigation", "rainfed").lower()
    area_ha = float(request.args.get("area_ha", 1.0))
    tenure = request.args.get("tenure", "owned").lower()
    cost_basis = request.args.get("cost_basis", "a2_fl").lower()
    price_basis = request.args.get("price_basis", "market").lower()

    if irrigation_param not in ["rainfed", "irrigated"]:
        return jsonify({"error": "Invalid irrigation parameter. Must be 'rainfed' or 'irrigated'", "code": "BAD_REQUEST"}), 400

    if tenure not in ["owned", "leased"]:
        return jsonify({"error": "Invalid tenure parameter. Must be 'owned' or 'leased'", "code": "BAD_REQUEST"}), 400

    if cost_basis not in ["a2_fl", "c2"]:
        return jsonify({"error": "Invalid cost_basis. Must be 'a2_fl' or 'c2'", "code": "BAD_REQUEST"}), 400

    if price_basis not in ["market", "msp"]:
        return jsonify({"error": "Invalid price_basis. Must be 'market' or 'msp'", "code": "BAD_REQUEST"}), 400

    # 1. Process Assessment via AssessmentService
    try:
        svc = AssessmentService(store=store)
        opts = {
            "area_ha": area_ha,
            "tenure": tenure,
            "cost_basis": cost_basis,
            "price_basis": price_basis,
            "yield_override_q_ha": request.args.get("yield_override_q_ha"),
            "price_override_per_q": request.args.get("price_override_per_q"),
        }
        res = svc.assess_location(
            lat=lat,
            lon=lon,
            crop_param=crop_param,
            season_param=season_param,
            irrigation_param=irrigation_param,
            options=opts,
        )
        return jsonify(res)
    except OutOfIndiaError as e:
        return jsonify({"error": str(e), "code": "OUT_OF_INDIA"}), 422
    except ValueError as e:
        return jsonify({"error": str(e), "code": "BAD_REQUEST"}), 400


@api_bp.route("/economics", methods=["GET", "POST"])
def economics_endpoint():
    """Standalone crop economics and scenario analysis endpoint."""
    store = _get_active_store()

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        lat = data.get("lat")
        lon = data.get("lon")
        crop = data.get("crop", "wheat")
        options = {
            "area_ha": data.get("area_ha", 1.0),
            "tenure": data.get("tenure", "owned"),
            "cost_basis": data.get("cost_basis", "a2_fl"),
            "price_basis": data.get("price_basis", "market"),
            "yield_override_q_ha": data.get("yield_override_q_ha"),
            "price_override_per_q": data.get("price_override_per_q"),
            "cost_multiplier": data.get("cost_multiplier", 1.0)
        }
    else:
        lat = request.args.get("lat")
        lon = request.args.get("lon")
        crop = request.args.get("crop", "wheat")
        options = {
            "area_ha": float(request.args.get("area_ha", 1.0)),
            "tenure": request.args.get("tenure", "owned"),
            "cost_basis": request.args.get("cost_basis", "a2_fl"),
            "price_basis": request.args.get("price_basis", "market"),
            "cost_multiplier": float(request.args.get("cost_multiplier", 1.0))
        }

    if lat is None or lon is None:
        return jsonify({"error": "Missing 'lat' and 'lon'", "code": "BAD_REQUEST"}), 400

    try:
        flat = float(lat)
        flon = float(lon)
        reg = locate(flat, flon)
    except OutOfIndiaError as e:
        return jsonify({"error": str(e), "code": "OUT_OF_INDIA"}), 422
    except ValueError:
        return jsonify({"error": "Invalid numeric coordinates", "code": "BAD_REQUEST"}), 400

    rep = compute_economics(
        crop=crop,
        region=reg,
        suitability_now=80.0,
        options=options
    )
    return jsonify(rep.to_dict())


@api_bp.route("/analyze")
def analyze():
    """Run Modified Mann-Kendall and Sen's slope trend test for point and indicator."""
    store = _get_active_store()
    lat_str = request.args.get("lat")
    lon_str = request.args.get("lon")
    indicator = request.args.get("indicator") or request.args.get("variable")
    source = request.args.get("source")

    if not lat_str or not lon_str or not indicator:
        return jsonify({"error": "Missing required parameters: lat, lon, and indicator (or variable)", "code": "BAD_REQUEST"}), 400

    try:
        lat = float(lat_str)
        lon = float(lon_str)
        # Check in India
        locate(lat, lon)
    except OutOfIndiaError as e:
        return jsonify({"error": str(e), "code": "OUT_OF_INDIA"}), 422
    except ValueError:
        return jsonify({"error": "Coordinates must be numbers", "code": "BAD_REQUEST"}), 400

    if indicator not in INDICATORS:
        return jsonify({"error": f"Unknown indicator '{indicator}'. Valid: {list(INDICATORS.keys())}", "code": "BAD_REQUEST"}), 400

    try:
        res = analyze_point(store, lat, lon, indicator, source=source)
        return jsonify(res.to_dict())
    except InsufficientDataError as e:
        return jsonify({"error": str(e.message), "code": "INSUFFICIENT_DATA"}), 422
    except KeyError as e:
        return jsonify({"error": str(e), "code": "SOURCE_NOT_LOADED"}), 422


@api_bp.route("/consensus")
def consensus_endpoint():
    """Evaluate multi-dataset consensus for indicator group on overlapping years."""
    store = _get_active_store()
    lat_str = request.args.get("lat")
    lon_str = request.args.get("lon")
    group = request.args.get("group")

    if not lat_str or not lon_str or not group:
        return jsonify({"error": "Missing parameters: lat, lon, and group", "code": "BAD_REQUEST"}), 400

    try:
        lat = float(lat_str)
        lon = float(lon_str)
        locate(lat, lon)
    except OutOfIndiaError as e:
        return jsonify({"error": str(e), "code": "OUT_OF_INDIA"}), 422
    except ValueError:
        return jsonify({"error": "Coordinates must be numbers", "code": "BAD_REQUEST"}), 400

    if group not in CONSENSUS_GROUPS:
        return jsonify({"error": f"Unknown group '{group}'. Valid: {list(CONSENSUS_GROUPS.keys())}", "code": "BAD_REQUEST"}), 400

    res = consensus_for_group(store, lat, lon, group)
    return jsonify(res.to_dict())
