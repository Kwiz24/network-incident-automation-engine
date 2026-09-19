# Network Incident Automation Engine — Phase 3

A **local-only educational network operations demo** for a systems administration interview. Python 3.9+, SQLite, HTML/CSS/JavaScript; no third-party dependencies, Cloudflare access, or live NetBox connection required.

**Safety:** Mock inventory and incidents only. The API is unauthenticated, bound to `127.0.0.1`, and must never be exposed on a public interface. No real devices, ticketing, silences, or configuration are changed.

## What's new in Phase 3

- Bundled NetBox-style mock network inventory (`samples/inventory.json`): devices, sites, circuit-to-device/interface mappings, providers, and owning teams.
- Input enrichment: known circuit alerts receive device, site, interface, owner, and routing status.
- Unknown circuits remain **MANUAL_REVIEW** with **no invented owner**.
- Impact-driven incident priorities (P1 for customer impact; P2 for link/port/BGP failures; P3 for other events), including upgrading existing incidents on escalation.
- Related open incidents on the same device are shown as **context only**; incidents on different circuits are **not automatically merged**.
- A new `GET /inventory` endpoint, routing metrics, owner/priority columns, and inventory table in the dashboard.
- Backward-compatible SQLite migration for Phase 1/2 `incidents.db`; existing incident IDs and event records are preserved.
- Additional unit and HTTP tests.

## macOS + VS Code quick start

1. Open the repository root in VS Code, then Terminal → New Terminal.
2. Confirm `python3 --version` is 3.9+.
3. Run `python3 -m unittest discover -s tests -v`.
4. Run `python3 -m app.server`.
5. Visit **http://127.0.0.1:8080/** in Firefox; keep the Python server running.
6. Stop the server with **Control+C**.

A local `incidents.db` is created automatically and excluded by `.gitignore`. Back it up before any merge or upgrade.

## Demo walkthrough

1. Send a `LINK_DOWN` event with circuit `circuit-42`: mapped to `edge-dfw-01`, interface `et-0/0/1`, Backbone Operations, P2.
2. Send a different event ID for `circuit-43`: new incident; shared-device incident appears as related context in the API response.
3. Send an alert for `unknown-circuit`: incident enters **MANUAL_REVIEW**, owner remains empty.
4. Tick *Customer-impacting event* and send a new alert for `circuit-42`: priority upgrades to P1 and decision is escalated.
5. Inspect routing metrics, incident ownership, and the inventory table. Refresh is automatic every 15 seconds.

API examples (in a second terminal):

```bash
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/inventory
curl http://127.0.0.1:8080/dashboard
curl -X POST http://127.0.0.1:8080/alerts \
  -H 'Content-Type: application/json' \
  -d '{"event_id":"demo-unique-101","circuit_id":"circuit-42","event_type":"LINK_DOWN","timestamp":"2026-09-19T17:00:00Z","customer_impact":false}'
```

Use a **new event ID** for each test. The example's fixed timestamp is for a reproducible sample; dashboard submissions use the current UTC timestamp. To view live maintenance behavior, register an approved window spanning the event timestamp using `POST /maintenance` with circuit ID, `start`, `end`, and `approved`.

## Architecture

```text
Browser dashboard ──GET /dashboard,/inventory──> Python HTTP API
Browser simulator ──POST /alerts───────────────> SQLite triage engine
                                                   ├─ deduplicate by event_id
                                                   ├─ check maintenance
                                                   ├─ look up mock inventory
                                                   ├─ create/update incident
                                                   └─ assign priority/owner or manual review
Bundled mock JSON ──seed only on new DB────────> SQLite inventory tables
```

**Routing is a decision label inside the local database, not a notification or production ticket dispatch.** The prototype is deliberately conservative: maintenance matching does not silence real alerts; shared-device context does not prove shared root cause; priority uses simplified demo rules.

## Database and safe upgrades

`init_db` uses `CREATE TABLE IF NOT EXISTS`, checks existing incident columns, adds Phase 3 fields where absent, seeds mock inventory only if there are no devices yet, and backfills old incidents with known circuit ownership. It does **not** delete incidents or their IDs. On real deployments, use versioned database migrations, backups, transactions, and monitoring rather than this simplified schema initializer.

To reset only an intentionally disposable demo, stop the server and rename `incidents.db` to `incidents.db.backup` before restarting. Do not delete an existing database unless you deliberately want to discard local history.

## Limitations / potential Phase 4

- Not authenticated; local only. No real NetBox API, NOC tooling, message queues, or vendor maintenance ingestion.
- Bundled inventory is demo data seeded once, not a live synchronization service. Editing the JSON does not update an existing database automatically.
- Correlation is by circuit + event type for existing open incidents. Same-device incidents are only associated in response context.
- No retries, persistent outbound ticket delivery, topology-based root-cause inference, automatic remediation, incident closing UI, or deployment hardening.
- For production: typed alert schemas, API auth, data freshness/ownership validation, audit logs, queue/retry guarantees, transactional outbox, formal change approvals, and tested failover.

## Git workflow for an existing Phase 2 repository

**Do not extract a new ZIP into the repository and do not copy `.git` or `incidents.db`.** Confirm `pwd` and `git status` first. Commit or back up any uncommitted work. Switch to up-to-date main and create a new feature branch. Preview the copy with `rsync -avn` before using `rsync -av`; verify tests and browser output before committing. See the conversation walkthrough for exact commands.
