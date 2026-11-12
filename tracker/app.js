import { SERVICES, CONNECTORS } from "/catalogue.js";

const COLUMNS = [
  ["backlog", "Backlog"],
  ["in_progress", "In progress"],
  ["review", "Review"],
  ["blocked", "Blocked"],
  ["done", "Done"],
];
const STATUS_COLOR = {
  online: "var(--online)", connected: "var(--online)", active: "var(--online)",
  degraded: "var(--degraded)", idle: "var(--degraded)",
  offline: "var(--offline)", error: "var(--offline)",
  planned: "var(--planned)", unknown: "var(--planned)", paused: "var(--planned)",
};

let S = { portals: [], connections: [], tasks: [], agents: [], events: [] };
let selected = null;
let filter = "";
let editingTask = null;

const $ = (sel) => document.querySelector(sel);
const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const portalBy = (slug) => S.portals.find((p) => p.slug === slug);
const ago = (iso) => {
  if (!iso) return "never";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${Math.round(s)}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
};

// ---------- API ----------
async function api(path, opts = {}) {
  const res = await fetch(`/api/${path}`, {
    ...opts,
    headers: { "content-type": "application/json" },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

async function refresh() {
  const sync = $("#sync");
  try {
    S = await api("state");
    sync.className = "sync live";
    sync.querySelector("b").textContent = `live · synced ${new Date().toLocaleTimeString()}`;
    render();
  } catch (e) {
    sync.className = "sync err";
    sync.querySelector("b").textContent = "sync failed";
    console.error(e);
  }
}

async function mutate(fn, okMsg) {
  try {
    await fn();
    if (okMsg) toast(okMsg);
    await refresh();
  } catch (e) {
    toast(e.message, true);
  }
}

function toast(msg, err = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = `toast show${err ? " err" : ""}`;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => (t.className = "toast"), 2600);
}

// ---------- Derived ----------
function portalStats(slug) {
  const conns = S.connections.filter((c) => c.portalSlug === slug);
  const tasks = S.tasks.filter((t) => t.portalSlug === slug);
  return {
    conns,
    connected: conns.filter((c) => c.status === "connected").length,
    open: tasks.filter((t) => t.status !== "done").length,
    blocked: tasks.filter((t) => t.status === "blocked" || (t.kind === "incident" && t.status !== "done")).length,
    agents: S.agents.filter((a) => a.portalSlug === slug),
  };
}

// Portal health shown in the GUI: the probe result if an endpoint is configured,
// otherwise inferred from the state of its aepx-core links.
function portalHealth(p) {
  if (p.baseUrl && p.status !== "unknown") return p.status;
  const { conns } = portalStats(p.slug);
  if (conns.some((c) => c.status === "offline")) return "offline";
  if (conns.some((c) => c.status === "degraded")) return "degraded";
  if (conns.some((c) => c.status === "connected")) return "online";
  return "unknown";
}

// ---------- Render ----------
function render() {
  renderKpis();
  renderTopology();
  renderPortals();
  renderFilter();
  renderBoard();
  renderMatrix();
  renderAgents();
  renderFeed();
  // Don't clobber a field the user is typing in during background polling.
  const active = document.activeElement;
  if (selected && !($("#drawer").contains(active) && active.tagName === "INPUT")) renderDrawer();
}

function renderKpis() {
  const c = S.connections;
  const byStatus = (s) => c.filter((x) => x.status === s).length;
  const healthy = S.portals.filter((p) => portalHealth(p) === "online").length;
  const open = S.tasks.filter((t) => t.status !== "done").length;
  const done = S.tasks.length - open;
  const incidents = S.tasks.filter((t) => t.kind === "incident" && t.status !== "done").length;
  const activeAgents = S.agents.filter((a) => a.status === "active").length;
  const avgTrust = S.agents.length ? Math.round(S.agents.reduce((n, a) => n + a.trustScore, 0) / S.agents.length) : 0;
  const bar = (parts) =>
    `<div class="kpi-bar">${parts.map(([n, col]) => `<span style="width:${(n / Math.max(1, parts.reduce((a, [x]) => a + x, 0))) * 100}%;background:${col}"></span>`).join("")}</div>`;
  $("#kpis").innerHTML = [
    ["Portals healthy", `${healthy}<small>/ ${S.portals.length}</small>`, bar([[healthy, "var(--online)"], [S.portals.length - healthy, "var(--line-2)"]])],
    ["Live connections", `${byStatus("connected")}<small>/ ${c.length}</small>`,
      bar([[byStatus("connected"), "var(--online)"], [byStatus("degraded"), "var(--degraded)"], [byStatus("offline"), "var(--offline)"], [byStatus("planned"), "var(--planned)"]])],
    ["Open items", `${open}`, bar([[done, "var(--online)"], [open, "var(--accent)"]])],
    ["Active incidents", `${incidents}`, bar([[incidents, "var(--offline)"], [Math.max(0, open - incidents), "var(--line-2)"]])],
    ["Agents active", `${activeAgents}<small>/ ${S.agents.length}</small>`, bar([[activeAgents, "var(--online)"], [S.agents.length - activeAgents, "var(--line-2)"]])],
    ["Avg. agent trust", `${avgTrust}<small>/ 100</small>`, bar([[avgTrust, "var(--accent)"], [100 - avgTrust, "var(--line-2)"]])],
  ]
    .map(([l, v, b]) => `<div class="kpi"><div class="kpi-label">${l}</div><div class="kpi-value">${v}</div>${b}</div>`)
    .join("");
}

const hex = (cx, cy, r) =>
  Array.from({ length: 6 }, (_, i) => {
    const a = (Math.PI / 3) * i - Math.PI / 2;
    return `${(cx + r * Math.cos(a)).toFixed(1)},${(cy + r * Math.sin(a)).toFixed(1)}`;
  }).join(" ");

function renderTopology() {
  const cx = 450, cy = 300, R = 220;
  const n = S.portals.length || 1;
  let links = "", nodes = "";
  S.portals.forEach((p, i) => {
    const a = (2 * Math.PI * i) / n - Math.PI / 2;
    const x = cx + R * 1.45 * Math.cos(a), y = cy + R * Math.sin(a);
    const health = portalHealth(p);
    const col = STATUS_COLOR[health];
    const { conns } = portalStats(p.slug);
    const mx = (cx + x) / 2 + Math.sin(a) * 30, my = (cy + y) / 2 - Math.cos(a) * 30;
    const flowing = health === "online" || health === "degraded";
    links += `<path class="topo-link ${flowing ? "flow" : ""} ${health === "degraded" ? "slow" : ""}" d="M${cx},${cy} Q${mx},${my} ${x},${y}" stroke="${col}" opacity="${flowing ? 0.9 : 0.4}"/>`;
    // satellites: one per connection, fanned on the far side of the portal
    const sats = conns
      .map((c, j) => {
        const spread = Math.min(1.9, 0.32 * conns.length);
        const sa = a + (conns.length > 1 ? (j / (conns.length - 1) - 0.5) * spread : 0);
        const sx = x + 62 * Math.cos(sa), sy = y + 62 * Math.sin(sa);
        return `<line x1="${x}" y1="${y}" x2="${sx}" y2="${sy}" stroke="${STATUS_COLOR[c.status]}" opacity="0.35"/>
          <circle class="topo-sat" cx="${sx}" cy="${sy}" r="${c.targetKind === "service" ? 5 : 3.6}" fill="${STATUS_COLOR[c.status]}"><title>${esc(c.target)} · ${esc(c.status)}</title></circle>`;
      })
      .join("");
    nodes += `<g class="topo-node ${selected === p.slug ? "selected" : ""}" data-slug="${esc(p.slug)}" tabindex="0" role="button" aria-label="${esc(p.name)}">
      ${sats}
      <polygon points="${hex(x, y, 40)}" stroke="${esc(p.color)}"/>
      <circle cx="${x + 28}" cy="${y - 26}" r="5" fill="${col}"/>
      <text class="topo-code" x="${x}" y="${y + 6}" fill="${esc(p.color)}">${esc(p.code)}</text>
      <text class="topo-name" x="${x}" y="${y + 58}">${esc(p.name.replace(" Portal", ""))}</text>
    </g>`;
  });
  $("#topology").innerHTML = `
    <ellipse class="topo-ring" cx="${cx}" cy="${cy}" rx="${R * 1.45}" ry="${R}"/>
    <ellipse class="topo-ring" cx="${cx}" cy="${cy}" rx="${R * 0.75}" ry="${R * 0.52}"/>
    ${links}
    <circle class="topo-hub-glow" cx="${cx}" cy="${cy}" r="78"/>
    <polygon class="topo-hub-core" points="${hex(cx, cy, 62)}"/>
    <polygon points="${hex(cx, cy, 48)}" fill="none" stroke="var(--line-2)"/>
    <text class="topo-hub-label" x="${cx}" y="${cy - 2}" font-size="20">AEP-X</text>
    <text class="topo-hub-sub" x="${cx}" y="${cy + 16}">gateway · bus</text>
    ${nodes}`;
}

function renderPortals() {
  $("#portal-list").innerHTML = S.portals
    .map((p) => {
      const st = portalStats(p.slug);
      const h = portalHealth(p);
      return `<button class="portal-card ${selected === p.slug ? "selected" : ""}" data-slug="${esc(p.slug)}">
        <span class="swatch" style="background:${esc(p.color)}"></span>
        <span>
          <span class="title"><span class="code" style="color:${esc(p.color)}">${esc(p.code)}</span>${esc(p.name)}</span>
          <span class="meta"><span class="health"><i class="dot ${h}"></i>${h}</span> · ${st.connected}/${st.conns.length} links · ${p.baseUrl ? esc(new URL(p.baseUrl).host) : "no endpoint"}</span>
        </span>
        <span class="stat"><b>${st.open}</b>open</span>
      </button>`;
    })
    .join("");
}

function renderFilter() {
  const opts = `<option value="">All portals</option>` + S.portals.map((p) => `<option value="${esc(p.slug)}">${esc(p.code)} — ${esc(p.name)}</option>`).join("");
  const f = $("#filter-portal");
  if (f.dataset.n !== String(S.portals.length)) {
    f.innerHTML = opts;
    f.dataset.n = S.portals.length;
    $("#task-form").elements.portalSlug.innerHTML = S.portals.map((p) => `<option value="${esc(p.slug)}">${esc(p.name)}</option>`).join("");
  }
  f.value = filter;
  $("#agent-names").innerHTML = S.agents.map((a) => `<option value="${esc(a.name)}">`).join("");
}

function taskCard(t) {
  const p = portalBy(t.portalSlug);
  return `<div class="card" draggable="true" data-task="${t.id}" style="border-left-color:${esc(p?.color)}">
    <div class="card-title">${esc(t.title)}</div>
    <div class="card-meta">
      <span class="tag" style="color:${esc(p?.color)}">${esc(p?.code)}</span>
      <span class="tag prio-${esc(t.priority)}">${esc(t.priority)}</span>
      <span>${esc(t.kind)}</span>
      ${t.agent ? `<span>· ${esc(t.agent)}</span>` : ""}
    </div>
  </div>`;
}

function renderBoard() {
  const tasks = S.tasks.filter((t) => !filter || t.portalSlug === filter);
  $("#board").innerHTML = COLUMNS.map(([key, label]) => {
    const items = tasks.filter((t) => t.status === key);
    return `<div class="column" data-status="${key}">
      <div class="column-head"><h3>${label}</h3><span class="count">${items.length}</span></div>
      <div class="column-body">${items.map(taskCard).join("") || `<div class="empty">—</div>`}</div>
    </div>`;
  }).join("");
}

function renderMatrix() {
  const targets = [...new Map(S.connections.map((c) => [c.target, c.targetKind])).entries()].sort(
    (a, b) => a[1].localeCompare(b[1]) * -1 || a[0].localeCompare(b[0]),
  );
  const ps = S.portals.filter((p) => !filter || p.slug === filter);
  $("#matrix").innerHTML = `<table class="matrix">
    <thead><tr><th></th>${ps.map((p) => `<th style="color:${esc(p.color)}">${esc(p.code)}</th>`).join("")}</tr></thead>
    <tbody>${targets
      .map(
        ([t, kind]) => `<tr><th>${esc(t)}<em>${esc(kind)}</em></th>${ps
          .map((p) => {
            const c = S.connections.find((x) => x.portalSlug === p.slug && x.target === t);
            return `<td>${c ? `<span class="cell ${esc(c.status)}" title="${esc(p.code)} → ${esc(t)}: ${esc(c.status)} (${esc(c.protocol)})"></span>` : ""}</td>`;
          })
          .join("")}</tr>`,
      )
      .join("")}</tbody></table>`;
}

function renderAgents() {
  $("#agents").innerHTML = S.agents
    .filter((a) => !filter || a.portalSlug === filter)
    .map((a) => {
      const p = portalBy(a.portalSlug);
      const work = S.tasks.filter((t) => t.agent === a.name && t.status !== "done").length;
      return `<div class="agent">
        <div class="agent-head">
          <span class="agent-name">${esc(a.name)}</span>
          <span class="health"><i class="dot ${esc(a.status)}"></i>${esc(a.status)}</span>
        </div>
        <div class="agent-role">${esc(a.role)} · <span style="color:${esc(p?.color)}">${esc(p?.code ?? "—")}</span></div>
        <div class="kpi-label">Trust score ${a.trustScore}</div>
        <div class="trust"><span style="width:${a.trustScore}%"></span></div>
        <div class="agent-foot">
          <span>${work} open · heartbeat ${ago(a.lastHeartbeatAt)}</span>
          <select data-agent="${a.id}" aria-label="Set status for ${esc(a.name)}">
            ${["active", "idle", "paused", "error"].map((s) => `<option ${s === a.status ? "selected" : ""}>${s}</option>`).join("")}
          </select>
        </div>
      </div>`;
    })
    .join("");
}

function renderFeed() {
  const ev = S.events.filter((e) => !filter || e.portalSlug === filter);
  $("#feed").innerHTML =
    ev
      .map((e) => {
        const p = portalBy(e.portalSlug);
        return `<li><time datetime="${esc(e.createdAt)}">${new Date(e.createdAt).toLocaleString()}</time>
          <span class="pcode" style="color:${esc(p?.color ?? "var(--muted)")}">${esc(p?.code ?? "SYS")}</span>
          <span class="kind">${esc(e.kind)}</span><span>${esc(e.message)}</span></li>`;
      })
      .join("") || `<li class="empty">No activity yet</li>`;
}

function renderDrawer() {
  const p = portalBy(selected);
  if (!p) return closeDrawer();
  const st = portalStats(p.slug);
  const h = portalHealth(p);
  const tasks = S.tasks.filter((t) => t.portalSlug === p.slug && t.status !== "done");
  const known = new Set(st.conns.map((c) => c.target));
  const suggestions = [
    ...SERVICES.filter((s) => !known.has(s)).map((s) => `<option value="${esc(s)}">service</option>`),
    ...CONNECTORS.filter((c) => !known.has(c.name)).map((c) => `<option value="${esc(c.name)}">${esc(c.category)} · ${esc(c.protocols.join("/"))}</option>`),
  ].join("");
  $("#drawer-body").innerHTML = `
    <div class="drawer-head" style="border-left-color:${esc(p.color)}">
      <div>
        <div class="kpi-label" style="color:${esc(p.color)}">${esc(p.code)} portal</div>
        <h3>${esc(p.name)}</h3>
        <p>${esc(p.description)}</p>
        <p class="health" style="margin-top:10px"><i class="dot ${h}"></i>${h}${p.latencyMs != null ? ` · ${p.latencyMs} ms` : ""}</p>
      </div>
      <button class="close" data-close aria-label="Close">×</button>
    </div>

    <section>
      <h2>Portal endpoint</h2>
      <form class="endpoint" id="endpoint-form">
        <input name="baseUrl" type="url" placeholder="https://crm.example.com" value="${esc(p.baseUrl)}" aria-label="Portal base URL" />
        <button class="btn" type="submit">Save</button>
        <button class="btn" type="button" id="probe-btn" ${p.baseUrl ? "" : "disabled"}>Probe</button>
      </form>
      <div class="probe-info">${p.baseUrl ? `last probe ${ago(p.lastCheckedAt)} · checks /health then root` : "Set the portal's public URL to enable live health checks."}</div>
    </section>

    <section>
      <h2>aepx-core connections (${st.connected}/${st.conns.length} live)</h2>
      <div class="conn-list">
        ${st.conns
          .map(
            (c) => `<div class="conn">
              <span class="conn-target"><i class="dot ${esc(c.status)}"></i> ${esc(c.target)}<small>${esc(c.targetKind)} · ${esc(c.protocol)}</small></span>
              <select data-conn="${c.id}" aria-label="Status of ${esc(c.target)}">
                ${["planned", "connected", "degraded", "offline"].map((s) => `<option ${s === c.status ? "selected" : ""}>${s}</option>`).join("")}
              </select>
              <button class="icon-btn" data-del-conn="${c.id}" title="Remove link" aria-label="Remove ${esc(c.target)}">×</button>
            </div>`,
          )
          .join("") || `<div class="empty">No connections yet</div>`}
      </div>
      <form class="conn-add" id="conn-form">
        <input name="target" list="conn-suggest" placeholder="service or connector" required maxlength="80" />
        <datalist id="conn-suggest">${suggestions}</datalist>
        <select name="targetKind"><option value="connector">connector</option><option value="service">service</option></select>
        <input name="protocol" placeholder="REST" maxlength="30" />
        <button class="btn" type="submit">Link</button>
      </form>
    </section>

    <section>
      <h2>Open items (${tasks.length})</h2>
      <div class="mini-tasks">${tasks.map(taskCard).join("") || `<div class="empty">Nothing open</div>`}</div>
      <button class="btn" style="margin-top:10px" id="drawer-new-task">+ New item for ${esc(p.code)}</button>
    </section>

    <section>
      <h2>Agents</h2>
      <div class="mini-tasks">${st.agents.map((a) => `<div class="conn"><span class="conn-target"><i class="dot ${esc(a.status)}"></i> ${esc(a.name)}<small>trust ${a.trustScore}</small></span><span class="health">${esc(a.status)}</span><span></span></div>`).join("") || `<div class="empty">No agents assigned</div>`}</div>
    </section>`;

  // Auto-pick a kind when the target matches a known service.
  const form = $("#conn-form").elements;
  form.target.addEventListener("change", () => {
    const name = form.target.value.trim();
    const cat = CONNECTORS.find((c) => c.name === name);
    form.targetKind.value = SERVICES.includes(name) ? "service" : "connector";
    if (cat && !form.protocol.value) form.protocol.value = cat.protocols.join("/");
  });
}

// ---------- Drawer / dialog ----------
function openDrawer(slug) {
  selected = slug;
  $("#drawer").classList.add("open");
  $("#drawer").setAttribute("aria-hidden", "false");
  $("#scrim").classList.add("open");
  render();
}
function closeDrawer() {
  selected = null;
  $("#drawer").classList.remove("open");
  $("#drawer").setAttribute("aria-hidden", "true");
  $("#scrim").classList.remove("open");
  renderTopology();
  renderPortals();
}

function openTaskDialog(task, portalSlug) {
  editingTask = task;
  const f = $("#task-form");
  f.reset();
  $("#task-error").textContent = "";
  $("#task-dialog-title").textContent = task ? "Edit tracker item" : "New tracker item";
  $("#task-delete").classList.toggle("hidden", !task);
  if (task) for (const k of ["title", "portalSlug", "kind", "status", "priority", "agent"]) f.elements[k].value = task[k];
  else if (portalSlug || filter) f.elements.portalSlug.value = portalSlug || filter;
  $("#task-dialog").showModal();
}

// ---------- Events ----------
document.addEventListener("click", (e) => {
  const node = e.target.closest("[data-slug]");
  if (node) return openDrawer(node.dataset.slug);
  if (e.target.closest("[data-close]") || e.target.id === "scrim") return closeDrawer();
  const card = e.target.closest("[data-task]");
  if (card) return openTaskDialog(S.tasks.find((t) => t.id === Number(card.dataset.task)));
  const del = e.target.closest("[data-del-conn]");
  if (del) return mutate(() => api(`connections/${del.dataset.delConn}`, { method: "DELETE" }), "Link removed");
  if (e.target.id === "probe-btn") {
    e.target.disabled = true;
    return mutate(() => api(`portals/${selected}/probe`, { method: "POST" }), "Probe complete");
  }
  if (e.target.id === "drawer-new-task") return openTaskDialog(null, selected);
  const tab = e.target.closest("[data-tab]");
  if (tab) {
    document.querySelectorAll("[data-tab]").forEach((b) => b.classList.toggle("active", b === tab));
    document.querySelectorAll(".tab-body").forEach((s) => s.classList.toggle("hidden", s.id !== `tab-${tab.dataset.tab}`));
  }
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && selected) closeDrawer();
  if ((e.key === "Enter" || e.key === " ") && e.target.matches(".topo-node")) {
    e.preventDefault();
    openDrawer(e.target.dataset.slug);
  }
});

document.addEventListener("change", (e) => {
  const t = e.target;
  if (t.dataset.conn) mutate(() => api(`connections/${t.dataset.conn}`, { method: "PATCH", body: { status: t.value } }));
  if (t.dataset.agent) mutate(() => api(`agents/${t.dataset.agent}`, { method: "PATCH", body: { status: t.value } }), "Agent updated");
  if (t.id === "filter-portal") {
    filter = t.value;
    render();
  }
});

document.addEventListener("submit", (e) => {
  document.activeElement?.blur();
  if (e.target.id === "endpoint-form") {
    e.preventDefault();
    const baseUrl = e.target.elements.baseUrl.value.trim();
    mutate(() => api(`portals/${selected}`, { method: "PATCH", body: { baseUrl } }), baseUrl ? "Endpoint saved & probed" : "Endpoint cleared");
  }
  if (e.target.id === "conn-form") {
    e.preventDefault();
    const f = e.target.elements;
    mutate(
      () => api("connections", { method: "POST", body: { portalSlug: selected, target: f.target.value, targetKind: f.targetKind.value, protocol: f.protocol.value } }),
      "Connection linked",
    );
  }
});

$("#task-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const body = Object.fromEntries(["title", "portalSlug", "kind", "status", "priority", "agent"].map((k) => [k, f.elements[k].value]));
  try {
    if (editingTask) await api(`tasks/${editingTask.id}`, { method: "PATCH", body });
    else await api("tasks", { method: "POST", body });
    $("#task-dialog").close();
    toast(editingTask ? "Item updated" : "Item created");
    refresh();
  } catch (err) {
    $("#task-error").textContent = err.message;
  }
});
$("#task-cancel").addEventListener("click", () => $("#task-dialog").close());
$("#task-delete").addEventListener("click", () => {
  if (!editingTask || !confirm(`Delete “${editingTask.title}”?`)) return;
  $("#task-dialog").close();
  mutate(() => api(`tasks/${editingTask.id}`, { method: "DELETE" }), "Item deleted");
});
$("#new-task").addEventListener("click", () => openTaskDialog(null));

// Drag & drop between board columns
document.addEventListener("dragstart", (e) => {
  const card = e.target.closest?.("[data-task]");
  if (!card) return;
  card.classList.add("dragging");
  e.dataTransfer.setData("text/plain", card.dataset.task);
});
document.addEventListener("dragend", (e) => e.target.classList?.remove("dragging"));
document.addEventListener("dragover", (e) => {
  const col = e.target.closest?.(".column");
  if (!col) return;
  e.preventDefault();
  document.querySelectorAll(".column.drop").forEach((c) => c !== col && c.classList.remove("drop"));
  col.classList.add("drop");
});
document.addEventListener("drop", (e) => {
  const col = e.target.closest?.(".column");
  document.querySelectorAll(".column.drop").forEach((c) => c.classList.remove("drop"));
  if (!col) return;
  e.preventDefault();
  const id = Number(e.dataTransfer.getData("text/plain"));
  const task = S.tasks.find((t) => t.id === id);
  if (!task || task.status === col.dataset.status) return;
  task.status = col.dataset.status; // optimistic
  renderBoard();
  mutate(() => api(`tasks/${id}`, { method: "PATCH", body: { status: col.dataset.status } }));
});

// Clock + polling
const tick = () => ($("#clock").textContent = new Date().toISOString().replace("T", " ").slice(0, 19) + " UTC");
tick();
setInterval(tick, 1000);
refresh();
setInterval(() => document.visibilityState === "visible" && !$("#task-dialog").open && refresh(), 20000);
