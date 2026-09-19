"""SQLite-backed network alert triage: educational demo, not a production control plane."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


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
    with sqlite3.connect(path) as conn:
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
        """)


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
    with sqlite3.connect(path) as conn:
        cursor = conn.execute("INSERT INTO maintenance(circuit_id,start,end,approved) VALUES(?,?,?,?)",
          (window["circuit_id"],start.isoformat(),end.isoformat(),int(window["approved"])))
        return {"maintenance_id": cursor.lastrowid, "status":"created"}


def triage(path, alert):
    validate_alert(alert)
    event_time = timestamp(alert["timestamp"]).isoformat()
    with sqlite3.connect(path, timeout=10) as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute("SELECT decision,incident_id FROM events WHERE event_id=?",(alert["event_id"],)).fetchone()
        if existing:
            return {"decision":"DUPLICATE_EVENT", "original_decision":existing[0], "incident_id":existing[1]}
        windows = conn.execute("SELECT start,end FROM maintenance WHERE circuit_id=? AND approved=1", (alert["circuit_id"],)).fetchall()
        in_maintenance = any(start <= event_time < end for start,end in windows)
        incident_id = None
        if in_maintenance and not alert.get("customer_impact",False):
            decision = "MAINTENANCE_MATCH"
        else:
            previous = conn.execute("SELECT id,event_count FROM incidents WHERE circuit_id=? AND event_type=? AND status='open'",
                (alert["circuit_id"],alert["event_type"])).fetchone()
            if previous:
                incident_id = previous[0]
                conn.execute("UPDATE incidents SET event_count=event_count+1,last_seen=? WHERE id=?",(event_time,incident_id))
                decision = "UPDATED_INCIDENT"
            else:
                cursor = conn.execute("INSERT INTO incidents(circuit_id,event_type,first_seen,last_seen) VALUES(?,?,?,?)",
                    (alert["circuit_id"],alert["event_type"],event_time,event_time))
                incident_id = cursor.lastrowid
                decision = "CREATED_INCIDENT"
            if alert.get("customer_impact",False):
                decision = "ESCALATE_" + decision
        conn.execute("INSERT INTO events(event_id,circuit_id,event_type,received_at,decision,incident_id) VALUES(?,?,?,?,?,?)",
            (alert["event_id"],alert["circuit_id"],alert["event_type"],event_time,decision,incident_id))
        return {"decision":decision,"incident_id":incident_id,"maintenance_match":in_maintenance}


def snapshot(path):
    with sqlite3.connect(path) as conn:
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
        }
