import tempfile
import unittest
from pathlib import Path
from app.engine import add_maintenance,init_db,snapshot,triage

BASE = {"event_id":"evt-1","circuit_id":"circuit-42","event_type":"LINK_DOWN","timestamp":"2026-09-19T14:00:00Z","customer_impact":False}

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name)/"test.db")
        init_db(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_creates_and_deduplicates(self):
        first = triage(self.db,BASE)
        self.assertEqual(first["decision"],"CREATED_INCIDENT")
        self.assertEqual(triage(self.db,BASE)["decision"],"DUPLICATE_EVENT")
        self.assertEqual(snapshot(self.db)["total_events"],1)

    def test_correlates_distinct_events(self):
        first = triage(self.db,BASE)
        second = triage(self.db,{**BASE,"event_id":"evt-2"})
        self.assertEqual(second["decision"],"UPDATED_INCIDENT")
        self.assertEqual(second["incident_id"],first["incident_id"])
        self.assertEqual(snapshot(self.db)["incidents"][0]["event_count"],2)

    def test_maintenance_and_customer_override(self):
        add_maintenance(self.db,{"circuit_id":"circuit-42","start":"2026-09-19T13:00:00Z","end":"2026-09-19T15:00:00Z","approved":True})
        self.assertEqual(triage(self.db,BASE)["decision"],"MAINTENANCE_MATCH")
        self.assertEqual(triage(self.db,{**BASE,"event_id":"evt-2","customer_impact":True})["decision"],"ESCALATE_CREATED_INCIDENT")

    def test_reject_bad_time_and_window(self):
        with self.assertRaises(ValueError):
            triage(self.db,{**BASE,"timestamp":"2026-09-19T14:00:00"})
        with self.assertRaises(ValueError):
            add_maintenance(self.db,{"circuit_id":"circuit-42","start":"2026-09-19T15:00:00Z","end":"2026-09-19T13:00:00Z","approved":True})

if __name__ == "__main__":
    unittest.main()
