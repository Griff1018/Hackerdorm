"use strict";

const KEY = "pad_key"; // localStorage key for optional admin passphrase
let adminKey = localStorage.getItem(KEY) || "";

// ---------- helpers ----------
function el(id) { return document.getElementById(id); }
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function fmtDate(iso) {
  if (!iso) return "-";
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toLocaleString(undefined, { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
function statusPill(s) {
  return `<span class="pill ${esc(s)}">${esc(s.replace("_", " "))}</span>`;
}
function toast(msg, kind) {
  const t = el("toast");
  t.textContent = msg;
  t.className = "toast " + (kind || "");
  t.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.add("hidden"), 3200);
}

async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json" };
  if (adminKey) headers["X-Admin-Key"] = adminKey;
  let res;
  try {
    res = await fetch(path, { ...opts, headers, body: opts.body ? JSON.stringify(opts.body) : undefined });
  } catch (e) {
    el("conn-dot").style.background = "var(--red)";
    el("conn-text").textContent = "offline";
    throw e;
  }
  if (res.status === 401) {
    // key rejected / required -> force login
    localStorage.removeItem(KEY);
    adminKey = "";
    location.reload();
    throw new Error("unauthorized");
  }
  el("conn-dot").style.background = "var(--green)";
  el("conn-text").textContent = "connected";
  if (!res.ok) {
    let detail = "";
    try { detail = (await res.json()).detail || ""; } catch {}
    throw new Error(detail || ("HTTP " + res.status));
  }
  if (res.status === 204) return null;
  return res.json();
}

// ---------- auth ----------
async function boot() {
  let status;
  try { status = await api("/api/admin/auth-status"); }
  catch { return; } // offline; will retry on nav
  if (status.required && !adminKey) {
    el("login").classList.remove("hidden");
  } else {
    el("app").classList.remove("hidden");
    loadView("overview");
  }
}
el("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const v = el("login-key").value;
  try {
    const r = await api("/api/admin/login", { method: "POST", body: { key: v } });
    if (r.ok) {
      adminKey = v; localStorage.setItem(KEY, v);
      el("login").classList.add("hidden");
      el("app").classList.remove("hidden");
      loadView("overview");
    } else { throw new Error(); }
  } catch (err) {
    const e2 = el("login-error");
    e2.textContent = "Wrong passphrase.";
    e2.classList.remove("hidden");
  }
});

// ---------- navigation ----------
const TITLES = { overview: "Overview", leads: "Leads", listings: "Listings", approvals: "Approvals", copilot: "Copilot", settings: "Settings" };
document.querySelectorAll(".sidebar nav a").forEach(a => {
  a.addEventListener("click", () => loadView(a.dataset.view));
});
function loadView(view) {
  document.querySelectorAll(".sidebar nav a").forEach(a => a.classList.toggle("active", a.dataset.view === view));
  document.querySelectorAll(".view").forEach(v => v.classList.add("hidden"));
  el("view-" + view).classList.remove("hidden");
  el("view-title").textContent = TITLES[view] || view;
  ({ overview: loadOverview, leads: loadLeads, listings: loadListings, approvals: loadApprovals, copilot: loadCopilot, settings: loadSettings }[view] || (() => {}))();
}
el("btn-briefing").addEventListener("click", async () => {
  toast("Generating briefing…");
  try { const r = await api("/api/admin/briefing", { method: "POST" }); toast(r.text, "ok"); switchView("overview"); }
  catch (e) { toast("Briefing failed: " + e.message, "err"); }
});
el("btn-followups").addEventListener("click", async () => {
  try { const r = await api("/api/admin/run_followups", { method: "POST" }); toast(r.message, "ok"); }
  catch (e) { toast("Follow-ups failed: " + e.message, "err"); }
});
el("btn-export").addEventListener("click", () => {
  const url = adminKey ? "/api/admin/export" : "/api/admin/export";
  const a = document.createElement("a"); a.href = url; a.download = "lead-database.xlsx";
  if (adminKey) a.setAttribute("data-x", "");
  document.body.appendChild(a); a.click(); a.remove();
});

// ---------- overview ----------
async function loadOverview() {
  let o;
  try { o = await api("/api/admin/overview"); } catch (e) { toast(e.message, "err"); return; }
  const t = o.totals, bs = o.by_status;
  const cards = [
    { n: t.total || 0, l: "Total leads" },
    { n: t.qualified || 0, l: "Qualified" },
    { n: t.needs_agent || 0, l: "Need agent" },
    { n: t.banned || 0, l: "Banned" },
    { n: o.pending_approvals, l: "Pending approvals", badge: "#nav-badge" },
    { n: o.followups_due, l: "Follow-ups due" },
    { n: o.reengagement_on ? "ON" : "OFF", l: "Re-engagement", cls: o.reengagement_on ? "on" : "off" },
    { n: o.briefing_on ? "ON" : "OFF", l: "Briefing", cls: o.briefing_on ? "on" : "off" },
  ];
  el("stat-cards").innerHTML = cards.map(c =>
    `<div class="stat ${c.cls || ""}"><div class="num">${esc(c.n)}</div><div class="lbl">${esc(c.l)}</div></div>`
  ).join("");
  // hot leads
  const hot = o.hot_leads || [];
  el("overview-hot").innerHTML = hot.length ? hot.map(h => `
    <div class="lead-row" data-lead="${h.id}">
      <div class="name">#${h.id} ${esc(h.name || "Unknown")} · ${esc(h.lead_type)}</div>
      <div class="meta">${esc(h.property_address || "no property")} · score ${h.score ?? "-"} · ${fmtDate(h.last_contacted_at)}</div>
    </div>`).join("") : `<div class="empty">No hot leads in the last 7 days.</div>`;
  el("overview-hot").querySelectorAll(".lead-row").forEach(r => r.addEventListener("click", () => openLead(r.dataset.lead)));
  // pending approvals preview
  updateApprovalBadge(o.pending_approvals);
  if (o.pending_approvals > 0) {
    const rows = await api("/api/admin/approvals").catch(() => []);
    el("overview-approvals").innerHTML = rows.slice(0, 5).map(a => approvalCard(a)).join("") +
      `<div class="empty"><a href="#" data-go="approvals">View all →</a></div>`;
    wireApprovals(el("overview-approvals"));
    el("overview-approvals").querySelector("[data-go]").addEventListener("click", e => { e.preventDefault(); loadView("approvals"); });
  } else {
    el("overview-approvals").innerHTML = `<div class="empty">Nothing waiting for approval.</div>`;
  }
}
function updateApprovalBadge(n) {
  const b = el("nav-badge");
  if (n > 0) { b.textContent = n; b.classList.remove("hidden"); } else { b.classList.add("hidden"); }
}

// ---------- leads ----------
el("lead-refresh").addEventListener("click", loadLeads);
["lead-search", "lead-status", "lead-type"].forEach(id => el(id).addEventListener("input", debounce(loadLeads, 300)));
async function loadLeads() {
  const q = el("lead-search").value.trim();
  const st = el("lead-status").value;
  const ty = el("lead-type").value;
  let url = "/api/admin/leads?limit=300";
  if (q) url += "&q=" + encodeURIComponent(q);
  if (st) url += "&status=" + encodeURIComponent(st);
  if (ty) url += "&lead_type=" + encodeURIComponent(ty);
  let rows;
  try { rows = await api(url); } catch (e) { toast(e.message, "err"); return; }
  const tb = el("leads-table").querySelector("tbody");
  if (!rows.length) { tb.innerHTML = `<tr><td colspan="8" class="empty">No leads match.</td></tr>`; return; }
  tb.innerHTML = rows.map(r => `
    <tr data-lead="${r.id}">
      <td>${r.id}</td>
      <td>${esc(r.name || "Unknown")}</td>
      <td>${esc(r.lead_type)}</td>
      <td>${statusPill(r.status)}</td>
      <td class="score ${r.score >= 6 ? "hot" : ""}">${r.score ?? "-"}</td>
      <td>${esc(r.property_address || "-")}</td>
      <td>${esc(r.budget || "-")}</td>
      <td>${fmtDate(r.last_contacted_at)}</td>
    </tr>`).join("");
  tb.querySelectorAll("tr").forEach(tr => tr.addEventListener("click", () => openLead(tr.dataset.lead)));
}
async function openLead(id) {
  let d;
  try { d = await api("/api/admin/leads/" + id); } catch (e) { toast(e.message, "err"); return; }
  const L = d.lead;
  const tx = (d.transcript || []).map(m => `
    <div class="m"><div class="role ${esc(m.role)}">${esc(m.role)} · ${esc(m.channel || "")}</div>${esc(m.content)}</div>`
  ).join("");
  el("lead-modal-body").innerHTML = `
    <h2>#${L.id} ${esc(L.name || "Unknown")}</h2>
    <div class="kv">
      <li><span>Type</span><b>${esc(L.lead_type)}</b></li>
      <li><span>Status</span><b>${statusPill(L.status)}</b></li>
      <li><span>Score</span><b>${L.score ?? "-"} / 10${L.is_qualified ? " (qualified)" : ""}</b></li>
      <li><span>Email</span><b>${esc(L.email || "-")}</b></li>
      <li><span>Phone</span><b>${esc(L.phone || "-")}</b></li>
      <li><span>Telegram</span><b>${L.telegram_username ? "@" + esc(L.telegram_username) : (L.telegram_chat_id ? "linked" : "no")}</b></li>
      <li><span>Property</span><b>${esc(L.property_address || "-")}</b></li>
      <li><span>Budget</span><b>${esc(L.budget || "-")}</b></li>
      <li><span>Timeline</span><b>${esc(L.timeline || "-")}</b></li>
      <li><span>Notes</span><b>${esc(L.notes || "-")}</b></li>
      <li><span>Source</span><b>${esc(L.source)}</b></li>
    </div>
    <h3>Conversation</h3>
    <div class="transcript">${tx || '<div class="empty">No messages yet.</div>'}</div>
    <div class="reply-box">
      <textarea id="reply-text" placeholder="Write a message to the lead…"></textarea>
      <button class="btn" id="reply-send">Send</button>
    </div>
    <div class="status-row">
      <button class="btn small" data-st="IN_PROGRESS">Resume / Unban</button>
      <button class="btn small danger" data-st="BANNED">Ban</button>
    </div>`;
  el("lead-modal").classList.remove("hidden");
  el("reply-send").addEventListener("click", async () => {
    const txt = el("reply-text").value.trim();
    if (!txt) { toast("Type a message first", "err"); return; }
    try {
      const r = await api(`/api/admin/leads/${L.id}/reply`, { method: "POST", body: { text: txt } });
      toast(r.message, "ok"); el("reply-text").value = "";
    } catch (e) { toast(e.message, "err"); }
  });
  el("lead-modal-body").querySelectorAll("[data-st]").forEach(b => b.addEventListener("click", async () => {
    try {
      const r = await api(`/api/admin/leads/${L.id}/status`, { method: "POST", body: { status: b.dataset.st } });
      toast(r.message, "ok"); el("lead-modal").classList.add("hidden"); loadLeads();
    } catch (e) { toast(e.message, "err"); }
  }));
}
el("lead-modal-close").addEventListener("click", () => el("lead-modal").classList.add("hidden"));
el("lead-modal").addEventListener("click", e => { if (e.target.id === "lead-modal") el("lead-modal").classList.add("hidden"); });

// ---------- listings ----------
async function loadListings() {
  let rows;
  try { rows = await api("/api/admin/listings"); } catch (e) { toast(e.message, "err"); return; }
  const tb = el("listings-table").querySelector("tbody");
  if (!rows.length) { tb.innerHTML = `<tr><td colspan="6" class="empty">No listings.</td></tr>`; return; }
  tb.innerHTML = rows.map(r => `
    <tr>
      <td>${r.id}</td>
      <td>${esc(r.address)}</td>
      <td>${esc(r.property_type || "-")}</td>
      <td>${esc(r.asking_price || "-")}</td>
      <td>${statusPill(r.status)}</td>
      <td>
        <button class="btn small" data-sold="${r.id}">Mark sold</button>
        ${r.review_token ? `<a class="btn small ghost" href="/listings/review/${esc(r.review_token)}" target="_blank">Review</a>` : ""}
        <button class="btn small ghost" data-match="${r.id}">Match</button>
      </td>
    </tr>`).join("");
  tb.querySelectorAll("[data-sold]").forEach(b => b.addEventListener("click", async () => {
    if (!confirm("Mark listing #" + b.dataset.sold + " as SOLD?")) return;
    try { const r = await api(`/api/admin/listings/${b.dataset.sold}/status`, { method: "POST", body: { status: "SOLD" } }); toast(r.message, "ok"); loadListings(); }
    catch (e) { toast(e.message, "err"); }
  }));
  tb.querySelectorAll("[data-match]").forEach(b => b.addEventListener("click", async () => {
    toast("Running matchmaker…");
    try { const r = await api(`/api/admin/match/${b.dataset.match}`, { method: "POST" });
      toast(`Matchmaker: ${r.candidates} checked, ${r.proposals?.length || 0} intros drafted for approval.`, "ok");
      loadView("approvals"); }
    catch (e) { toast("Match failed: " + e.message, "err"); }
  }));
}

// ---------- approvals ----------
async function loadApprovals() {
  let rows;
  try { rows = await api("/api/admin/approvals"); } catch (e) { toast(e.message, "err"); return; }
  updateApprovalBadge(rows.length);
  const box = el("approvals-list");
  box.innerHTML = rows.length ? rows.map(a => approvalCard(a)).join("") : `<div class="empty">Nothing waiting for approval.</div>`;
  wireApprovals(box);
}
function approvalCard(a) {
  return `<div class="approval" data-id="${a.id}">
    <div class="src">${esc(a.source)} · #${a.id} · ${fmtDate(a.created_at)}</div>
    <div class="summary">${esc(a.summary)}</div>
    <div class="approval-actions">
      <button class="btn small" data-act="approve">✅ Approve</button>
      <button class="btn small ghost" data-act="cancel">✖️ Cancel</button>
    </div>
  </div>`;
}
function wireApprovals(box) {
  box.querySelectorAll(".approval").forEach(card => {
    const id = card.dataset.id;
    card.querySelectorAll("[data-act]").forEach(b => b.addEventListener("click", async () => {
      try {
        const r = await api(`/api/admin/approvals/${id}/decide`, { method: "POST", body: { approve: b.dataset.act === "approve" } });
        toast(r.message, "ok"); loadApprovals();
      } catch (e) { toast(e.message, "err"); }
    }));
  });
}

// ---------- copilot ----------
function loadCopilot() {
  const log = el("copilot-log");
  if (!log.dataset.init) {
    log.dataset.init = "1";
    addBubble("assistant", "Hi, I'm your back-office copilot. Ask me about leads, listings or stats, or ask me to draft a message or change a status — I'll prepare it for your approval.");
  }
}
el("copilot-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const txt = el("copilot-text").value.trim();
  if (!txt) return;
  el("copilot-text").value = "";
  addBubble("user", txt);
  const thinking = addBubble("assistant", "…");
  try {
    const r = await api("/api/admin/copilot", { method: "POST", body: { message: txt } });
    thinking.remove();
    let out = r.answer || "(no answer)";
    if (r.proposals && r.proposals.length) {
      out += "\n\n" + r.proposals.map(p => "▸ " + p.summary).join("\n");
    }
    addBubble("assistant", out);
  } catch (err) {
    thinking.remove();
    addBubble("assistant", "⚠️ " + err.message);
  }
});
el("copilot-reset").addEventListener("click", async () => {
  try { await api("/api/admin/copilot/reset", { method: "POST" }); el("copilot-log").innerHTML = ""; el("copilot-log").dataset.init = ""; loadCopilot(); toast("Copilot memory cleared", "ok"); }
  catch (e) { toast(e.message, "err"); }
});
function addBubble(role, text) {
  const b = document.createElement("div");
  b.className = "bubble " + role;
  b.textContent = text;
  el("copilot-log").appendChild(b);
  el("copilot-log").scrollTop = el("copilot-log").scrollHeight;
  return b;
}

// ---------- settings ----------
async function loadSettings() {
  let s;
  try { s = await api("/api/admin/settings"); } catch (e) { toast(e.message, "err"); return; }
  el("set-reengagement").checked = s.reengagement_on;
  el("set-briefing").checked = s.briefing_on;
  el("settings-schedule").textContent =
    `Re-engagement fires at ${s.reengagement_hour}:00. Briefing at ${s.briefing_hour}:00. Timezone: ${s.timezone}.`;
  el("settings-conn").innerHTML = [
    ["Email intake", s.mail_enabled ? "connected" : "not configured"],
    ["Telegram bot", s.telegram_enabled ? "connected" : "not configured"],
    ["LLM (Hunyuan)", s.llm_configured ? "configured" : "not configured"],
  ].map(([k, v]) => `<li><span>${k}</span><b>${v}</b></li>`).join("");
  // profile
  let p;
  try { p = await api("/api/admin/profile"); } catch (e) { toast(e.message, "err"); return; }
  const prof = p.profile, fields = p.fields;
  el("profile-form").innerHTML = fields.map(f => {
    const val = prof[f] ?? "";
    const input = f === "include_phone"
      ? `<input type="checkbox" ${val ? "checked" : ""} data-field="${f}" />`
      : (f === "commission_policy" || f === "marketing_services" || f === "showing_style" || f === "service_areas" || f === "working_hours")
        ? `<textarea rows="2" data-field="${f}">${esc(val)}</textarea>`
        : `<input type="text" data-field="${f}" value="${esc(val)}" />`;
    return `<label>${esc(f.replace(/_/g, " "))}${input}</label>`;
  }).join("");
}
el("set-reengagement").addEventListener("change", async e => {
  try { await api("/api/admin/settings/reengagement", { method: "POST", body: { enabled: e.target.checked } }); toast("Re-engagement " + (e.target.checked ? "ON" : "OFF"), "ok"); }
  catch (err) { toast(err.message, "err"); e.target.checked = !e.target.checked; }
});
el("set-briefing").addEventListener("change", async e => {
  try { await api("/api/admin/settings/briefing", { method: "POST", body: { enabled: e.target.checked } }); toast("Briefing " + (e.target.checked ? "ON" : "OFF"), "ok"); }
  catch (err) { toast(err.message, "err"); e.target.checked = !e.target.checked; }
});
el("profile-save").addEventListener("click", async () => {
  const fields = [...el("profile-form").querySelectorAll("[data-field]")];
  for (const f of fields) {
    const field = f.dataset.field;
    const value = f.type === "checkbox" ? (f.checked ? "1" : "0") : f.value;
    try { await api("/api/admin/profile", { method: "POST", body: { field, value } }); }
    catch (e) { toast("Failed: " + field + " — " + e.message, "err"); return; }
  }
  toast("Profile saved", "ok");
});

// ---------- util ----------
function debounce(fn, ms) {
  let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}
function switchView(v) { loadView(v); }

boot();
