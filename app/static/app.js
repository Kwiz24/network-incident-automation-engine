"use strict";
const $ = (id) => document.getElementById(id);
const statusNode = $("api-status");
const errorNode = $("error");
const number = (value) => new Intl.NumberFormat().format(value || 0);
function addText(element, content) { element.textContent = String(content ?? "—"); return element; }
function cell(row, text) { const td = document.createElement("td"); addText(td, text); row.append(td); return td; }
function emptyRow(body, columns, label) { const row = document.createElement("tr"); const td = cell(row, label); td.colSpan = columns; td.className = "empty"; body.append(row); }
function badge(row, label, type) { const td = document.createElement("td"); const b = document.createElement("span"); b.className = "state " + (type || ""); addText(b, label); td.append(b); row.append(td); }
function utc(value) { if (!value) return "—"; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toISOString().replace("T", " ").replace(/\.\d{3}Z$/, "Z"); }
function renderRows(bodyId, records, columns, emptyLabel, makeRow) { const body = $(bodyId); body.replaceChildren(); if (!records.length) return emptyRow(body, columns, emptyLabel); records.forEach((record) => { const row = document.createElement("tr"); makeRow(row, record); body.append(row); }); }
function renderChart(decisions) {
  const chart = $("decision-chart"); chart.replaceChildren();
  if (!decisions.length) { const p = document.createElement("p"); p.className = "empty"; p.textContent = "No events yet. Send a simulated alert to populate this chart."; chart.append(p); return; }
  const max = Math.max(...decisions.map((d) => d.count), 1);
  decisions.forEach((d) => {
    const row = document.createElement("div"); row.className = "bar-row";
    const label = addText(document.createElement("span"), d.decision.replaceAll("_", " "));
    const track = document.createElement("div"); track.className = "track";
    const fill = document.createElement("div"); fill.className = "fill";
    if (d.decision.includes("MAINTENANCE")) fill.classList.add("maintenance");
    else if (d.decision.includes("ESCALATE")) fill.classList.add("escalate");
    else if (d.decision.includes("UPDATED")) fill.classList.add("updated");
    fill.style.width = `${(d.count / max) * 100}%`; track.append(fill);
    const count = addText(document.createElement("span"), d.count); count.className = "bar-count";
    row.append(label, track, count); chart.append(row);
  });
  chart.setAttribute("aria-label", decisions.map((d) => `${d.decision}: ${d.count}`).join(", "));
}
function render(data) {
  const incidents = data.incidents || [], decisions = data.decisions || [];
  const sum = (test) => decisions.filter((d) => test(d.decision)).reduce((total, d) => total + d.count, 0);
  addText($("total-events"), number(data.total_events));
  addText($("open-incidents"), number(incidents.filter((x) => x.status === "open").length));
  addText($("maintenance-matches"), number(sum((v) => v === "MAINTENANCE_MATCH")));
  addText($("escalated"), number(sum((v) => v.startsWith("ESCALATE_"))));
  addText($("incident-count"), `${incidents.length} incidents`);
  const circuits = data.inventory?.circuits || [];
  addText($("routed-open"), number(data.routing?.routed_open));
  addText($("manual-review-open"), number(data.routing?.manual_review_open));
  addText($("inventory-circuit-count"), number(circuits.length));
  addText($("inventory-count"), `${circuits.length} circuits`);
  renderRows("inventory-rows", circuits, 6, "No inventory available.", (row, item) => {
    cell(row,item.circuit_id); cell(row,item.device_id); cell(row,item.interface_name);
    cell(row,item.site); cell(row,item.provider); cell(row,item.owner_team);
  });
  renderChart(decisions);
  renderRows("incident-rows", incidents, 9, "No incidents yet. Send a simulated alert.", (row, item) => {
    cell(row, `INC-${String(item.id).padStart(4, "0")}`); cell(row, item.circuit_id);
    cell(row, item.device_id ? `${item.device_id} / ${item.site || "?"}` : "Unknown circuit");
    cell(row, item.owner_team ? `${item.owner_team} / ${item.routing_status}` : "MANUAL REVIEW");
    badge(row, item.priority || "P3", item.priority === "P1" ? "warning" : "muted");
    cell(row, item.event_type);
    badge(row, item.status.toUpperCase(), item.status === "open" ? "" : "muted");
    cell(row, item.event_count); cell(row, utc(item.last_seen));
  });
  renderRows("event-rows", data.events || [], 4, "No processed events yet.", (row, item) => {
    cell(row, item.event_id); cell(row, item.circuit_id);
    badge(row, item.decision.replaceAll("_", " "), item.decision.includes("ESCALATE") ? "warning" : "muted"); cell(row, utc(item.received_at));
  });
  renderRows("maintenance-rows", data.maintenance || [], 4, "No maintenance windows recorded.", (row, item) => {
    cell(row, item.circuit_id); badge(row, item.approved ? "APPROVED" : "UNAPPROVED", item.approved ? "" : "warning"); cell(row, utc(item.start)); cell(row, utc(item.end));
  });
  addText($("last-updated"), `REFRESHED ${new Date().toLocaleTimeString()}`);
}
async function refresh() {
  try {
    const response = await fetch("/dashboard", {cache: "no-store"});
    if (!response.ok) throw new Error(`Dashboard returned HTTP ${response.status}`);
    render(await response.json());
    statusNode.innerHTML = '<span class="status-dot"></span> API connected';
    errorNode.hidden = true;
  } catch (err) {
    statusNode.textContent = "API unavailable";
    errorNode.textContent = `Could not load data: ${err.message}. Confirm the Python server is running.`;
    errorNode.hidden = false;
  }
}
$("alert-form").addEventListener("submit", async (event) => {
  event.preventDefault(); const button = $("send-alert"); button.disabled = true;
  const result = $("action-result"); result.className = "result"; result.textContent = "Submitting alert…";
  const payload = {
    event_id: `demo-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
    circuit_id: $("circuit").value.trim(),
    event_type: $("event-type").value,
    timestamp: new Date().toISOString(),
    customer_impact: $("customer-impact").checked,
  };
  try {
    const response = await fetch("/alerts", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
    const json = await response.json(); if (!response.ok) throw new Error(json.error || `HTTP ${response.status}`);
    result.className = "result success";
    result.textContent = `${json.decision} · Incident ${json.incident_id == null ? "not created" : `#${json.incident_id}`} · Maintenance: ${json.maintenance_match ? "yes" : "no"} · Route: ${json.owner_team || "manual review"} · Related: ${(json.related_incident_ids || []).join(", ") || "none"}`;
    await refresh();
  } catch (err) { result.className = "result fail"; result.textContent = `Alert failed: ${err.message}`; }
  finally { button.disabled = false; }
});
$("refresh").addEventListener("click", refresh);
refresh();
setInterval(refresh, 15000);
