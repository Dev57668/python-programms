/* CodeVault landing page: the desk of real snapshots, git counts, chapter progress, copy buttons. */
"use strict";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

function parseTs(ts) {
  const d = new Date(String(ts || "").replace(" ", "T"));
  return isNaN(d) ? null : d;
}
function ago(d) {
  const s = Math.max(0, Math.round((Date.now() - d) / 1000));
  if (s < 60) return s < 5 ? "just now" : `${s} s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  return h < 24 ? `${h} h ago` : `${plural(Math.round(h / 24), "day")} ago`;
}
const clock = (d) => d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

async function getJSON(path) {
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

/* ---------- the desk: one disk per recent snapshot ---------- */

const COLOUR = { pushed: "black", committed: "blue", local: "red" };
const STATE_TEXT = { pushed: "on GitHub", committed: "committed, not pushed", local: "only on this machine" };
const isAi = (ev) => {
  const e = String(ev.event || "").toUpperCase();
  const src = String(ev.note || "").split(" · ")[0].toLowerCase();
  return e === "AI_EDIT" || e === "PRE_AI" || (!!src && !["manual", "me", "human"].includes(src));
};

function diskHTML(d, i, all) {
  const rot = ((d.id * 37) % 9) - 4; // a stable, slightly scattered pile
  const parts = d.path.split("/");
  const name = parts.pop();
  // Two files with the same name (e.g. two server.py): the folder goes on the small line, the name stays big.
  const dup = all.filter((x) => x.path.split("/").pop() === name).length > 1;
  const folder = dup && parts.length ? `${parts.pop()}/ · ` : "";
  const label = `${d.path}, snapshot #${d.id}, saved ${ago(d.date)}, ${STATE_TEXT[d.state] || "saved"}${d.ai ? ", AI edit" : ""}${d.sample ? " (sample)" : ""}`;
  return `<div class="disk-wrap drop" style="--i:${i}">
    <button class="disk ${COLOUR[d.state] || "red"}${d.pinned ? " pinned" : ""}" style="--r:${rot}deg" aria-label="${esc(label)}">
      <span class="well">sha256 ${esc(String(d.hash || "").slice(0, 12))}…</span>
      <span class="shutter"></span>
      <span class="label${d.ai ? " yellow" : ""}"><span class="l-file">${esc(name)}</span><span class="l-meta">${esc(folder)}${esc(clock(d.date))} · #${d.id}</span></span>
      <span class="tab"></span>
    </button>
  </div>`;
}

let shownKey = "";
function renderPile(disks) {
  const key = disks.map((d) => `${d.id}${d.state}`).join(",");
  if (key === shownKey) return;
  shownKey = key;
  $("#pile").innerHTML = disks.map((d, i) => diskHTML(d, i, disks)).join("");
}

function sampleDisks() {
  const files = ["src/app.js", "src/auth.py", "src/utils.py", "tests/test_auth.py", "src/api.py", "main.py", "src/db.py"];
  const states = ["local", "local", "committed", "pushed", "local", "pushed", "pushed"];
  return files.map((path, i) => ({
    id: 47 - i, path, state: states[i], ai: i === 1, pinned: i === 3, sample: true,
    date: new Date(Date.now() - (i + 1) * 23 * 60e3), hash: "b0103817464bb37c4ab66446e1d0",
  }));
}

async function load() {
  let overview, timeline, git;
  try {
    [overview, timeline] = await Promise.all([getJSON("/api/overview"), getJSON("/api/timeline")]);
  } catch {
    $("#desk-status").innerHTML = `<span class="sample">Sample disks. Run <code>codevault ui</code> in a project to see its own snapshots here.</span>`;
    renderPile(sampleDisks());
    return;
  }
  try { git = await getJSON("/api/git"); } catch { git = null; }

  // The newest snapshot of each of the most recently saved files.
  const picks = [];
  const seen = new Set();
  for (const ev of timeline) {
    if (!ev.snapshot_id || seen.has(ev.path)) continue;
    seen.add(ev.path);
    picks.push(ev);
    if (picks.length === (innerWidth < 760 ? 6 : 7)) break;
  }
  const histories = await Promise.all(picks.map((ev) =>
    getJSON(`/api/history?path=${encodeURIComponent(ev.path)}`).catch(() => null)));
  const disks = picks.map((ev, i) => {
    const snap = histories[i]?.snapshots.find((s) => s.id === ev.snapshot_id) || {};
    return {
      id: ev.snapshot_id, path: ev.path, date: parseTs(ev.timestamp) || new Date(),
      state: snap.git || (git && git.is_repo ? "pushed" : "local"),
      ai: isAi(ev), pinned: !!snap.pinned, hash: snap.hash,
    };
  }).reverse();

  const running = overview.daemon.status === "RUNNING";
  let risk = "";
  if (git && git.is_repo) {
    const n = git.at_risk.length;
    risk = n
      ? ` · <span class="risk">${plural(n, "file")} ${n === 1 ? "has" : "have"} work that exists only on this machine</span>`
      : " · everything is in git";
    const vc = git.version_counts;
    $('[data-count="pushed"]').textContent = `${plural(vc.pushed, "snapshot")} here`;
    $('[data-count="committed"]').textContent = `${plural(vc.committed, "snapshot")} here`;
    $('[data-count="local"]').textContent = `${plural(vc.local, "snapshot")} here`;
  }
  $("#desk-status").innerHTML = disks.length
    ? `<b>${esc(overview.project_name)}</b> · watcher ${running ? "on" : "off"} · ${plural(overview.stats.snapshots, "snapshot")}${risk}`
    : `<b>${esc(overview.project_name)}</b> · no snapshots yet. Open the dashboard and start the watcher.`;
  renderPile(disks.length ? disks : sampleDisks());
}

/* ---------- interactions ---------- */

document.addEventListener("click", (e) => {
  const disk = e.target.closest("#pile .disk");
  if (disk) {
    // Touch screens have no hover: a tap opens the shutter, a second tap goes to the dashboard.
    if (matchMedia("(hover: none)").matches && !disk.classList.contains("open")) {
      $$("#pile .disk.open").forEach((d) => d.classList.remove("open"));
      disk.classList.add("open");
      return;
    }
    location.href = "dashboard/#files";
    return;
  }
  const copy = e.target.closest(".copy");
  if (copy) {
    const text = copy.previousElementSibling.textContent;
    navigator.clipboard?.writeText(text).then(() => {
      copy.textContent = "Copied";
      copy.classList.add("done");
      setTimeout(() => { copy.textContent = "Copy"; copy.classList.remove("done"); }, 1600);
    }).catch(() => { copy.textContent = "Select and copy"; });
  }
});

// Mark the chapter being read in the top bar.
const links = new Map($$(".chapters a").map((a) => [a.getAttribute("href").slice(1), a]));
const chapterOf = { why: "why", how: "how", git: "git", ai: "ai", restore: "ai", start: "start" };
if ("IntersectionObserver" in window) {
  const io = new IntersectionObserver((entries) => {
    entries.forEach((en) => {
      if (!en.isIntersecting) return;
      links.forEach((a, key) => a.classList.toggle("on", key === chapterOf[en.target.id]));
    });
  }, { rootMargin: "-45% 0px -50% 0px" });
  $$(".chapter").forEach((s) => io.observe(s));
}

load();
setInterval(() => { if (!document.hidden) load(); }, 6000);
