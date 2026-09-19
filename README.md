# Network Incident Automation Engine — Phase 2

A **local-only portfolio demonstration** for infrastructure operations interviews. Python + SQLite + vanilla HTML/CSS/JavaScript; no third-party packages or Node.js installation. Includes alert deduplication, incident grouping by circuit and event type, approved maintenance matching, customer-impact escalation, and a browser dashboard.

> **Safety:** Simulation only. No real network devices, ticketing systems, production maintenance-control integration, authentication, or real alert silences. The development API listens only on `127.0.0.1` and must not be exposed to the public internet.

## What the dashboard shows

- Four metrics: processed unique events, open incidents, maintenance matches, and escalated events.
- A decision-distribution bar chart of **stored** events (duplicate replays are not stored/counted).
- Active incident table, recent event feed (latest 100), and maintenance table (latest 100).
- A form to submit a simulated network event with a fresh unique ID and current UTC timestamp.
- Automatic refresh every 15 seconds, plus a manual Refresh button and an API error state.
- Responsive dark-mode styling; no third-party assets or external requests.

## Quick start on a MacBook Pro with VS Code

1. Extract the ZIP, open the `network-incident-automation-engine` folder in VS Code, and open **Terminal → New Terminal**.
2. Confirm Python 3.9+ and run tests:

```bash
python3 --version
python3 -m unittest discover -s tests -v
```

3. Start the local application:

```bash
python3 -m app.server
```

4. Open **http://127.0.0.1:8080/** in your browser. Press **Send simulated alert**, then view the updated metric cards, decision chart, and incident/event tables.

5. Submit another alert with the same circuit and event type to demonstrate `UPDATED_INCIDENT`. Tick **Customer-impacting event** and send another alert to demonstrate escalation. The event IDs are generated uniquely, so they are not delivery duplicates.

**Stop the server:** `Ctrl+C` in the VS Code terminal. **Reset demo data:** stop the server, delete `incidents.db` in the project folder, then start the server again. This deletes only the local demo data.

### Optional: reproduce exact duplicate delivery

Open a second VS Code terminal while the server runs:

```bash
curl -X POST http://127.0.0.1:8080/alerts -H 'Content-Type: application/json' --data-binary @samples/alert.json
curl -X POST http://127.0.0.1:8080/alerts -H 'Content-Type: application/json' --data-binary @samples/alert.json
```

The second request returns `DUPLICATE_EVENT`; the count of stored events does **not** increase. The supplied sample event has a fixed historical timestamp, so it sorts according to its actual timestamp rather than necessarily appearing first in the recent-event table.

### Optional: demonstrate an approved maintenance match

Register a sample window first, then submit a fresh alert whose timestamp falls inside it:

```bash
curl -X POST http://127.0.0.1:8080/maintenance -H 'Content-Type: application/json' --data-binary @samples/maintenance.json
curl -X POST http://127.0.0.1:8080/alerts -H 'Content-Type: application/json' -d '{"event_id":"sample-maintenance-1","circuit_id":"circuit-42","event_type":"LINK_DOWN","timestamp":"2026-09-19T14:05:00Z","customer_impact":false}'
```

A matching event returns `MAINTENANCE_MATCH`, appears in the feed, and increases the maintenance-match metric. The dashboard's **Send simulated alert** button uses current UTC time; it will match this sample maintenance only if the current time is inside the defined window. An event with `customer_impact: true` still escalates even when maintenance matches.

## API reference

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Browser dashboard |
| GET | `/styles.css`, `/app.js` | Dashboard assets |
| GET | `/health` | Health status |
| GET | `/dashboard` | Aggregate counts, all incidents, latest 100 recorded events and maintenance windows |
| POST | `/alerts` | Validate, deduplicate, correlate, triage and store an alert |
| POST | `/maintenance` | Add a validated maintenance window |

The dashboard is read-only except for its simulated alert submission form. Maintenance records are added through the API. Dashboard metrics are lifetime counts of the local demo database, not live network metrics. Incidents do not have a resolve/close workflow yet.

## Folder structure

```text
app/
  engine.py            SQLite persistence and triage engine
  server.py            Python HTTP API + safe static route allowlist
  static/
    index.html         Dashboard layout
    styles.css         Responsive dark interface
    app.js             Fetch, visualization, local simulator
samples/               Sample alert and maintenance payloads
tests/                 Engine and HTTP smoke tests
.gitignore             Excludes local SQLite databases
```

## Architecture

```text
Browser (http://127.0.0.1:8080/)
  |-- GET /dashboard --------------------> Python HTTP server
  |-- POST /alerts (simulation) --------> Python HTTP server
                                          |
                                          v
                                    Triage engine
                             deduplicate / correlate /
                             check maintenance / escalate
                                          |
                                          v
                                       SQLite
```

## Interview demo (2 minutes)

1. Explain the issue: repetitive interface and backbone tickets cost engineering time.
2. Open the dashboard and show the current baseline metrics.
3. Submit a LINK_DOWN alert to create an incident; submit another alert for the same circuit to show correlation.
4. Mark the next alert customer-impacting to show escalation.
5. Use identical `curl` requests to prove duplicate delivery is idempotent. Show the decision chart, event audit feed, and tests.
6. Explain the safeguards required before production: validated network inventory, incident expiry/resolution, secure APIs, durable queues, operator-approved remediation, audit logs, and accurate suppression rules.

## Running tests

```bash
python3 -m unittest discover -s tests -v
```

The HTTP smoke tests use a temporary database and a random loopback port; they do not modify your normal `incidents.db` data.

## GitHub: existing repository or first publish

If you already cloned a Git repository locally, **do not run `git init` again unnecessarily or replace its `.git` folder.** Copy the updated `app/`, `tests/`, and `README.md` into that repository; keep your existing `.git` folder and any work you added. Then:

```bash
git status
git add app tests README.md
git commit -m "Add incident operations dashboard"
git push
```

If this is your *first* publish, create an empty repository in the `Kwiz24` GitHub account, then from the project root:

```bash
git init
git add .
git commit -m "Build network incident automation engine dashboard"
git branch -M main
git remote add origin https://github.com/Kwiz24/network-incident-automation-engine.git
git push -u origin main
```

Verify the destination with `git remote -v` before pushing. Never commit secrets, local incident databases, or real company telemetry.

## Design limitations / Phase 3

- Correlation only matches open incidents with the same circuit ID and event type; it does not use network topology or time-windowed clusters.
- Existing incidents remain `open` indefinitely: there is no resolution API, lifecycle, or TTL.
- Approved maintenance is matched against **event time** and circuit ID, not notification ingestion time or an authoritative operational change system.
- `customer_impact` is provided by untrusted simulated input; genuine impact would need independent telemetry and verification.
- The UI renders server-provided text with `textContent` rather than injecting HTML, and the Python server only serves a fixed list of local static assets.
- Next: inventory enrichment via NetBox, meaningful alert correlation windows, alert delivery metrics, tests for race conditions, structured logging, secure API access, and safe human-approved remediation.
