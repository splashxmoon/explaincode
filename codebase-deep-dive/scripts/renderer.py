"""Render a codebase map (from mapper.map_codebase) as one standalone HTML page.

No network, no CDN: the page is inline SVG, CSS and text, so it opens offline
and can be shared as a single file. Colours come from the --series-N theme
variables, which the page defines itself.

Views, from high level to detail:
  1. Architecture: folders in dependency layers, with cycles flagged.
  2. Change-risk quadrant: each file by what it depends on vs what depends on it.
  3. Folder treemap: size by lines, with subfolders inside.
  4. Hotspots and an explainer written from the same numbers.
"""
import html
import math

W, H = 960, 420


def esc(s):
    return html.escape(str(s), quote=True)


def fmt(n):
    return f"{n:,}"


def pct(part, whole):
    return f"{100 * part / whole:.1f}%" if whole else "0%"


def series(i):
    return f"var(--series-{i % 8 + 1}, #8ea9c1)"


def top_key(path):
    parts = path.split("/")
    return parts[0] if len(parts) > 1 else "(root)"


def group_key(path):
    """Return (top-level group, child tile) for a file path."""
    parts = path.split("/")
    if len(parts) == 1:
        return "(root)", path
    if len(parts) == 2:
        return parts[0], "(files)"
    return parts[0], parts[1]


def build_groups(files):
    groups = {}
    for f in files:
        top, child = group_key(f["path"])
        bucket = groups.setdefault(top, {})
        bucket[child] = bucket.get(child, 0) + max(f["lines"], 1)
    return groups


def edge_weights(files):
    weights = {}
    for f in files:
        a = top_key(f["path"])
        for target in f["imports"]:
            b = top_key(target)
            if a == b:
                continue
            key = tuple(sorted((a, b)))
            weights[key] = weights.get(key, 0) + 1
    return weights


def msg(text):
    return f'<p class="muted">{esc(text)}</p>'


# ---------------------------------------------------------------- architecture


ARCH_BOX_W, ARCH_BOX_H = 200, 64
ARCH_COL_GAP, ARCH_ROW_GAP = 36, 120
ARCH_LEFT, ARCH_TOP = 150, 58


def _order_rows(rows, arch):
    """Order each row by the average position of what its folders depend on.

    rows[0] is the foundation row (depends on nothing); each later row sits
    one layer higher. Ordering from the bottom up keeps edges from crossing
    more than they must.
    """
    edges = arch["edges"]
    rank = {}
    for r, members in enumerate(rows):
        if r == 0:
            members.sort(key=lambda n: n["name"])
        else:
            def barycentre(node):
                deps = [e["to"] for e in edges if e["from"] == node["name"] and e["to"] in rank]
                if not deps:
                    return len(rows[0]) + 1
                return sum(rank[d] for d in deps) / len(deps)
            members.sort(key=barycentre)
        for i, node in enumerate(members):
            rank[node["name"]] = i
    return rows


def architecture_svg(arch):
    """Layered diagram: each row is a dependency layer, arrows point at dependencies."""
    nodes = arch["nodes"]
    if len(nodes) < 2:
        return msg("Only one top-level folder, so there is no architecture to draw.")
    if not arch["edges"]:
        return msg("No imports between the files or folders in view, so nothing depends on anything else.")

    rows = [list(layer["folders"]) for layer in arch["layers"]]
    rows = _order_rows(rows, arch)
    widest = max(len(r) for r in rows)
    span = widest * (ARCH_BOX_W + ARCH_COL_GAP) - ARCH_COL_GAP
    width = ARCH_LEFT + span + 40
    height = ARCH_TOP + len(rows) * ARCH_ROW_GAP + 62

    pos = {}
    for r, members in enumerate(rows):
        row_w = len(members) * ARCH_BOX_W + (len(members) - 1) * ARCH_COL_GAP
        start = ARCH_LEFT + (span - row_w) / 2
        y = ARCH_TOP + (len(rows) - 1 - r) * ARCH_ROW_GAP  # highest layer drawn at the top
        for i, node in enumerate(members):
            x = start + i * (ARCH_BOX_W + ARCH_COL_GAP)
            pos[node["name"]] = (x, y, r)

    cycle_of = {}
    for ci, comp in enumerate(arch["cycles"]):
        for v in comp:
            cycle_of[v] = ci

    max_w = max(e["weight"] for e in arch["edges"])
    out = [
        f'<svg viewBox="0 0 {width:.0f} {height:.0f}" role="img" aria-label="Layered dependency flow">',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="var(--muted, #98a2ad)"/></marker></defs>',
    ]

    # Layer bands and labels, drawn first so they sit behind everything.
    for r, members in enumerate(rows):
        y = ARCH_TOP + (len(rows) - 1 - r) * ARCH_ROW_GAP
        out.append(
            f'<rect x="10" y="{y - 14:.1f}" width="{width - 20:.0f}" height="{ARCH_BOX_H + 28}" rx="10" '
            f'fill="var(--series-{r % 8 + 1}, #8ea9c1)" fill-opacity="0.06"/>'
        )
        label = f"Layer {r}"
        note = "foundation" if r == 0 else ("consumers" if r == len(rows) - 1 else "")
        out.append(
            f'<text x="24" y="{y + 20:.1f}" fill="var(--fg, #e4e8ec)" font-size="13" font-weight="700">{label}</text>'
            f'<text x="24" y="{y + 38:.1f}" fill="var(--muted, #98a2ad)" font-size="11">{esc(note)}</text>'
        )

    # Edges: consumer (upper box, bottom edge) to dependency (lower box, top edge).
    for e in sorted(arch["edges"], key=lambda e: e["weight"]):
        a, b, w = e["from"], e["to"], e["weight"]
        ax, ay, ar = pos[a]
        bx, by, br = pos[b]
        stroke_w = 1.2 + 4.8 * w / max_w
        in_cycle = a in cycle_of and cycle_of.get(a) == cycle_of.get(b)
        colour = "var(--bad, #c08072)" if in_cycle else "var(--muted, #98a2ad)"
        opacity = 0.9 if in_cycle else 0.5
        title = f"{esc(a)} depends on {esc(b)}: {w} import{'s' if w != 1 else ''}"
        if ar == br:  # same layer only happens inside a cycle: arc out to the right
            x1, y1 = ax + ARCH_BOX_W, ay + ARCH_BOX_H / 2
            x2, y2 = bx + ARCH_BOX_W, by + ARCH_BOX_H / 2
            bulge = 70 + 20 * (abs(x1 - x2) / ARCH_BOX_W)
            d = f"M{x1:.1f},{y1:.1f} C{x1 + bulge:.1f},{y1:.1f} {x2 + bulge:.1f},{y2:.1f} {x2:.1f},{y2:.1f}"
        else:
            x1, y1 = ax + ARCH_BOX_W / 2, ay + ARCH_BOX_H
            x2, y2 = bx + ARCH_BOX_W / 2, by
            gap = (y1 - y2) * 0.5
            d = f"M{x1:.1f},{y1:.1f} C{x1:.1f},{y1 + gap:.1f} {x2:.1f},{y2 - gap:.1f} {x2:.1f},{y2:.1f}"
        out.append(
            f'<path d="{d}" fill="none" stroke="{colour}" stroke-opacity="{opacity}" '
            f'stroke-width="{stroke_w:.1f}" marker-end="url(#arrow)"><title>{title}</title></path>'
        )

    # Boxes.
    for node in nodes:
        name = node["name"]
        x, y, r = pos[name]
        border = "var(--bad, #c08072)" if name in cycle_of else series(r)
        dash = ' stroke-dasharray="5 4"' if name in cycle_of else ""
        if "/" in name:  # a file: title is the file name, the folder goes underneath
            head, _, tail = name.rpartition("/")
            short = tail if len(tail) <= 26 else tail[:25] + "…"
            sub = f"{head}/ · {fmt(node['lines'])} lines"
        else:
            short = name if len(name) <= 24 else name[:23] + "…"
            sub = f"{node['files']} files · {fmt(node['lines'])} lines"
        sub = sub if len(sub) <= 34 else sub[:33] + "…"
        out.append(
            f'<g><title>{esc(name)}: {node["files"]} files, {fmt(node["lines"])} lines</title>'
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{ARCH_BOX_W}" height="{ARCH_BOX_H}" rx="10" '
            f'fill="var(--surface, #1b2128)" stroke="{border}" stroke-width="2"{dash}/>'
            f'<rect x="{x:.1f}" y="{y:.1f}" width="5" height="{ARCH_BOX_H}" rx="2" fill="{series(r)}"/>'
            f'<text x="{x + 16:.1f}" y="{y + 27:.1f}" fill="var(--fg, #e4e8ec)" font-size="14" '
            f'font-weight="700">{esc(short)}</text>'
            f'<text x="{x + 16:.1f}" y="{y + 46:.1f}" fill="var(--muted, #98a2ad)" font-size="11.5">'
            f'{esc(sub)}</text></g>'
        )
    ly = height - 22
    out.append(
        f'<line x1="24" y1="{ly - 4:.0f}" x2="64" y2="{ly - 4:.0f}" stroke="var(--muted, #98a2ad)" stroke-width="2" marker-end="url(#arrow)"/>'
        f'<text x="72" y="{ly:.0f}" fill="var(--muted, #98a2ad)" font-size="11">points from a folder to the folder it depends on; read top to bottom, foundations at the bottom</text>'
        f'<line x1="24" y1="{ly + 14:.0f}" x2="64" y2="{ly + 14:.0f}" stroke="var(--bad, #c08072)" stroke-width="2" stroke-dasharray="5 4"/>'
        f'<text x="72" y="{ly + 18:.0f}" fill="var(--muted, #98a2ad)" font-size="11">dashed red: folders in a dependency cycle, to be treated as one unit</text>'
    )
    out.append("</svg>")
    return "".join(out)


# ------------------------------------------------------------- risk quadrant


def risk_quadrant_svg(files, groups_ordered):
    pts = [f for f in files if f["fan_in"] or f["fan_out"]]
    if not pts:
        return msg("No file-level imports were found, so there is no change-risk map.")
    top_index = {name: i for i, (name, _) in enumerate(groups_ordered)}
    W2, H2 = 720, 500
    L, B, T, R = 64, 84, 72, 24
    pw, ph = W2 - L - R, H2 - T - B
    max_x = max(f["fan_out"] for f in pts) or 1
    max_y = max(f["fan_in"] for f in pts) or 1
    max_lines = max(f["lines"] for f in pts) or 1
    mid_x, mid_y = max_x / 2, max_y / 2

    def sx(v):
        return L + pw * (v / (max_x * 1.08))

    def sy(v):
        return T + ph - ph * (v / (max_y * 1.08))

    out = [f'<svg viewBox="0 0 {W2} {H2}" role="img" aria-label="Change-risk quadrant of files">']
    out.append(
        f'<rect x="{L}" y="{T}" width="{pw}" height="{ph}" rx="8" fill="var(--bg, #11151a)" '
        'stroke="var(--border, #2e3742)"/>'
    )
    out.append(
        f'<line x1="{sx(mid_x):.1f}" y1="{T}" x2="{sx(mid_x):.1f}" y2="{T + ph}" '
        'stroke="var(--border, #2e3742)" stroke-dasharray="4 4"/>'
        f'<line x1="{L}" y1="{sy(mid_y):.1f}" x2="{L + pw}" y2="{sy(mid_y):.1f}" '
        'stroke="var(--border, #2e3742)" stroke-dasharray="4 4"/>'
    )
    # Captions sit outside the plot so they never cover a bubble.
    quad = [
        (L, T - 40, "STABLE CORE", "many depend on it, it depends on little: change with care"),
        (L + pw, T - 40, "HUB", "many in and many out: highest risk"),
        (L, T + ph + 20, "LEAF", "few dependencies either way: safe to change"),
        (L + pw, T + ph + 20, "ORCHESTRATOR", "pulls many modules together: fragile to refactor"),
    ]
    for x, y, title, sub in quad:
        anchor = "end" if x > L + pw / 2 else "start"
        out.append(
            f'<text x="{x}" y="{y}" text-anchor="{anchor}" fill="var(--muted, #98a2ad)" '
            f'font-size="11" font-weight="700" letter-spacing="0.06em">{title}</text>'
            f'<text x="{x}" y="{y + 14}" text-anchor="{anchor}" fill="var(--muted, #98a2ad)" '
            f'font-size="10.5" opacity="0.8">{esc(sub)}</text>'
        )
    out.append(
        f'<text x="{L + pw / 2:.0f}" y="{H2 - 14}" text-anchor="middle" fill="var(--muted, #98a2ad)" '
        'font-size="12">files this file depends on  →</text>'
        f'<text x="18" y="{T + ph / 2:.0f}" text-anchor="middle" fill="var(--muted, #98a2ad)" font-size="12" '
        f'transform="rotate(-90 18 {T + ph / 2:.0f})">files that depend on this  →</text>'
    )
    # Bubbles, largest first so small ones stay visible.
    labelled = 0
    for f in sorted(pts, key=lambda f: -f["lines"]):
        x, y = sx(f["fan_out"]), sy(f["fan_in"])
        r = 5 + 14 * math.sqrt(f["lines"] / max_lines)
        colour = series(top_index.get(top_key(f["path"]), 0))
        out.append(
            f'<g><title>{esc(f["path"])}: in {f["fan_in"]} · out {f["fan_out"]} · {fmt(f["lines"])} lines</title>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{colour}" fill-opacity="0.72" '
            'stroke="var(--bg, #11151a)" stroke-width="1.5"/>'
        )
        if labelled < 7 and (f["fan_in"] >= 2 or f["fan_out"] >= 3):
            name = f["path"].split("/")[-1]
            out.append(
                f'<text x="{x + r + 4:.1f}" y="{y + 4:.1f}" fill="var(--fg, #e4e8ec)" font-size="11">'
                f'{esc(name)}</text>'
            )
            labelled += 1
        out.append("</g>")
    out.append("</svg>")
    return "".join(out)


# ------------------------------------------------------------------ treemap


def treemap_svg(files):
    groups = build_groups(files)
    ordered = sorted(groups.items(), key=lambda kv: -sum(kv[1].values()))
    top_items = [(name, sum(children.values()), i) for i, (name, children) in enumerate(ordered)]
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Treemap of folders by lines">']
    for name, total, i, x, y, w, h in split_layout(top_items, 0, 0, W, H):
        children = sorted(groups[name].items(), key=lambda kv: -kv[1])
        child_items = [(c, v, i) for c, v in children]
        for label, value, idx, cx, cy, cw, ch in split_layout(child_items, x + 2, y + 2, max(w - 4, 0), max(h - 4, 0)):
            shown = f"{name} (files)" if label == "(files)" else label
            out.append(
                f'<g><title>{esc(name)}/{esc(label)}: {fmt(value)} lines</title>'
                f'<rect x="{cx:.1f}" y="{cy:.1f}" width="{max(cw - 2, 0):.1f}" '
                f'height="{max(ch - 2, 0):.1f}" rx="4" fill="{series(idx)}" fill-opacity="0.78"/>'
            )
            if cw > 90 and ch > 26:
                max_chars = max(int((cw - 12) / 7.2), 4)
                text = shown if len(shown) <= max_chars else shown[: max_chars - 1] + "…"
                out.append(
                    f'<text x="{cx + 8:.1f}" y="{cy + 18:.1f}" fill="var(--bg, #11151a)" font-size="12" '
                    f'font-weight="600">{esc(text)}</text>'
                )
            out.append("</g>")
    out.append("</svg>")
    return "".join(out), ordered


def split_layout(items, x, y, w, h, vertical=True):
    """Binary-split treemap. items: [(label, value, colour_index)], sorted desc."""
    if not items:
        return []
    if len(items) == 1:
        label, value, idx = items[0]
        return [(label, value, idx, x, y, w, h)]
    total = sum(v for _, v, _ in items)
    acc, k = 0, len(items) - 1
    for i, (_, v, _) in enumerate(items[:-1]):
        acc += v
        if acc >= total / 2:
            k = i + 1
            break
    left, right = items[:k], items[k:]
    frac = sum(v for _, v, _ in left) / total
    if vertical:
        wl = w * frac
        return split_layout(left, x, y, wl, h, False) + split_layout(right, x + wl, y, w - wl, h, False)
    hl = h * frac
    return split_layout(left, x, y, w, hl, True) + split_layout(right, x, y + hl, w, h - hl, True)


# ------------------------------------------------------------- text sections


def language_bar(data):
    t = data["totals"]["lines"] or 1
    segs, legend = [], []
    x = 0.0
    for i, lang in enumerate(data["languages"]):
        w = 100 * lang["lines"] / t
        segs.append(
            f'<rect x="{x:.2f}%" y="0" width="{w:.2f}%" height="100%" fill="{series(i)}">'
            f'<title>{esc(lang["name"])}: {fmt(lang["lines"])} lines</title></rect>'
        )
        legend.append(
            f'<li><span class="sw" style="background:{series(i)}"></span>'
            f'{esc(lang["name"])} <span class="muted">{pct(lang["lines"], t)} · {fmt(lang["files"])} files</span></li>'
        )
        x += w
    bar = f'<svg class="langbar" viewBox="0 0 100 10" preserveAspectRatio="none">{"".join(segs)}</svg>'
    return bar + f'<ul class="legend">{"".join(legend)}</ul>'


def hotspots(files):
    by_size = sorted(files, key=lambda f: -f["lines"])[:10]
    by_fan = sorted((f for f in files if f["fan_in"] > 0), key=lambda f: (-f["fan_in"], f["path"]))[:10]

    def rows(items, extra):
        if not items:
            return '<tr><td colspan="3" class="muted">None found.</td></tr>'
        return "".join(
            f'<tr><td><code>{esc(f["path"])}</code></td><td class="num">{extra(f)}</td>'
            f'<td class="num">{fmt(f["lines"])}</td></tr>'
            for f in items
        )

    big = (
        '<table><thead><tr><th>Largest files</th><th class="num">Lang</th><th class="num">Lines</th></tr></thead>'
        f'<tbody>{rows(by_size, lambda f: esc(f["lang"]))}</tbody></table>'
    )
    fan = (
        '<table><thead><tr><th>Most depended on</th><th class="num">Imported by</th><th class="num">Lines</th></tr></thead>'
        f'<tbody>{rows(by_fan, lambda f: f["fan_in"])}</tbody></table>'
    )
    return big + fan


def explain(data, groups_ordered, files):
    t = data["totals"]
    arch = data.get("architecture", {})
    langs = data["languages"]
    bullets = []
    if langs:
        top = langs[0]
        bullets.append(
            f"<b>{esc(data['name'])}</b> has {fmt(t['files'])} files and {fmt(t['lines'])} lines. "
            f"{esc(top['name'])} is the largest language at {pct(top['lines'], t['lines'])}."
        )
    if arch.get("layers"):
        depth = len(arch["layers"])
        bullets.append(
            f"Folders form {depth} dependency layer{'s' if depth != 1 else ''}, from foundations "
            f"(Layer 0) up to consumers (Layer {depth - 1}). Lower layers should not depend on higher ones."
        )
    if arch.get("cycles"):
        cyc = "; ".join(" ↔ ".join(f"<code>{esc(v)}</code>" for v in c) for c in arch["cycles"])
        bullets.append(f"<b>Circular dependencies:</b> {cyc}. These folders can't be understood or tested apart.")
    if groups_ordered:
        name, children = groups_ordered[0]
        total = sum(children.values())
        bullets.append(f"The biggest folder is <code>{esc(name)}</code> with {pct(total, t['lines'])} of all lines.")
    if files:
        hub = max(files, key=lambda f: (f["fan_in"], -f["lines"]))
        if hub["fan_in"] > 0:
            bullets.append(
                f"<code>{esc(hub['path'])}</code> is imported by {hub['fan_in']} files. "
                "A change there has the widest blast radius, so review it with extra care."
            )
    weights = edge_weights(files)
    if weights:
        (a, b), w = max(weights.items(), key=lambda kv: kv[1])
        bullets.append(f"The tightest coupling is between <code>{esc(a)}</code> and <code>{esc(b)}</code> ({w} imports).")
    if data["entry_points"]:
        eps = ", ".join(f"<code>{esc(p)}</code>" for p in data["entry_points"][:6])
        bullets.append(f"Start reading at the entry points: {eps}.")
    if data["external_packages"]:
        ext = ", ".join(esc(p["name"]) for p in data["external_packages"][:8])
        bullets.append(f"Main external dependencies: {ext}.")
    if not bullets:
        return msg("Not enough code to explain yet.")
    return '<ul class="explain">' + "".join(f"<li>{b}</li>" for b in bullets) + "</ul>"


