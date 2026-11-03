/* Hosted demo: answers the dashboard's /api calls from demo/api.json (recorded from a sample project by
   scripts/build_demo_data.py) because the static site has no Python server. Loaded only by the static build. */
"use strict";
(() => {
  const base = document.currentScript.src.replace(/demo\.js.*$/, "demo/");
  const real = window.fetch.bind(window);
  const pad = (n) => String(n).padStart(2, "0");
  const fmt = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  const parse = (s) => new Date(s.replace(" ", "T"));
  let loaded;
  // Move every recorded timestamp forward so the newest snapshot always looks a few minutes old.
  const load = () => loaded ||= real(base + "api.json").then((r) => r.text()).then((text) => {
    const delta = Date.now() - parse(JSON.parse(text)._recorded_at);
    return JSON.parse(text.replace(/\d{4}-\d\d-\d\d \d\d:\d\d:\d\d/g, (m) => fmt(new Date(parse(m).getTime() + delta))));
  });
  const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

  window.fetch = async (url, opts = {}) => {
    const u = new URL(url, location.href);
    if (!u.pathname.startsWith("/api/")) return real(url, opts);
    if ((opts.method || "GET") !== "GET")
      return json({ error: "This is a read-only demo with sample data. Install CodeVault to do this on your own project." }, 403);
    const key = u.pathname + (u.search ? "?" + [...u.searchParams].map(([k, v]) => `${k}=${v}`).join("&") : "");
    const hit = (await load())[key];
    return hit === undefined ? json({ error: "Not part of the demo data." }, 404) : json(hit);
  };

  if (location.pathname.includes("/dashboard")) {
    const tag = document.createElement("a");
    tag.href = "../#start";
    tag.textContent = "Demo · sample data · get CodeVault";
    tag.style.cssText = "position:fixed;bottom:12px;right:12px;z-index:99;background:#f5c400;color:#15171c;font:600 12px/1 'JetBrains Mono',monospace;padding:8px 12px;text-decoration:none;border:2px solid #15171c";
    const st = document.createElement("style");
    st.textContent = "@media (max-width:1100px){a.demo-tag{bottom:72px!important}}";
    tag.className = "demo-tag";
    document.head.appendChild(st);
    document.body.appendChild(tag);
  }
})();
