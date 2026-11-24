"""Two standalone pages from one codebase map.

  visuals.html   the diagrams: architecture, change risk, folders, languages, hotspots
  explainer.html the story: what the project is, how it is organised, where to start,
                 what to watch, written from the same numbers

Both share one theme, have no network dependencies, and print cleanly.
"""
import html

import renderer as R


def esc(s):
    return html.escape(str(s), quote=True)


THEME = """
:root{
  --bg:#11151a;--bg2:#161b21;--surface:#1b2128;--surface2:#222a33;--border:#2e3742;
  --fg:#e4e8ec;--muted:#98a2ad;--accent:#8ea9c1;--bad:#c08072;--good:#8fa98a;
  --series-1:#8ea9c1;--series-2:#8fa98a;--series-3:#c4b48f;--series-4:#b79c9c;
  --series-5:#a9a3c0;--series-6:#8fb0ab;--series-7:#c39c86;--series-8:#a9ada6;
  --radius:16px;--shadow:0 1px 0 rgba(255,255,255,.03) inset,0 12px 40px -18px rgba(0,0,0,.6);
}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:72px}
body{margin:0;background:var(--bg);
  color:var(--fg);font:15.5px/1.6 Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
  -webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
nav.top{position:sticky;top:0;z-index:10;backdrop-filter:saturate(1.4) blur(10px);
  background:rgba(11,15,20,.72);border-bottom:1px solid var(--border)}
nav.top .in{max-width:1180px;margin:0 auto;padding:12px 24px;display:flex;align-items:center;gap:18px}
nav.top .brand{font-weight:700;letter-spacing:.01em;margin-right:auto;color:var(--fg)}
nav.top a.tab{color:var(--muted);padding:6px 10px;border-radius:999px;font-size:13.5px}
nav.top a.tab:hover{color:var(--fg);background:var(--surface2);text-decoration:none}
nav.top a.tab.on{color:var(--fg);background:var(--surface2);box-shadow:inset 0 0 0 1px var(--border)}
main{max-width:1180px;margin:0 auto;padding:40px 24px 72px}
.hero{padding:28px 0 8px}
.eyebrow{color:var(--accent);font-size:12px;font-weight:700;letter-spacing:.14em;text-transform:uppercase}
.hero h1{font-size:44px;line-height:1.1;margin:10px 0 12px;letter-spacing:-.02em;
  color:var(--fg)}
.hero p.dek{color:var(--muted);font-size:18px;max-width:760px;margin:0}
h2{font-size:22px;letter-spacing:-.01em;margin:48px 0 6px;scroll-margin-top:80px}
.lede{color:var(--muted);margin:0 0 16px;max-width:820px}
.card{background:linear-gradient(180deg,var(--surface2) 0,var(--surface) 60%);border:1px solid var(--border);
  border-radius:var(--radius);padding:20px 22px;box-shadow:var(--shadow)}
.panel{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:18px;box-shadow:var(--shadow)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin-top:24px}
.stat .label{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.08em}
.stat .value{font-size:28px;font-weight:700;margin-top:2px;font-variant-numeric:tabular-nums}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
@media (max-width:900px){.grid2,.grid3{grid-template-columns:1fr}.hero h1{font-size:34px}}
svg{width:100%;height:auto;display:block}
.langbar{height:14px;border-radius:999px;overflow:hidden;background:var(--border);margin-bottom:14px}
.legend{list-style:none;padding:0;margin:0;display:flex;flex-wrap:wrap;gap:8px 18px}
.legend li{display:flex;align-items:center;gap:7px}
.sw{width:10px;height:10px;border-radius:3px;display:inline-block}
.muted{color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th,td{padding:9px 10px;border-bottom:1px solid var(--border);text-align:left}
th{color:var(--muted);font-weight:600;font-size:12.5px;text-transform:uppercase;letter-spacing:.06em}
tr:last-child td{border-bottom:0}
.num{text-align:right;font-variant-numeric:tabular-nums}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px;word-break:break-all;color:var(--fg)}
.explain{padding-left:20px;margin:0}.explain li{margin:10px 0}
.steps{counter-reset:s;list-style:none;padding:0;margin:0}
.steps li{counter-increment:s;position:relative;padding:14px 16px 14px 56px;border:1px solid var(--border);
  border-radius:12px;margin:10px 0;background:var(--surface)}
.steps li::before{content:counter(s);position:absolute;left:14px;top:12px;width:28px;height:28px;border-radius:50%;
  display:grid;place-items:center;font-weight:700;background:var(--surface2);color:var(--accent);border:1px solid var(--border)}
.callout{border-left:3px solid var(--accent);background:var(--surface);padding:14px 18px;border-radius:0 12px 12px 0}
.callout.warn{border-color:var(--bad)}
a.btn{display:inline-block;padding:8px 14px;border-radius:10px;background:var(--surface2);color:var(--fg);
  border:1px solid var(--border);font-weight:600;font-size:14px}
a.btn:hover{border-color:var(--muted);text-decoration:none}
.kv{display:grid;grid-template-columns:200px 1fr;gap:8px 16px;margin:0}
.kv dt{color:var(--muted)}.kv dd{margin:0}
footer{margin-top:56px;color:var(--muted);font-size:12.5px;border-top:1px solid var(--border);padding-top:16px}
@media print{nav.top{display:none}body{background:#fff;color:#111}.card,.panel{box-shadow:none}
  h2,.hero h1{-webkit-text-fill-color:#111;color:#111;background:none}}
"""


def shell(title, active, data, body, app_css=None):
    tabs = [("explainer.html", "Explainer", "explainer"), ("index.html", "Visuals", "visuals"),
            ("flow.html", "Flow", "flow")]
    nav = "".join(
        f'<a class="tab{" on" if key == active else ""}" href="{href}">{label}</a>'
        for href, label, key in tabs
    )
    head = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<style>{THEME}</style>"""
    if app_css is not None:
        # Full-screen app page: no reading column, no footer.
        return f"""{head}<style id="flow-css">{app_css}</style></head>
<body class="app">
<nav class="top"><div class="in wide"><span class="brand">{esc(data["name"])}</span>{nav}</div></nav>
{body}
</body></html>
"""
    return f"""{head}</head>
<body>
<nav class="top"><div class="in"><span class="brand">{esc(data["name"])}</span>{nav}</div></nav>
<main>{body}
<footer>Generated {esc(data["generated"])} from static analysis of imports. Dynamic imports, generated code
and framework conventions are not followed. Re-run the deep-dive tool to refresh.</footer>
</main></body></html>
"""


def _stats(data):
    t = data["totals"]
    arch = data.get("architecture", {})
    items = [
        ("Files", R.fmt(t["files"])),
        ("Lines", R.fmt(t["lines"])),
        ("Languages", str(len(data["languages"]))),
        ("Layers", str(len(arch.get("layers", [])))),
        ("Cycles", str(len(arch.get("cycles", [])))),
        ("External packages", R.fmt(t["external_packages"])),
    ]
    return '<div class="stats">' + "".join(
        f'<div class="card stat"><div class="label">{esc(k)}</div><div class="value">{esc(v)}</div></div>'
        for k, v in items
    ) + "</div>"


def _arch_lede(arch):
    if arch.get("granularity") == "file":
        return ("Folders do not depend on each other, so this is the file-level flow: arrows point from a file "
                "to the file it imports. Red dashed boxes are in a cycle.")
    return "Folders in dependency layers. Arrows point from a folder to what it depends on. Red dashed boxes are in a cycle."


def render_visuals(data):
    files = data["files"]
    ordered = sorted(R.build_groups(files).items(), key=lambda kv: -sum(kv[1].values()))
    arch = data.get("architecture", {"nodes": [], "edges": [], "layers": [], "cycles": []})
    tree_svg, _ = R.treemap_svg(files)
    folder_legend = "".join(
        f'<li><span class="sw" style="background:{R.series(i)}"></span>'
        f'<code>{esc(name)}</code> <span class="muted">{R.pct(sum(c.values()), data["totals"]["lines"])}</span></li>'
        for i, (name, c) in enumerate(ordered)
    )
    body = f"""
<section class="hero">
  <div class="eyebrow">Visuals</div>
  <h1>{esc(data["name"])}</h1>
  <p class="dek">How the code is shaped: its layers, its change risk, and where the weight sits.</p>
  {_stats(data)}
</section>

<h2 id="architecture">Architecture</h2>
<p class="lede">{_arch_lede(arch)}</p>
<div class="panel">{R.architecture_svg(arch)}</div>
<p style="margin:14px 0 0"><a class="btn" href="flow.html">Open the interactive flow</a>
<span class="muted" style="margin-left:10px">Drag, zoom, click a file to see its blast radius, trace import paths.</span></p>

<h2 id="risk">Change risk</h2>
<p class="lede">Each bubble is a file. Right: it depends on many files. Up: many files depend on it. Size: lines of code.</p>
<div class="panel">{R.risk_quadrant_svg(files, ordered)}</div>

<h2 id="folders">Where the code lives</h2>
<p class="lede">Folders by lines. Each big box is a top-level folder; the boxes inside are its subfolders.</p>
<div class="panel">{tree_svg}<ul class="legend" style="margin-top:14px">{folder_legend}</ul></div>

<h2 id="languages">Languages</h2>
<div class="panel">{R.language_bar(data)}</div>

<h2 id="hotspots">Hotspots</h2>
<p class="lede">The largest files, and the files the most other files depend on.</p>
<div class="panel">{R.hotspots(files)}</div>
"""
    return shell(f'{data["name"]} · visuals', "visuals", data, body)


def render_explainer(data):
    t = data["totals"]
    arch = data.get("architecture", {"nodes": [], "edges": [], "layers": [], "cycles": []})
    files = data["files"]
    langs = data["languages"]
    top_lang = langs[0] if langs else None
    layers = arch.get("layers", [])
    depth = len(layers)
    biggest = max(arch.get("nodes", []), key=lambda n: n["lines"], default=None)
    hub = max(files, key=lambda f: (f["fan_in"], -f["lines"]), default=None)
    entries = data["entry_points"]

    summary_bits = [
        f"{R.fmt(t['files'])} files and {R.fmt(t['lines'])} lines",
        f"{R.fmt(len(langs))} language{'s' if len(langs) != 1 else ''}",
    ]
    if top_lang:
        summary_bits.append(f"mostly {esc(top_lang['name'])} ({R.pct(top_lang['lines'], t['lines'])})")
    dek = "A map of " + ", ".join(summary_bits) + "."

    overview = f"""
<div class="grid2">
  <div class="card">
    <h3 style="margin:0 0 8px">What it is</h3>
    <p class="muted" style="margin:0">Read the file names and entry points below to confirm what the project does.
    The map shows the structure; the README and the code say the purpose.</p>
  </div>
  <div class="card">
    <h3 style="margin:0 0 8px">Shape at a glance</h3>
    <dl class="kv">
      <dt>Dependency layers</dt><dd>{depth}</dd>
      <dt>Circular groups</dt><dd>{len(arch.get("cycles", []))}</dd>
      <dt>Biggest folder</dt><dd>{f"<code>{esc(biggest['name'])}</code> · {R.fmt(biggest['lines'])} lines" if biggest else "n/a"}</dd>
      <dt>Most depended on</dt><dd>{f"<code>{esc(hub['path'])}</code> · imported by {hub['fan_in']}" if hub and hub['fan_in'] else "none found"}</dd>
    </dl>
  </div>
</div>"""

    if layers:
        layer_items = []
        for layer in reversed(layers):
            names = ", ".join(f"<code>{esc(f['name'])}</code>" for f in layer["folders"][:6]) or "none"
            tag = " · foundation" if layer["layer"] == 0 else (" · consumers" if layer is layers[-1] else "")
            layer_items.append(f"<li><b>Layer {layer['layer']}</b>{tag}: {names}</li>")
        layer_html = "<ul class=\"explain\">" + "".join(layer_items) + "</ul>"
    else:
        layer_html = R.msg("Not enough folders to layer.")

    if entries:
        read_html = '<ol class="steps">' + "".join(
            f"<li><code>{esc(p)}</code></li>" for p in entries[:6]
        )
        read_html += '<li>Then read the foundation layer, so the lower-level types and helpers make sense.</li></ol>'
    else:
        read_html = (
            '<ol class="steps"><li>Start with the top-layer folders listed above.</li>'
            '<li>Then read the foundation layer, so the lower-level types and helpers make sense.</li></ol>'
        )

    cycles = arch.get("cycles", [])
    if cycles:
        cyc = "".join(
            f'<li>{" ↔ ".join(f"<code>{esc(v)}</code>" for v in c)} depend on each other. '
            "Treat them as one unit: changing one can break the other, and they are hard to test apart.</li>"
            for c in cycles
        )
        watch = f'<ul class="explain">{cyc}</ul>'
        watch_cls = "callout warn"
    else:
        watch = '<p style="margin:0">No circular dependencies between folders. Good: each layer can be read on its own.</p>'
        watch_cls = "callout"

    hub_text = (
        f"<code>{esc(hub['path'])}</code> is imported by {hub['fan_in']} file{'s' if hub['fan_in'] != 1 else ''}. A change there reaches "
        "that many places, so review it with extra care and keep its interface stable."
        if hub and hub["fan_in"] > 0
        else "No file is imported by others in a way the map can see."
    )

    ext = data.get("external_packages", [])
    ext_html = (
        ", ".join(f"<code>{esc(p['name'])}</code> <span class=\"muted\">({p['files']})</span>" for p in ext[:12])
        if ext else "<span class=\"muted\">None found.</span>"
    )

    body = f"""
<section class="hero">
  <div class="eyebrow">Explainer</div>
  <h1>{esc(data["name"])}</h1>
  <p class="dek">{dek}</p>
  {_stats(data)}
</section>

<h2 id="overview">Overview</h2>
{overview}

<h2 id="layers">How it is organised</h2>
<p class="lede">The folders form layers. Foundations depend on nothing. Each layer above depends only on the layers below. The diagram on the Visuals page shows the same structure.</p>
<div class="panel">{layer_html}</div>

<h2 id="reading">Where to start reading</h2>
<p class="lede">Follow the arrows down. You will understand each part before the parts that use it.
The <a href="flow.html">interactive flow</a> lets you click any file to see what uses it and what it uses.</p>
{read_html}

<h2 id="risk">What to watch</h2>
<div class="{watch_cls}">
  {watch}
  <p style="margin:12px 0 0">{hub_text}</p>
</div>

<h2 id="dependencies">External dependencies</h2>
<p class="lede">Third-party packages the code imports, with how many files use each.</p>
<div class="card">{ext_html}</div>

<h2 id="method">How this was made</h2>
<div class="card muted" style="font-size:14px">
  Every number here comes from a static scan of the source: file sizes, the import graph between files,
  and the folders those files sit in. Only <code>import</code>, <code>from … import</code>, <code>require()</code>
  and <code>export … from</code> are followed. Dynamic imports, string-built paths and framework conventions are not.
  Python and JavaScript/TypeScript have import graphs; other languages get size and language counts only.
</div>
"""
    return shell(f'{data["name"]} · explainer', "explainer", data, body)
