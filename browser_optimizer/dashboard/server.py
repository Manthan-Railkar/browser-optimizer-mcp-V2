"""
Lightweight dashboard HTTP server using Python's built-in http.server.
Serves the dashboard UI and exposes a JSON API for live metrics polling.
Runs on port 8050 alongside the MCP stdio server.
"""

import json
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from browser_optimizer.metrics.metrics import metrics
from browser_optimizer.cache.db import macro_store
from browser_optimizer.utils.logger import logger


DASHBOARD_DIR = Path(__file__).parent
DASHBOARD_PORT = 8050


class DashboardHandler(SimpleHTTPRequestHandler):
    """
    Custom request handler that serves the dashboard HTML and a JSON metrics API.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DASHBOARD_DIR), **kwargs)

    def do_GET(self):
        if self.path == "/api/metrics":
            self._serve_metrics()
        elif self.path == "/" or self.path == "/index.html":
            self._serve_dashboard()
        else:
            super().do_GET()

    def _serve_metrics(self):
        """Return live metrics + macro stats as JSON."""
        stats = metrics.get_stats()

        # Enrich with macro data
        all_macros = macro_store.list_macros()
        macro_summary = []
        for m in all_macros:
            macro_summary.append({
                "id": m["id"],
                "name": m["name"],
                "page_type": m["page_type"],
                "confidence": m["confidence"],
                "success_count": m["success_count"],
                "fail_count": m["fail_count"],
                "steps": len(m.get("sequence", []))
            })

        stats["macros"] = macro_summary
        stats["macro_count"] = len(all_macros)

        # Estimated cost savings (rough: $0.002 per 1K tokens, ~4 chars per token)
        tokens_saved = stats.get("bytes_saved_total", 0) / 4
        stats["estimated_tokens_saved"] = int(tokens_saved)
        stats["estimated_cost_saved_usd"] = round(tokens_saved / 1000 * 0.002, 4)

        body = json.dumps(stats).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_dashboard(self):
        """Serve the index.html dashboard file."""
        index_path = DASHBOARD_DIR / "index.html"
        if index_path.exists():
            content = index_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_error(404, "Dashboard not found")

    def log_message(self, format, *args):
        """Suppress default HTTP logs to avoid cluttering MCP stdio."""
        pass


def start_dashboard_server():
    """Launch the dashboard HTTP server in a background daemon thread."""
    try:
        server = HTTPServer(("0.0.0.0", DASHBOARD_PORT), DashboardHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info(f"Dashboard server started at http://localhost:{DASHBOARD_PORT}")
        return server
    except OSError as e:
        logger.warning(f"Could not start dashboard server on port {DASHBOARD_PORT}: {e}")
        return None
