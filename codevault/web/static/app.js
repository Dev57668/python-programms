/* CodeVault dashboard: vanilla JS, no build step. */
"use strict";

const POLL_MS = 2500;
const VIEWS = ["overview", "files", "git", "timeline", "deleted", "integrity", "settings"];
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const state = {
  view: "overview",
  overview: null,
  files: [],
  timeline: [],
  deleted: [],
  git: null,
  range: "1h",
  timelineFilter: "ALL",
  fileFilter: "",
  selectedPath: null,
  history: null,
  selectedSnapId: null,
  viewerMode: "view", // view | prev | current
  maxSnapId: null,
  online: true,
  loaded: false,
};

/* ---------------- utils ---------------- */

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const ic = (name, cls = "") => `<svg class="i ${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`;

function parseTs(ts) {
  if (!ts || ts === "None") return null;
  const d = new Date(ts.replace(" ", "T"));
  return isNaN(d) ? null : d;
}

function ago(ts) {
  const d = parseTs(ts);
  if (!d) return "never";
  const s = Math.max(0, Math.round((Date.now() - d.getTime()) / 1000));
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  const days = Math.round(h / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

function clock(ts) {
  const d = parseTs(ts);
  return d ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "";
}

function splitPath(p) {
  const i = p.lastIndexOf("/");
  return i < 0 ? ["", p] : [p.slice(0, i + 1), p.slice(i + 1)];
}

function shortPath(p) {
  const parts = p.split("/").filter(Boolean);
  return parts.length > 4 ? `…/${parts.slice(-3).join("/")}` : p;
}

function eventClass(ev) {
  const e = String(ev || "").toUpperCase();
  if (e === "CREATION") return "CREATED";
  if (["CREATED", "MODIFIED", "DELETED", "RENAMED", "PRE_RESTORE", "INITIAL", "AI_EDIT", "PRE_AI", "CHECKPOINT"].includes(e)) return e;
  return "OTHER";
}

const EVENT_ICON = {
  CREATED: "plus", INITIAL: "scan", MODIFIED: "edit", DELETED: "trash", RENAMED: "move", PRE_RESTORE: "restore",
  AI_EDIT: "bot", PRE_AI: "bot", CHECKPOINT: "pin", OTHER: "dot",
};
const EVENT_LABEL = {
  CREATED: "created", INITIAL: "initial scan", MODIFIED: "modified", DELETED: "deleted", RENAMED: "renamed",
  PRE_RESTORE: "pre-restore", AI_EDIT: "AI edit", PRE_AI: "before AI edit", CHECKPOINT: "checkpoint", OTHER: "snapshot",
};

/* Where a snapshot's content lives: on GitHub, committed locally, or only here. */
const GIT_STATE = {
  pushed: { label: "on GitHub", icon: "cloud", tip: "This exact content is in the pushed branch history." },
  committed: { label: "committed, not pushed", icon: "commit", tip: "Committed locally but not pushed yet." },
  local: { label: "only on this machine", icon: "laptop", tip: "Never committed. Only CodeVault has this version." },
};
const gitBadge = (st) => (st && GIT_STATE[st]
  ? `<span class="badge g-${st}" title="${GIT_STATE[st].tip}">${ic(GIT_STATE[st].icon)}${GIT_STATE[st].label}</span>`
  : "");

const HUMAN_SOURCES = ["manual", "me", "human"];
function sourceName(note) {
  return note ? String(note).split(" · ")[0].trim() : "";
}
function srcBadge(note, withDetail = false) {
  const name = sourceName(note);
  if (!name) return "";
  const human = HUMAN_SOURCES.includes(name.toLowerCase());
  const label = withDetail ? note : name;
  return `<span class="badge src ${human ? "human" : ""}" title="${esc(note)}">${ic(human ? "edit" : "bot")}${esc(label)}</span>`;
}

const GIT_LETTER = { modified: "M", added: "A", deleted: "D", untracked: "U", renamed: "R" };
const gitLetter = (st) => (st ? `<span class="st st-${st}" title="git: ${st}">${GIT_LETTER[st] || "?"}</span>` : "");
const evIco = (c) => `<span class="ev-ico ev-${c}" title="${EVENT_LABEL[c]}">${ic(EVENT_ICON[c])}</span>`;

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function toast(title, detail = "", kind = "") {
  const icon = kind === "err" ? "alert" : kind === "info" ? "layers" : "check";
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.innerHTML = `<span class="t-ico">${ic(icon)}</span><div><b>${esc(title)}</b>${detail ? `<span class="t-detail">${esc(detail)}</span>` : ""}</div>`;
  const box = $("#toasts");
  box.appendChild(el);
  while (box.children.length > 3) box.firstChild.remove();
  setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 300); }, 4200);
}

function setBusy(btn, busy, label) {
  btn.disabled = busy;
  btn.classList.toggle("is-busy", busy);
  const lbl = $(".lbl", btn);
  if (label && lbl) lbl.textContent = label;
}

/* ---------------- modal ---------------- */

function openModal(title, bodyHtml, { okLabel = "Confirm", cancelLabel = "Cancel", showOk = true } = {}) {
  return new Promise((resolve) => {
    const modal = $("#modal");
    const prevFocus = document.activeElement;
    $("#modal-title").textContent = title;
    $("#modal-body").innerHTML = bodyHtml;
    $("#modal-ok").textContent = okLabel;
    $("#modal-ok").hidden = !showOk;
    $("#modal-cancel").textContent = cancelLabel;
    modal.hidden = false;
    document.body.style.overflow = "hidden";
    (showOk ? $("#modal-ok") : $("#modal-cancel")).focus();
    const done = (v) => {
      modal.hidden = true;
      document.body.style.overflow = "";
      $("#modal-ok").onclick = $("#modal-cancel").onclick = modal.onclick = modal.onkeydown = null;
      if (prevFocus && prevFocus.focus) prevFocus.focus();
      resolve(v);
    };
    $("#modal-ok").onclick = () => done(true);
    $("#modal-cancel").onclick = () => done(false);
    modal.onclick = (e) => { if (e.target === modal) done(false); };
    modal.onkeydown = (e) => {
      if (e.key === "Escape") { e.stopPropagation(); done(false); }
      if (e.key === "Tab") { // keep focus inside the dialog
        const f = $$("button:not([hidden])", modal);
        const i = f.indexOf(document.activeElement);
        e.preventDefault();
        f[(i + (e.shiftKey ? -1 : 1) + f.length) % f.length].focus();
      }
    };
  });
}

/* ---------------- theme ---------------- */

const THEMES = ["system", "light", "dark"];
const THEME_ICON = { system: "monitor", light: "sun", dark: "moon" };
let theme = "system";
try { theme = localStorage.getItem("cv-theme") || "system"; } catch { /* storage blocked */ }

function applyTheme() {
  if (theme === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = theme;
  $$("[data-theme-btn]").forEach((b) => {
    $("use", b).setAttribute("href", `#i-${THEME_ICON[theme]}`);
    b.setAttribute("aria-label", `Theme: ${theme}. Click to change`);
    b.title = `Theme: ${theme}`;
    const lbl = $(".lbl", b);
    if (lbl) lbl.textContent = `${theme[0].toUpperCase()}${theme.slice(1)} theme`;
  });
  if (state.loaded) renderChart();
}

function cycleTheme() {
  theme = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
  try { localStorage.setItem("cv-theme", theme); } catch { /* ignore */ }
  applyTheme();
}

/* ---------------- count-up stats ---------------- */

const shownStats = {};
function setStat(key, value) {
  $$(`[data-stat="${key}"]`).forEach((el) => {
    const prev = shownStats[key];
    if (prev === value) return;
    if (typeof value === "number" && typeof prev === "number") {
      const start = performance.now();
      const step = (now) => {
        const t = Math.min(1, (now - start) / 600);
        el.textContent = Math.round(prev + (value - prev) * (1 - Math.pow(1 - t, 3)));
        if (t < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
      if (el.classList.contains("stat-value")) {
        el.classList.remove("bump"); void el.offsetWidth; el.classList.add("bump");
      }
    } else {
      el.textContent = value;
    }
  });
  shownStats[key] = value;
}

/* ---------------- overview ---------------- */

function renderDaemon(o) {
  const running = o.daemon.status === "RUNNING";
  $$("[data-daemon-dot]").forEach((d) => d.classList.toggle("on", running));
  $$("[data-daemon-title]").forEach((d) => { d.textContent = running ? "Watcher running" : "Watcher stopped"; });
  $$("[data-daemon-sub]").forEach((d) => { d.textContent = running ? `PID ${o.daemon.pid} · saving every change` : "start it to capture new saves"; });
  $$("[data-daemon-btn]").forEach((btn) => {
    if (btn.classList.contains("is-busy")) return;
    btn.disabled = false;
    btn.dataset.action = running ? "stop" : "start";
    btn.setAttribute("aria-label", running ? "Stop watcher" : "Start watcher");
    btn.title = running ? "Stop watcher" : "Start watcher";
    const lbl = $(".lbl", btn);
    if (btn.classList.contains("pill-btn")) {
      btn.classList.toggle("on", running);
      lbl.textContent = running ? "Watching" : "Paused";
      return;
    }
    $("use", btn).setAttribute("href", running ? "#i-stop" : "#i-play");
    lbl.textContent = running ? "Stop watcher" : "Start watcher";
    if (!btn.classList.contains("hero-cta")) btn.classList.toggle("btn-primary", !running);
    else btn.hidden = running;
  });
}

function renderOverview() {
  const o = state.overview;
  if (!o) return;
  $("#project-name").textContent = o.project_name;
  $("#project-path").textContent = shortPath(o.project_dir);
  $("#project-path").title = o.project_dir;
  document.title = `CodeVault · ${o.project_name}`;

  const s = o.stats;
  setStat("protected_files", s.protected_files);
  setStat("snapshots", s.snapshots);
  setStat("deleted_files", s.deleted_files);
  setStat("pinned", s.pinned);
  setStat("storage", s.storage);
  $$('[data-count="files"]').forEach((c) => { c.textContent = state.files.length || ""; });
  $$('[data-count="deleted"]').forEach((c) => { c.textContent = s.deleted_files || ""; });

  renderDaemon(o);

  const running = o.daemon.status === "RUNNING";
  const total = s.protected_files + s.deleted_files;
  const coverage = total ? s.protected_files / total : 0;
  $("#hero").classList.toggle("idle", !running);
  $("#hero-status").textContent = running
    ? "Protection active"
    : s.snapshots ? "Watcher paused · history safe" : "Not protecting yet";
  $("#hero-desc").textContent = running
    ? "Every save is captured, hashed with SHA-256 and stored atomically, so uncommitted work is never lost."
    : s.snapshots
      ? "Existing snapshots are still restorable. Start the watcher to keep capturing new changes."
      : "Start the watcher and CodeVault will snapshot every source file you save in this project.";
  $("#hero-last").textContent = ago(s.last_snapshot);
  $("#hero-retention").textContent = `${o.config.max_snapshots} versions · ${o.config.max_age_days} days`;
  const circ = 339.3;
  $("#ring-progress").style.strokeDashoffset = String(circ * (1 - (running ? Math.max(coverage, 0.02) : coverage * 0.35)));

  renderChart();
  renderSettings();
}

function renderChart() {
  const el = $("#activity-chart");
  const acts = (state.overview?.activity || []).map((a) => ({ d: parseTs(a.t), type: a.type }));
  const narrow = el.clientWidth < 480;
  const cfg = {
    "1h": { n: 12, ms: 5 * 60e3, every: narrow ? 3 : 2, fmt: (d) => d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) },
    "24h": { n: 24, ms: 3600e3, every: narrow ? 6 : 4, fmt: (d) => d.toLocaleTimeString([], { hour: "2-digit" }) },
    "7d": { n: 7, ms: 86400e3, every: 1, fmt: (d) => d.toLocaleDateString([], { weekday: "short" }) },
  }[state.range];

  const end = state.range === "7d"
    ? new Date(new Date().setHours(24, 0, 0, 0)).getTime()
    : Math.ceil(Date.now() / cfg.ms) * cfg.ms;
  const startT = end - cfg.n * cfg.ms;
  const buckets = Array.from({ length: cfg.n }, (_, i) => ({ t: new Date(startT + i * cfg.ms), mod: 0, new: 0, pre: 0 }));
  for (const a of acts) {
    if (!a.d) continue;
    const i = Math.floor((a.d.getTime() - startT) / cfg.ms);
    if (i < 0 || i >= cfg.n) continue;
    const t = String(a.type).toLowerCase();
    const k = t === "pre_restore" ? "pre" : ["created", "creation", "initial"].includes(t) ? "new" : "mod";
    buckets[i][k]++;
  }
  const totals = buckets.map((b) => b.mod + b.new + b.pre);
  const sum = totals.reduce((a, b) => a + b, 0);
  const max = Math.max(1, ...totals);
  const W = Math.max(el.clientWidth, 280), H = el.clientHeight || 200, padL = 28, padB = 22, plotH = H - padB - 8;
  const bw = (W - padL) / cfg.n;
  const y = (v) => 8 + plotH - (v / max) * plotH;
  const ticks = [0, Math.ceil(max / 2), max].filter((v, i, a) => a.indexOf(v) === i);

  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Snapshots per interval, ${state.range} window">`;
  for (const t of ticks) {
    svg += `<line class="grid" x1="${padL}" x2="${W}" y1="${y(t)}" y2="${y(t)}"/>`;
    svg += `<text class="axis" x="${padL - 8}" y="${y(t) + 3.5}" text-anchor="end">${t}</text>`;
  }
  const colors = { mod: "var(--green)", new: "var(--cyan)", pre: "var(--violet)" };
  buckets.forEach((b, i) => {
    const w = Math.min(bw * 0.62, 34);
    const x = padL + i * bw + (bw - w) / 2;
    svg += `<rect class="hit" data-i="${i}" x="${padL + i * bw}" y="0" width="${bw}" height="${H - padB}" fill="transparent"/>`;
    let acc = 0;
    for (const k of ["mod", "new", "pre"]) {
      if (!b[k]) continue;
      const y1 = y(acc + b[k]);
      const h = y(acc) - y1;
      svg += `<rect class="bar" data-i="${i}" x="${x}" y="${y1}" width="${w}" height="${Math.max(h - 1.5, 2)}" rx="4" fill="${colors[k]}"/>`;
      acc += b[k];
    }
    if (i % cfg.every === 0) {
      svg += `<text class="axis" x="${padL + i * bw + bw / 2}" y="${H - 5}" text-anchor="middle">${esc(cfg.fmt(b.t))}</text>`;
    }
  });
  if (!sum) {
    svg += `<text class="empty" x="${(W + padL) / 2}" y="${H / 2 - 6}" text-anchor="middle">No snapshots in this window yet.</text>`;
    svg += `<text class="empty" x="${(W + padL) / 2}" y="${H / 2 + 14}" text-anchor="middle" style="font-size:12px">Save a file to see it appear.</text>`;
  }
  svg += `</svg><div class="chart-tip" hidden></div>`;
  el.innerHTML = svg;

  const busiest = buckets[totals.indexOf(Math.max(...totals))];
  $("#chart-summary").textContent = sum
    ? `${sum} snapshots in the last ${state.range}. Busiest interval ${cfg.fmt(busiest.t)} with ${Math.max(...totals)}.`
    : `No snapshots in the last ${state.range}.`;

  const tip = $(".chart-tip", el);
  const showTip = (e) => {
    const i = e.target.dataset?.i;
    if (i === undefined) { tip.hidden = true; return; }
    const b = buckets[+i];
    const total = totals[+i];
    const r = el.getBoundingClientRect();
    const pt = e.touches ? e.touches[0] : e;
    tip.hidden = false;
    tip.style.left = `${Math.min(Math.max(pt.clientX - r.left, 70), r.width - 70)}px`;
    tip.style.top = `${pt.clientY - r.top}px`;
    tip.innerHTML = `<b>${total}</b> snapshot${total === 1 ? "" : "s"} · ${esc(cfg.fmt(b.t))}`;
  };
  el.onmousemove = showTip;
  el.ontouchstart = showTip;
  el.onmouseleave = () => { tip.hidden = true; };
}

function evPath(ev) {
  return ev.event === "RENAMED" ? `${ev.old_path} → ${ev.new_path}` : ev.path;
}

function renderFeed(newIds = new Set()) {
  const items = state.timeline.slice(0, 14);
  $("#feed").innerHTML = items.length
    ? items.map((ev) => {
        const c = eventClass(ev.event);
        return `<li class="${newIds.has(ev.snapshot_id) ? "new" : ""}">
          ${evIco(c)}
          <span class="fp" title="${esc(evPath(ev))}${ev.note ? ` (${esc(ev.note)})` : ""}">${esc(evPath(ev))}</span>
          <time datetime="${esc(ev.timestamp)}" title="${esc(ev.timestamp)}">${ago(ev.timestamp)}</time>
        </li>`;
      }).join("")
    : `<li><span></span><span class="muted">Nothing yet. Start the watcher and save a file.</span><span></span></li>`;
}

/* ---------------- files ---------------- */

function renderFileList() {
  const q = state.fileFilter.toLowerCase();
  const files = state.files.filter((f) => f.path.toLowerCase().includes(q));
  $("#file-list").innerHTML = files.length
    ? files.map((f) => {
        const [dir, name] = splitPath(f.path);
        const active = f.path === state.selectedPath;
        return `<li role="option" tabindex="0" aria-selected="${active}" data-path="${esc(f.path)}" class="${active ? "active" : ""} ${f.exists ? "" : "deleted"}">
          <span class="f-ico">${ic("files", "i-sm")}</span>
          <span class="fname" title="${esc(f.path)}"><span class="dir">${esc(dir)}</span>${esc(name)}</span>
          ${f.local_only ? `<span class="local-dot" title="${f.local_only} version${f.local_only === 1 ? "" : "s"} only on this machine"></span>` : ""}
          ${gitLetter(f.git)}
          <span class="badge type" title="${f.snapshots} snapshots">${ic("layers")}${f.snapshots}</span>
          ${f.exists ? "" : `<span class="badge bad">deleted</span>`}
        </li>`;
      }).join("")
    : `<li class="empty">${state.loaded ? `No tracked files${q ? " match" : " yet"}.` : `<span class="sk sk-line"></span>`}</li>`;
}

async function selectFile(path, snapId = null) {
  state.selectedPath = path;
  state.viewerMode = "view";
  state.selectedSnapId = snapId;
  $("#files-split").classList.add("show-detail");
  renderFileList();
  await loadHistory();
  if (window.matchMedia("(max-width: 1023px)").matches) window.scrollTo({ top: 0, behavior: "smooth" });
}

function closeDetail() {
  $("#files-split").classList.remove("show-detail");
  const active = $(`#file-list li[data-path="${CSS.escape(state.selectedPath || "")}"]`);
  if (active) active.focus();
}

async function loadHistory() {
  if (!state.selectedPath) return;
  try {
    state.history = await api(`/api/history?path=${encodeURIComponent(state.selectedPath)}`);
  } catch (e) {
    toast("Could not load history", e.message, "err");
    return;
  }
  const snaps = state.history.snapshots;
  if (!snaps.some((s) => s.id === state.selectedSnapId)) state.selectedSnapId = snaps[0]?.id ?? null;
  renderDetail();
}

function renderDetail() {
  const h = state.history;
  if (!h) return;
  const snaps = h.snapshots;
  $("#file-detail").innerHTML = `
    <div class="detail-head">
      <button class="icon-btn back" data-back aria-label="Back to files">${ic("back")}</button>
      <div style="min-width:0">
        <h2>${esc(h.path)}</h2>
        <div class="sub">
          <span>${snaps.length} snapshot${snaps.length === 1 ? "" : "s"}</span>
          <span class="badge ${h.exists ? "ok" : "bad"}">${ic(h.exists ? "check" : "trash")}${h.exists ? "on disk" : "deleted from disk"}</span>
          ${h.github_url ? `<a class="gh-link" href="${esc(h.github_url)}" target="_blank" rel="noopener noreferrer">${ic("github")}View on GitHub${ic("external")}</a>` : ""}
        </div>
      </div>
    </div>
    <div class="detail-body">
      <ol class="versions" aria-label="Snapshot versions">
        ${snaps.map((s, i) => `
          <li tabindex="0" data-id="${s.id}" aria-current="${s.id === state.selectedSnapId}" class="${esc(String(s.event_type).toLowerCase())} ${s.git === "local" ? "local" : ""} ${s.id === state.selectedSnapId ? "active" : ""}">
            <div class="v-top"><span class="v-id">#${s.id}${i === 0 ? " · latest" : ""}</span><span class="v-time">${ago(s.timestamp)}</span></div>
            <div class="v-meta">
              <span class="badge type">${esc(EVENT_LABEL[eventClass(s.event_type)])}</span>
              <span class="badge type">${esc(s.size_str)}</span>
              ${s.pinned ? `<span class="badge pin">${ic("pin")}pinned</span>` : ""}
              ${srcBadge(s.note)}
              ${gitBadge(s.git)}
            </div>
          </li>`).join("")}
      </ol>
      <div class="viewer" id="viewer"></div>
    </div>`;
  const active = $(".versions li.active");
  if (active) active.scrollIntoView({ block: "nearest", inline: "nearest" });
  renderViewer();
}

async function renderViewer() {
  const el = $("#viewer");
  const snaps = state.history?.snapshots || [];
  const idx = snaps.findIndex((s) => s.id === state.selectedSnapId);
  const snap = snaps[idx];
  if (!el) return;
  if (!snap) { el.innerHTML = `<div class="empty-state"><p>No snapshots for this file.</p></div>`; return; }
  const prev = snaps[idx + 1];
  const canCurrent = state.history.exists;
  if (state.viewerMode === "prev" && !prev) state.viewerMode = "view";
  if (state.viewerMode === "current" && !canCurrent) state.viewerMode = "view";
  const mode = (m, label) => `<button role="tab" aria-selected="${state.viewerMode === m}" data-mode="${m}" class="${state.viewerMode === m ? "active" : ""}"`
    + `${(m === "prev" && !prev) || (m === "current" && !canCurrent) ? " disabled" : ""}>${label}</button>`;

  el.innerHTML = `
    <div class="viewer-bar">
      <div class="seg" id="viewer-seg" role="tablist" aria-label="View mode">
        ${mode("view", "Content")}${mode("prev", "vs previous")}${mode("current", "vs current")}
      </div>
      <div class="viewer-actions">
        <button class="btn btn-sm" data-act="pin">${ic("pin")}<span>${snap.pinned ? "Unpin" : "Pin"}</span></button>
        <button class="btn btn-sm btn-primary" data-act="restore">${ic("restore")}<span>Restore #${snap.id}</span></button>
      </div>
    </div>
    <div class="code" id="code" tabindex="0" aria-label="Snapshot content"><table><tr class="note-row"><td><span class="sk sk-line" style="width:240px"></span></td></tr></table></div>
    <div class="hint" title="${esc(snap.hash)}">${ic("hash", "i-sm")}sha256 ${esc(snap.hash)} · ${esc(snap.timestamp)}${snap.note ? ` · ${esc(snap.note)}` : ""}</div>`;

  try {
    let html;
    if (state.viewerMode === "view") {
      const d = await api(`/api/snapshot?id=${snap.id}`);
      if (d.binary) html = `<table><tr class="note-row"><td>Binary content cannot be previewed.</td></tr></table>`;
      else {
        const lines = d.content.split("\n");
        if (lines.length > 1 && lines[lines.length - 1] === "") lines.pop();
        html = `<table>${lines.map((l, i) => `<tr><td class="ln">${i + 1}</td><td>${esc(l)}</td></tr>`).join("")}</table>`;
      }
    } else {
      const to = state.viewerMode === "prev" ? snap.id : "current";
      const from = state.viewerMode === "prev" ? prev.id : snap.id;
      const d = await api(`/api/diff?from=${from}&to=${to}`);
      const head = `<tr class="hunk"><td colspan="4"><span class="diff-stats">${esc(d.from_label)} → ${esc(d.to_label)} &nbsp; <span class="a">+${d.added}</span> <span class="r">−${d.removed}</span></span></td></tr>`;
      const body = d.lines.length
        ? d.lines.map((l) => l.kind === "hunk"
            ? `<tr class="hunk"><td colspan="4">${esc(l.text)}</td></tr>`
            : `<tr class="${l.kind}"><td class="ln">${l.old ?? ""}</td><td class="ln">${l.new ?? ""}</td><td class="sign">${l.kind === "add" ? "+" : l.kind === "del" ? "−" : ""}</td><td>${esc(l.text)}</td></tr>`).join("")
        : `<tr class="note-row"><td colspan="4">Identical content.</td></tr>`;
      html = `<table>${head}${body}</table>`;
    }
    const code = $("#code");
    if (code) code.innerHTML = html;
  } catch (e) {
    const code = $("#code");
    if (code) code.innerHTML = `<table><tr class="note-row"><td>${esc(e.message)}</td></tr></table>`;
  }
}

async function restoreSnapshot(snap, path, existsNow) {
  const ok = await openModal(
    `Restore ${path}?`,
    `<dl>
      <dt>Snapshot</dt><dd>#${snap.id} · ${esc(EVENT_LABEL[eventClass(snap.event_type)])}</dd>
      <dt>Saved</dt><dd>${esc(snap.timestamp)} (${ago(snap.timestamp)})</dd>
      <dt>SHA-256</dt><dd>${esc(String(snap.hash).slice(0, 24))}…</dd>
    </dl>
    <div class="note ${existsNow ? "warn" : ""}">${ic(existsNow ? "alert" : "restore")}<span>${existsNow
      ? "The current file will be overwritten. Its present content is kept as a <b>pre-restore snapshot</b> first, so this is undoable."
      : "This file is missing from disk and will be recreated at its original path."}</span></div>`,
    { okLabel: "Restore file" },
  );
  if (!ok) return;
  try {
    const r = await api("/api/restore", { id: snap.id });
    toast("File restored", r.message);
    await refresh();
    if (state.selectedPath === path) await loadHistory();
  } catch (e) {
    toast("Restore failed", e.message, "err");
  }
}

/* ---------------- git sync ---------------- */

function renderSyncStrip() {
  const el = $("#sync-strip");
  const g = state.git;
  if (!g) { el.hidden = true; return; }
  el.hidden = false;
  if (!g.is_repo) {
    el.className = "sync-strip";
    el.innerHTML = `<span class="s-ico">${ic("branch")}</span><span class="s-text"><b>Not a git repository</b>
      <span class="s-sub">Connect this project to GitHub to see which versions are pushed.</span></span>
      <span class="s-go"><span>Set up</span>${ic("move", "i-sm")}</span>`;
    return;
  }
  const risk = g.at_risk.length;
  const ok = !risk && !g.ahead && !g.changes.length;
  el.className = `sync-strip ${ok ? "ok" : ""}`;
  const parts = [];
  if (g.changes.length) parts.push(`${g.changes.length} uncommitted`);
  if (g.ahead) parts.push(`${g.ahead} commit${g.ahead === 1 ? "" : "s"} not pushed`);
  if (g.behind) parts.push(`${g.behind} behind`);
  el.innerHTML = `<span class="s-ico">${ic(ok ? "cloud" : "laptop")}</span>
    <span class="s-text">
      <b>${ok ? "Everything is on GitHub" : risk
        ? `${risk} file${risk === 1 ? " has" : "s have"} work that exists only on this machine`
        : "Some work isn't on GitHub yet"}</b>
      <span class="s-sub">${esc(g.branch)}${g.upstream ? ` → ${esc(g.upstream)}` : " (no upstream)"}${parts.length ? ` · ${parts.join(" · ")}` : ""}</span>
    </span>
    <span class="s-go"><span>Review</span>${ic("move", "i-sm")}</span>`;
}

function renderGit() {
  const root = $("#git-root");
  const g = state.git;
  if (!g) return;
  if (!g.is_repo) {
    root.innerHTML = `<div class="card">
      <div class="git-head"><span class="gh-ico">${ic("github")}</span>
        <div class="gh-main"><div class="gh-title">This project isn't a git repository yet</div>
        <div class="gh-sub">CodeVault still protects every save. Connect git to see what's on GitHub.</div></div></div>
      <ol class="setup-steps">
        <li>Run <code>git init</code> in the project folder and make a first commit.</li>
        <li>Add your GitHub repo: <code>git remote add origin https://github.com/you/repo.git</code></li>
        <li>Push once with <code>git push -u origin main</code>. This page updates automatically.</li>
      </ol></div>`;
    return;
  }
  const vc = g.version_counts;
  const lc = g.last_commit;
  const ghBtn = g.web_url
    ? `<a class="btn btn-sm" href="${esc(g.web_url)}" target="_blank" rel="noopener noreferrer">${ic("github")}Open on GitHub</a>` : "";
  const pills = [
    g.upstream ? `<span class="sync-pill ${g.ahead ? "warn" : "good"}">${ic("upload")}${g.ahead} to push</span>` : `<span class="sync-pill warn">${ic("alert")}no upstream branch</span>`,
    g.upstream ? `<span class="sync-pill ${g.behind ? "warn" : ""}">${ic("download")}${g.behind} to pull</span>` : "",
    `<span class="sync-pill ${g.changes.length ? "warn" : "good"}">${ic("edit")}${g.changes.length} uncommitted</span>`,
  ].join("");

  const riskHtml = g.at_risk.length
    ? `<ul class="risk-list">${g.at_risk.map((r) => `
        <li>
          <span class="r-ico">${ic("laptop")}</span>
          <div style="min-width:0">
            <div class="r-path" title="${esc(r.path)}">${esc(r.path)}</div>
            <div class="r-meta">
              <span>${r.local_versions} local-only version${r.local_versions === 1 ? "" : "s"} · newest ${esc(ago(r.latest_ts))}</span>
              ${r.sources.map((src) => srcBadge(src)).join("")}
              ${r.git ? gitLetter(r.git) : ""}
              ${r.exists ? "" : `<span class="badge bad">deleted</span>`}
            </div>
          </div>
          <div class="r-actions">
            <button class="btn btn-sm" data-open="${esc(r.path)}" data-snap="${r.latest_id}">${ic("timeline")}Versions</button>
            ${r.exists ? "" : `<button class="btn btn-sm btn-primary" data-recover="${esc(r.path)}" data-id="${r.latest_id}">${ic("restore")}Recover</button>`}
          </div>
        </li>`).join("")}</ul>`
    : `<div class="git-empty">${ic("check")}Every saved version is committed. Nothing exists only on this machine.</div>`;

  const changesHtml = g.changes.length
    ? `<ul class="plain-list">${g.changes.map((c) => `<li>${gitLetter(c.status)}<span class="mono grow" title="${esc(c.path)}">${esc(c.path)}</span>
        ${c.tracked ? `<button class="link" data-open="${esc(c.path)}">history</button>` : `<span class="muted small">not watched</span>`}</li>`).join("")}</ul>`
    : `<div class="git-empty">${ic("check")}Working tree clean.</div>`;

  const commitsHtml = g.unpushed_commits.length
    ? `<ul class="plain-list">${g.unpushed_commits.map((c) => `<li><span class="sha">${esc(c.sha.slice(0, 7))}</span>
        <span class="grow" title="${esc(c.subject)}">${esc(c.subject)}</span><time>${esc(ago(c.date.slice(0, 19)))}</time></li>`).join("")}</ul>`
    : `<div class="git-empty">${ic("check")}${g.upstream ? "All commits are pushed." : "Set an upstream with git push -u to track this."}</div>`;

  root.innerHTML = `
    <div class="card">
      <div class="git-head">
        <span class="gh-ico">${ic(g.web_url ? "github" : "branch")}</span>
        <div class="gh-main">
          <div class="gh-title"><span class="branch-chip">${ic("branch", "i-sm")}${esc(g.branch)}</span>${g.upstream ? `<span class="muted small">tracking ${esc(g.upstream)}</span>` : ""}</div>
          <div class="gh-sub" title="${esc(g.remote_url || "")}">${lc ? `Last commit ${esc(lc.sha.slice(0, 7))} · ${esc(lc.subject)} · ${esc(ago(lc.date.slice(0, 19)))}` : "No commits yet"}</div>
          <div class="sync-pills">${pills}</div>
        </div>
        <div class="gh-actions">
          <button class="btn btn-sm" id="git-fetch">${ic("refresh")}<span class="lbl">Check GitHub</span></button>
          ${ghBtn}
        </div>
      </div>
      <div class="lanes">
        <div class="lane" data-tone="green"><div class="l-top"><span class="l-ico">${ic("cloud")}</span><span class="l-name">On GitHub</span></div>
          <div class="l-num">${vc.pushed}</div><p>versions safe in the pushed branch</p></div>
        <div class="lane" data-tone="cyan"><div class="l-top"><span class="l-ico">${ic("commit")}</span><span class="l-name">Committed, not pushed</span></div>
          <div class="l-num">${vc.committed}</div><p>in local git history only</p></div>
        <div class="lane" data-tone="amber"><div class="l-top"><span class="l-ico">${ic("laptop")}</span><span class="l-name">Only on this machine</span></div>
          <div class="l-num">${vc.local}</div><p>never committed. CodeVault is the only copy</p></div>
      </div>
    </div>

    <div class="card">
      <div class="card-head"><h3>Work that exists only here</h3><span class="muted small">restore these if you lose local changes</span></div>
      ${riskHtml}
    </div>

    <div class="git-cols">
      <div class="card"><div class="card-head"><h3>Uncommitted changes</h3><span class="muted small">git status</span></div>${changesHtml}</div>
      <div class="card"><div class="card-head"><h3>Commits not pushed</h3><span class="muted small">${g.upstream ? esc(`${g.upstream}..HEAD`) : ""}</span></div>${commitsHtml}</div>
    </div>`;
}

async function gitFetch(btn) {
  setBusy(btn, true, "Checking…");
  try {
    await api("/api/git/fetch", {});
    toast("Up to date with GitHub", "Fetched the latest remote branch state");
    await refresh();
  } catch (e) {
    toast("Could not reach GitHub", e.message, "err");
    setBusy(btn, false, "Check GitHub");
  }
}

/* ---------------- timeline ---------------- */

function renderTimeline() {
  const f = state.timelineFilter;
  const evs = state.timeline.filter((e) => {
    const c = eventClass(e.event);
    if (f === "ALL") return true;
    if (f === "AI") return c === "AI_EDIT" || c === "PRE_AI" || (sourceName(e.note) && !HUMAN_SOURCES.includes(sourceName(e.note).toLowerCase()));
    if (f === "CREATED") return c === "CREATED" || c === "INITIAL";
    if (f === "MODIFIED") return c === "MODIFIED" || c === "CHECKPOINT";
    return c === f;
  });
  if (!evs.length) {
    $("#timeline").innerHTML = `<li class="muted" style="padding:12px 4px">No events to show.</li>`;
    return;
  }
  let html = "";
  let day = "";
  for (const ev of evs) {
    const d = parseTs(ev.timestamp);
    const label = d ? d.toLocaleDateString([], { weekday: "long", day: "numeric", month: "short" }) : "Unknown";
    if (label !== day) { day = label; html += `<li class="day">${esc(label)}</li>`; }
    const c = eventClass(ev.event);
    const target = ev.event === "RENAMED" ? ev.new_path : ev.path;
    html += `<li class="ev">
      <time datetime="${esc(ev.timestamp)}">${esc(clock(ev.timestamp))}</time>
      ${evIco(c)}
      <span class="p" title="${esc(evPath(ev))}">${esc(evPath(ev))}<small>${EVENT_LABEL[c]}${ev.note ? ` · ${esc(ev.note)}` : ""}</small></span>
      ${ev.snapshot_id ? `<button class="link" data-open="${esc(target)}" data-snap="${ev.snapshot_id}" aria-label="Open snapshot ${ev.snapshot_id}">#${ev.snapshot_id}</button>` : "<span></span>"}
    </li>`;
  }
  $("#timeline").innerHTML = html;
}

/* ---------------- deleted ---------------- */

function renderDeleted() {
  const list = state.deleted;
  $("#deleted-list").innerHTML = list.length
    ? list.map((d) => `
      <div class="del-card">
        <div class="del-top">${evIco("DELETED")}<span class="fname">${esc(d.path)}</span></div>
        <div class="meta">Deleted ${esc(ago(d.deleted_at))} · ${d.snapshots} snapshot${d.snapshots === 1 ? "" : "s"} available</div>
        <div class="actions">
          ${d.latest_id ? `<button class="btn btn-sm btn-primary" data-recover="${esc(d.path)}" data-id="${d.latest_id}">${ic("restore")}Recover latest</button>` : ""}
          <button class="btn btn-sm" data-open="${esc(d.path)}">${ic("timeline")}Browse versions</button>
        </div>
      </div>`).join("")
    : `<div class="celebrate"><span class="empty-ico">${ic("integrity")}</span><b>Nothing to recover</b><span>Every tracked file is present on disk. Try deleting one, then come back.</span></div>`;
}

/* ---------------- integrity ---------------- */

async function runVerify() {
  const btn = $("#verify-btn");
  setBusy(btn, true, "Verifying…");
  try {
    const r = await api("/api/verify", {});
    const c = r.counts;
    $("#verify-result").innerHTML = `
      <div class="verify-summary">
        <div class="stat" data-tone="green"><div class="stat-label">Valid</div><div class="stat-value">${c.valid}</div></div>
        <div class="stat" data-tone="violet"><div class="stat-label">Corrupted</div><div class="stat-value" style="color:var(--red)">${c.corrupted}</div></div>
        <div class="stat" data-tone="amber"><div class="stat-label">Missing</div><div class="stat-value">${c.missing}</div></div>
      </div>
      <div class="verify-grid" role="list" aria-label="Per-snapshot results">${r.results.map((x, i) =>
        `<span role="listitem" class="cell ${x.state}" style="animation-delay:${Math.min(i * 14, 1500)}ms" title="#${x.id} ${esc(x.path)} · ${x.state}" aria-label="Snapshot ${x.id} ${esc(x.path)} ${x.state}"></span>`).join("")}</div>
      <div class="verify-banner ${r.ok ? "ok" : "bad"}">${ic(r.ok ? "check" : "alert")}<span>${r.results.length
        ? r.ok ? `All ${c.valid} snapshots match their recorded SHA-256 hashes.` : "Some snapshots failed verification and will not be restored."
        : "No snapshots to verify yet."}</span></div>`;
  } catch (e) {
    toast("Verification failed", e.message, "err");
  } finally {
    setBusy(btn, false, "Run verification");
  }
}

/* ---------------- settings ---------------- */

function renderSettings() {
  const c = state.overview?.config;
  if (!c) return;
  const tags = (arr) => arr.map((x) => `<span class="tag">${esc(x)}</span>`).join("");
  $("#settings").innerHTML = `
    <dt>Monitored extensions</dt><dd>${tags(c.monitored_extensions)}</dd>
    <dt>Ignored directories</dt><dd>${tags(c.ignored_directories)}</dd>
    <dt>Max snapshots per file</dt><dd><span class="tag">${c.max_snapshots}</span></dd>
    <dt>Max snapshot age</dt><dd><span class="tag">${c.max_age_days} days</span></dd>
    <dt>Debounce</dt><dd><span class="tag">${c.debounce_time}s</span></dd>
    <dt>Vault directory</dt><dd><span class="tag">${esc(c.snapshot_directory_name)}/</span></dd>`;
}

/* ---------------- polling ---------------- */

function setOnline(on) {
  if (state.online === on) return;
  state.online = on;
  const live = $("#live-indicator");
  live.classList.toggle("off", !on);
  $(".lbl", live).textContent = on ? "Live" : "Offline";
  if (!on) toast("Lost connection to CodeVault", "Is `codevault ui` still running?", "err");
}

async function refresh() {
  try {
    const [overview, files, timeline, deleted, git] = await Promise.all([
      api("/api/overview"), api("/api/files"), api("/api/timeline"), api("/api/deleted"),
      api("/api/git").catch(() => null),
    ]);
    setOnline(true);

    const snapIds = timeline.map((e) => e.snapshot_id).filter(Boolean);
    const maxId = snapIds.length ? Math.max(...snapIds) : 0;
    const newIds = new Set();
    if (state.maxSnapId !== null && maxId > state.maxSnapId) {
      const fresh = timeline.filter((e) => e.snapshot_id && e.snapshot_id > state.maxSnapId);
      fresh.forEach((e) => newIds.add(e.snapshot_id));
      fresh.slice(0, 2).forEach((e) => toast(`Snapshot #${e.snapshot_id} saved`, e.path, "info"));
      if (state.selectedPath && fresh.some((e) => e.path === state.selectedPath)) {
        state.selectedSnapId = null;
        loadHistory();
      }
    }
    state.maxSnapId = maxId;

    state.overview = overview;
    state.files = files;
    state.timeline = timeline;
    state.deleted = deleted;
    state.git = git;
    state.loaded = true;
    renderOverview();
    renderFeed(newIds);
    renderFileList();
    renderSyncStrip();
    $$('[data-count="git"]').forEach((c) => { c.textContent = git?.at_risk?.length || ""; });
    if (state.view === "git" && !$("#git-root .is-busy")) renderGit();
    if (state.view === "timeline") renderTimeline();
    if (state.view === "deleted") renderDeleted();
  } catch {
    setOnline(false);
  }
}

/* ---------------- navigation ---------------- */

function show(view, { focus = false } = {}) {
  if (!VIEWS.includes(view)) return;
  state.view = view;
  $$("[data-nav] button").forEach((b) => {
    const on = b.dataset.view === view;
    b.classList.toggle("active", on);
    if (on) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
  });
  $$(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${view}`));
  if (view === "timeline") renderTimeline();
  if (view === "deleted") renderDeleted();
  if (view === "git") renderGit();
  if (view === "overview") renderChart();
  if (window.matchMedia("(max-width: 1023px)").matches) window.scrollTo({ top: 0 });
  if (focus) $("#main").focus({ preventScroll: true });
  try { history.replaceState(null, "", `#${view}`); } catch { /* ignore */ }
}

function openFile(path, snapId) {
  show("files");
  selectFile(path, snapId ? Number(snapId) : null);
}

/* ---------------- events ---------------- */

$$("[data-nav]").forEach((nav) => nav.addEventListener("click", (e) => {
  const b = e.target.closest("button[data-view]");
  if (b) show(b.dataset.view, { focus: true });
}));

$$("[data-theme-btn]").forEach((b) => b.addEventListener("click", cycleTheme));

$("#range-seg").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-range]");
  if (!b) return;
  state.range = b.dataset.range;
  $$("#range-seg button").forEach((x) => { x.classList.toggle("active", x === b); x.setAttribute("aria-selected", x === b); });
  renderChart();
});

$("#file-search").addEventListener("input", (e) => { state.fileFilter = e.target.value; renderFileList(); });

$("#file-list").addEventListener("click", (e) => {
  const li = e.target.closest("li[data-path]");
  if (li) selectFile(li.dataset.path);
});
$("#file-list").addEventListener("keydown", (e) => {
  const li = e.target.closest("li[data-path]");
  if (!li) return;
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectFile(li.dataset.path); }
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    const sib = e.key === "ArrowDown" ? li.nextElementSibling : li.previousElementSibling;
    if (sib) sib.focus();
  }
});

function pickVersion(v) {
  state.selectedSnapId = Number(v.dataset.id);
  $$(".versions li").forEach((x) => { x.classList.toggle("active", x === v); x.setAttribute("aria-current", x === v); });
  renderViewer();
}

$("#file-detail").addEventListener("click", (e) => {
  if (e.target.closest("[data-back]")) { closeDetail(); return; }
  const v = e.target.closest(".versions li[data-id]");
  if (v) { pickVersion(v); return; }
  const m = e.target.closest("#viewer-seg button[data-mode]");
  if (m && !m.disabled) { state.viewerMode = m.dataset.mode; renderViewer(); return; }
  const act = e.target.closest("button[data-act]");
  if (!act) return;
  const snap = state.history.snapshots.find((s) => s.id === state.selectedSnapId);
  if (!snap) return;
  if (act.dataset.act === "restore") restoreSnapshot(snap, state.history.path, state.history.exists);
  if (act.dataset.act === "pin") {
    setBusy(act, true);
    api("/api/pin", { id: snap.id, pinned: !snap.pinned })
      .then((r) => {
        toast(r.pinned ? "Snapshot pinned" : "Snapshot unpinned", `#${snap.id} ${r.pinned ? "is protected from retention cleanup" : "follows retention rules again"}`);
        loadHistory(); refresh();
      })
      .catch((err) => { toast("Pin failed", err.message, "err"); setBusy(act, false); });
  }
});
$("#file-detail").addEventListener("keydown", (e) => {
  const v = e.target.closest(".versions li[data-id]");
  if (!v) return;
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pickVersion(v); }
  if (["ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight"].includes(e.key)) {
    e.preventDefault();
    const next = e.key === "ArrowDown" || e.key === "ArrowRight" ? v.nextElementSibling : v.previousElementSibling;
    if (next) { next.focus(); pickVersion(next); }
  }
});

$("#timeline-filter").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-f]");
  if (!b) return;
  state.timelineFilter = b.dataset.f;
  $$("#timeline-filter .chip").forEach((x) => { x.classList.toggle("active", x === b); x.setAttribute("aria-pressed", x === b); });
  renderTimeline();
});

document.addEventListener("click", (e) => {
  const go = e.target.closest("[data-goto]");
  if (go) { show(go.dataset.goto, { focus: true }); return; }
  const fetchBtn = e.target.closest("#git-fetch");
  if (fetchBtn) { gitFetch(fetchBtn); return; }
  const o = e.target.closest("[data-open]");
  if (o) { openFile(o.dataset.open, o.dataset.snap); return; }
  const r = e.target.closest("[data-recover]");
  if (r) {
    const path = r.dataset.recover;
    api(`/api/history?path=${encodeURIComponent(path)}`).then((h) => {
      const snap = h.snapshots.find((s) => s.id === Number(r.dataset.id));
      if (snap) restoreSnapshot(snap, path, h.exists);
    }).catch((err) => toast("Could not load history", err.message, "err"));
  }
});

$("#verify-btn").addEventListener("click", runVerify);

$$("[data-daemon-btn]").forEach((btn) => btn.addEventListener("click", async () => {
  const action = btn.dataset.action;
  if (!action) return;
  const all = $$("[data-daemon-btn]");
  all.forEach((b) => setBusy(b, true, action === "start" ? "Starting…" : "Stopping…"));
  try {
    const r = await api("/api/daemon", { action });
    toast(action === "start" ? "Watcher started" : "Watcher stopped", r.message.split("\n").pop());
  } catch (err) {
    toast("Watcher error", err.message, "err");
  } finally {
    all.forEach((b) => b.classList.remove("is-busy"));
    // the daemon takes a moment to scan existing files
    await refresh();
    setTimeout(refresh, 1200);
  }
}));

function showShortcuts() {
  openModal("Keyboard shortcuts", `<div class="kbd-list">
    <kbd>1 – 7</kbd><span>Switch between sections</span>
    <kbd>/</kbd><span>Filter files</span>
    <kbd>↑ ↓</kbd><span>Move through files and versions</span>
    <kbd>Enter</kbd><span>Open the focused item</span>
    <kbd>t</kbd><span>Cycle light / dark / system theme</span>
    <kbd>Esc</kbd><span>Close dialog or go back</span>
    <kbd>?</kbd><span>Show this help</span>
  </div>`, { showOk: false, cancelLabel: "Close" });
}
$("#kbd-btn").addEventListener("click", showShortcuts);

document.addEventListener("keydown", (e) => {
  if (!$("#modal").hidden || e.metaKey || e.ctrlKey || e.altKey) return;
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName);
  if (e.key === "Escape") {
    if (typing) { document.activeElement.blur(); return; }
    if (state.view === "files" && $("#files-split").classList.contains("show-detail")) closeDetail();
    return;
  }
  if (typing) return;
  if (/^[1-7]$/.test(e.key)) { show(VIEWS[+e.key - 1], { focus: true }); return; }
  if (e.key === "/") { e.preventDefault(); show("files"); $("#files-split").classList.remove("show-detail"); $("#file-search").focus(); return; }
  if (e.key === "t") { cycleTheme(); return; }
  if (e.key === "?") showShortcuts();
});

let resizeT;
window.addEventListener("resize", () => {
  clearTimeout(resizeT);
  resizeT = setTimeout(() => { if (state.view === "overview" && state.loaded) renderChart(); }, 120);
});

/* ---------------- boot ---------------- */

applyTheme();
const initial = location.hash.slice(1);
if (VIEWS.includes(initial)) show(initial);
window.addEventListener("hashchange", () => {
  const v = location.hash.slice(1);
  if (VIEWS.includes(v) && v !== state.view) show(v);
});
refresh();
setInterval(() => { if (!document.hidden) refresh(); }, POLL_MS);
setInterval(() => { if (!document.hidden && state.view === "overview") renderFeed(); }, 15000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
