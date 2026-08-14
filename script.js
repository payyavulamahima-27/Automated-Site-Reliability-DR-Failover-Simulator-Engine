const POLL_INTERVAL_MS = 2000;

function statusColor(status) {
    if (status === "healthy") return "#059669";
    if (status === "degraded") return "#d97706";
    return "#dc2626";
}

function severityClass(sev) {
    return `sev-${sev}`;
}

async function fetchStatus() {
    try {
        const res = await fetch("/api/status");
        const data = await res.json();
        renderStatus(data);
    } catch (err) {
        console.error("Failed to fetch status", err);
    }
}

function renderStatus(data) {
    document.getElementById("server-time").textContent = "Server time: " + data.server_time;
    document.getElementById("active-site-name").textContent = data.active_site || "None";

    const badge = document.getElementById("engine-badge");
    badge.textContent = "Auto-Failover: " + (data.auto_failover_enabled ? "ON" : "OFF");
    badge.className = "engine-badge " + (data.auto_failover_enabled ? "badge-on" : "badge-off");

    const grid = document.getElementById("sites-grid");
    grid.innerHTML = "";

    data.sites.forEach(site => {
        const card = document.createElement("div");
        card.className = "site-card" + (site.is_active ? " site-active" : "");

        const outageNote = site.forced_outage
            ? `<div class="chaos-note">⚠ Forced outage active</div>` : "";

        card.innerHTML = `
            <div class="site-card-header">
                <span class="site-name">${site.name}</span>
                ${site.is_active ? '<span class="active-tag">ACTIVE</span>' : ''}
            </div>
            <div class="site-role">${site.role.toUpperCase()} &middot; ${site.region}</div>
            <div class="health-bar-wrapper">
                <div class="health-bar" style="width:${site.health_score}%; background:${statusColor(site.status)}"></div>
            </div>
            <div class="health-score">${site.health_score}/100 &middot; <span style="color:${statusColor(site.status)}">${site.status}</span></div>
            <div class="metrics-row">
                <span>Latency: ${site.latency_ms} ms</span>
                <span>Errors: ${site.error_rate}%</span>
            </div>
            ${outageNote}
            <div class="site-actions">
                ${!site.is_active ? `<button class="btn btn-small" onclick="triggerFailover(${site.id})">Failover Here</button>` : ""}
                ${!site.forced_outage
                    ? `<button class="btn btn-small btn-warning" onclick="injectChaos(${site.id})">Inject Outage</button>`
                    : `<button class="btn btn-small btn-success" onclick="recoverSite(${site.id})">Recover</button>`}
            </div>
        `;
        grid.appendChild(card);
    });

    const logBody = document.getElementById("event-log-body");
    logBody.innerHTML = "";
    data.events.forEach(ev => {
        const row = document.createElement("tr");
        row.className = severityClass(ev.severity);
        row.innerHTML = `
            <td class="log-time">${ev.created_at}</td>
            <td class="log-type">${ev.event_type.replace(/_/g, ' ')}</td>
            <td class="log-detail">${ev.detail || ''}</td>
        `;
        logBody.appendChild(row);
    });
}

async function triggerFailover(siteId) {
    await fetch(`/api/failover/${siteId}`, { method: "POST" });
    fetchStatus();
}

async function injectChaos(siteId) {
    await fetch(`/api/chaos/${siteId}`, { method: "POST" });
    fetchStatus();
}

async function recoverSite(siteId) {
    await fetch(`/api/recover/${siteId}`, { method: "POST" });
    fetchStatus();
}

document.getElementById("toggle-auto-btn").addEventListener("click", async () => {
    await fetch("/api/toggle-auto-failover", { method: "POST" });
    fetchStatus();
});

document.getElementById("reset-btn").addEventListener("click", async () => {
    if (confirm("Reset the entire simulation to its initial state?")) {
        await fetch("/api/reset", { method: "POST" });
        fetchStatus();
    }
});

fetchStatus();
setInterval(fetchStatus, POLL_INTERVAL_MS);
