import os
import sys
from pathlib import Path

# Setup paths so backend modules and frontend templates are discoverable
ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"

for p in [str(ROOT_DIR), str(BACKEND_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from backend.app import app
except Exception as e:
    import traceback
    err_tb = traceback.format_exc()
    from flask import Flask, Response
    app = Flask(__name__)
    
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def diagnostic_fallback(path):
        return Response(
            f"<!DOCTYPE html><html><head><title>TerraTrend Diagnostics</title></head>"
            f"<body style='font-family:sans-serif; background:#06080d; color:#f8fafc; padding:32px;'>"
            f"<h2>TerraTrend Initialization Note</h2>"
            f"<pre style='background:#131a26; padding:16px; border-radius:8px; overflow:auto;'>{err_tb}</pre>"
            f"</body></html>",
            status=500,
            mimetype="text/html"
        )
