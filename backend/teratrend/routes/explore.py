"""TerraTrend Spatial Exploration Blueprint.

Serves precomputed territorial grid rankings and state suitability summaries.
"""
from __future__ import annotations

import logging
from flask import Blueprint, jsonify, request

from teratrend.services.explore_service import ExploreService

log = logging.getLogger("teratrend.routes.explore")
explore_bp = Blueprint("explore", __name__, url_prefix="/api/explore")
_explore_service = ExploreService()


@explore_bp.route("/best-places", methods=["GET"])
def best_places():
    """Return top precomputed grid cells for a given crop across India or within a state."""
    crop_key = request.args.get("crop", "wheat").strip().lower()
    state_name = request.args.get("state")
    limit = int(request.args.get("limit", 20))

    try:
        result = _explore_service.get_best_places(crop_key=crop_key, state_name=state_name, limit=limit)
        return jsonify(result)
    except Exception as exc:
        log.error("Failed to query best places: %s", exc)
        return jsonify({"error": str(exc), "code": "EXPLORE_ERROR"}), 500


@explore_bp.route("/state-summary", methods=["GET"])
def state_summary():
    """Return average and peak suitability scores grouped by state for a crop."""
    crop_key = request.args.get("crop", "wheat").strip().lower()

    try:
        result = _explore_service.get_state_summary(crop_key=crop_key)
        return jsonify(result)
    except Exception as exc:
        log.error("Failed to query state summary: %s", exc)
        return jsonify({"error": str(exc), "code": "EXPLORE_ERROR"}), 500
