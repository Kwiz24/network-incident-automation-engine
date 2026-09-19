"""SQLite-backed network alert triage: educational demo, not a production control plane."""
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .inventory import lookup, seed_inventory, inventory_snapshot


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 string")
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid ISO-8601 timestamp") from exc
    if date.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return date.astimezone(timezone.utc)


def init_db(path):
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS events (
          event_id TEXT PRIMARY KEY, circuit_id TEXT NOT NULL,
          event_type TEXT NOT NULL, received_at TEXT NOT NULL,
          decision TEXT NOT NULL, incident_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS maintenance (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          circuit_id TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL,
          approved INTEGER NOT NULL CHECK(approved IN (0,1))
        );
        CREATE TABLE IF NOT EXISTS incidents (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          circuit_id TEXT NOT NULL, event_type TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'open', first_seen TEXT NOT NULL,
          last_seen TEXT NOT NULL, event_count INTEGER NOT NULL DEFAULT 1,
          UNIQUE(circuit_id,event_type,status)
        );
        CREATE TABLE IF NOT EXISTS inventory_devices (
          device_id TEXT PRIMARY KEY, site TEXT NOT NULL,
          role TEXT NOT NULL, owner_team TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS inventory_circuits (
          circuit_id TEXT PRIMARY KEY, device_id TEXT NOT NULL,
          interface_name TEXT NOT NULL, provider TEXT NOT NULL,
          owner_team TEXT NOT NULL,
          FOREIGN KEY(device_id) REFERENCES inventory_devices(device_id)
        );
        """)
        # Backward-compatible migration for the existing Phase 1/2 incidents.db.
        additions = {"device_id": "TEXT", "interface_name": "TEXT", "owner_team": "TEXT",
                     "site": "TEXT", "priority": "TEXT NOT NULL DEFAULT 'P3'",
                     "routing_status": "TEXT NOT NULL DEFAULT 'MANUAL_REVIEW'"}
        existing = {row[1] for row in conn.execute("PRAGMA table_info(incidents)")}
        for column, definition in additions.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE incidents ADD COLUMN {column} {definition}")
        seed_inventory(conn)
        # Fill in metadata for incidents created before Phase 3; do not change tickets/IDs.
        conn.execute("""UPDATE incidents SET
            device_id=(SELECT device_id FROM inventory_circuits c WHERE c.circuit_id=incidents.circuit_id),
            interface_name=(SELECT interface_name FROM inventory_circuits c WHERE c.circuit_id=incidents.circuit_id),
            owner_team=(SELECT owner_team FROM inventory_circuits c WHERE c.circuit_id=incidents.circuit_id),
            site=(SELECT d.site FROM inventory_circuits c JOIN inventory_devices d ON c.device_id=d.device_id WHERE c.circuit_id=incidents.circuit_id),
            routing_status=CASE WHEN EXISTS(SELECT 1 FROM inventory_circuits c WHERE c.circuit_id=incidents.circuit_id)
               THEN 'ROUTED' ELSE 'MANUAL_REVIEW' END
            WHERE device_id IS NULL""")
        # Reconstruct priority for older tickets from stored escalation decisions.
        conn.execute("""UPDATE incidents SET priority = CASE
          WHEN EXISTS(SELECT 1 FROM events e WHERE e.incident_id=incidents.id AND e.decision LIKE 'ESCALATE_%') THEN 'P1'
          WHEN event_type IN ('LINK_DOWN','PORT_DOWN','BGP_SESSION_DOWN') THEN 'P2'
          ELSE 'P3' END WHERE priority='P3'""")


def validate_alert(alert):
    if not isinstance(alert, dict):
        raise ValueError("JSON body must be an object")
    for field in ("event_id", "circuit_id", "event_type", "timestamp"):
        if not isinstance(alert.get(field), str) or not alert[field].strip():
            raise ValueError(f"{field} must be a nonempty string")
    if type(alert.get("customer_impact", False)) is not bool:
        raise ValueError("customer_impact must be a boolean")
    timestamp(alert["timestamp"])


def add_maintenance(path, window):
    if not isinstance(window, dict) or not isinstance(window.get("circuit_id"), str) or not window["circuit_id"].strip():
        raise ValueError("circuit_id must be a nonempty string")
    if type(window.get("approved")) is not bool:
        raise ValueError("approved must be a boolean")
    start, end = timestamp(window.get("start")), timestamp(window.get("end"))
    if end <= start:
        raise ValueError("maintenance end must follow start")
    with closing(sqlite3.connect(path)) as conn, conn:
        cursor = conn.execute("INSERT INTO maintenance(circuit_id,start,end,approved) VALUES(?,?,?,?)",
          (window["circuit_id"],start.isoformat(),end.isoformat(),int(window["approved"])))
        return {"maintenance_id": cursor.lastrowid, "status":"created"}


def triage(path, alert):
    validate_alert(alert)
    event_time = timestamp(alert["timestamp"]).isoformat()
    with closing(sqlite3.connect(path, timeout=10)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute("SELECT decision,incident_id FROM events WHERE event_id=?",(alert["event_id"],)).fetchone()
        if existing:
            return {"decision":"DUPLICATE_EVENT", "original_decision":existing[0], "incident_id":existing[1]}
        windows = conn.execute("SELECT start,end FROM maintenance WHERE circuit_id=? AND approved=1", (alert["circuit_id"],)).fetchall()
        in_maintenance = any(start <= event_time < end for start,end in windows)
        incident_id = None
        inventory = lookup(conn, alert["circuit_id"])
        routing_status = "ROUTED" if inventory else "MANUAL_REVIEW"
        owner_team = inventory["owner_team"] if inventory else None
        priority = "P1" if alert.get("customer_impact", False) else (
            "P2" if alert["event_type"] in ("LINK_DOWN", "PORT_DOWN", "BGP_SESSION_DOWN") else "P3"
        )
        if in_maintenance and not alert.get("customer_impact",False):
            decision = "MAINTENANCE_MATCH"
        else:
            previous = conn.execute("SELECT id,event_count FROM incidents WHERE circuit_id=? AND event_type=? AND status='open'",
                (alert["circuit_id"],alert["event_type"])).fetchone()
            if previous:
                incident_id = previous[0]
                conn.execute("""UPDATE incidents SET event_count=event_count+1,last_seen=?,
                       priority=CASE WHEN priority='P1' OR ?='P1' THEN 'P1'
                                     WHEN priority='P2' OR ?='P2' THEN 'P2' ELSE 'P3' END,
                       device_id=?,interface_name=?,owner_team=?,site=?,routing_status=? WHERE id=?""",
                     (event_time, priority, priority, inventory["device_id"] if inventory else None,
                      inventory["interface_name"] if inventory else None,owner_team,
                      inventory["site"] if inventory else None,routing_status,incident_id))
                decision = "UPDATED_INCIDENT"
            else:
                cursor = conn.execute("""INSERT INTO incidents
                   (circuit_id,event_type,first_seen,last_seen,device_id,interface_name,owner_team,site,priority,routing_status)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                   (alert["circuit_id"],alert["event_type"],event_time,event_time,
                    inventory["device_id"] if inventory else None,
                    inventory["interface_name"] if inventory else None,owner_team,
                    inventory["site"] if inventory else None,priority,routing_status))
                incident_id = cursor.lastrowid
                decision = "CREATED_INCIDENT"
            if alert.get("customer_impact",False):
                decision = "ESCALATE_" + decision
        conn.execute("INSERT INTO events(event_id,circuit_id,event_type,received_at,decision,incident_id) VALUES(?,?,?,?,?,?)",
            (alert["event_id"],alert["circuit_id"],alert["event_type"],event_time,decision,incident_id))
        if incident_id is not None:
            priority = conn.execute("SELECT priority FROM incidents WHERE id=?", (incident_id,)).fetchone()[0]
        # Nearby incident context only. Never merge separate circuits just because
        # they share a device: operators must validate the actual root cause.
        related = []
        if incident_id is not None and inventory:
            related = [row[0] for row in conn.execute("""SELECT id FROM incidents
                WHERE device_id=? AND id<>? AND status='open' ORDER BY id""",
                (inventory["device_id"], incident_id))]
        return {"decision":decision,"incident_id":incident_id,"maintenance_match":in_maintenance,
                "owner_team":owner_team,"device_id":inventory["device_id"] if inventory else None,
                "priority":priority if incident_id is not None else None,
                "routing_status":routing_status if incident_id is not None else "NO_INCIDENT",
                "related_incident_ids":related}


def snapshot(path):
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.row_factory = sqlite3.Row
        incidents = [dict(row) for row in conn.execute("SELECT * FROM incidents ORDER BY id DESC")]
        decisions = [dict(row) for row in conn.execute("SELECT decision,COUNT(*) AS count FROM events GROUP BY decision ORDER BY decision")]
        events = [dict(row) for row in conn.execute(
            "SELECT event_id,circuit_id,event_type,received_at,decision,incident_id "
            "FROM events ORDER BY received_at DESC,event_id DESC LIMIT 100"
        )]
        maintenance = [dict(row) for row in conn.execute(
            "SELECT id,circuit_id,start,end,approved FROM maintenance ORDER BY start DESC,id DESC LIMIT 100"
        )]
        return {
            "total_events": sum(row["count"] for row in decisions),
            "incidents": incidents,
            "decisions": decisions,
            "events": events,
            "maintenance": maintenance,
            "inventory": inventory_snapshot(path),
            "routing": {
                "routed_open": sum(i["routing_status"] == "ROUTED" and i["status"] == "open" for i in incidents),
                "manual_review_open": sum(i["routing_status"] == "MANUAL_REVIEW" and i["status"] == "open" for i in incidents),
            },
        }
