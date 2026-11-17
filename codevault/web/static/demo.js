/* Hosted demo: a small in-browser copy of the dashboard backend (codevault/web/server.py).
   The static site has no Python server, so this answers the dashboard's /api calls itself from demo/projects.json
   (built by scripts/build_demo_projects.py). Restore, pin, verify, the watcher switch, "Check GitHub" and
   "Switch project" all really change state, which is kept in this browser's localStorage. Nothing is uploaded.
   Loaded only by the static build; the real `codevault ui` server does not load this file. */
"use strict";
(() => {
  const real = window.fetch.bind(window);
  const base = document.currentScript.src.replace(/demo\.js.*$/, "demo/");
  const KEY = "codevault-demo-v2";
  const MIN = 60000;
  window.CODEVAULT_DEMO = true;

  const pad = (n) => String(n).padStart(2, "0");
  const fmt = (ms) => { const d = new Date(ms); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`; };
  const stamp = (ms) => fmt(ms).replace(/[- :]/g, "").replace(/^(\d{8})(\d{6})$/, "$1_$2");
  const size = (n) => (n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(2)} MB`);
  const bytes = (s) => new TextEncoder().encode(s).length;
  const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  const fail = (message, status = 400) => { const e = new Error(message); e.status = status; return e; };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  async function sha256(text) {
    const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
  }
  const lines = (t) => { const a = String(t ?? "").split("\n"); if (a.length && a[a.length - 1] === "") a.pop(); return a; };

  /* ---------- unified diff, same JSON shape as server.py's /api/diff ---------- */
  function diffLines(a, b, ctx = 3) {
    const n = a.length, m = b.length, dp = Array.from({ length: n + 1 }, () => new Int32Array(m + 1));
    for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--)
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    const ops = []; let i = 0, j = 0;
    while (i < n && j < m) {
      if (a[i] === b[j]) { ops.push({ t: "ctx", i, j }); i++; j++; }
      else if (dp[i + 1][j] >= dp[i][j + 1]) { ops.push({ t: "del", i, j }); i++; }
      else { ops.push({ t: "add", i, j }); j++; }
    }
    while (i < n) ops.push({ t: "del", i: i++, j });
    while (j < m) ops.push({ t: "add", i, j: j++ });
    const changed = ops.map((o, k) => (o.t === "ctx" ? -1 : k)).filter((k) => k >= 0);
    const out = []; let added = 0, removed = 0;
    if (!changed.length) return { added, removed, lines: out };
    const groups = []; let g = [changed[0], changed[0]];
    for (const k of changed.slice(1)) { if (k - g[1] <= ctx * 2) g[1] = k; else { groups.push(g); g = [k, k]; } }
    groups.push(g);
    const rng = (start, len) => (len === 1 ? `${start}` : `${len === 0 ? start - 1 : start},${len}`);
    for (const [first, last] of groups) {
      const from = Math.max(0, first - ctx), to = Math.min(ops.length - 1, last + ctx), part = ops.slice(from, to + 1);
      const oldLen = part.filter((o) => o.t !== "add").length, newLen = part.filter((o) => o.t !== "del").length;
      const oldStart = part.find((o) => o.t !== "add")?.i + 1 || part[0].i + 1, newStart = part.find((o) => o.t !== "del")?.j + 1 || part[0].j + 1;
      out.push({ kind: "hunk", text: `@@ -${rng(oldStart, oldLen)} +${rng(newStart, newLen)} @@` });
      for (const o of part) {
        if (o.t === "ctx") out.push({ kind: "ctx", text: a[o.i], old: o.i + 1, new: o.j + 1 });
        else if (o.t === "del") { out.push({ kind: "del", text: a[o.i], old: o.i + 1 }); removed++; }
        else { out.push({ kind: "add", text: b[o.j], new: o.j + 1 }); added++; }
      }
    }
    return { added, removed, lines: out };
  }

  /* ---------- state ---------- */
  let S, loaded;
  const save = () => { try { S.lastSeen = Date.now(); localStorage.setItem(KEY, JSON.stringify(S)); } catch { /* private mode: state just lasts for this page view */ } };
  const resetDemo = () => { try { localStorage.removeItem(KEY); } catch { /* ignore */ } location.reload(); };

  async function build(raw) {
    const now = Date.now();
    const projects = [];
    for (const [pi, p] of raw.projects.entries()) {
      const snapshots = [];
      for (const s of p.snapshots) {
        snapshots.push({ id: s.id, path: s.path, ts: now - s.ago_min * MIN, event_type: s.event, pinned: s.pinned ? 1 : 0, note: s.note || null,
          git: s.git, content: s.content, hash: s.hash || await sha256(s.content), size: bytes(s.content) });
      }
      const disk = {};
      for (const s of [...snapshots].sort((x, y) => x.ts - y.ts || x.id - y.id)) disk[s.path] = s.content;
      const deletedAt = {};
      for (const [path, ago] of Object.entries(p.deleted || {})) { disk[path] = null; deletedAt[path] = now - ago * MIN; }
      projects.push({ name: p.name, dir: p.dir, branch: p.branch, upstream: p.upstream, ahead: p.ahead, behind: p.behind, remoteBehind: p.remote_behind || 0,
        config: p.config, commits: p.commits.map((c) => ({ ...c, ts: now - c.ago_min * MIN })), snapshots, disk, deletedAt,
        daemon: { running: true, pid: 4242 + pi }, nextId: Math.max(...snapshots.map((s) => s.id)) + 1 });
    }
    return { v: 2, current: projects[0].name, lastSeen: now, projects };
  }

  async function init() {
    let stored = null;
    try { stored = JSON.parse(localStorage.getItem(KEY) || "null"); } catch { /* ignore */ }
    if (stored && stored.v === 2) {
      S = stored;
      const gap = Date.now() - S.lastSeen;
      if (gap > 60 * MIN) { // keep the "a few minutes ago" feel for returning visitors
        for (const p of S.projects) {
          p.snapshots.forEach((s) => { s.ts += gap; });
          p.commits.forEach((c) => { c.ts += gap; });
          for (const k of Object.keys(p.deletedAt)) p.deletedAt[k] += gap;
        }
        save();
      }
    } else {
      S = await build(await (await real(base + "projects.json")).json());
      save();
    }
  }
  const ready = () => (loaded ||= init());
  const cur = () => S.projects.find((p) => p.name === S.current) || S.projects[0];

  /* ---------- views of a project (mirrors DashboardApi in server.py) ---------- */
  const forFile = (p, path) => p.snapshots.filter((s) => s.path === path).sort((a, b) => a.ts - b.ts || a.id - b.id);
  const tracked = (p) => [...new Set([...p.snapshots].sort((a, b) => a.ts - b.ts).map((s) => s.path))];
  const exists = (p, path) => p.disk[path] != null;
  const meta = (s) => ({ id: s.id, relative_path: s.path, snapshot_path: `.lifejacket/snapshots/${s.path}.${stamp(s.ts)}.bak`, timestamp: fmt(s.ts), hash: s.hash, size: s.size, event_type: s.event_type, pinned: s.pinned, note: s.note });
  const headOf = (p, path) => { const f = forFile(p, path); return (f.filter((s) => s.git === "committed").pop() || f.filter((s) => s.git === "pushed").pop())?.content ?? null; };
  const changesOf = (p) => {
    const out = {};
    for (const path of tracked(p)) {
      const head = headOf(p, path), now = p.disk[path];
      if (head == null) { if (now != null) out[path] = "untracked"; } else if (now == null) out[path] = "deleted"; else if (now !== head) out[path] = "modified";
    }
    return out;
  };
  const snapById = (p, id) => { const s = p.snapshots.find((x) => String(x.id) === String(id)); if (!s) throw fail("No snapshot with that id.", 404); return s; };
  const gitState = (p, content) => { // like gitinfo.classifier: classified by content, best match wins
    const m = p.snapshots.filter((s) => s.content === content).map((s) => s.git);
    return m.includes("pushed") ? "pushed" : m.includes("committed") ? "committed" : "local";
  };

  const routes = {
    GET: {
      "/api/overview"() {
        const p = cur(), snaps = [...p.snapshots].sort((a, b) => a.ts - b.ts || a.id - b.id), paths = tracked(p);
        const total = snaps.reduce((n, s) => n + s.size, 0), deleted = paths.filter((x) => !exists(p, x)).length;
        return { project_dir: p.dir, project_name: p.name,
          stats: { protected_files: paths.length - deleted, snapshots: snaps.length, deleted_files: deleted, storage_bytes: total, storage: size(total),
            pinned: snaps.filter((s) => s.pinned).length, last_snapshot: snaps.length ? fmt(snaps[snaps.length - 1].ts) : null },
          daemon: p.daemon.running ? { status: "RUNNING", pid: p.daemon.pid } : { status: "STOPPED", pid: null },
          activity: snaps.map((s) => ({ t: fmt(s.ts), type: s.event_type })), config: p.config };
      },
      "/api/files"() {
        const p = cur(), ch = changesOf(p);
        return tracked(p).map((path) => { const f = forFile(p, path), last = f[f.length - 1];
          return { git: ch[path] || null, local_only: f.filter((s) => s.git === "local").length, path, exists: exists(p, path), snapshots: f.length,
            last_modified: fmt(last.ts), size: size(last.size), last_hash: last.hash.slice(0, 12) }; })
          .sort((a, b) => (a.exists - b.exists) || a.path.localeCompare(b.path));
      },
      "/api/history"(q) {
        const p = cur(), path = q.get("path") || "";
        return { path, exists: exists(p, path), is_repo: true, github_url: null,
          snapshots: forFile(p, path).reverse().map((s) => ({ ...meta(s), size_str: size(s.size), git: s.git })) };
      },
      "/api/snapshot"(q) { const s = snapById(cur(), q.get("id")); return { ...meta(s), binary: false, content: s.content }; },
      "/api/diff"(q) {
        const p = cur(), a = snapById(p, q.get("from")), to = q.get("to");
        const b = to === "current" ? null : snapById(p, to);
        const d = diffLines(lines(a.content), lines(b ? b.content : p.disk[a.path] ?? ""));
        return { path: a.path, from_label: `#${a.id}`, to_label: b ? `#${b.id}` : "current file", ...d };
      },
      "/api/timeline"() {
        const p = cur(), ev = [];
        for (const path of tracked(p)) {
          const f = forFile(p, path);
          ev.push({ timestamp: fmt(f[0].ts), event: "CREATED", path, snapshot_id: null, file_id: path, _t: f[0].ts - 1 });
          if (p.deletedAt[path] && !exists(p, path)) ev.push({ timestamp: fmt(p.deletedAt[path]), event: "DELETED", path, snapshot_id: null, file_id: path, _t: p.deletedAt[path] });
        }
        for (const s of p.snapshots) ev.push({ timestamp: fmt(s.ts), event: s.event_type.toUpperCase(), path: s.path, snapshot_id: s.id, file_id: s.path, note: s.note, _t: s.ts });
        return ev.sort((a, b) => b._t - a._t).slice(0, 300).map(({ _t, ...e }) => e);
      },
      "/api/deleted"() {
        const p = cur();
        return tracked(p).filter((x) => !exists(p, x)).map((path) => { const f = forFile(p, path);
          return { path, deleted_at: fmt(p.deletedAt[path] || f[f.length - 1].ts), snapshots: f.length, latest_id: f[f.length - 1].id }; });
      },
      "/api/git"() {
        const p = cur(), ch = changesOf(p), snaps = [...p.snapshots].sort((a, b) => a.ts - b.ts || a.id - b.id), per = {};
        for (const s of snaps) {
          if (s.git !== "local") continue;
          const e = per[s.path] ||= { path: s.path, local_versions: 0, sources: new Set() };
          e.local_versions++; e.latest_id = s.id; e.latest_ts = fmt(s.ts); e.ts = s.ts;
          if (s.note) e.sources.add(s.note.split(" · ")[0]);
        }
        const atRisk = Object.values(per).sort((a, b) => b.ts - a.ts).map(({ ts, sources, ...e }) => ({ ...e, sources: [...sources].sort(), exists: exists(p, e.path), git: ch[e.path] || null }));
        const unpushed = p.commits.filter((c) => !c.pushed).map((c) => ({ sha: c.sha, subject: c.subject, date: `${fmt(c.ts)} +0000` }));
        const lastC = [...p.commits].sort((a, b) => b.ts - a.ts)[0];
        const tr = new Set(tracked(p));
        return { is_repo: true, branch: p.branch, upstream: p.upstream, ahead: unpushed.length, behind: p.behind, remote_url: "origin (sample remote)", web_url: null,
          last_commit: lastC ? { sha: lastC.sha, subject: lastC.subject, date: `${fmt(lastC.ts)} +0000` } : null, unpushed_commits: unpushed, prefix: "",
          changes: Object.entries(ch).sort().map(([path, status]) => ({ path, status, tracked: tr.has(path) })), at_risk: atRisk,
          version_counts: Object.fromEntries(["pushed", "committed", "local"].map((k) => [k, p.snapshots.filter((s) => s.git === k).length])) };
      },
      "/api/projects"() { return { current: cur().dir, recent: S.projects.map((p) => p.dir) }; },
    },
    POST: {
      async "/api/restore"(b) {
        const p = cur(), snap = snapById(p, b.id), path = snap.path, now = Date.now();
        const add = async (content, event, note) => {
          const prev = forFile(p, path).pop();
          if (prev && prev.content === content && event !== "pre_restore") return;
          p.snapshots.push({ id: p.nextId++, path, ts: now + p.snapshots.length, event_type: event, pinned: 0, note, git: gitState(p, content), content, hash: await sha256(content), size: bytes(content) });
        };
        const present = p.disk[path];
        if (present === snap.content) return { ok: true, message: `${path} already matches snapshot #${snap.id}; nothing to restore` };
        if (present != null) await add(present, "pre_restore", null); // never overwrite without keeping a copy
        p.disk[path] = snap.content;
        if (p.daemon.running) await add(snap.content, present == null ? "created" : "modified", null); // the watcher notices the write
        delete p.deletedAt[path];
        return { ok: true, message: `Restored ${path} from snapshot #${snap.id}` };
      },
      "/api/pin"(b) { const s = snapById(cur(), b.id); s.pinned = b.pinned ? 1 : 0; return { ok: true, pinned: !!s.pinned }; },
      async "/api/verify"() {
        const results = [];
        for (const s of [...cur().snapshots].sort((a, b) => a.id - b.id))
          results.push({ id: s.id, path: s.path, state: (await sha256(s.content)) === s.hash ? "valid" : "corrupted" }); // real SHA-256, computed in your browser
        const counts = { valid: 0, corrupted: 0, missing: 0 }; results.forEach((r) => counts[r.state]++);
        return { ok: !counts.corrupted && !counts.missing, counts, results };
      },
      async "/api/git/fetch"() { await sleep(700); const p = cur(); p.behind = p.remoteBehind; return { ok: true }; },
      "/api/project"(b) {
        const t = String(b.target || "").trim(), key = t.replace(/\/+$/, "").toLowerCase();
        if (!t) throw fail("Enter a project name or path");
        const hit = S.projects.find((p) => p.name.toLowerCase() === key || p.dir.toLowerCase() === key || key.endsWith("/" + p.name.toLowerCase()));
        if (hit) { S.current = hit.name; return { ok: true, project_dir: hit.dir, cloned: false }; }
        if (/github\.com[:/]/.test(t)) throw fail("The hosted demo can't clone repositories, because it runs entirely in your browser. Pick one of the sample projects below, or install CodeVault (3 steps on the home page) to open your own repo.");
        throw fail(`There's no sample project called "${t}". Try: ${S.projects.map((p) => p.name).join(", ")}.`, 404);
      },
      "/api/daemon"(b) {
        if (!["start", "stop"].includes(b.action)) throw fail("action must be 'start' or 'stop'");
        const p = cur(); p.daemon.running = b.action === "start";
        return { ok: true, message: p.daemon.running ? "Watcher started" : "Watcher stopped", daemon: p.daemon.running ? { status: "RUNNING", pid: p.daemon.pid } : { status: "STOPPED", pid: null } };
      },
    },
  };

  window.fetch = async (url, opts = {}) => {
    const u = new URL(url, location.href);
    if (!u.pathname.startsWith("/api/")) return real(url, opts);
    try {
      await ready();
      const method = (opts.method || "GET").toUpperCase(), fn = routes[method]?.[u.pathname];
      if (!fn) return json({ error: "Not available in the demo." }, 404);
      const out = await fn(method === "GET" ? u.searchParams : JSON.parse(opts.body || "{}"));
      if (method === "POST") save();
      return json(out);
    } catch (e) {
      return json({ error: e.message || "Demo error" }, e.status || 500);
    }
  };

  if (location.pathname.includes("/dashboard")) {
    const tag = document.createElement("div");
    tag.className = "demo-tag";
    tag.style.cssText = "position:fixed;bottom:12px;right:12px;z-index:99;display:flex;gap:0;background:#f5c400;color:#15171c;font:600 12px/1 'JetBrains Mono',monospace;border:2px solid #15171c";
    const mk = (text, onclick, href) => { const a = document.createElement("a"); a.textContent = text; a.href = href || "#"; a.style.cssText = "color:inherit;text-decoration:none;padding:8px 12px;cursor:pointer"; a.addEventListener("click", (e) => { if (onclick) { e.preventDefault(); onclick(); } }); return a; };
    const sep = document.createElement("span"); sep.style.cssText = "width:2px;background:#15171c";
    tag.append(mk("Demo · sample data", null, "../#start"), sep, mk("Reset demo", () => { if (confirm("Reset the demo to its starting state?")) resetDemo(); }));
    const st = document.createElement("style");
    st.textContent = "@media (max-width:1100px){.demo-tag{bottom:72px!important}}";
    document.head.appendChild(st);
    document.body.appendChild(tag);
  }
  window.__codevaultDemo = { diffLines, ready, reset: resetDemo, state: () => S }; // handy for tests
})();
