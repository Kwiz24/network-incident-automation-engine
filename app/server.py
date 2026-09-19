"""Loopback-only demo API and dashboard. No authentication; never expose publicly."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .engine import add_maintenance, init_db, snapshot, triage

ROOT = Path(__file__).resolve().parent
DB = os.environ.get("INCIDENT_DB", str(ROOT.parent / "incidents.db"))
STATIC = ROOT / "static"
STATIC_ROUTES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
}


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, payload):
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        route = urlsplit(self.path).path
        if route in STATIC_ROUTES:
            filename, content_type = STATIC_ROUTES[route]
            data = (STATIC / filename).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if route == "/health":
            return self.respond(200, {"status": "ok"})
        if route == "/dashboard":
            return self.respond(200, snapshot(DB))
        return self.respond(404, {"error": "not found"})

    def do_POST(self):
        route = urlsplit(self.path).path
        if route not in ("/alerts", "/maintenance"):
            return self.respond(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 65536:
                return self.respond(413, {"error": "body must be 1–65536 bytes"})
            data = json.loads(self.rfile.read(length))
            result = triage(DB, data) if route == "/alerts" else add_maintenance(DB, data)
            return self.respond(200 if result.get("decision") == "DUPLICATE_EVENT" else 201, result)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            return self.respond(400, {"error": str(exc)})


def main():
    init_db(DB)
    server = ThreadingHTTPServer(("127.0.0.1", 8080), Handler)
    print("Dashboard: http://127.0.0.1:8080/ (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
