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
                check: "all", query: "", limit: 24, selected: null, trail: [] };

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
  setupCoursePicker();
  renderEval();
  // A refresh always returns to the landing page; a first visit through a shared link still opens it.
  const nav = performance.getEntriesByType("navigation")[0];
  if (nav && nav.type === "reload") history.replaceState(null, "", location.pathname);
  await route();
}

async function loadCatalog(id, course, goingBack = false) {
  if (!goingBack) remember();   // keep history across catalogs
  const meta = state.index.catalogs.find((c) => c.id === id);
  $("#findings").innerHTML = `<div class="more">Loading…</div>`;
  const cat = await (await fetch("data/" + meta.file)).json();
  state.cat = cat; state.check = "all"; state.query = ""; state.selected = null; state.limit = 24;
  $("#search").value = "";
  state.byKey = new Map(cat.courses.map((c) => [c.k, c]));
  state.sorted = cat.courses.slice().sort((a, b) => a.c.localeCompare(b.c, undefined, { numeric: true }));
  $("#search-label").textContent = `Find a course (${cat.courses.length.toLocaleString()} in this catalog)`;
  closeList();
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
  $("#chips").querySelectorAll(".chip").forEach((b) => b.addEventListener("click", () => { state.check = b.dataset.k; state.limit = 24; renderChips(); renderFindings(); }));
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
  el.querySelectorAll(".f").forEach((b) => b.addEventListener("click", () => selectCourse(b.dataset.k, true)));
  $("#more")?.addEventListener("click", () => { state.limit += 48; renderFindings(); });
}

// ------------------------------------------------------------------ course picker (combobox)
const picker = { items: [], active: -1, label: "" };
function courseMatches(q) {
  q = q.trim();
  if (!q) return state.sorted;
  const nq = norm(q), lq = q.toLowerCase(), starts = [], codeHas = [], titleHas = [];
  for (const c of state.sorted) {
    if (nq && c.k.startsWith(nq)) starts.push(c);
    else if (nq && c.k.includes(nq)) codeHas.push(c);
    else if (c.t && c.t.toLowerCase().includes(lq)) titleHas.push(c);
  }
  return starts.concat(codeHas, titleHas);
}
function renderList(q) {
  const ul = $("#course-list"), all = courseMatches(q), MAX = 80;
  picker.items = all.slice(0, MAX); picker.active = picker.items.length ? 0 : -1;
  if (!picker.items.length) {
    ul.innerHTML = `<li class="note">No course matches “${esc(q)}”. Try a code like CS 225 or a word from the name.</li>`;
  } else {
    ul.innerHTML = picker.items.map((c, i) => {
      const fs = state.findingsByCourse.get(c.k) || [];
      const sev = fs.find((f) => f.severity === "blocking") ? "blocking" : fs.find((f) => f.severity === "warning") ? "warning" : "";
      return `<li role="option" id="copt-${i}" data-i="${i}" class="${i === 0 ? "active" : ""}" aria-selected="${i === 0}">
        <b>${esc(c.c)}</b><span>${esc(c.t || "No title listed")}</span>${sev ? `<i class="dot ${sev}" title="has a ${sev} finding"></i>` : ""}</li>`;
    }).join("") + (all.length > MAX ? `<li class="note">${(all.length - MAX).toLocaleString()} more. Keep typing to narrow the list.</li>` : "");
  }
  ul.classList.add("open"); $("#search").setAttribute("aria-expanded", "true");
  $("#search").setAttribute("aria-activedescendant", picker.active >= 0 ? "copt-0" : "");
}
function closeList() {
  $("#course-list")?.classList.remove("open");
  $("#search")?.setAttribute("aria-expanded", "false");
}
function setActive(i) {
  const lis = [...$("#course-list").querySelectorAll("li[data-i]")];
  if (!lis.length) return;
  picker.active = (i + lis.length) % lis.length;
  lis.forEach((li, j) => { li.classList.toggle("active", j === picker.active); li.setAttribute("aria-selected", j === picker.active); });
  lis[picker.active].scrollIntoView({ block: "nearest" });
  $("#search").setAttribute("aria-activedescendant", "copt-" + picker.active);
}
function pickCourse(c) {
  closeList();
  picker.label = `${c.c} · ${c.t || ""}`.trim();
  $("#search").value = picker.label;
  $("#search").blur();
  state.query = ""; state.limit = 24; renderFindings();
  selectCourse(c.k, true);
}
function setupCoursePicker() {
  const input = $("#search"), ul = $("#course-list");
  const current = () => (input.value === picker.label ? "" : input.value);
  input.addEventListener("focus", () => { input.select(); renderList(current()); });
  input.addEventListener("click", () => {
    if (input.value === picker.label) input.select();   // typing replaces the picked course's name
    if (!ul.classList.contains("open")) renderList(current());
  });
  input.addEventListener("input", () => {
    picker.label = "";
    state.query = input.value.trim(); state.limit = 24; renderFindings();   // also narrows the findings below
    renderList(input.value);
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); if (!ul.classList.contains("open")) renderList(current()); else setActive(picker.active + 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive(picker.active - 1); }
    else if (e.key === "Enter") { e.preventDefault(); const c = picker.items[picker.active]; if (c) pickCourse(c); }
    else if (e.key === "Escape") { closeList(); }
  });
  ul.addEventListener("mousedown", (e) => {   // mousedown fires before the input loses focus
    const li = e.target.closest("li[data-i]"); if (!li) return;
    e.preventDefault(); pickCourse(picker.items[+li.dataset.i]);
  });
  input.addEventListener("blur", () => setTimeout(closeList, 120));
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

function remember() {
  if (!state.cat || !state.selected) return;
  const last = state.trail[state.trail.length - 1];
  if (last && last.cat === state.cat.id && last.k === state.selected) return;
  state.trail.push({ cat: state.cat.id, k: state.selected, label: state.byKey.get(state.selected)?.c || state.selected });
  if (state.trail.length > 50) state.trail.shift();
}
function backButton() {
  const last = state.trail[state.trail.length - 1];
  if (!last) return "";
  const where = last.cat === state.cat.id ? "" : ` (${esc(state.index.catalogs.find((c) => c.id === last.cat)?.name.split(",")[0] || last.cat)})`;
  return `<button class="back" id="back">← Back to ${esc(last.label)}${where}</button>`;
}
async function goBack() {
  const prev = state.trail.pop();
  if (!prev) return;
  if (prev.cat === state.cat.id) return selectCourse(prev.k, true, true);
  $("#catalog").value = prev.cat;
  await loadCatalog(prev.cat, prev.k, true);
}
function selectCourse(k, scroll = false, goingBack = false) {
  const c = state.byKey.get(k);
  if (!c) return;
  if (!goingBack && state.selected && state.selected !== k) remember();   // remember where we came from
  state.selected = k;
  document.querySelectorAll(".f").forEach((b) => b.classList.toggle("sel", b.dataset.k === k));
  const fs = state.findingsByCourse.get(k) || [];
  const conds = c.p.includes("COND:") ? c.p.split("COND:")[1].trim() : "";
  const deps = [...(state.requiredBy.get(k) || [])].map((x) => state.byKey.get(x)).filter(Boolean);
  $("#detail").innerHTML = `
    ${backButton()}
    <div class="d-head"><h2>${esc(c.c)}</h2><div class="title">${esc(c.t)}</div>
      ${fs.map((f) => `<div class="d-find"><span class="sev ${f.severity}">${f.severity}</span> <span>${esc(f.detail)}</span></div>`).join("")}</div>
    <div class="d-body">
      <div class="d-left">
        <div class="label">Catalog text</div><div class="raw">${esc(c.r || "No prerequisite listed.")}</div>
        <div class="label">Parsed requirement</div><div class="logic">${logicHTML(c)}</div>
        ${conds ? `<div class="legend">Conditions: ${esc(conds)}</div>` : ""}
        ${c.nr ? `<div class="review">Flagged for review: ${esc(c.nr)}</div>` : ""}
        ${deps.length ? `<div class="label">Required by (${deps.length})</div><div class="logic">${deps.slice(0, 30).map((d) => `<span class="opt" data-k="${esc(d.k)}">${esc(d.c)}</span>`).join("")}${deps.length > 30 ? `<span class="op">+${deps.length - 30} more</span>` : ""}</div>` : ""}
      </div>
      <div class="d-right">
        <div class="label">Prerequisite graph</div><div class="graph">${graphSVG(k)}</div>
        <div class="legend">Arrows point toward the course they unlock. Dashed arrow = one of several alternatives. ${state.cat.complete === false
          ? "Dashed box = not in this term's file (not a problem: the file lists one term's offerings)."
          : "Red = a problem, or a course missing from the catalog."}</div>
      </div>
    </div>`;
  $("#detail").querySelectorAll("[data-k]").forEach((e) => e.addEventListener("click", () => selectCourse(e.dataset.k, true)));
  $("#back")?.addEventListener("click", goBack);
  const gr = $("#detail .graph"); if (gr) gr.scrollLeft = gr.scrollWidth;   // keep the selected course in view
  writeHash();
  if (scroll) {   // bring the course panel into view when it was picked from further down
    const r = $("#detail").getBoundingClientRect();
    if (r.top < 64 || r.top > window.innerHeight * 0.5) window.scrollTo({ top: window.scrollY + r.top - 76, behavior: "smooth" });
  }
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
  const names = { missing_course: "Requires a course that doesn't exist", removed: "A required course was removed",
                  cycle: "Prerequisite loop", self_reference: "Course requires itself" };
  const recallRows = pl ? Object.entries(pl.recall).map(([k, v]) => `<tr><td>${esc(names[k] || k)}</td><td class="num">${pl.planted[k]}</td><td class="num win">${pct(v)}</td></tr>`).join("") : "";
  const planted = pl ? Object.values(pl.planted).reduce((a, b) => a + b, 0) : 0;
  $("#eval").innerHTML = `
  <div class="evalgrid">
    <div class="card" style="grid-column:1/-1">
      <h3>How accurately Muse Spark reads prerequisites</h3>
      <p class="sub">150 courses from 13 universities were hand-labeled, oversampling hard cases, and held out from all development until the final run. A course counts as correct only if every course and every AND/OR matches the label.</p>
      <div class="kpis">
        <div><div class="big">${pct(tier(gm, "all"))}</div><div class="l">Muse Spark 1.3</div></div>
        <div><div class="big" style="color:var(--muted)">${pct(tier(gb, "all"))}</div><div class="l">a rule-based parser (no AI)</div></div>
        <div><div class="big">${pct(gm?.all?.structure_exact_unflagged)}</div><div class="l">on courses not flagged for review (flagged: ${pct(gm?.all?.flag_rate)})</div></div>
      </div>
      <table style="margin-top:14px"><thead><tr><th>Difficulty</th><th class="num">Courses</th><th class="num">Rule-based parser</th><th class="num">Muse Spark</th></tr></thead>
      <tbody>${row("simple", "Easy: a single course")}${row("moderate", "Medium: lists, grades, conditions")}${row("hard", "Hard: alternatives, nesting, timing")}${row("all", "<b>All</b>")}</tbody></table>
      ${cost ? `<p class="sub" style="margin-top:10px">Cost: about $${cost.usd_per_course.toFixed(4)} per course, about ${cost.median_latency_s.toFixed(1)} seconds each. ${cost.guardrail_failures === 0 ? "No final answers failed the code checks" : `${cost.guardrail_failures} final answers failed the code checks`}, and there ${cost.api_errors === 0 ? "were no API errors" : `were ${cost.api_errors} API errors`}.</p>` : ""}
    </div>
    <div class="card"><h3>Do the audit checks catch real problems?</h3>
      <p class="sub">${pl ? `${planted} known defects were planted in ${pl.catalogs.length} real catalogs to measure whether the audit finds them. False alarms: <b>${pl.false_alarms}</b>.` : ""}</p>
      <table><thead><tr><th>Planted defect</th><th class="num">Planted</th><th class="num">Found</th></tr></thead><tbody>${recallRows}</tbody></table></div>
    <div class="card"><h3>Does a second model help?</h3>
      <p class="sub">Muse Spark Open, the open-weights version, was run on Baseten over 150 development courses and compared against Muse Spark.</p>
      ${ens ? `<div class="kpis"><div><div class="big">${pct(ens.disagreement_rate)}</div><div class="l">of courses where the two models disagreed</div></div></div>
      <p>The two models are closely related and tend to make the same mistakes, so their disagreements caught no new errors. An effective second check needs a verifier that fails in different ways; the code checks remain the primary safeguard.</p>` : "<p>Not run.</p>"}</div>
    <div class="card" style="grid-column:1/-1"><h3>Findings about the reference dataset</h3>
      <ul><li>The research dataset's own parsed prerequisites were fully correct for 110 of the 130 test courses that have one (85%). On those same courses, Muse Spark got the AND/OR structure right 96.9% of the time, and the dataset 90.8%.</li>
      <li>When Muse Spark and the dataset disagreed, the dataset was often the one that was wrong. It leaves out corequisites, flattens AND/OR for one university, and sometimes counts the next course's heading as a prerequisite.</li>
      <li>The lowest reasoning setting, <code>minimal</code>, matched <code>low</code> on 299 of 300 development courses at 28% lower cost, so it is used throughout.</li></ul></div>
  </div>`;
}

init().catch((err) => { $("#findings").innerHTML = `<div class="more">Could not load data: ${esc(err.message)}</div>`; });
