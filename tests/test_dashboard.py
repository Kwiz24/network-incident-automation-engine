"""HTTP smoke tests for the Phase 2 UI and API."""
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from app import server
from app.engine import init_db


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.original_db = server.DB
        server.DB = str(Path(cls.temp.name) / "dashboard.db")
        init_db(server.DB)
        cls.http = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.base = f"http://127.0.0.1:{cls.http.server_port}"
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join(timeout=3)
        server.DB = cls.original_db
        cls.temp.cleanup()

    def get(self, route):
        with urlopen(self.base + route, timeout=4) as response:
            return response.status, response.headers, response.read()

    def test_home_serves_html_and_assets(self):
        status, headers, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn(b"Network incident overview", body)
        for route, media in [("/styles.css", "text/css"), ("/app.js", "application/javascript")]:
            status, headers, body = self.get(route)
            self.assertEqual(status, 200)
            self.assertIn(media, headers["Content-Type"])
            self.assertTrue(body)

    def test_a_initial_dashboard_includes_events_and_maintenance(self):
        status, _, body = self.get("/dashboard")
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(data["total_events"], 0)
        self.assertEqual(data["events"], [])
        self.assertEqual(data["maintenance"], [])

    def test_alert_post_populates_dashboard(self):
        alert = {"event_id": "dashboard-test", "circuit_id": "test-circuit", "event_type": "LINK_DOWN", "timestamp": "2026-09-19T14:00:00Z", "customer_impact": False}
        request = Request(self.base + "/alerts", data=json.dumps(alert).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=4) as response:
            self.assertEqual(json.load(response)["decision"], "CREATED_INCIDENT")
        _, _, body = self.get("/dashboard")
        data = json.loads(body)
        self.assertEqual(data["total_events"], 1)
        self.assertEqual(data["events"][0]["event_id"], "dashboard-test")
        self.assertEqual(len(data["incidents"]), 1)

    def test_inventory_api_returns_mock_source(self):
        status, _, body = self.get("/inventory")
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertIn("not live NetBox", data["source"])
        self.assertEqual(len(data["circuits"]), 3)

    def test_static_path_not_exposed(self):
        with self.assertRaises(HTTPError) as caught:
            self.get("/app/engine.py")
        self.assertEqual(caught.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
