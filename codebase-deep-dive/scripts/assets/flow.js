/* Interactive dependency flow. Plain JS, no libraries, no network.
 *
 * Data: #flow-data (built by flow.py). Two views, "folder" and "file", each with
 * nodes (id, label, sub, group, lines, layer, cyc, fan_in, fan_out) and edges
 * (s imports t, w = weight, cyc = inside a cycle). Layer 0 = foundations.
 */
(() => {
  'use strict';
  const DATA = JSON.parse(document.getElementById('flow-data').textContent);
  const NS = 'http://www.w3.org/2000/svg';
  const RM = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const $ = (s) => document.querySelector(s);

  const svg = $('#flow-svg'), vp = $('#vp'), gBands = $('#bands'), gEdges = $('#edges'), gNodes = $('#nodes');
  const stage = $('#stage'), tip = $('#tip'), detail = $('#detail'), mini = $('#mini'), toastEl = $('#toast');

  const NODE_H = 54, ROW_GAP = 136, SUB_GAP = 78, COL_GAP = 28, MAX_PER_ROW = 8;
  const GROUP_INDEX = new Map(DATA.groups.map((g, i) => [g, i]));
  const colour = (g) => `var(--series-${((GROUP_INDEX.get(g) || 0) % 8) + 1})`;
  const fmt = (n) => Number(n).toLocaleString('en-US');
  const plural = (n, w) => `${fmt(n)} ${w}${n === 1 ? '' : 's'}`;
  const clip = (s, n) => (s.length > n ? s.slice(0, n - 1) + '…' : s);

  const state = {
    view: DATA.defaultView, layout: 'layered', mode: 'down', depth: Infinity,
    selected: null, path: null, tracing: false, hidden: new Set(), scope: null,
  };
  let T = { x: 0, y: 0, k: 1 };
  let G = null;
  let simHandle = null;

  // ------------------------------------------------------------------ helpers
  function el(tag, attrs, parent) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function h(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  const measureCtx = document.createElement('canvas').getContext('2d');
  const F1 = '600 13px Inter, -apple-system, system-ui, sans-serif';
  const F2 = '11px ui-monospace, SFMono-Regular, Menlo, monospace';
  function textW(s, font) { measureCtx.font = font; return measureCtx.measureText(s).width; }

  let toastTimer = null;
  function toast(msg, ms = 2600) {
    toastEl.textContent = msg; toastEl.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toastEl.hidden = true; }, ms);
  }

  // -------------------------------------------------------------------- graph
  function buildGraph() {
    const v = DATA.views[state.view];
    let src = v.nodes;
    const ghost = new Set();
    if (state.view === 'file' && state.scope) {
      // A scope is a top-level folder or any folder below it (src/flask).
      const pre = state.scope.replace(/\/+$/, '') + '/';
      const inside = new Set(src.filter((n) => n.group === state.scope || n.id.startsWith(pre)).map((n) => n.id));
      const keep = new Set(inside);
      for (const e of v.edges) {
        if (inside.has(e.s)) keep.add(e.t);
        if (inside.has(e.t)) keep.add(e.s);
      }
      for (const id of keep) if (!inside.has(id)) ghost.add(id);
      src = src.filter((n) => keep.has(n.id));
    }
    src = src.filter((n) => !state.hidden.has(n.group));
    const nodes = src.map((n) => {
      const label = clip(n.label, 30), sub = clip(n.sub, 40);
      const pill = n.fan_in > 0 ? 34 : 0;
      const w = Math.max(150, Math.min(300, Math.max(textW(label, F1) + pill, textW(sub, F2)) + 40));
      return Object.assign({}, n, { label, sub, w, h: NODE_H, x: 0, y: 0, vx: 0, vy: 0, ghost: ghost.has(n.id), pinned: false });
    });
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const edges = v.edges.filter((e) => byId.has(e.s) && byId.has(e.t))
      .map((e) => Object.assign({}, e, { a: byId.get(e.s), b: byId.get(e.t), p1: 0, p2: 0 }));
    const out = new Map(nodes.map((n) => [n.id, []]));
    const inc = new Map(nodes.map((n) => [n.id, []]));
    for (const e of edges) { out.get(e.s).push(e); inc.get(e.t).push(e); }
    G = { nodes, byId, edges, out, inc, bands: [] };
  }

  // Breadth-first reach. 'down' = who depends on id (blast radius), 'up' = what id depends on.
  function reach(id, dir, depth) {
    const dist = new Map([[id, 0]]);
    const q = [id];
    while (q.length) {
      const v = q.shift(), d = dist.get(v);
      if (d >= depth) continue;
      const next = dir === 'down' ? G.inc.get(v).map((e) => e.s) : G.out.get(v).map((e) => e.t);
      for (const w of next) if (!dist.has(w)) { dist.set(w, d + 1); q.push(w); }
    }
    dist.delete(id);
    return dist;
  }

  function shortestPath(a, b) {
    const bfs = (next) => {
      const prev = new Map([[a, null]]);
      const q = [a];
      while (q.length) {
        const v = q.shift();
        if (v === b) break;
        for (const w of next(v)) if (!prev.has(w)) { prev.set(w, v); q.push(w); }
      }
      if (!prev.has(b)) return null;
      const p = [];
      for (let v = b; v != null; v = prev.get(v)) p.unshift(v);
      return p;
    };
    const fwd = bfs((v) => G.out.get(v).map((e) => e.t));
    if (fwd) return { path: fwd, kind: 'depends' };
    const back = bfs((v) => G.inc.get(v).map((e) => e.s));
    if (back) return { path: back, kind: 'used-by' };
    const any = bfs((v) => G.out.get(v).map((e) => e.t).concat(G.inc.get(v).map((e) => e.s)));
    if (any) return { path: any, kind: 'linked' };
    return null;
  }

  // ------------------------------------------------------------------- layout
  // Layered (Sugiyama-style): one row per dependency layer, consumers on top,
  // foundations at the bottom, rows ordered by barycentre to cut crossings.
  function layeredLayout() {
    const layers = [...new Set(G.nodes.map((n) => n.layer))].sort((a, b) => b - a);
    const rowOf = new Map(layers.map((l, i) => [l, i]));
    const rows = layers.map(() => []);
    for (const n of G.nodes) rows[rowOf.get(n.layer)].push(n);
    for (const r of rows) r.sort((a, b) => (GROUP_INDEX.get(a.group) - GROUP_INDEX.get(b.group)) || (b.lines - a.lines));
    const rank = new Map();
    const setRanks = (r) => r.forEach((n, i) => rank.set(n.id, r.length > 1 ? i / (r.length - 1) : 0.5));
    rows.forEach(setRanks);
    const nbrs = (n) => G.out.get(n.id).map((e) => e.b).concat(G.inc.get(n.id).map((e) => e.a))
      .filter((m) => m.layer !== n.layer);
    for (let it = 0; it < 10; it++) {
      const order = it % 2 ? rows.slice().reverse() : rows;
      for (const r of order) {
        const bc = new Map(r.map((n) => {
          const ns = nbrs(n);
          return [n.id, ns.length ? ns.reduce((s, m) => s + rank.get(m.id), 0) / ns.length : rank.get(n.id)];
        }));
        r.sort((a, b) => bc.get(a.id) - bc.get(b.id));
        setRanks(r);
      }
    }
    let y = 0;
    G.bands = [];
    rows.forEach((r, ri) => {
      const chunks = [];
      for (let i = 0; i < r.length; i += MAX_PER_ROW) chunks.push(r.slice(i, i + MAX_PER_ROW));
      const y0 = y;
      chunks.forEach((c, ci) => {
        const total = c.reduce((s, n) => s + n.w, 0) + COL_GAP * (c.length - 1);
        let x = -total / 2;
        for (const n of c) { n.x = x + n.w / 2; n.y = y; n.home = { x: n.x, y: n.y }; n.pinned = false; x += n.w + COL_GAP; }
        if (ci < chunks.length - 1) y += SUB_GAP;
      });
      G.bands.push({
        y0: y0 - NODE_H / 2 - 20, y1: y + NODE_H / 2 + 20, layer: layers[ri],
        note: ri === rows.length - 1 ? 'foundation' : ri === 0 ? 'entry points and consumers' : '',
      });
      y += ROW_GAP;
    });
  }

  // Organic: a force simulation that still pulls each node towards its layer's
  // height, so dependencies keep flowing downwards.
  function stopSim() { if (simHandle) cancelAnimationFrame(simHandle); simHandle = null; }
  function startForce() {
    stopSim();
    const ns = G.nodes;
    let alpha = 1;
    const tick = () => {
      for (let i = 0; i < ns.length; i++) {
        const a = ns[i];
        for (let j = i + 1; j < ns.length; j++) {
          const b = ns[j];
          let dx = b.x - a.x, dy = b.y - a.y;
          const d2 = dx * dx + dy * dy || 0.01;
          const min = (a.w + b.w) / 2 + 36;
          if (d2 > 4 * min * min) continue;
          const d = Math.sqrt(d2);
          const f = Math.min(40, (min * min) / d2) * 3 * alpha;
          dx /= d; dy /= d;
          a.vx -= dx * f; a.vy -= dy * f * 0.6; b.vx += dx * f; b.vy += dy * f * 0.6;
        }
      }
      for (const e of G.edges) {
        const dx = e.b.x - e.a.x, dy = e.b.y - e.a.y, d = Math.hypot(dx, dy) || 1;
        const f = (d - 200) * 0.015 * alpha;
        e.a.vx += (dx / d) * f; e.a.vy += (dy / d) * f; e.b.vx -= (dx / d) * f; e.b.vy -= (dy / d) * f;
      }
      for (const n of ns) {
        n.vy += ((n.home ? n.home.y : 0) - n.y) * 0.05 * alpha;
        n.vx -= n.x * 0.0015 * alpha;
        if (n.pinned || (drag && drag.node === n)) { n.vx = n.vy = 0; continue; }
        n.vx *= 0.55; n.vy *= 0.55;
        n.x += n.vx; n.y += n.vy;
      }
      // Hard collision: boxes never overlap, whatever the forces did.
      for (let i = 0; i < ns.length; i++) {
        const a = ns[i];
        for (let j = i + 1; j < ns.length; j++) {
          const b = ns[j];
          const dx = b.x - a.x, dy = b.y - a.y;
          const ox = (a.w + b.w) / 2 + 14 - Math.abs(dx), oy = NODE_H + 18 - Math.abs(dy);
          if (ox <= 0 || oy <= 0) continue;
          const fixedA = a.pinned || (drag && drag.node === a), fixedB = b.pinned || (drag && drag.node === b);
          if (fixedA && fixedB) continue;
          const sa = fixedA ? 0 : fixedB ? 1 : 0.5, sb = 1 - sa;
          if (ox < oy) { const s = dx >= 0 ? 1 : -1; a.x -= s * ox * sa; b.x += s * ox * sb; }
          else { const s = dy >= 0 ? 1 : -1; a.y -= s * oy * sa; b.y += s * oy * sb; }
        }
      }
      alpha *= 0.982;
      return alpha;
    };
    if (RM) { for (let i = 0; i < 260 && tick() > 0.01; i++); updatePositions(); drawMinimap(); return; }
    const run = () => {
      const a = tick();
      updatePositions();
      if (a > 0.012) simHandle = requestAnimationFrame(run);
      else { simHandle = null; drawMinimap(); }
    };
    simHandle = requestAnimationFrame(run);
  }

  // Spread the ends of edges along a node's top and bottom so arrows don't bunch.
  function assignPorts() {
    for (const n of G.nodes) {
      const o = G.out.get(n.id).slice().sort((p, q) => p.b.x - q.b.x);
      o.forEach((e, i) => { e.p1 = ((i + 1) / (o.length + 1) - 0.5) * n.w * 0.6; });
      const ii = G.inc.get(n.id).slice().sort((p, q) => p.a.x - q.a.x);
      ii.forEach((e, i) => { e.p2 = ((i + 1) / (ii.length + 1) - 0.5) * n.w * 0.6; });
    }
  }

  function edgePath(e) {
    const a = e.a, b = e.b; // a imports b
    const dy = b.y - a.y;
    if (Math.abs(dy) > NODE_H * 0.8) {
      const down = dy > 0;
      const x1 = a.x + e.p1, y1 = a.y + (down ? a.h / 2 : -a.h / 2);
      const x2 = b.x + e.p2, y2 = b.y + (down ? -b.h / 2 - 2 : b.h / 2 + 2);
      const c = Math.max(36, Math.abs(y2 - y1) * 0.5) * (down ? 1 : -1);
      return `M${x1.toFixed(1)},${y1.toFixed(1)} C${x1.toFixed(1)},${(y1 + c).toFixed(1)} ${x2.toFixed(1)},${(y2 - c).toFixed(1)} ${x2.toFixed(1)},${y2.toFixed(1)}`;
    }
    // Same row: leave from the side and arc over the row so the line stays readable.
    const right = b.x > a.x;
    const x1 = a.x + (right ? a.w / 2 : -a.w / 2), y1 = a.y - 8;
    const x2 = b.x + (right ? -b.w / 2 - 2 : b.w / 2 + 2), y2 = b.y - 8;
    const lift = Math.min(90, 26 + Math.abs(x2 - x1) * 0.12);
    return `M${x1.toFixed(1)},${y1.toFixed(1)} C${(x1 + (right ? 40 : -40)).toFixed(1)},${(y1 - lift).toFixed(1)} ${(x2 + (right ? -40 : 40)).toFixed(1)},${(y2 - lift).toFixed(1)} ${x2.toFixed(1)},${y2.toFixed(1)}`;
  }

  // ------------------------------------------------------------------- render
  function render() {
    gBands.textContent = ''; gEdges.textContent = ''; gNodes.textContent = '';
    if (state.layout === 'layered' && G.nodes.length) {
      const b = bbox();
      const x0 = b.x0 - 170, x1 = b.x1 + 40;
      for (const band of G.bands) {
        el('rect', { x: x0, y: band.y0, width: x1 - x0, height: band.y1 - band.y0, rx: 16, class: 'band' }, gBands);
        el('text', { x: x0 + 20, y: band.y0 + 28, class: 'band-t' }, gBands).textContent = `Layer ${band.layer}`;
        if (band.note) el('text', { x: x0 + 20, y: band.y0 + 45, class: 'band-s' }, gBands).textContent = band.note;
      }
    }
    for (const e of G.edges) {
      e.el = el('path', {
        class: 'edge' + (e.cyc ? ' cyc' : ''),
        'stroke-width': (1.2 + Math.log2(e.w + 1) * 0.9).toFixed(2),
        'marker-end': `url(#${e.cyc ? 'ah-cyc' : 'ah'})`,
      }, gEdges);
    }
    for (const n of G.nodes) {
      const g = el('g', {
        class: 'node' + (n.ghost ? ' ghost' : '') + (n.cyc >= 0 ? ' cyc' : ''),
        'data-id': n.id, tabindex: 0, role: 'button', 'aria-label': `${n.id}. ${n.sub}`,
      }, gNodes);
      el('rect', { class: 'card', x: -n.w / 2, y: -n.h / 2, width: n.w, height: n.h, rx: 11 }, g);
      el('rect', { class: 'bar', x: -n.w / 2 + 7, y: -n.h / 2 + 11, width: 3.5, height: n.h - 22, rx: 1.75, style: `fill:${colour(n.group)}` }, g);
      el('text', { class: 't1', x: -n.w / 2 + 18, y: -3 }, g).textContent = n.label;
      el('text', { class: 't2', x: -n.w / 2 + 18, y: 14 }, g).textContent = n.sub;
      if (n.fan_in > 0) el('text', { class: 'pill', x: n.w / 2 - 12, y: -6, 'text-anchor': 'end' }, g).textContent = `↑${n.fan_in}`;
      n.el = g;
    }
    updatePositions();
    drawMinimap();
    applyHighlight();
  }

  function updatePositions() {
    assignPorts();
    for (const n of G.nodes) n.el.setAttribute('transform', `translate(${n.x.toFixed(1)},${n.y.toFixed(1)})`);
    for (const e of G.edges) e.el.setAttribute('d', edgePath(e));
  }

  function bbox(nodes) {
    nodes = nodes || G.nodes;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const n of nodes) {
      x0 = Math.min(x0, n.x - n.w / 2); y0 = Math.min(y0, n.y - n.h / 2);
      x1 = Math.max(x1, n.x + n.w / 2); y1 = Math.max(y1, n.y + n.h / 2);
    }
    if (x0 === Infinity) return { x0: 0, y0: 0, x1: 1, y1: 1 };
    return { x0, y0, x1, y1 };
  }

  // ---------------------------------------------------------------- viewport
  function applyT() {
    vp.setAttribute('transform', `translate(${T.x.toFixed(2)},${T.y.toFixed(2)}) scale(${T.k.toFixed(4)})`);
    stage.style.backgroundSize = `${22 * T.k}px ${22 * T.k}px`;
    stage.style.backgroundPosition = `${T.x}px ${T.y}px`;
    $('#zoom-level').textContent = Math.round(T.k * 100) + '%';
    drawMiniView();
  }
  function usableWidth() {
    const r = svg.getBoundingClientRect();
    return r.width - (detail.classList.contains('open') && r.width > 900 ? 380 : 0);
  }
  function tween(to, animate) {
    if (!animate || RM) { T = to; applyT(); return; }
    const from = Object.assign({}, T), t0 = performance.now(), dur = 450;
    const step = (now) => {
      const p = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - p, 3);
      T = { x: from.x + (to.x - from.x) * e, y: from.y + (to.y - from.y) * e, k: from.k + (to.k - from.k) * e };
      applyT();
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }
  function fit(nodes, animate) {
    nodes = nodes || G.nodes;
    if (!nodes.length) return;
    const r = svg.getBoundingClientRect(), b = bbox(nodes), pad = 70;
    const W = usableWidth(), H = r.height;
    const extraLeft = state.layout === 'layered' ? 170 : 0;
    const bw = b.x1 - b.x0 + extraLeft, bh = b.y1 - b.y0;
    const k = Math.max(0.1, Math.min(1.2, Math.min((W - pad * 2) / (bw || 1), (H - pad * 2 - 60) / (bh || 1))));
    const cx = (b.x0 - extraLeft + b.x1) / 2, cy = (b.y0 + b.y1) / 2;
    tween({ k, x: W / 2 - cx * k, y: H / 2 + 10 - cy * k }, animate !== false);
  }
  function centreOn(n) {
    const r = svg.getBoundingClientRect();
    const k = Math.max(T.k, 0.85);
    tween({ k, x: usableWidth() / 2 - n.x * k, y: r.height / 2 - n.y * k }, true);
  }
  function focusOn(n) {
    const near = [n].concat(G.out.get(n.id).map((e) => e.b), G.inc.get(n.id).map((e) => e.a));
    if (near.length === 1) { centreOn(n); return; }
    const r = svg.getBoundingClientRect(), b = bbox(near), pad = 80;
    const W = usableWidth(), H = r.height;
    const k = Math.max(0.25, Math.min(1, Math.min((W - pad * 2) / (b.x1 - b.x0 || 1), (H - pad * 2) / (b.y1 - b.y0 || 1))));
    tween({ k, x: W / 2 - ((b.x0 + b.x1) / 2) * k, y: H / 2 - ((b.y0 + b.y1) / 2) * k }, true);
  }
  function zoomBy(f, px, py) {
    const r = svg.getBoundingClientRect();
    if (px == null) { px = r.width / 2; py = r.height / 2; }
    const k = Math.max(0.08, Math.min(3, T.k * f));
    T = { k, x: px - (px - T.x) * (k / T.k), y: py - (py - T.y) * (k / T.k) };
    applyT();
  }

  // ----------------------------------------------------------------- minimap
  function drawMinimap() {
    mini.textContent = '';
    if (!G.nodes.length) return;
    const b = bbox(), pad = 30, W = 200, H = 130;
    const bw = b.x1 - b.x0 + pad * 2, bh = b.y1 - b.y0 + pad * 2;
    const s = Math.min(W / bw, H / bh);
    G.mm = { s, ox: b.x0 - pad - (W / s - bw) / 2, oy: b.y0 - pad - (H / s - bh) / 2 };
    for (const n of G.nodes) {
      el('rect', {
        class: 'mm-n', x: ((n.x - n.w / 2 - G.mm.ox) * s).toFixed(1), y: ((n.y - n.h / 2 - G.mm.oy) * s).toFixed(1),
        width: Math.max(1.5, n.w * s).toFixed(1), height: Math.max(1.5, n.h * s).toFixed(1), rx: 1, style: `fill:${colour(n.group)}`,
      }, mini);
    }
    G.mmView = el('rect', { class: 'mm-v', rx: 2 }, mini);
    drawMiniView();
  }
  function drawMiniView() {
    if (!G || !G.mm || !G.mmView) return;
    const r = svg.getBoundingClientRect(), m = G.mm;
    G.mmView.setAttribute('x', ((-T.x / T.k - m.ox) * m.s).toFixed(1));
    G.mmView.setAttribute('y', ((-T.y / T.k - m.oy) * m.s).toFixed(1));
    G.mmView.setAttribute('width', Math.max(2, (r.width / T.k) * m.s).toFixed(1));
    G.mmView.setAttribute('height', Math.max(2, (r.height / T.k) * m.s).toFixed(1));
  }
  function miniJump(ev) {
    if (!G.mm) return;
    const mr = mini.getBoundingClientRect(), r = svg.getBoundingClientRect();
    const mx = ((ev.clientX - mr.left) / mr.width) * 200, my = ((ev.clientY - mr.top) / mr.height) * 130;
    const wx = mx / G.mm.s + G.mm.ox, wy = my / G.mm.s + G.mm.oy;
    T = { k: T.k, x: r.width / 2 - wx * T.k, y: r.height / 2 - wy * T.k };
    applyT();
  }
  let miniDrag = false;
  mini.addEventListener('pointerdown', (ev) => { miniDrag = true; mini.setPointerCapture(ev.pointerId); miniJump(ev); });
  mini.addEventListener('pointermove', (ev) => { if (miniDrag) miniJump(ev); });
  mini.addEventListener('pointerup', () => { miniDrag = false; });

  // --------------------------------------------------------------- highlight
  function applyHighlight() {
    for (const n of G.nodes) n.el.classList.remove('sel', 'dn', 'up', 'dim', 'onpath');
    for (const e of G.edges) {
      e.el.classList.remove('on', 'dn', 'up', 'dim');
      e.el.setAttribute('marker-end', `url(#${e.cyc ? 'ah-cyc' : 'ah'})`);
    }
    const lift = [];
    if (state.path) {
      const ids = new Set(state.path), pairs = new Set();
      for (let i = 0; i < state.path.length - 1; i++) {
        pairs.add(state.path[i] + '\u0000' + state.path[i + 1]);
        pairs.add(state.path[i + 1] + '\u0000' + state.path[i]);
      }
      for (const n of G.nodes) n.el.classList.add(ids.has(n.id) ? 'onpath' : 'dim');
      for (const e of G.edges) {
        if (pairs.has(e.s + '\u0000' + e.t)) { e.el.classList.add('on', 'up'); e.el.setAttribute('marker-end', 'url(#ah-up)'); lift.push(e.el); }
        else e.el.classList.add('dim');
      }
    } else {
      const s = state.selected && G.byId.get(state.selected);
      if (s) {
        const dn = state.mode !== 'up' ? reach(s.id, 'down', state.depth) : new Map();
        const up = state.mode !== 'down' ? reach(s.id, 'up', state.depth) : new Map();
        for (const n of G.nodes) n.el.classList.add(n === s ? 'sel' : dn.has(n.id) ? 'dn' : up.has(n.id) ? 'up' : 'dim');
        for (const e of G.edges) {
          const isDn = dn.has(e.s) && (e.t === s.id || dn.has(e.t));
          const isUp = up.has(e.t) && (e.s === s.id || up.has(e.s));
          if (isDn) { e.el.classList.add('on', 'dn'); e.el.setAttribute('marker-end', 'url(#ah-dn)'); lift.push(e.el); }
          else if (isUp) { e.el.classList.add('on', 'up'); e.el.setAttribute('marker-end', 'url(#ah-up)'); lift.push(e.el); }
          else e.el.classList.add('dim');
        }
      }
    }
    for (const p of lift) gEdges.appendChild(p); // draw highlighted edges on top
  }

  // ------------------------------------------------------------ detail panel
  function nodeButton(id, extra) {
    const n = G.byId.get(id);
    const b = h('button');
    b.type = 'button';
    const sw = h('span', 'sw'); sw.style.background = colour(n ? n.group : '');
    sw.style.cssText += ';width:8px;height:8px;border-radius:2px;flex:none;align-self:center';
    b.append(sw, h('span', 'nm', n ? (n.kind === 'file' ? n.id : n.label) : id));
    if (extra) b.append(h('small', null, extra));
    b.title = id;
    b.addEventListener('click', () => { const m = G.byId.get(id); if (m) { select(id); focusOn(m); } });
    return b;
  }
  function list(ids, extraFn, limit) {
    const ul = h('ul', 'ilist');
    ids.slice(0, limit || 12).forEach((id) => { const li = h('li'); li.append(nodeButton(id, extraFn ? extraFn(id) : null)); ul.append(li); });
    if (ids.length > (limit || 12)) ul.append(h('li', 'more', `+ ${ids.length - (limit || 12)} more`));
    return ul;
  }
  function role(n) {
    const maxIn = Math.max(1, ...G.nodes.map((m) => m.fan_in)), maxOut = Math.max(1, ...G.nodes.map((m) => m.fan_out));
    const hiIn = n.fan_in >= Math.max(2, 0.4 * maxIn), hiOut = n.fan_out >= Math.max(2, 0.4 * maxOut);
    if (hiIn && hiOut) return ['Hub. Many parts use it and it pulls in many. This is the riskiest kind of place to change; consider splitting it.', true];
    if (hiIn) return ['Stable core. Many parts rely on it and it depends on little. Keep its interface stable and change it with tests.', false];
    if (hiOut) return ['Orchestrator. It wires many modules together, so changes below it tend to break it.', false];
    if (!n.fan_in && !n.fan_out) return ['Standalone in this view.', false];
    return ['Leaf. Few links either way, so it is relatively safe to change.', false];
  }
  function showDetail(n) {
    detail.textContent = '';
    const top = h('div', 'd-top');
    const eb = h('div', 'eyebrow');
    const sw = h('span', 'sw'); sw.style.cssText = `width:8px;height:8px;border-radius:2px;background:${colour(n.group)}`;
    eb.append(sw, document.createTextNode(n.kind === 'file' ? `File · ${n.group}` : 'Folder'));
    const x = h('button', 'x', '×'); x.type = 'button'; x.title = 'Close (Esc)'; x.setAttribute('aria-label', 'Close');
    x.addEventListener('click', () => select(null));
    top.append(eb, x);
    detail.append(top, h('h3', null, n.kind === 'file' ? n.id.split('/').pop() : n.id));
    if (n.kind === 'file') detail.append(h('code', 'path', n.id));

    const chips = h('div', 'dchips');
    const bits = [n.kind === 'file' ? n.lang : plural(n.files, 'file'), plural(n.lines, 'line'), `Layer ${n.layer}`];
    if (n.cyc >= 0) bits.push('in a cycle');
    if (n.pinned) bits.push('pinned');
    bits.forEach((t) => chips.append(h('span', null, t)));
    detail.append(chips);

    const allDn = reach(n.id, 'down', Infinity), allUp = reach(n.id, 'up', Infinity);
    const stats = h('div', 'dstats');
    const stat = (cls, v, label) => { const d = h('div', cls); d.append(h('b', null, fmt(v)), h('span', null, label)); stats.append(d); };
    stat('', n.fan_in, 'used by directly');
    stat('', n.fan_out, 'imports directly');
    stat('dn', allDn.size, 'blast radius (all levels)');
    stat('up', allUp.size, 'depends on (all levels)');
    detail.append(stats);

    const [text, warn] = role(n);
    detail.append(h('p', 'role' + (warn || n.cyc >= 0 ? ' warn' : ''), n.cyc >= 0 ? text + ' It is also in a dependency cycle, so it cannot be changed or tested apart from the others in it.' : text));

    if (allDn.size) {
      detail.append(h('h4', null, 'If this changes, these may break'));
      const byHop = new Map();
      for (const [id, d] of allDn) { if (!byHop.has(d)) byHop.set(d, []); byHop.get(d).push(id); }
      [...byHop.keys()].sort((a, b) => a - b).slice(0, 4).forEach((d) => {
        detail.append(h('div', 'ihead', d === 1 ? 'Directly' : `${d} steps away`));
        detail.append(list(byHop.get(d).sort(), null, 8));
      });
    }
    const direct = G.out.get(n.id).slice().sort((a, b) => b.w - a.w);
    if (direct.length) {
      detail.append(h('h4', null, 'It depends on'));
      detail.append(list(direct.map((e) => e.t), (id) => {
        const e = direct.find((q) => q.t === id); return n.kind === 'folder' ? plural(e.w, 'import') : null;
      }, 10));
    }
    if (n.kind === 'folder') {
      const inside = DATA.views.file.nodes.filter((f) => f.group === n.id).sort((a, b) => b.fan_in - a.fan_in || b.lines - a.lines);
      if (inside.length) {
        detail.append(h('h4', null, 'Most used files inside'));
        const ul = h('ul', 'ilist');
        inside.slice(0, 6).forEach((f) => { const li = h('li'); const b = h('button'); b.type = 'button';
          b.append(h('span', 'nm', f.id), h('small', null, f.fan_in ? `used by ${f.fan_in}` : plural(f.lines, 'line')));
          b.addEventListener('click', () => drill(n.id, f.id)); li.append(b); ul.append(li); });
        detail.append(ul);
      }
    }
    if (n.ext && n.ext.length) {
      detail.append(h('h4', null, 'External packages'));
      const c = h('div', 'dchips'); n.ext.forEach((p) => c.append(h('span', null, p))); detail.append(c);
    }
    const act = h('div', 'dactions');
    const btn = (label, fn) => { const b = h('button', null, label); b.type = 'button'; b.addEventListener('click', fn); act.append(b); };
    btn('Centre', () => centreOn(n));
    btn('Trace path to…', () => { state.tracing = true; toast('Now click the file or folder to trace a path to.'); });
    if (n.kind === 'folder') btn('Open its files', () => drill(n.id));
    if (n.pinned) btn('Unpin', () => { n.pinned = false; n.el.classList.remove('pinned'); if (state.layout === 'force') startForce(); showDetail(n); });
    btn('Copy path', () => copy(n.id, 'Path copied.'));
    detail.append(act);
    openDetail();
  }
  function showPath(res, from, to) {
    detail.textContent = '';
    const top = h('div', 'd-top');
    top.append(h('div', 'eyebrow', `Import path · ${plural(res.path.length - 1, 'step')}`));
    const x = h('button', 'x', '×'); x.type = 'button'; x.setAttribute('aria-label', 'Close'); x.addEventListener('click', () => select(null));
    top.append(x);
    detail.append(top);
    const name = (id) => (G.byId.get(id).kind === 'file' ? id.split('/').pop() : id);
    const sentence = {
      depends: `${name(from)} depends on ${name(to)} through this chain. Each step imports the next.`,
      'used-by': `${name(to)} depends on ${name(from)}: read the chain bottom-up. Each step imports the one above it.`,
      linked: `These two are connected, but not by a one-way chain of imports. The path mixes directions.`,
    }[res.kind];
    detail.append(h('p', 'role', sentence));
    const ul = h('ul', 'ilist pathlist');
    res.path.forEach((id) => { const li = h('li'); li.append(nodeButton(id)); ul.append(li); });
    detail.append(ul);
    openDetail();
  }
  function openDetail() { detail.classList.add('open'); stage.classList.add('has-detail'); }
  function closeDetail() { detail.classList.remove('open'); stage.classList.remove('has-detail'); }

  // ----------------------------------------------------------------- actions
  function select(id) {
    state.selected = id; state.path = null; state.tracing = false;
    applyHighlight();
    const n = id && G.byId.get(id);
    if (n) showDetail(n); else closeDetail();
    writeHash();
  }
  function trace(fromId, toId) {
    state.tracing = false;
    const res = shortestPath(fromId, toId);
    if (!res) { toast('No import path connects these two in this view.'); return; }
    state.path = res.path; state.selected = fromId; state.traceTo = toId;
    applyHighlight();
    writeHash();
    showPath(res, fromId, toId);
    fit(res.path.map((id) => G.byId.get(id)), true);
  }
  function drill(folder, focus) {
    state.view = 'file'; state.scope = folder; state.selected = focus || null; state.path = null;
    rebuild();
    if (focus && G.byId.get(focus)) { select(focus); focusOn(G.byId.get(focus)); }
  }
  let lastClick = { id: null, t: 0 };
  function onNodeClick(n, shift) {
    const now = performance.now();
    const dbl = lastClick.id === n.id && now - lastClick.t < 320;
    lastClick = { id: n.id, t: now };
    if (dbl) {
      if (n.kind === 'folder') drill(n.id); else centreOn(n);
      return;
    }
    if ((state.tracing || shift) && state.selected && state.selected !== n.id) { trace(state.selected, n.id); return; }
    select(n.id);
  }

  function copy(text, msg) {
    const done = () => toast(msg);
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, () => fallback());
    else fallback();
    function fallback() {
      const ta = document.createElement('textarea'); ta.value = text; document.body.append(ta); ta.select();
      try { document.execCommand('copy'); done(); } catch (_) { toast('Copy failed. The link is in the address bar.'); }
      ta.remove();
    }
  }

  function exportSvg() {
    const bb = vp.getBBox(), pad = 40;
    const clone = svg.cloneNode(true);
    clone.removeAttribute('class');
    clone.setAttribute('xmlns', NS);
    clone.querySelector('#vp').removeAttribute('transform');
    const vx = bb.x - pad, vy = bb.y - pad, vw = bb.width + pad * 2, vh = bb.height + pad * 2;
    clone.setAttribute('viewBox', `${vx} ${vy} ${vw} ${vh}`);
    clone.setAttribute('width', Math.round(vw)); clone.setAttribute('height', Math.round(vh));
    clone.style.width = ''; clone.style.height = '';
    const cs = getComputedStyle(document.documentElement);
    const names = ['--bg', '--bg2', '--surface', '--surface2', '--border', '--fg', '--muted', '--accent', '--bad', '--good']
      .concat([1, 2, 3, 4, 5, 6, 7, 8].map((i) => `--series-${i}`));
    const vars = names.map((v) => `${v}:${cs.getPropertyValue(v).trim()}`).join(';');
    const style = document.createElementNS(NS, 'style');
    style.textContent = `#flow-svg{${vars}}` + document.getElementById('flow-css').textContent;
    const bg = document.createElementNS(NS, 'rect');
    for (const [k, v] of Object.entries({ x: vx, y: vy, width: vw, height: vh, style: 'fill:var(--bg)' })) bg.setAttribute(k, v);
    clone.insertBefore(bg, clone.firstChild);
    clone.insertBefore(style, clone.firstChild);
    const blob = new Blob([new XMLSerializer().serializeToString(clone)], { type: 'image/svg+xml' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${DATA.name}-${state.view}${state.scope ? '-' + state.scope : ''}-flow.svg`.replace(/[^\w.-]+/g, '_');
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    toast('Exported what you see as SVG.');
  }

  // ------------------------------------------------------------------ hash
  function writeHash() {
    const p = new URLSearchParams();
    p.set('view', state.view);
    if (state.scope) p.set('scope', state.scope);
    if (state.layout !== 'layered') p.set('layout', state.layout);
    if (state.selected) p.set('focus', state.selected);
    if (state.path && state.traceTo) p.set('trace', state.traceTo);
    if (state.mode !== 'down') p.set('mode', state.mode);
    if (state.depth !== Infinity) p.set('depth', String(state.depth));
    try { history.replaceState(null, '', '#' + p.toString()); } catch (_) { /* file:// in some browsers */ }
  }
  function readHash() {
    const p = new URLSearchParams(location.hash.slice(1));
    const v = p.get('view');
    if (v === 'file' || (v === 'folder' && DATA.folderUsable)) state.view = v;
    if (p.get('scope')) state.scope = p.get('scope');
    if (p.get('layout') === 'force') state.layout = 'force';
    if (['down', 'up', 'both'].includes(p.get('mode'))) state.mode = p.get('mode');
    const d = parseInt(p.get('depth'), 10);
    if (d > 0) state.depth = d;
    return { focus: p.get('focus'), trace: p.get('trace') };
  }

  // --------------------------------------------------------------- sidebar
  function syncControls() {
    const val = { view: state.view, layout: state.layout, mode: state.mode, depth: state.depth === Infinity ? 'all' : String(state.depth) };
    document.querySelectorAll('.seg').forEach((s) => {
      s.querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.dataset.v === val[s.dataset.ctl]));
    });
    const fb = document.querySelector('.seg[data-ctl=view] button[data-v=folder]');
    fb.disabled = !DATA.folderUsable;
    if (!DATA.folderUsable) fb.title = 'Top-level folders do not import each other, so there is no folder flow.';
  }
  function renderSidebar() {
    syncControls();
    const v = DATA.views[state.view];
    const bits = [plural(G.nodes.length, state.view === 'file' ? 'file' : 'folder'), plural(G.edges.length, 'link')];
    const layers = new Set(G.nodes.map((n) => n.layer)).size;
    bits.push(plural(layers, 'layer'));
    let dek = bits.join(' · ') + '.';
    if (state.view === 'file' && v.standalone) dek += ` ${plural(v.standalone, 'file')} with no in-repo imports are not drawn.`;
    if (state.view === 'file' && v.omitted) dek += ` ${fmt(v.omitted)} smaller linked files are left out to keep it fast.`;
    $('#count').textContent = dek;

    const crumb = $('#crumb'); crumb.textContent = '';
    if (state.scope) {
      const back = h('button', null, 'All files'); back.type = 'button';
      back.addEventListener('click', () => { state.scope = null; state.selected = null; rebuild(); });
      crumb.append(back, document.createTextNode(' › '), h('code', null, state.scope),
        h('div', null, 'Dashed boxes are outside this folder but linked to it.'));
    }

    const ins = $('#insights'); ins.textContent = '';
    const hubs = G.nodes.filter((n) => n.fan_in > 0).sort((a, b) => b.fan_in - a.fan_in || b.lines - a.lines).slice(0, 5);
    if (hubs.length) { ins.append(h('div', 'ihead', 'Most depended on')); ins.append(list(hubs.map((n) => n.id), (id) => `used by ${G.byId.get(id).fan_in}`)); }
    const entries = DATA.entry.filter((id) => G.byId.has(id));
    if (entries.length) { ins.append(h('div', 'ihead', 'Entry points')); ins.append(list(entries, null, 5)); }
    const cycles = v.cycles.filter((c) => c.some((id) => G.byId.has(id)));
    if (cycles.length) {
      ins.append(h('div', 'ihead', `Cycles (${cycles.length})`));
      ins.append(list(cycles.map((c) => c.find((id) => G.byId.has(id))), (id) => {
        const c = cycles.find((q) => q.includes(id)); return `${c.length} in loop`;
      }, 5));
    }
    if (!ins.childNodes.length) ins.append(h('div', 'ihead', 'No imports between these nodes.'));

    const gwrap = $('#groups'); gwrap.textContent = '';
    const counts = new Map();
    for (const n of DATA.views[state.view].nodes) counts.set(n.group, (counts.get(n.group) || 0) + 1);
    [...counts.keys()].sort((a, b) => GROUP_INDEX.get(a) - GROUP_INDEX.get(b)).forEach((g) => {
      const c = h('button', 'chip' + (state.hidden.has(g) ? ' off' : '')); c.type = 'button';
      const sw = h('span', 'sw'); sw.style.background = colour(g);
      c.append(sw, h('span', null, g), h('small', null, String(counts.get(g))));
      c.title = state.hidden.has(g) ? 'Show this folder' : 'Hide this folder';
      c.addEventListener('click', () => { if (state.hidden.has(g)) state.hidden.delete(g); else state.hidden.add(g); rebuild(); });
      gwrap.append(c);
    });
  }

  function rebuild(animateFit) {
    stopSim();
    buildGraph();
    layeredLayout();
    if (state.selected && !G.byId.has(state.selected)) state.selected = null;
    state.path = null;
    render();
    if (state.layout === 'force') startForce();
    renderSidebar();
    if (state.selected) showDetail(G.byId.get(state.selected)); else closeDetail();
    fit(G.nodes, animateFit);
    if (state.layout === 'force' && !RM) setTimeout(() => { if (!state.selected && !state.path) fit(G.nodes, true); }, 1400);
    writeHash();
  }

  document.querySelectorAll('.seg').forEach((s) => s.addEventListener('click', (ev) => {
    const b = ev.target.closest('button'); if (!b || b.disabled) return;
    const v = b.dataset.v, ctl = s.dataset.ctl;
    if (ctl === 'view') { if (v === state.view && !state.scope) return; state.view = v; state.scope = null; state.selected = null; rebuild(true); }
    else if (ctl === 'layout') { if (v === state.layout) return; state.layout = v; const keep = state.selected; rebuild(true); if (keep && G.byId.has(keep)) select(keep); }
    else if (ctl === 'mode') { state.mode = v; syncControls(); applyHighlight(); writeHash(); }
    else if (ctl === 'depth') { state.depth = v === 'all' ? Infinity : parseInt(v, 10); syncControls(); applyHighlight(); writeHash(); }
  }));
  $('#show-all').addEventListener('click', () => { state.hidden.clear(); rebuild(true); });

  // Search
  const q = $('#q'), results = $('#results');
  let hits = [], cursor = 0;
  function runSearch() {
    const s = q.value.trim().toLowerCase();
    results.textContent = '';
    hits = [];
    if (!s) return;
    const score = (n) => { const id = n.id.toLowerCase(), base = n.label.toLowerCase();
      return base === s ? 0 : base.startsWith(s) ? 1 : base.includes(s) ? 2 : id.includes(s) ? 3 : 9; };
    hits = G.nodes.map((n) => [score(n), n]).filter(([sc]) => sc < 9)
      .sort((a, b) => a[0] - b[0] || b[1].fan_in - a[1].fan_in).slice(0, 8).map(([, n]) => n);
    cursor = 0;
    if (!hits.length) { results.append(h('li', 'more', 'No match in this view.')); return; }
    hits.forEach((n, i) => {
      const li = h('li'); const b = h('button', i === cursor ? 'kb' : null); b.type = 'button';
      b.append(h('span', 'nm', n.kind === 'file' ? n.id : n.label), h('small', null, n.fan_in ? `used by ${n.fan_in}` : plural(n.lines, 'line')));
      b.addEventListener('click', () => pick(n)); li.append(b); results.append(li);
    });
  }
  function pick(n) { select(n.id); focusOn(n); q.blur(); }
  q.addEventListener('input', runSearch);
  q.addEventListener('keydown', (ev) => {
    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      ev.preventDefault(); if (!hits.length) return;
      cursor = (cursor + (ev.key === 'ArrowDown' ? 1 : hits.length - 1)) % hits.length;
      results.querySelectorAll('button').forEach((b, i) => b.classList.toggle('kb', i === cursor));
    } else if (ev.key === 'Enter' && hits[cursor]) pick(hits[cursor]);
    else if (ev.key === 'Escape') { q.value = ''; runSearch(); q.blur(); }
  });

  // Toolbar
  document.querySelector('.toolbar').addEventListener('click', (ev) => {
    const b = ev.target.closest('button'); if (!b) return;
    const a = b.dataset.act;
    if (a === 'in') zoomBy(1.25); else if (a === 'out') zoomBy(0.8);
    else if (a === 'fit') fit(G.nodes, true);
    else if (a === 'reset') { const keep = state.selected; rebuild(true); if (keep && G.byId.has(keep)) select(keep); }
    else if (a === 'export') exportSvg();
    else if (a === 'link') { writeHash(); copy(location.href, 'Link to this view copied.'); }
  });

  // ------------------------------------------------------ pointer and keys
  let drag = null;
  svg.addEventListener('pointerdown', (ev) => {
    if (ev.button !== 0) return;
    const g = ev.target.closest('.node');
    drag = { id: ev.pointerId, node: g ? G.byId.get(g.dataset.id) : null, lx: ev.clientX, ly: ev.clientY, moved: 0, shift: ev.shiftKey };
    svg.setPointerCapture(ev.pointerId);
    if (!drag.node) svg.classList.add('panning');
  });
  svg.addEventListener('pointermove', (ev) => {
    if (!drag || ev.pointerId !== drag.id) { hover(ev); return; }
    const dx = ev.clientX - drag.lx, dy = ev.clientY - drag.ly;
    drag.lx = ev.clientX; drag.ly = ev.clientY;
    drag.moved += Math.abs(dx) + Math.abs(dy);
    if (drag.moved <= 3) return;
    hideTip();
    if (drag.node) {
      drag.node.x += dx / T.k; drag.node.y += dy / T.k;
      drag.node.pinned = true; drag.node.el.classList.add('pinned');
      if (!simHandle) updatePositions();
    } else { T.x += dx; T.y += dy; applyT(); }
  });
  function endDrag(ev) {
    if (!drag || ev.pointerId !== drag.id) return;
    const d = drag; drag = null;
    svg.classList.remove('panning');
    if (d.moved <= 3) { if (d.node) onNodeClick(d.node, d.shift); else if (!state.tracing) select(null); }
    else if (d.node) drawMinimap();
  }
  svg.addEventListener('pointerup', endDrag);
  svg.addEventListener('pointercancel', endDrag);
  svg.addEventListener('wheel', (ev) => {
    ev.preventDefault();
    const r = svg.getBoundingClientRect();
    if (ev.ctrlKey || Math.abs(ev.deltaY) >= Math.abs(ev.deltaX)) zoomBy(Math.exp(-ev.deltaY * (ev.ctrlKey ? 0.01 : 0.0016)), ev.clientX - r.left, ev.clientY - r.top);
    else { T.x -= ev.deltaX; applyT(); }
  }, { passive: false });

  let hoverId = null;
  function hover(ev) {
    const g = ev.target.closest && ev.target.closest('.node');
    const id = g ? g.dataset.id : null;
    if (id !== hoverId) {
      if (hoverId && G.byId.get(hoverId)) for (const e of G.out.get(hoverId).concat(G.inc.get(hoverId))) e.el.classList.remove('hl');
      hoverId = id;
      if (id) for (const e of G.out.get(id).concat(G.inc.get(id))) e.el.classList.add('hl');
    }
    if (!id) { hideTip(); return; }
    const n = G.byId.get(id), r = stage.getBoundingClientRect();
    tip.textContent = '';
    tip.append(h('b', null, n.id));
    tip.append(h('span', null, `${n.kind === 'file' ? n.lang + ' · ' : plural(n.files, 'file') + ' · '}${plural(n.lines, 'line')} · used by ${n.fan_in} · imports ${n.fan_out}`));
    tip.hidden = false;
    const x = Math.min(ev.clientX - r.left + 14, r.width - tip.offsetWidth - 10);
    const y = Math.min(ev.clientY - r.top + 16, r.height - tip.offsetHeight - 10);
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
  }
  function hideTip() { tip.hidden = true; }
  svg.addEventListener('pointerleave', () => { hideTip(); });

  gNodes.addEventListener('keydown', (ev) => {
    const g = ev.target.closest('.node');
    if (g && (ev.key === 'Enter' || ev.key === ' ')) { ev.preventDefault(); onNodeClick(G.byId.get(g.dataset.id), ev.shiftKey); }
  });
  document.addEventListener('keydown', (ev) => {
    if (ev.target.matches('input, textarea')) return;
    if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
    const k = ev.key;
    if (k === '/') { ev.preventDefault(); q.focus(); q.select(); }
    else if (k === 'f' || k === 'F') fit(G.nodes, true);
    else if (k === 'l' || k === 'L') { state.layout = state.layout === 'layered' ? 'force' : 'layered'; const keep = state.selected; rebuild(true); if (keep && G.byId.has(keep)) select(keep); }
    else if (k === '1' && DATA.folderUsable) { state.view = 'folder'; state.scope = null; state.selected = null; rebuild(true); }
    else if (k === '2') { state.view = 'file'; state.scope = null; state.selected = null; rebuild(true); }
    else if (k === '+' || k === '=') zoomBy(1.25);
    else if (k === '-') zoomBy(0.8);
    else if (k === 'Escape') { if (state.path || state.tracing) { state.tracing = false; select(state.selected); } else select(null); }
  });
  window.addEventListener('resize', () => drawMiniView());

  // -------------------------------------------------------------------- go
  const start = readHash();
  rebuild(false);
  if (start.focus && G.byId.has(start.focus)) {
    select(start.focus);
    if (start.trace && G.byId.has(start.trace)) trace(start.focus, start.trace);
    else focusOn(G.byId.get(start.focus));
  }
})();
