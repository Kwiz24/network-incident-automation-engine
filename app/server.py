"""Local-only JSON HTTP API. No authentication: never expose to the Internet."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from .engine import add_maintenance, init_db, snapshot, triage

DB = os.environ.get("INCIDENT_DB", str(Path(__file__).resolve().parent.parent / "incidents.db"))

class Handler(BaseHTTPRequestHandler):
    def respond(self, status, payload):
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        route = urlsplit(self.path).path
        if route == "/health":
            return self.respond(200,{"status":"ok"})
        if route == "/dashboard":
            return self.respond(200,snapshot(DB))
        self.respond(404,{"error":"not found"})

    def do_POST(self):
        route = urlsplit(self.path).path
        if route not in ("/alerts","/maintenance"):
            return self.respond(404,{"error":"not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 65536:
                return self.respond(413,{"error":"body must be 1–65536 bytes"})
            data = json.loads(self.rfile.read(length))
            result = triage(DB,data) if route == "/alerts" else add_maintenance(DB,data)
            return self.respond(200 if result.get("decision")=="DUPLICATE_EVENT" else 201,result)
        except (ValueError,TypeError,json.JSONDecodeError) as exc:
            self.respond(400,{"error":str(exc)})

if __name__ == "__main__":
    init_db(DB)
    server = ThreadingHTTPServer(("127.0.0.1",8080),Handler)
    print("Running locally at http://127.0.0.1:8080 (Ctrl+C to stop)",flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
