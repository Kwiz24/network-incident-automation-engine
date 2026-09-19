# Network Incident Automation Engine

A local Python portfolio project for infrastructure operations interviews. Demonstrates alert deduplication, correlation by circuit and event type, approved maintenance matching, incident creation/update, customer-impact escalation, SQLite persistence, and JSON metrics. **Simulation only:** no real device access, real ticketing integration, authentication, or production-safe alert suppression.

## Requirements

- macOS or another operating system with Python 3.9+ installed
- VS Code recommended
- No third-party packages required

## Quick start (VS Code terminal on macOS)

```bash
cd network-incident-automation-engine
python3 --version
python3 -m unittest discover -s tests -v
python3 -m app.server
```

Open a **second** VS Code terminal and run:

```bash
curl http://127.0.0.1:8080/health
curl -X POST http://127.0.0.1:8080/alerts -H 'Content-Type: application/json' --data-binary @samples/alert.json
curl -X POST http://127.0.0.1:8080/alerts -H 'Content-Type: application/json' --data-binary @samples/alert.json
curl http://127.0.0.1:8080/dashboard
```

First alert creates an incident; repeating the same event ID returns `DUPLICATE_EVENT`.

## Try maintenance matching

To see a *new* alert match maintenance, register the window first, then submit an alert with a new event ID and a timestamp inside the window:

```bash
curl -X POST http://127.0.0.1:8080/maintenance -H 'Content-Type: application/json' --data-binary @samples/maintenance.json
curl -X POST http://127.0.0.1:8080/alerts -H 'Content-Type: application/json' -d '{"event_id":"event-1002","circuit_id":"circuit-42","event_type":"LINK_DOWN","timestamp":"2026-09-19T14:05:00Z","customer_impact":false}'
```

If you already submitted `event-1001`, use `event-1002` as shown above. The maintenance alert returns `MAINTENANCE_MATCH`. Any alert marked `customer_impact: true` instead creates or updates an incident and returns an `ESCALATE_...` decision.

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/health` | Local health check |
| GET | `/dashboard` | JSON counts and incidents |
| POST | `/alerts` | Validate, deduplicate, correlate, triage |
| POST | `/maintenance` | Record an approved/unapproved maintenance window |

## Project layout

```
app/engine.py       triage and SQLite functions
app/server.py       localhost-only JSON HTTP server
samples/            example inputs
tests/              automated tests
```

## Limitations and roadmap

- `incidents.db` is generated locally and ignored by Git.
- Demo correlation groups open events by circuit ID + event type; production needs topology, incident time windows, severity, and more sophisticated state transitions.
- Demo maintenance matches event timestamps and approved circuit IDs, not authoritative ingestion time. Real implementations must check clock skew, provider identity, vendor approval, and maintenance lifecycle.
- Customer impact is supplied by a simulated caller. Do not trust this value in production without validation.
- Dashboard is JSON, not a graphical UI; visualize with Grafana in a future iteration.
- No authentication: binds only to 127.0.0.1. Do **not** expose or deploy publicly as-is.
- Next: add NetBox API enrichment, ticketing integrations, Prometheus metrics, structured logs, secure API access, and actual safe workflows.

## GitHub publishing

Create a new **empty** public repository called `network-incident-automation-engine` in your GitHub account (don't pre-create README or .gitignore). Then, inside this folder:

```bash
git init
git add .
git commit -m "Build network incident automation prototype"
git branch -M main
git remote add origin https://github.com/Kwiz24/network-incident-automation-engine.git
git push -u origin main
```

Authenticate using GitHub's supported sign-in flow (such as Git Credential Manager or GitHub CLI); don't paste a password or personal access token into a README or chat.
