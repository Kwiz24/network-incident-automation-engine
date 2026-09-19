"""Phase 3 enrichment, cautious routing, migration, and mock inventory API."""
import json
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from urllib.request import urlopen

from app.engine import init_db, snapshot, triage
from app.inventory import inventory_snapshot, load_inventory
BASE = {"event_id":"evt-1", "circuit_id":"circuit-42", "event_type":"LINK_DOWN",
        "timestamp":"2026-09-19T14:00:00Z", "customer_impact":False}


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp.name) / "incident.db")
        init_db(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def test_seed_inventory_and_known_circuit_routing(self):
        inventory = inventory_snapshot(self.db)
        self.assertEqual(len(inventory["devices"]), 3)
        self.assertEqual(len(inventory["circuits"]), 3)
        result = triage(self.db, BASE)
        self.assertEqual(result["owner_team"], "Backbone Operations")
        self.assertEqual(result["device_id"], "edge-dfw-01")
        self.assertEqual(result["routing_status"], "ROUTED")
        self.assertEqual(result["priority"], "P2")
        self.assertEqual(snapshot(self.db)["routing"]["routed_open"], 1)

    def test_unknown_circuit_never_guesses_owner(self):
        result = triage(self.db, {**BASE, "event_id": "unknown", "circuit_id": "circuit-not-listed"})
        self.assertIsNone(result["owner_team"])
        self.assertEqual(result["routing_status"], "MANUAL_REVIEW")
        self.assertEqual(snapshot(self.db)["routing"]["manual_review_open"], 1)

    def test_related_circuits_show_context_but_do_not_merge(self):
        first = triage(self.db, BASE)
        second = triage(self.db, {**BASE, "event_id": "next", "circuit_id": "circuit-43"})
        self.assertNotEqual(first["incident_id"], second["incident_id"])
        self.assertEqual(second["related_incident_ids"], [first["incident_id"]])

    def test_escalation_upgrades_priority(self):
        triage(self.db, BASE)
        result = triage(self.db, {**BASE, "event_id": "impact", "customer_impact": True})
        self.assertEqual(result["decision"], "ESCALATE_UPDATED_INCIDENT")
        self.assertEqual(snapshot(self.db)["incidents"][0]["priority"], "P1")

    def test_initialization_is_idempotent_and_does_not_erase_existing(self):
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("UPDATE inventory_circuits SET owner_team='Demo Custom Team' WHERE circuit_id='circuit-42'")
        init_db(self.db)
        self.assertEqual(triage(self.db, BASE)["owner_team"], "Demo Custom Team")
        self.assertEqual(len(inventory_snapshot(self.db)["circuits"]), 3)

    def test_migrate_phase2_database_preserves_ticket_id(self):
        old = str(Path(self.temp.name) / "old.db")
        with closing(sqlite3.connect(old)) as conn, conn:
            conn.executescript("""CREATE TABLE incidents (id INTEGER PRIMARY KEY AUTOINCREMENT,
            circuit_id TEXT NOT NULL,event_type TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'open',
            first_seen TEXT NOT NULL,last_seen TEXT NOT NULL,event_count INTEGER NOT NULL DEFAULT 1,
            UNIQUE(circuit_id,event_type,status));
            CREATE TABLE events (event_id TEXT PRIMARY KEY,circuit_id TEXT NOT NULL,event_type TEXT NOT NULL,
            received_at TEXT NOT NULL,decision TEXT NOT NULL,incident_id INTEGER);
            CREATE TABLE maintenance (id INTEGER PRIMARY KEY AUTOINCREMENT,circuit_id TEXT NOT NULL,
            start TEXT NOT NULL,end TEXT NOT NULL,approved INTEGER NOT NULL);""")
            conn.execute("INSERT INTO incidents (id,circuit_id,event_type,first_seen,last_seen) VALUES (7,'circuit-42','LINK_DOWN','2026-09-19T14:00:00+00:00','2026-09-19T14:00:00+00:00')")
            conn.execute("INSERT INTO events VALUES (?,?,?,?,?,?)", ('old-impact','circuit-42','LINK_DOWN','2026-09-19T14:00:00+00:00','ESCALATE_CREATED_INCIDENT',7))
        init_db(old)
        item = snapshot(old)["incidents"][0]
        self.assertEqual(item["id"], 7)
        self.assertEqual(item["owner_team"], "Backbone Operations")
        self.assertEqual(item["priority"], "P1")
        init_db(old)
        self.assertEqual(len(snapshot(old)["incidents"]), 1)

    def test_reject_invalid_inventory_reference(self):
        invalid = Path(self.temp.name) / "invalid.json"
        invalid.write_text(json.dumps({"devices": [], "circuits": [{"circuit_id":"c", "device_id":"missing", "interface_name":"x", "provider":"p", "owner_team":"t"}]}))
        with self.assertRaises(ValueError):
            load_inventory(invalid)


if __name__ == "__main__":
    unittest.main()
