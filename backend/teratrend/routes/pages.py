"""TerraTrend web page routes serving HTML templates."""
from flask import Blueprint, render_template, redirect, url_for

pages_bp = Blueprint("pages", __name__)


@pages_bp.route("/")
def index():
    """Home landing page introducing TerraTrend and its 3 core pillars."""
    try:
        return render_template("index.html")
    except Exception:
        return (
            "<!DOCTYPE html><html><head><title>TerraTrend</title></head>"
            "<body><h1>TerraTrend</h1><p>Geospatial Agricultural Decision-Support for India (NASA Space Apps Challenge 2026).</p>"
            "<p><a href='/decision'>Launch Decision Engine</a> | <a href='/methodology'>Methodology & Science</a></p></body></html>",
            200,
            {"Content-Type": "text/html"}
        )


@pages_bp.route("/decision")
@pages_bp.route("/engine")
@pages_bp.route("/app")
def decision():
    """Core decision engine workspace: 5-factor land card, crops, and CACP economics."""
    try:
        return render_template("decision.html")
    except Exception:
        return (
            "<!DOCTYPE html><html><head><title>TerraTrend — Decision Engine</title></head>"
            "<body><h1>TerraTrend Decision Engine</h1><p>Land suitability report and CACP crop economics workspace.</p></body></html>",
            200,
            {"Content-Type": "text/html"}
        )


@pages_bp.route("/explorer")
def explorer():
    """Redirect legacy explorer route to the primary Decision Engine."""
    return redirect(url_for("pages.decision"))


@pages_bp.route("/methodology")
@pages_bp.route("/science")
def methodology():
    """Scientific methodology and CACP economics whitepaper documentation page."""
    try:
        return render_template("methodology.html")
    except Exception:
        return (
            "<!DOCTYPE html><html><head><title>TerraTrend Methodology</title></head>"
            "<body><h1>TerraTrend Methodology</h1><p>Modified Mann-Kendall trend detection, multi-dataset consensus, and CACP crop economics methodology.</p></body></html>",
            200,
            {"Content-Type": "text/html"}
        )
