"""The interactive flow page: a draggable, zoomable dependency explorer.

The graph data is computed here (layers and cycles come from mapper), embedded
as JSON, and drawn in the browser by assets/flow.js. The page is one file with
no network access: script and styles are inlined.
"""
import json
import os

import mapper
from pages import esc, shell

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
MAX_FILE_NODES = 600  # beyond this a browser SVG gets sluggish; the largest linked files are kept


def _read_asset(name):
    with open(os.path.join(ASSETS, name), encoding="utf-8") as f:
        return f.read()


def _cycle_index(cycles):
    return {v: i for i, comp in enumerate(cycles) for v in comp}


def _degree(edges):
    fan_in, fan_out = {}, {}
    for e in edges:
        fan_out[e["from"]] = fan_out.get(e["from"], 0) + 1
        fan_in[e["to"]] = fan_in.get(e["to"], 0) + 1
    return fan_in, fan_out


def _edges(edges, cyc):
    return [
        {"s": e["from"], "t": e["to"], "w": e["weight"],
         "cyc": e["from"] in cyc and cyc.get(e["from"]) == cyc.get(e["to"])}
        for e in edges
    ]


def folder_view(files):
    nodes, edges = mapper.folder_graph(files)
    layer_of, cycles = mapper.assign_layers(nodes, edges)
    cyc = _cycle_index(cycles)
    fan_in, fan_out = _degree(edges)
    out = []
    for name, n in sorted(nodes.items(), key=lambda kv: -kv[1]["lines"]):
        out.append({
            "id": name, "kind": "folder", "label": name, "group": name,
            "sub": f'{n["files"]} file{"s" if n["files"] != 1 else ""} · {n["lines"]:,} lines',
            "lines": n["lines"], "files": n["files"], "layer": layer_of[name], "cyc": cyc.get(name, -1),
            "fan_in": fan_in.get(name, 0), "fan_out": fan_out.get(name, 0),
        })
    return {"nodes": out, "edges": _edges(edges, cyc), "cycles": cycles, "omitted": 0}


def file_view(files):
    linked = [f for f in files if f["imports"] or f["fan_in"]]
    linked.sort(key=lambda f: (-(f["fan_in"] + f["fan_out"]), -f["lines"], f["path"]))
    keep = linked[:MAX_FILE_NODES]
    ids = {f["path"] for f in keep}
    nodes = {f["path"]: {"name": f["path"]} for f in keep}
    edges = [
        {"from": f["path"], "to": t, "weight": 1}
        for f in keep for t in f["imports"] if t in ids and t != f["path"]
    ]
    layer_of, cycles = mapper.assign_layers(nodes, edges)
    cyc = _cycle_index(cycles)
    fan_in, fan_out = _degree(edges)
    out = []
    for f in sorted(keep, key=lambda f: f["path"]):
        head, _, tail = f["path"].rpartition("/")
        out.append({
            "id": f["path"], "kind": "file", "label": tail, "sub": (head + "/") if head else "(root)",
            "group": mapper._top(f["path"]), "lines": f["lines"], "lang": f["lang"],
            "layer": layer_of[f["path"]], "cyc": cyc.get(f["path"], -1),
            "fan_in": fan_in.get(f["path"], 0), "fan_out": fan_out.get(f["path"], 0),
            "ext": f.get("external", [])[:12],
        })
    return {
        "nodes": out, "edges": _edges(edges, cyc), "cycles": cycles,
        "omitted": len(linked) - len(keep), "standalone": len(files) - len(linked),
    }


def payload(data):
    files = data["files"]
    folder = folder_view(files)
    file = file_view(files)
    groups = {}
    for f in files:
        g = mapper._top(f["path"])
        groups[g] = groups.get(g, 0) + f["lines"]
    folder_ok = len(folder["nodes"]) > 1 and len(folder["edges"]) > 0
    return {
        "name": data["name"],
        "groups": [g for g, _ in sorted(groups.items(), key=lambda kv: -kv[1])],
        "entry": data.get("entry_points", []),
        "views": {"folder": folder, "file": file},
        "folderUsable": folder_ok,
        "defaultView": "folder" if folder_ok and max((n["layer"] for n in folder["nodes"]), default=0) > 0 else "file",
    }


def _json_for_html(obj):
    # Safe inside <script type="application/json">: no tag can be closed or opened.
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return s.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")


MARKERS = "".join(
    f'<marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" '
    f'markerUnits="userSpaceOnUse" orient="auto-start-reverse"><path d="M0,1 L10,5 L0,9 z" style="fill:var({var})"/></marker>'
    for mid, var in (("ah", "--muted"), ("ah-dn", "--series-7"), ("ah-up", "--series-1"), ("ah-cyc", "--bad"))
)


def seg(ctl, options):
    buttons = "".join(f'<button type="button" data-v="{v}">{esc(label)}</button>' for v, label in options)
    return f'<div class="seg" role="group" data-ctl="{ctl}">{buttons}</div>'


def render_flow(data):
    body = f"""
<div class="flow">
  <aside class="side" aria-label="Controls">
    <div class="sec">
      <div class="eyebrow">Interactive flow</div>
      <h1 class="side-h">{esc(data["name"])}</h1>
      <p class="side-dek" id="count"></p>
    </div>
    <div class="sec">
      <div class="lbl">View</div>
      {seg("view", [("folder", "Folders"), ("file", "Files")])}
      <div id="crumb" class="crumb"></div>
    </div>
    <div class="sec">
      <div class="lbl">Layout</div>
      {seg("layout", [("layered", "Layered"), ("force", "Organic")])}
    </div>
    <div class="sec">
      <div class="lbl">When you select a node, show</div>
      {seg("mode", [("down", "Blast radius"), ("up", "Dependencies"), ("both", "Both")])}
      <div class="lbl" style="margin-top:12px">Depth</div>
      {seg("depth", [("1", "1 hop"), ("2", "2 hops"), ("all", "All")])}
    </div>
    <div class="sec">
      <label class="lbl" for="q">Find</label>
      <input id="q" type="search" placeholder="File or folder name" autocomplete="off" spellcheck="false">
      <ul id="results" class="results"></ul>
    </div>
    <div class="sec">
      <div class="lbl">Start here</div>
      <div id="insights"></div>
    </div>
    <div class="sec">
      <div class="lbl">Folders <button type="button" class="link" id="show-all">show all</button></div>
      <div id="groups" class="chips"></div>
    </div>
    <div class="sec keys">
      <div class="lbl">How to use it</div>
      <ul>
        <li><b>Click</b> a node to see what it affects. <b>Shift-click</b> another to trace the import path.</li>
        <li><b>Drag</b> nodes to rearrange, drag the background to pan, scroll to zoom.</li>
        <li><b>Double-click</b> a folder to open its files.</li>
        <li><kbd>/</kbd> find · <kbd>F</kbd> fit · <kbd>L</kbd> layout · <kbd>1</kbd>/<kbd>2</kbd> view · <kbd>Esc</kbd> clear</li>
      </ul>
    </div>
  </aside>
  <section class="stage" id="stage">
    <svg id="flow-svg" role="application" aria-label="Dependency flow diagram">
      <defs>{MARKERS}</defs>
      <g id="vp"><g id="bands"></g><g id="edges"></g><g id="nodes"></g></g>
    </svg>
    <div class="toolbar" role="toolbar" aria-label="Canvas">
      <button type="button" data-act="out" title="Zoom out (-)">−</button>
      <span id="zoom-level" class="zl">100%</span>
      <button type="button" data-act="in" title="Zoom in (+)">+</button>
      <span class="sep"></span>
      <button type="button" data-act="fit" title="Fit to screen (F)">Fit</button>
      <button type="button" data-act="reset" title="Undo your drags and lay out again">Re-layout</button>
      <span class="sep"></span>
      <button type="button" data-act="export" title="Download what you see as an SVG">Export SVG</button>
      <button type="button" data-act="link" title="Copy a link to this exact view">Copy link</button>
    </div>
    <div class="key">
      <span><i class="k-line"></i>imports (points to the dependency)</span>
      <span><i class="k-line dn"></i>blast radius</span>
      <span><i class="k-line up"></i>dependencies</span>
      <span><i class="k-line cyc"></i>cycle</span>
      <span><b>↑N</b> used by N</span>
    </div>
    <svg id="mini" class="mini" viewBox="0 0 200 130" aria-label="Minimap: click to move the view"></svg>
    <aside id="detail" class="detail" aria-live="polite"></aside>
    <div id="tip" class="tip" hidden></div>
    <div id="toast" class="toast" role="status" hidden></div>
  </section>
</div>
<script type="application/json" id="flow-data">{_json_for_html(payload(data))}</script>
<script>{_read_asset("flow.js")}</script>
"""
    return shell(f'{data["name"]} · flow', "flow", data, body, app_css=_read_asset("flow.css"))
