"use strict";
// Landing-page background: a slowly turning 3D prerequisite network. Gold links are ordinary
// prerequisites; a few coral links are "broken" ones. No library, ~150 lines of canvas.
(function () {
  const canvas = document.getElementById("net");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const CODES = ["CS 225", "MATH 213", "CS 173", "PHYS 211", "CHEM 102", "MATH 231", "CS 374", "ECE 220",
    "STAT 200", "BIOL 120", "ECON 101", "NUTR 377", "CS 124", "MATH 241", "ENGL 214", "CHEM 104", "ME 301", "CS 421"];
  let rand = 7;   // seeded random, so the picture is the same on every visit
  const rnd = () => ((rand = (rand * 16807) % 2147483647) / 2147483647);

  // layered like a curriculum: earlier courses on the left, later on the right
  const LAYERS = 7, nodes = [], edges = [];
  for (let l = 0; l < LAYERS; l++) {
    const count = 9 + Math.floor(rnd() * 6);
    for (let i = 0; i < count; i++) {
      const a = rnd() * Math.PI * 2, r = Math.sqrt(rnd()) * 1.05;
      nodes.push({ l, x: -1.7 + (3.4 * l) / (LAYERS - 1) + (rnd() - 0.5) * 0.25, y: Math.sin(a) * r, z: Math.cos(a) * r, label: null });
    }
  }
  const byLayer = (l) => nodes.filter((n) => n.l === l);
  for (const n of nodes) {
    if (n.l === LAYERS - 1) continue;
    const next = byLayer(n.l + 1).map((m) => [m, (m.y - n.y) ** 2 + (m.z - n.z) ** 2]).sort((a, b) => a[1] - b[1]);
    const k = 1 + (rnd() < 0.55 ? 1 : 0);
    for (let i = 0; i < k && i < next.length; i++) edges.push({ a: n, b: next[i][0], broken: false });
  }
  for (let i = 0; i < 7; i++) edges[Math.floor(rnd() * edges.length)].broken = true;
  const shuffled = nodes.slice().sort(() => rnd() - 0.5);
  CODES.forEach((c, i) => { shuffled[i].label = c; });
  // the NUTR 377 node sits at the end of a broken link: the renumbered course from the demo
  const nutr = nodes.find((n) => n.label === "NUTR 377");
  const into = edges.find((e) => e.b === nutr) || edges.find((e) => e.a === nutr);
  if (into) into.broken = true;

  let W = 0, H = 0, dpr = 1, angle = 0.6, tiltX = 0.25, tiltY = 0, aimX = 0.25, aimY = 0, t = 0, raf = 0, running = false;
  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = canvas.clientWidth; H = canvas.clientHeight;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (!running) draw();
  }
  function project(n) {
    const ca = Math.cos(angle + tiltY), sa = Math.sin(angle + tiltY);
    let x = n.x * ca - n.z * sa, z = n.x * sa + n.z * ca, y = n.y;
    const cb = Math.cos(tiltX), sb = Math.sin(tiltX);
    const y2 = y * cb - z * sb; z = y * sb + z * cb;
    const mobile = W < 860, scale = Math.min(W, H * 1.6) * (mobile ? 0.26 : 0.165);
    const f = 3.2 / (3.2 + z);
    return { x: (mobile ? W * 0.5 : W * 0.74) + x * scale * f, y: H * (mobile ? 0.78 : 0.47) + y2 * scale * f, f, z };
  }
  function fade(p) {   // keep the text column calm: fade the network out toward it
    const v = W < 860 ? (p.y - H * 0.45) / (H * 0.2) : (p.x - W * 0.48) / (W * 0.14);
    return Math.max(0, Math.min(1, v)) * (W < 860 ? 0.5 : 1);   // phones: a quieter background
  }
  function draw() {
    ctx.clearRect(0, 0, W, H);
    const P = new Map(nodes.map((n) => [n, project(n)]));
    for (const e of edges) {
      const p = P.get(e.a), q = P.get(e.b), depth = ((p.f + q.f) / 2) * Math.min(fade(p), fade(q));
      if (depth <= 0.01) continue;
      if (e.broken) {
        const pulse = reduce ? 1 : 0.75 + 0.25 * Math.sin(t * 2.2 + p.x * 0.01);
        ctx.strokeStyle = `rgba(255,116,102,${Math.min(1, pulse * depth * 1.3).toFixed(3)})`; ctx.lineWidth = 2.2 * depth;
        ctx.setLineDash([5, 4]);
      } else {
        ctx.strokeStyle = `rgba(226,181,90,${(0.32 * depth * depth).toFixed(3)})`; ctx.lineWidth = 1 * depth;
        ctx.setLineDash([]);
      }
      ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y); ctx.stroke();
    }
    ctx.setLineDash([]);
    const order = nodes.slice().sort((a, b) => P.get(b).z - P.get(a).z);
    for (const n of order) {
      const p0 = P.get(n), brokenEnd = n === nutr, fd = fade(p0);
      if (fd <= 0.01) continue;
      const p = { ...p0, f: p0.f * fd };
      ctx.fillStyle = brokenEnd ? `rgba(255,116,102,${0.95 * p.f})` : `rgba(244,239,227,${(0.35 + 0.55 * (p.f - 0.7)).toFixed(3)})`;
      ctx.beginPath(); ctx.arc(p.x, p.y, (n.label ? 3.2 : 2) * p.f, 0, Math.PI * 2); ctx.fill();
      if (n.label && W >= 860 && p.f > 0.85 && fd > 0.95) {
        ctx.font = `${Math.round(11 * p0.f)}px "JetBrains Mono", ui-monospace, monospace`;
        ctx.fillStyle = brokenEnd ? `rgba(255,116,102,${0.9 * p.f})` : `rgba(244,239,227,${(0.6 * (p.f - 0.8)).toFixed(3)})`;
        ctx.fillText(n.label, p.x + 7, p.y - 6);
      }
    }
  }
  function frame() {
    t += 1 / 60; angle += 0.0016;
    tiltX += (aimX - tiltX) * 0.04; tiltY += (aimY - tiltY) * 0.04;
    draw(); raf = requestAnimationFrame(frame);
  }
  function start() { if (running || reduce) { draw(); return; } running = true; raf = requestAnimationFrame(frame); }
  function stop() { running = false; cancelAnimationFrame(raf); }
  window.addEventListener("pointermove", (e) => {
    aimY = ((e.clientX / window.innerWidth) - 0.5) * 0.5;
    aimX = 0.25 + ((e.clientY / window.innerHeight) - 0.5) * 0.3;
  });
  window.addEventListener("resize", resize);
  document.addEventListener("visibilitychange", () => (document.hidden ? stop() : window.netActive && start()));
  window.net = { start() { window.netActive = true; resize(); start(); }, stop() { window.netActive = false; stop(); } };
})();
