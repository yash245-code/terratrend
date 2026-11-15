"""TerraTrend Admin & Operations Blueprint.

Provides protected endpoints for reloading in-memory reference tables, clearing assessment caches,
and diagnostic data health checks.
"""
from __future__ import annotations

import hmac
import logging
from typing import Optional
from flask import Blueprint, jsonify, request

from config import Config
from db.base import get_session
from db.repositories.economics_repo import EconomicsRepository
from db.repositories.results_repo import ResultsRepository
from teratrend.services.reference_cache import get_reference_cache

log = logging.getLogger("teratrend.routes.admin")
admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def _verify_admin_auth() -> bool:
    """Validate admin token using constant-time comparison."""
    if not Config.ADMIN_TOKEN:
        return False

    token = (
        request.headers.get("X-Admin-Token")
        or request.args.get("admin_token")
        or (
            request.headers.get("Authorization", "").replace("Bearer ", "").strip()
            if request.headers.get("Authorization", "").startswith("Bearer ")
            else ""
        )
    )

    if not token:
        return False

    return hmac.compare_digest(token.encode("utf-8"), Config.ADMIN_TOKEN.encode("utf-8"))


@admin_bp.before_request
def require_admin():
    """Enforce admin authentication on all routes in blueprint."""
    if not _verify_admin_auth():
        return jsonify({"error": "Unauthorized admin access", "code": "UNAUTHORIZED"}), 403


@admin_bp.route("/reload-reference", methods=["POST"])
def reload_reference():
    """Hot-reload in-memory reference cache from database."""
    try:
        cache = get_reference_cache()
        cache.reload()
        return jsonify({
            "status": "reloaded",
            "snapshot": cache.snapshot(),
        })
    except Exception as exc:
        log.error("Failed to reload reference cache: %s", exc, exc_info=True)
        return jsonify({"error": str(exc), "code": "RELOAD_FAILED"}), 500


@admin_bp.route("/cache/clear", methods=["POST"])
def clear_cache():
    """Clear all assessment cache entries."""
    try:
        with get_session() as session:
            repo = ResultsRepository(session)
            cleared = repo.clear()
            session.commit()
        return jsonify({"status": "cleared", "entries_removed": cleared})
    except Exception as exc:
        log.error("Failed to clear cache: %s", exc)
        return jsonify({"error": str(exc), "code": "CACHE_CLEAR_FAILED"}), 500


@admin_bp.route("/data-health", methods=["GET"])
def data_health():
    """Diagnostic report on reference table completeness, cache, and unverified data."""
    try:
        with get_session() as session:
            econ_repo = EconomicsRepository(session)
            matrix = econ_repo.coverage_matrix()

        ref_cache = get_reference_cache()
        return jsonify({
            "status": "healthy",
            "reference_version": ref_cache.reference_version,
            "counts": ref_cache.counts,
            "coverage": matrix,
        })
    except Exception as exc:
        log.error("Data health check failed: %s", exc)
        return jsonify({"error": str(exc), "code": "DATA_HEALTH_ERROR"}), 500
