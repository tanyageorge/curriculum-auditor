"use strict";
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const norm = (s) => String(s).toUpperCase().replace(/[^A-Z0-9/]/g, "");
const pct = (v) => (v == null ? "–" : (v * 100).toFixed(1) + "%");
const CHECKS = {
  self_reference: "Requires itself", cycle: "Prerequisite loop", missing_course: "Missing course",
  renumbered: "Renumbered / removed", long_chain: "Long chain",
};
const state = { index: null, cat: null, byKey: new Map(), requiredBy: new Map(), findingsByCourse: new Map(),
                check: "all", query: "", limit: 150, selected: null };

// ------------------------------------------------------------------ tabs + hash state
const FEATURED = { "uiuc@2026-spring": "CS374", "uaeu@2025_2026": "NUTR481" };
document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => {
  if (b.dataset.tab === "audit" && !state.cat) return openCatalog(state.index.catalogs[0].id);
  showTab(b.dataset.tab);
}));
$("#home-link").addEventListener("click", (e) => { e.preventDefault(); history.pushState(null, "", location.pathname); showTab("home"); });
function showTab(t) {
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === t));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === "tab-" + t));
  document.body.classList.toggle("on-home", t === "home");
  if (window.net) (t === "home" ? window.net.start() : window.net.stop());
  window.scrollTo({ top: 0 });
}
async function openCatalog(id, course) {
  showTab("audit");
  if (state.cat?.id === id) { if (course && state.byKey.has(course)) selectCourse(course); return; }
  $("#catalog").value = id;
  await loadCatalog(id, course);
}
async function route() {   // the URL decides the view: #catalog=...&course=... opens the app
  const h = readHash();
  const meta = state.index.catalogs.find((c) => c.id === h.catalog);
  if (meta) await openCatalog(meta.id, h.course); else showTab("home");
}
window.addEventListener("hashchange", route);
function readHash() { return Object.fromEntries(new URLSearchParams(location.hash.slice(1))); }
function writeHash() {
  const h = new URLSearchParams({ catalog: state.cat?.id || "" });
  if (state.selected) h.set("course", state.selected);
  history.replaceState(null, "", "#" + h.toString());
}

// ------------------------------------------------------------------ load
async function init() {
  state.index = await (await fetch("data/index.json")).json();
  const sel = $("#catalog");
  sel.innerHTML = state.index.catalogs.map((c) => `<option value="${esc(c.id)}">${esc(c.name)} · ${c.courses.toLocaleString()} courses</option>`).join("");
  sel.addEventListener("change", () => loadCatalog(sel.value));
  $("#search").addEventListener("input", (e) => { state.query = e.target.value.trim(); state.limit = 150; onSearch(); });
  renderEval();
  await route();
}

async function loadCatalog(id, course) {
  const meta = state.index.catalogs.find((c) => c.id === id);
  $("#findings").innerHTML = `<div class="more">Loading…</div>`;
  const cat = await (await fetch("data/" + meta.file)).json();
  state.cat = cat; state.check = "all"; state.query = ""; state.selected = null; state.limit = 150;
  $("#search").value = "";
  state.byKey = new Map(cat.courses.map((c) => [c.k, c]));
  state.requiredBy = new Map();
  for (const c of cat.courses) for (const g of c.g) for (const [k] of g) {
    if (!state.requiredBy.has(k)) state.requiredBy.set(k, new Set());
    state.requiredBy.get(k).add(c.k);
  }
  state.findingsByCourse = new Map();
  for (const f of cat.findings) {
    const k = norm(f.course);
    if (!state.findingsByCourse.has(k)) state.findingsByCourse.set(k, []);
    state.findingsByCourse.get(k).push(f);
  }
  $("#source").textContent = `${cat.source}.`;
  renderTiles(meta); renderChips(); renderFindings();
  renderHint(cat);
  const first = course && state.byKey.has(course) ? course
    : FEATURED[id] && state.byKey.has(FEATURED[id]) ? FEATURED[id]
    : cat.findings.length ? norm(cat.findings[0].course) : null;
  if (first) selectCourse(first);
  else $("#detail").innerHTML = `<div class="empty">Select a finding or search for a course to see its prerequisites and graph.</div>`;
  writeHash();
}

// ------------------------------------------------------------------ audit view
function renderHint(cat) {
  const el = $("#hint");
  if (cat.id.startsWith("uiuc")) {
    el.innerHTML = `This file lists one term's offerings, so only structural checks run here; it shows Muse Spark's parsing best. Search any course (try <a href="#catalog=uiuc@2026-spring&course=CS225">CS 225</a> or <a href="#catalog=uiuc@2026-spring&course=ECE391">ECE 391</a>), or <a href="#catalog=uaeu@2025_2026&course=NUTR481">open a catalog with more problems →</a>`;
    el.style.display = "block";
  } else { el.innerHTML = ""; el.style.display = "none"; }
}

function renderTiles(m) {
  $("#tiles").innerHTML = [
    ["", m.courses.toLocaleString(), "courses checked"],
    ["block", m.blocking, "blocking issues"],
    ["warn", m.warning, "warnings"],
    ["info", m.info, "notes"],
  ].map(([c, n, l]) => `<div class="tile ${c}"><div class="n">${n}</div><div class="l">${l}</div></div>`).join("");
}

function renderChips() {
  const counts = {};
  for (const f of state.cat.findings) counts[f.check] = (counts[f.check] || 0) + 1;
  const items = [["all", "All findings", state.cat.findings.length], ...Object.entries(CHECKS).filter(([k]) => counts[k]).map(([k, l]) => [k, l, counts[k]])];
  $("#chips").innerHTML = items.map(([k, l, n]) => `<button class="chip ${state.check === k ? "on" : ""}" data-k="${k}">${esc(l)}<span class="c">${n}</span></button>`).join("");
  $("#chips").querySelectorAll(".chip").forEach((b) => b.addEventListener("click", () => { state.check = b.dataset.k; state.limit = 150; renderChips(); renderFindings(); }));
}

const SEV = { blocking: 0, warning: 1, info: 2 };
function filteredFindings() {
  const q = norm(state.query);
  return state.cat.findings
    .filter((f) => state.check === "all" || f.check === state.check)
    .filter((f) => !q || norm(f.course).includes(q) || f.related.some((r) => norm(r).includes(q)))
    .sort((a, b) => SEV[a.severity] - SEV[b.severity] || a.course.localeCompare(b.course));
}

function renderFindings() {
  const list = filteredFindings();
  const el = $("#findings");
  if (!list.length) { el.innerHTML = `<div class="more">No findings${state.query ? " for this search" : ""}.</div>`; return; }
  el.innerHTML = list.slice(0, state.limit).map((f) => `
    <button class="f ${norm(f.course) === state.selected ? "sel" : ""}" data-k="${esc(norm(f.course))}">
      <div class="row"><span class="sev ${f.severity}">${f.severity}</span><span class="code">${esc(f.course)}</span><span class="fid">${esc(f.id)}</span></div>
      <div class="d">${esc(f.detail)}</div>
      <q>“${esc(f.evidence)}”</q>
    </button>`).join("") + (list.length > state.limit ? `<button class="chip" id="more">Show more (${list.length - state.limit} left)</button>` : "");
  el.querySelectorAll(".f").forEach((b) => b.addEventListener("click", () => selectCourse(b.dataset.k)));
  $("#more")?.addEventListener("click", () => { state.limit += 300; renderFindings(); });
}

function onSearch() {
  renderFindings();
  const q = norm(state.query);
  if (q && state.byKey.has(q)) selectCourse(q);
}

// ------------------------------------------------------------------ course detail
function logicHTML(c) {
  if (!c.g.length) return `<span class="op">No course requirement${c.p ? " (conditions only)" : ""}</span>`;
  return c.g.map((g) => `<span class="grp">${g.map(([k, t]) => {
    const known = state.byKey.get(k);
    const tag = t === "c" ? " · concurrent" : t === "p" ? " · prior or concurrent" : "";
    const flag = !known && state.cat.complete !== false;   // absent from a partial file proves nothing
    return `<span class="opt ${flag ? "missing" : known ? "" : "absent"}" data-k="${esc(k)}" title="${known ? esc(known.t) : flag ? "not in this catalog" : "not in this term's file"}">${esc(known ? known.c : k)}${tag}</span>`;
  }).join(`<span class="op">OR</span>`)}</span>`).join(`<span class="op">AND</span>`);
}

function selectCourse(k) {
  const c = state.byKey.get(k);
  if (!c) return;
  state.selected = k;
  document.querySelectorAll(".f").forEach((b) => b.classList.toggle("sel", b.dataset.k === k));
  const fs = state.findingsByCourse.get(k) || [];
  const conds = c.p.includes("COND:") ? c.p.split("COND:")[1].trim() : "";
  const deps = [...(state.requiredBy.get(k) || [])].map((x) => state.byKey.get(x)).filter(Boolean);
  $("#detail").innerHTML = `
    <h2>${esc(c.c)}</h2><div class="title">${esc(c.t)}</div>
    ${fs.map((f) => `<div class="row" style="margin:4px 0"><span class="sev ${f.severity}">${f.severity}</span> <span>${esc(f.detail)}</span></div>`).join("")}
    <div class="label">Catalog text</div><div class="raw">${esc(c.r || "No prerequisite listed.")}</div>
    <div class="label">Parsed requirement</div><div class="logic">${logicHTML(c)}</div>
    ${conds ? `<div class="legend">Conditions: ${esc(conds)}</div>` : ""}
    ${c.nr ? `<div class="review">Flagged for review: ${esc(c.nr)}</div>` : ""}
    <div class="label">Prerequisite graph</div><div class="graph">${graphSVG(k)}</div>
    <div class="legend">Arrows point toward the course they unlock. Dashed arrow = one of several alternatives. ${state.cat.complete === false
      ? "Dashed box = not in this term's file (not a problem: the file lists one term's offerings)."
      : "Red = a problem, or a course missing from the catalog."}</div>
    ${deps.length ? `<div class="label">Required by (${deps.length})</div><div class="logic">${deps.slice(0, 30).map((d) => `<span class="opt" data-k="${esc(d.k)}">${esc(d.c)}</span>`).join("")}${deps.length > 30 ? `<span class="op">+${deps.length - 30} more</span>` : ""}</div>` : ""}`;
  $("#detail").querySelectorAll("[data-k]").forEach((e) => e.addEventListener("click", () => selectCourse(e.dataset.k)));
  const gr = $("#detail .graph"); if (gr) gr.scrollLeft = gr.scrollWidth;   // keep the selected course in view
  writeHash();
  if (window.innerWidth < 860) $("#detail").scrollIntoView({ behavior: "smooth" });
}

// Upstream prerequisite graph, laid out in columns by depth (root on the right).
function graphSVG(root) {
  const MAXD = 4, MAXN = 45, W = 116, H = 24, GX = 36, GY = 10;
  const level = new Map([[root, 0]]), edges = [], queue = [root];
  while (queue.length && level.size < MAXN) {
    const k = queue.shift(), d = level.get(k), c = state.byKey.get(k);
    if (!c || d >= MAXD) continue;
    for (const g of c.g) for (const [p] of g) {
      if (level.size >= MAXN && !level.has(p)) continue;
      edges.push([p, k, g.length > 1]);
      if (!level.has(p)) { level.set(p, d + 1); queue.push(p); }
    }
  }
  if (level.size === 1) return `<div class="more">No course prerequisites.</div>`;
  const cols = [];
  for (const [k, d] of level) (cols[d] ||= []).push(k);
  const depth = cols.length, rows = Math.max(...cols.map((c) => c.length));
  const width = depth * (W + GX) - GX + 20, height = rows * (H + GY) - GY + 20;
  const pos = new Map();
  cols.forEach((col, d) => col.sort().forEach((k, i) => {
    const x = 10 + (depth - 1 - d) * (W + GX);
    const y = 10 + i * (H + GY) + ((rows - col.length) * (H + GY)) / 2;
    pos.set(k, [x, y]);
  }));
  const partial = state.cat.complete === false;
  const bad = (k) => (!state.byKey.has(k) && !partial) || (state.findingsByCourse.get(k) || []).some((f) => f.severity !== "info");
  const seen = new Set();
  const paths = edges.filter(([a, b]) => {   // only draw edges that flow left-to-right, once each
    const ok = pos.has(a) && pos.has(b) && level.get(a) > level.get(b) && !seen.has(a + ">" + b);
    seen.add(a + ">" + b); return ok;
  }).map(([a, b, alt]) => {
    const [x1, y1] = pos.get(a), [x2, y2] = pos.get(b);
    const sx = x1 + W, sy = y1 + H / 2, ex = x2, ey = y2 + H / 2, mx = (sx + ex) / 2;
    return `<path class="${alt ? "alt" : ""}" d="M${sx},${sy} C${mx},${sy} ${mx},${ey} ${ex - 4},${ey}" marker-end="url(#arr)"/>`;
  }).join("");
  const nodes = [...pos].map(([k, [x, y]]) => {
    const c = state.byKey.get(k);
    const label = (c ? c.c : k).slice(0, 15);
    const cls = ["node", k === root ? "root" : "", bad(k) ? "bad" : "", c ? "" : "ghost"].join(" ");
    return `<g class="${cls}" data-k="${esc(k)}"><title>${esc(c ? c.c + " · " + c.t : k + " (not in this catalog)")}</title>
      <rect x="${x}" y="${y}" width="${W}" height="${H}" rx="6"/><text x="${x + 8}" y="${y + 16}">${esc(label)}</text></g>`;
  }).join("");
  return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="Prerequisite graph">
    <defs><marker id="arr" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,0 L8,4 L0,8z" style="fill:var(--muted);stroke:none"/></marker></defs>
    ${paths}${nodes}</svg>`;
}

// ------------------------------------------------------------------ evaluation tab
function renderEval() {
  const e = state.index.evals, gm = e.gold_muse?.scores, gb = e.gold_baseline?.scores;
  const tier = (s, t) => s?.[t]?.structure_exact;
  const row = (t, label) => {
    const b = tier(gb, t), m = tier(gm, t);
    return `<tr><td>${label}</td><td class="num">${gm?.[t]?.n ?? ""}</td><td class="num">${pct(b)}</td><td class="num ${m > b ? "win" : ""}">${pct(m)}</td></tr>`;
  };
  const pl = e.audit_planted, ens = e.ensemble?.ensemble, cost = e.gold_muse?.cost;
  const recallRows = pl ? Object.entries(pl.recall).map(([k, v]) => `<tr><td>${esc({ missing_course: "Requires a non-existent course", removed: "Required course removed", cycle: "Prerequisite loop", self_reference: "Requires itself" }[k] || k)}</td><td class="num">${pl.planted[k]}</td><td class="num win">${pct(v)}</td></tr>`).join("") : "";
  $("#eval").innerHTML = `
  <div class="evalgrid">
    <div class="card" style="grid-column:1/-1">
      <h3>Parsing accuracy on the hand-labeled test set</h3>
      <p class="sub">150 held-out courses from 13 universities, oversampling hard cases, labeled by hand and scored once. Metric: exact match of the AND/OR course structure.</p>
      <div class="kpis">
        <div><div class="big">${pct(tier(gm, "all"))}</div><div class="l">Muse Spark 1.3</div></div>
        <div><div class="big" style="color:var(--muted)">${pct(tier(gb, "all"))}</div><div class="l">regex baseline</div></div>
        <div><div class="big">${pct(gm?.all?.structure_exact_unflagged)}</div><div class="l">on courses it did not flag (${pct(gm?.all?.flag_rate)} flagged)</div></div>
      </div>
      <table style="margin-top:14px"><thead><tr><th>Difficulty</th><th class="num">Courses</th><th class="num">Regex baseline</th><th class="num">Muse Spark</th></tr></thead>
      <tbody>${row("simple", "Simple (one course)")}${row("moderate", "Moderate (lists, grades, conditions)")}${row("hard", "Hard (alternatives, nesting, timing)")}${row("all", "<b>All</b>")}</tbody></table>
      ${cost ? `<p class="sub" style="margin-top:10px">Cost $${cost.usd_per_course.toFixed(4)} per course; median latency ${cost.median_latency_s.toFixed(1)} s; ${cost.guardrail_failures} guardrail failures; ${cost.api_errors} API errors.</p>` : ""}
    </div>
    <div class="card"><h3>Audit checks: planted defects</h3>
      <p class="sub">${pl ? `${Object.values(pl.planted).reduce((a, b) => a + b, 0)} defects planted in ${pl.catalogs.length} real catalogs × ${pl.seeds} seeds. False alarms: <b>${pl.false_alarms}</b>.` : ""}</p>
      <table><thead><tr><th>Defect</th><th class="num">Planted</th><th class="num">Found</th></tr></thead><tbody>${recallRows}</tbody></table></div>
    <div class="card"><h3>Second opinion: Muse Spark Open</h3>
      <p class="sub">Open-weights Muse Spark on Baseten, parsing the same 150 dev courses independently.</p>
      ${ens ? `<div class="kpis"><div><div class="big">${pct(ens.disagreement_rate)}</div><div class="l">of courses where the two disagreed</div></div></div>
      <p>The two models are from the same family and almost always fail on the same inputs, so disagreement caught no new errors here. An independent check needs a verifier that fails differently; the code guardrails remain the main safety net.</p>` : "<p>Not run.</p>"}</div>
    <div class="card" style="grid-column:1/-1"><h3>What the evaluation found about the reference data</h3>
      <ul><li>Of 130 gold courses with a published parse in the Mendeley dataset, that parse was fully correct for 110 (85%). Muse Spark matched the gold structure on 96.9% of them, the published parses on 90.8%.</li>
      <li>Most disagreements on the development set traced to the reference: it omits corequisites, flattens explicit AND/OR for one institution, and in some catalogs counts the next course's heading (extracted onto the end of the prerequisite) as a prerequisite.</li>
      <li>Muse Spark at <code>minimal</code> reasoning matched <code>low</code> on 299 of 300 dev courses at 28% lower cost.</li></ul></div>
  </div>`;
}

init().catch((err) => { $("#findings").innerHTML = `<div class="more">Could not load data: ${esc(err.message)}</div>`; });
