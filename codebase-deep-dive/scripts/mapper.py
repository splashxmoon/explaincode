"""Map a codebase: languages, sizes and the internal import graph. No dependencies.

The output is plain JSON, so an agent can read it, and the renderer can turn
it into a page. Python and JavaScript/TypeScript imports are resolved to
files inside the repo; anything else counts as an external package.
"""
import datetime as dt
import os
import re
import sys

IGNORE_DIRS = {
    "node_modules", "__pycache__", "venv", "env", "dist", "build", "out",
    "target", "vendor", "coverage", "site-packages",
}
LANG_BY_EXT = {
    ".py": "Python", ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".jsx": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript", ".go": "Go",
    ".rs": "Rust", ".java": "Java", ".kt": "Kotlin", ".swift": "Swift", ".rb": "Ruby",
    ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++", ".hpp": "C++", ".cs": "C#",
    ".php": "PHP", ".sh": "Shell", ".md": "Markdown", ".html": "HTML", ".css": "CSS",
    ".scss": "CSS", ".json": "JSON", ".yml": "YAML", ".yaml": "YAML", ".toml": "TOML",
}
JS_LANGS = {"JavaScript", "TypeScript"}
JS_EXTS = [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"]
ENTRY_NAMES = {
    "main.py", "__main__.py", "cli.py", "app.py", "manage.py", "server.py",
    "index.js", "index.ts", "main.js", "main.ts", "main.go", "main.rs",
    "server.js", "server.ts", "App.tsx", "App.jsx",
}
MAX_BYTES = 1_000_000

PY_IMPORT = re.compile(
    r"^\s*(?:from\s+(\.*[\w.]*)\s+import\s+([^\n]*)|import\s+([\w.]+))", re.M
)
JS_IMPORT = re.compile(
    r"""(?:\bimport\b[^'"\n;]*?|\bexport\b[^'"\n;]*?\bfrom\b|\brequire\(|\bimport\()\s*['"]([^'"]+)['"]"""
)


def walk(root):
    """Yield (relative posix path, absolute path) for every visible file."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")
        )
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                continue
            yield os.path.relpath(full, root).replace(os.sep, "/"), full


def read_text(path):
    """Return the file's text, or None if it is binary or too large."""
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return None
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


def python_targets(rel, text, known):
    """Return (internal paths, external package names) for a Python file."""
    internal, external = set(), set()
    pkg_dir = os.path.dirname(rel)
    for m in PY_IMPORT.finditer(text):
        from_spec, names, plain = m.group(1), m.group(2), m.group(3)
        if from_spec is not None:  # "from X import a, b"
            dots = len(from_spec) - len(from_spec.lstrip("."))
            parts = [p for p in from_spec.lstrip(".").split(".") if p]
            if dots:  # relative import: climb (dots - 1) directories from this file
                base = pkg_dir
                for _ in range(dots - 1):
                    base = os.path.dirname(base)
                parts = [p for p in base.split("/") if p] + parts
                prefix_only = True
            else:
                prefix_only = False
            # "from pkg import util" may name a submodule, so try each name first.
            hit = False
            for name in _imported_names(names):
                resolved = _resolve_py(parts + [name], known)
                if resolved:
                    internal.add(resolved)
                    hit = True
            if not hit:
                resolved = _resolve_py(parts, known)
                if resolved:
                    internal.add(resolved)
                elif parts and not prefix_only:
                    _add_external(external, parts[0])
        elif plain:  # "import a.b.c"
            resolved = _resolve_py(plain.split("."), known)
            if resolved:
                internal.add(resolved)
            else:
                _add_external(external, plain.split(".")[0])
    return internal, external


def _add_external(external, top):
    """Record a third-party package, skipping the Python standard library."""
    if top and top not in sys.stdlib_module_names:
        external.add(top)


def _imported_names(text):
    """Names from the tail of 'from X import ...', without aliases or parens."""
    if not text:
        return []
    text = text.split("#")[0].replace("(", "").replace(")", "")
    names = []
    for piece in text.split(","):
        name = piece.strip().split(" as ")[0].strip()
        if name and name != "*" and name.isidentifier():
            names.append(name)
    return names


PY_ROOTS = ("", "src/", "lib/")


def _resolve_py(parts, known):
    """Find the longest prefix of parts that names a file in the repo.

    Falls back to a bare module name that matches exactly one file anywhere in
    the repo, which covers scripts that import their siblings (import mapper).
    """
    parts = [p for p in parts if p]
    for n in range(len(parts), 0, -1):
        stem = "/".join(parts[:n])
        for root in PY_ROOTS:
            for cand in (root + stem + ".py", root + stem + "/__init__.py"):
                if cand in known:
                    return cand
    if parts:
        first = parts[0]
        matches = [
            k for k in known
            if k == first + ".py" or k.endswith("/" + first + ".py")
        ]
        if len(matches) == 1:
            return matches[0]
    return None


def js_targets(rel, text, known):
    internal, external = set(), set()
    base = os.path.dirname(rel)
    for m in JS_IMPORT.finditer(text):
        spec = m.group(1)
        if spec.startswith("."):
            target = os.path.normpath(os.path.join(base, spec)).replace(os.sep, "/")
            hit = _resolve_js(target, known)
            if hit:
                internal.add(hit)
        elif not _is_node_builtin(spec):
            external.add(_package_name(spec))
    return internal, external


NODE_BUILTINS = {
    "assert", "buffer", "child_process", "cluster", "crypto", "dns", "events", "fs",
    "http", "https", "module", "net", "os", "path", "perf_hooks", "process", "querystring",
    "readline", "stream", "string_decoder", "test", "timers", "tls", "tty", "url", "util",
    "vm", "worker_threads", "zlib",
}


def _is_node_builtin(spec):
    return spec.startswith("node:") or spec.split("/")[0] in NODE_BUILTINS


def _resolve_js(target, known):
    if target in known:
        return target
    for ext in JS_EXTS:
        if target + ext in known:
            return target + ext
    for ext in JS_EXTS:
        if target + "/index" + ext in known:
            return target + "/index" + ext
    return None


def _package_name(spec):
    if spec.startswith("@"):
        return "/".join(spec.split("/")[:2])
    return spec.split("/")[0]


def _top(path):
    parts = path.split("/")
    return parts[0] if len(parts) > 1 else "(root)"


def folder_graph(files):
    """Folder-level nodes (size, file count) and weighted import edges."""
    nodes, weights = {}, {}
    for f in files:
        a = _top(f["path"])
        n = nodes.setdefault(a, {"name": a, "lines": 0, "files": 0})
        n["lines"] += f["lines"]
        n["files"] += 1
        for target in f["imports"]:
            b = _top(target)
            if a != b:
                weights[(a, b)] = weights.get((a, b), 0) + 1
    edges = [{"from": a, "to": b, "weight": w} for (a, b), w in sorted(weights.items())]
    return nodes, edges


def strongly_connected(nodes, adj):
    """Tarjan's algorithm. Returns the components; size > 1 means a cycle."""
    index, low, on_stack, stack, out = {}, {}, set(), [], []
    counter = [0]

    def visit(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in adj.get(v, ()):
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on_stack:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                comp.append(w)
                if w == v:
                    break
            out.append(sorted(comp))

    for v in sorted(nodes):
        if v not in index:
            visit(v)
    return out


def assign_layers(nodes, edges):
    """Layer 0 = foundations (depend on nothing); higher = more application-level.

    Cycles collapse into one component, so every folder in a cycle shares a layer.
    """
    adj = {}
    for e in edges:
        adj.setdefault(e["from"], set()).add(e["to"])
    comps = strongly_connected(nodes, adj)
    comp_of = {v: i for i, c in enumerate(comps) for v in c}
    cadj = {i: set() for i in range(len(comps))}
    for v, targets in adj.items():
        for w in targets:
            if comp_of[v] != comp_of[w]:
                cadj[comp_of[v]].add(comp_of[w])
    depth = {}

    def d(i):
        if i not in depth:
            depth[i] = 0  # the condensation is a DAG, so this guard is only a safety net
            depth[i] = 1 + max((d(j) for j in cadj[i]), default=-1)
        return depth[i]

    layer_of = {v: d(comp_of[v]) for v in nodes}
    cycles = [c for c in comps if len(c) > 1]
    return layer_of, cycles


def file_graph(files, limit=40):
    """File-level nodes for the files that import or are imported, largest first."""
    linked = {f["path"] for f in files if f["imports"] or f["fan_in"]}
    chosen = sorted((f for f in files if f["path"] in linked), key=lambda f: -f["lines"])[:limit]
    keep = {f["path"] for f in chosen}
    nodes = {f["path"]: {"name": f["path"], "lines": f["lines"], "files": 1} for f in chosen}
    weights = {}
    for f in chosen:
        for target in f["imports"]:
            if target in keep and target != f["path"]:
                weights[(f["path"], target)] = weights.get((f["path"], target), 0) + 1
    edges = [{"from": a, "to": b, "weight": w} for (a, b), w in sorted(weights.items())]
    return nodes, edges


def architecture(files):
    nodes, edges = folder_graph(files)
    granularity = "folder"
    layer_of, cycles = assign_layers(nodes, edges)
    if max(layer_of.values(), default=0) == 0 and len(nodes) > 1:
        # Folders do not depend on each other, so the folder view is one flat row.
        # Show the file-level dependency flow instead.
        fnodes, fedges = file_graph(files)
        if fedges:
            nodes, edges, granularity = fnodes, fedges, "file"
            layer_of, cycles = assign_layers(nodes, edges)
    top = max(layer_of.values(), default=0)
    layers = []
    for k in range(top + 1):
        members = sorted(
            (nodes[v] for v in nodes if layer_of[v] == k),
            key=lambda n: -n["lines"],
        )
        layers.append({"layer": k, "folders": members})
    return {
        "granularity": granularity,
        "nodes": list(nodes.values()),
        "edges": edges,
        "layers": layers,
        "layer_of": layer_of,
        "cycles": cycles,
    }


def map_codebase(root):
    root = os.path.abspath(root)
    entries = list(walk(root))
    texts = {}
    for rel, full in entries:
        ext = os.path.splitext(rel)[1].lower()
        if ext not in LANG_BY_EXT:
            continue
        text = read_text(full)
        if text is None:
            continue
        texts[rel] = (LANG_BY_EXT[ext], text, full)

    known = set(texts)
    files = []
    languages = {}
    total_lines = total_bytes = edges = 0
    external_counts = {}
    fan_in = {}

    for rel in sorted(texts):
        lang, text, full = texts[rel]
        lines = text.count("\n") + (0 if text.endswith("\n") or not text else 1)
        size = os.path.getsize(full)
        internal, external = set(), set()
        if lang == "Python":
            internal, external = python_targets(rel, text, known)
        elif lang in JS_LANGS:
            internal, external = js_targets(rel, text, known)
        internal.discard(rel)
        for pkg in external:
            external_counts[pkg] = external_counts.get(pkg, 0) + 1
        for target in internal:
            fan_in[target] = fan_in.get(target, 0) + 1
        edges += len(internal)
        total_lines += lines
        total_bytes += size
        stat = languages.setdefault(lang, {"name": lang, "files": 0, "lines": 0})
        stat["files"] += 1
        stat["lines"] += lines
        files.append({
            "path": rel,
            "lang": lang,
            "lines": lines,
            "bytes": size,
            "imports": sorted(internal),
            "external": sorted(external),
        })

    for f in files:
        f["fan_in"] = fan_in.get(f["path"], 0)
        f["fan_out"] = len(f["imports"])

    return {
        "architecture": architecture(files),
        "name": os.path.basename(root) or root,
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "totals": {
            "files": len(files),
            "lines": total_lines,
            "bytes": total_bytes,
            "internal_edges": edges,
            "external_packages": len(external_counts),
        },
        "languages": sorted(languages.values(), key=lambda x: -x["lines"]),
        "external_packages": sorted(
            ({"name": k, "files": v} for k, v in external_counts.items()),
            key=lambda x: (-x["files"], x["name"]),
        )[:25],
        "entry_points": [f["path"] for f in files if os.path.basename(f["path"]) in ENTRY_NAMES],
        "files": files,
    }
