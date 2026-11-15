"""TerraTrend Flask Web Application.

Geospatial agricultural decision-support web app for India.
NASA Space Apps Challenge 2026 ("Be An Earth System Trend Detective!").
"""
import logging
import os
import sys
from pathlib import Path

# Ensure backend root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from flask import Flask, jsonify

from config import Config
from db.base import close_db_session
from teratrend.cube_store import get_store
from teratrend.economics import load_data as load_economics_data
from teratrend.regions import load_boundaries
from teratrend.routes.admin import admin_bp
from teratrend.routes.api import api_bp
from teratrend.routes.explore import explore_bp
from teratrend.routes.pages import pages_bp
from teratrend.routes.saved import saved_bp
from teratrend.services.reference_cache import get_reference_cache

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("teratrend")


def create_app(config_class: type = Config) -> Flask:
    """Create and configure the Flask monolith application."""
    frontend_dir = BASE_DIR.parent / "frontend"
    template_folder = frontend_dir if frontend_dir.exists() else (BASE_DIR / "templates")
    static_folder = frontend_dir if frontend_dir.exists() else (BASE_DIR / "static")

    app = Flask(
        __name__,
        template_folder=str(template_folder),
        static_folder=str(static_folder),
        static_url_path="/static"
    )
    app.config.from_object(config_class)

    # 1. Preload administrative boundaries
    try:
        load_boundaries()
        log.info("Loaded India sovereign boundary GeoJSON into spatial index.")
    except Exception as e:
        log.warning(f"Boundary initialization note: {e}")

    # 2. Preload economic baseline datasets and in-memory reference cache
    try:
        ref_cache = get_reference_cache()
        app.extensions["reference_cache"] = ref_cache
        log.info(f"Loaded reference database cache (version: {ref_cache.reference_version}).")
    except Exception as e:
        log.warning(f"Reference cache initialization note: {e}")

    # 3. Preload all available NetCDF cubes into RAM
    try:
        store = get_store()
        app.extensions["cubes"] = store
        operational, missing = store.is_operational()
        if operational:
            log.info("TerraTrend CubeStore fully operational in RAM.")
        else:
            log.warning(f"CubeStore operating in degraded mode. Missing required: {missing}")
    except Exception as e:
        log.error(f"Failed to initialize CubeStore: {e}")

    # 4. Register session cleanup
    app.teardown_appcontext(close_db_session)

    # 5. Register Blueprints
    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(saved_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(explore_bp)

    # Global Error Handlers
    @app.errorhandler(404)
    def handle_404(e):
        return jsonify({"error": "Resource not found", "code": "NOT_FOUND"}), 404

    @app.errorhandler(500)
    def handle_500(e):
        log.error(f"Internal server error: {e}")
        return jsonify({"error": "Internal server error", "code": "INTERNAL_ERROR"}), 500

    return app


app = create_app()

if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    log.info(f"Starting TerraTrend backend server on http://{host}:{port}")
    app.run(host=host, port=port, debug=app.config.get("DEBUG", False))
