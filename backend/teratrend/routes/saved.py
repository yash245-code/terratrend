"""TerraTrend Saved Farm Locations and Scenarios Blueprint.

Provides anonymous, cookie-backed storage for farmers' saved fields and economics runs.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional, Tuple
from flask import Blueprint, jsonify, make_response, request, Response

from config import Config
from teratrend.services.saved_service import SavedService
from db.repositories.clients_repo import LimitExceededError

log = logging.getLogger("teratrend.routes.saved")
saved_bp = Blueprint("saved", __name__, url_prefix="/api")

def _get_saved_service() -> SavedService:
    """Retrieve SavedService wired with active CubeStore from current_app."""
    from flask import current_app
    store = current_app.extensions.get("cubes") if current_app else None
    from teratrend.services.assessment_service import AssessmentService
    assessment_svc = AssessmentService(store) if store else None
    return SavedService(assessment_service=assessment_svc)
COOKIE_NAME = "tt_client_id"


def _resolve_client() -> Tuple[str, bool]:
    """Retrieve existing client UUID from cookie or mint a new one."""
    client_id = request.cookies.get(COOKIE_NAME)
    is_new = False
    if client_id:
        try:
            uuid.UUID(client_id)
        except ValueError:
            client_id = None

    if not client_id:
        client_id = str(uuid.uuid4())
        is_new = True

    actual_id = _get_saved_service().get_or_create_client(client_id)
    return actual_id, is_new


def _attach_cookie(resp: Response, client_id: str) -> Response:
    """Set persistent anonymous client session cookie."""
    resp.set_cookie(
        COOKIE_NAME,
        client_id,
        max_age=365 * 24 * 3600,
        httponly=True,
        samesite="Lax",
        secure=Config.COOKIE_SECURE,
    )
    return resp


@saved_bp.route("/me", methods=["GET"])
def get_client_profile():
    """Return anonymous client profile and count of saved items."""
    client_id, is_new = _resolve_client()
    locs = _get_saved_service().list_locations(client_id)
    scens = _get_saved_service().list_scenarios(client_id)

    resp = make_response(jsonify({
        "client_id": client_id,
        "saved_locations_count": len(locs),
        "saved_scenarios_count": len(scens),
        "limits": {
            "locations": Config.SAVED_LOCATION_LIMIT,
            "scenarios": Config.SAVED_SCENARIO_LIMIT,
        }
    }))
    return _attach_cookie(resp, client_id)


@saved_bp.route("/me", methods=["DELETE"])
def delete_client_profile():
    """Wipe all saved data associated with this client."""
    client_id, _ = _resolve_client()
    _get_saved_service().delete_client_data(client_id)
    resp = make_response(jsonify({"status": "deleted", "message": "All saved data wiped."}))
    resp.delete_cookie(COOKIE_NAME)
    return resp


@saved_bp.route("/saved/locations", methods=["GET"])
def list_locations():
    """List all saved locations for the active client."""
    client_id, is_new = _resolve_client()
    locs = _get_saved_service().list_locations(client_id)
    resp = make_response(jsonify({"locations": locs, "count": len(locs)}))
    if is_new:
        resp = _attach_cookie(resp, client_id)
    return resp


@saved_bp.route("/saved/locations", methods=["POST"])
def save_location():
    """Save a new plot location."""
    client_id, _ = _resolve_client()
    data = request.get_json(silent=True) or {}

    label = data.get("label", "").strip()
    lat = data.get("lat")
    lon = data.get("lon")

    if not label:
        return jsonify({"error": "Missing required field: 'label'", "code": "BAD_REQUEST"}), 400
    if lat is None or lon is None:
        return jsonify({"error": "Missing required coordinates: 'lat' and 'lon'", "code": "BAD_REQUEST"}), 400

    try:
        lat_val = float(lat)
        lon_val = float(lon)
    except ValueError:
        return jsonify({"error": "Coordinates must be valid numbers", "code": "BAD_REQUEST"}), 400

    try:
        saved = _get_saved_service().save_location(client_id=client_id, label=label, lat=lat_val, lon=lon_val)
        resp = make_response(jsonify(saved), 201)
        return _attach_cookie(resp, client_id)
    except LimitExceededError as exc:
        return jsonify({"error": str(exc), "code": "LIMIT_EXCEEDED"}), 429


@saved_bp.route("/saved/locations/<int:loc_id>", methods=["DELETE"])
def delete_location(loc_id: int):
    """Delete a saved location."""
    client_id, _ = _resolve_client()
    deleted = _get_saved_service().delete_location(client_id, loc_id)
    if not deleted:
        return jsonify({"error": "Location not found or unauthorized", "code": "NOT_FOUND"}), 404
    return jsonify({"status": "deleted", "location_id": loc_id})


@saved_bp.route("/saved/scenarios", methods=["GET"])
def list_scenarios():
    """List all saved scenarios for the active client."""
    client_id, is_new = _resolve_client()
    scens = _get_saved_service().list_scenarios(client_id)
    resp = make_response(jsonify({"scenarios": scens, "count": len(scens)}))
    if is_new:
        resp = _attach_cookie(resp, client_id)
    return resp


@saved_bp.route("/saved/scenarios", methods=["POST"])
def save_scenario():
    """Save a new farm scenario and result snapshot."""
    client_id, _ = _resolve_client()
    data = request.get_json(silent=True) or {}

    label = data.get("label", "").strip()
    crop_key = data.get("crop_key", "").strip()
    options = data.get("options", {})
    snapshot = data.get("snapshot_json", {})
    data_version = data.get("data_version", "v1.0.0")
    location_id = data.get("location_id")

    if not label or not crop_key:
        return jsonify({"error": "Missing 'label' or 'crop_key'", "code": "BAD_REQUEST"}), 400
    if not snapshot:
        return jsonify({"error": "Missing 'snapshot_json' result payload", "code": "BAD_REQUEST"}), 400

    try:
        saved = _get_saved_service().save_scenario(
            client_id=client_id,
            location_id=int(location_id) if location_id else None,
            label=label,
            crop_key=crop_key,
            options=options,
            snapshot_json=snapshot,
            data_version=data_version,
        )
        resp = make_response(jsonify(saved), 201)
        return _attach_cookie(resp, client_id)
    except LimitExceededError as exc:
        return jsonify({"error": str(exc), "code": "LIMIT_EXCEEDED"}), 429


@saved_bp.route("/saved/scenarios/<int:scen_id>", methods=["GET"])
def get_scenario(scen_id: int):
    """Fetch single saved scenario."""
    client_id, _ = _resolve_client()
    scen = _get_saved_service().get_scenario(client_id, scen_id)
    if not scen:
        return jsonify({"error": "Scenario not found", "code": "NOT_FOUND"}), 404
    return jsonify(scen)


@saved_bp.route("/saved/scenarios/<int:scen_id>", methods=["DELETE"])
def delete_scenario(scen_id: int):
    """Delete single saved scenario."""
    client_id, _ = _resolve_client()
    deleted = _get_saved_service().delete_scenario(client_id, scen_id)
    if not deleted:
        return jsonify({"error": "Scenario not found", "code": "NOT_FOUND"}), 404
    return jsonify({"status": "deleted", "scenario_id": scen_id})


@saved_bp.route("/saved/scenarios/<int:scen_id>/run", methods=["POST"])
def rerun_scenario(scen_id: int):
    """Rerun scenario and compare against baseline snapshot."""
    client_id, _ = _resolve_client()
    try:
        result = _get_saved_service().rerun_scenario(client_id, scen_id)
        if not result:
            return jsonify({"error": "Scenario not found", "code": "NOT_FOUND"}), 404
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"error": str(exc), "code": "BAD_REQUEST"}), 400
    except Exception as exc:
        log.error("Failed to rerun scenario: %s", exc, exc_info=True)
        return jsonify({"error": f"Scenario rerun failed: {exc}", "code": "SERVER_ERROR"}), 500
