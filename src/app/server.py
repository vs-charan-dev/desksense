"""
DeskSense Local Embedded API Server (Phase 3)
Serves a local HTTP/JSON API over localhost for the Desktop UI (Tauri / React).
Provides endpoints for dashboard metrics, live status, calibration wizard,
tray actions, hotkey toggling, and widget configuration.
Zero external network access; strictly localhost.
"""

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Optional

from src.app.core import DeskSenseApp
from src.app.tray import TrayCommand


class DeskSenseAPIHandler(BaseHTTPRequestHandler):
    app_instance: Optional[DeskSenseApp] = None

    def log_message(self, format, *args):
        # Silence default server stdout spam during tests/production
        pass

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        app = self.app_instance
        if not app:
            self._send_json({"error": "App instance not bound"}, 500)
            return

        if path == "/api/status":
            self._send_json(app.get_state().to_dict())

        elif path == "/api/dashboard":
            date_param = query.get("date", [None])[0]
            self._send_json(app.get_dashboard_data(target_date=date_param))

        elif path == "/api/wizard":
            self._send_json(app.wizard.get_status())

        elif path == "/api/widget":
            self._send_json(app.widget.to_dict())

        elif path == "/api/timeline":
            dash = app.get_dashboard_data()
            self._send_json({"timeline": dash.get("timeline", [])})

        elif path == "/api/categories":
            rules = app.db.get_category_rules()
            self._send_json({"rules": rules})

        elif path == "/api/summary":
            dash = app.get_dashboard_data()
            self._send_json(dash.get("summary", {}))

        elif path == "/api/health":
            self._send_json({"status": "HEALTHY", "is_running": app.is_running})

        else:
            self._send_json({"error": f"Unknown endpoint '{path}'"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        app = self.app_instance

        if not app:
            self._send_json({"error": "App instance not bound"}, 500)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        post_data = {}
        if content_length > 0:
            try:
                raw_body = self.rfile.read(content_length)
                post_data = json.loads(raw_body.decode("utf-8"))
            except Exception:
                post_data = {}

        if path == "/api/tray":
            cmd_str = post_data.get("command")
            try:
                cmd = TrayCommand(cmd_str)
                args = post_data.get("args", [])
                kwargs = post_data.get("kwargs", {})
                res = app.tray.dispatch(cmd, *args, **kwargs)
                self._send_json({"status": "ok", "command": cmd_str, "result": res})
            except ValueError:
                self._send_json({"error": f"Unknown tray command '{cmd_str}'"}, 400)

        elif path == "/api/hotkey/toggle":
            app.hotkey.trigger("Ctrl+Shift+P")
            self._send_json({"status": "ok", "state": app.get_state().to_dict()})

        elif path == "/api/wizard/start":
            app.start_calibration()
            self._send_json(app.wizard.get_status())

        elif path == "/api/wizard/countdown":
            app.wizard.begin_countdown()
            self._send_json(app.wizard.get_status())

        elif path == "/api/wizard/tick":
            app.wizard.update()
            self._send_json(app.wizard.get_status())

        elif path == "/api/wizard/sample":
            metrics = post_data.get("metrics")
            confidence = float(post_data.get("confidence", 1.0))
            finished, reason = app.wizard.add_sample(metrics, confidence)
            self._send_json({
                "finished": finished,
                "reason": reason,
                "status": app.wizard.get_status()
            })

        elif path == "/api/wizard/finish":
            success = app.finish_calibration()
            self._send_json({"success": success, "status": app.wizard.get_status()})

        elif path == "/api/wizard/retry":
            app.wizard.retry()
            self._send_json(app.wizard.get_status())

        elif path == "/api/wizard/cancel":
            app.cancel_calibration()
            self._send_json({"status": "cancelled", "wizard": app.wizard.get_status()})

        elif path == "/api/widget":
            if "x" in post_data and "y" in post_data:
                app.widget.set_position(post_data["x"], post_data["y"])
            if "opacity" in post_data:
                app.widget.set_opacity(post_data["opacity"])
            if "collapsed" in post_data:
                app.widget.collapsed = bool(post_data["collapsed"])
            if "enabled" in post_data:
                if post_data["enabled"]:
                    app.widget.enable()
                else:
                    app.widget.disable()
            self._send_json(app.widget.to_dict())

        elif path == "/api/categories/add":
            pattern = post_data.get("pattern", "")
            rule_type = post_data.get("rule_type", "process")
            category = post_data.get("category", "productive")
            rule_id = app.app_classifier.add_rule(pattern, rule_type, category)
            self._send_json({"status": "ok", "rule_id": rule_id, "rules": app.db.get_category_rules()})

        elif path == "/api/categories/delete":
            rule_id = int(post_data.get("rule_id", 0))
            pattern = post_data.get("pattern", "")
            rule_type = post_data.get("rule_type", "process")
            success = app.app_classifier.delete_rule(pattern, rule_type, rule_id=rule_id)
            self._send_json({"status": "ok" if success else "not_found", "rules": app.db.get_category_rules()})

        elif path == "/api/window/close":
            # Intercept close
            app.on_close_requested()
            self._send_json({"status": "hidden", "visible": app.window_visible})

        elif path == "/api/window/show":
            app.show_dashboard()
            self._send_json({"status": "visible", "visible": app.window_visible})

        else:
            self._send_json({"error": f"Unknown endpoint '{path}'"}, 404)


class EmbeddedAPIServer:
    def __init__(self, app: DeskSenseApp, host: str = "127.0.0.1", port: int = 0):
        self.app = app
        self.host = host
        self.port = port
        self.server: Optional[HTTPServer] = None
        self.thread: Optional[threading.Thread] = None

    def start(self) -> int:
        """Starts HTTP server in background thread, returns allocated port."""
        DeskSenseAPIHandler.app_instance = self.app
        self.server = HTTPServer((self.host, self.port), DeskSenseAPIHandler)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self.port

    def stop(self) -> None:
        """Stops background server cleanly."""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
            self.thread = None
