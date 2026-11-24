import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import mapper  # noqa: E402
import pages  # noqa: E402
import renderer  # noqa: E402
import deep_dive  # noqa: E402
import flow  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402


def write(root, rel, text):
    full = os.path.join(root, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(text)


class MapperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_python_absolute_relative_and_external_imports(self):
        write(self.root, "pkg/__init__.py", "")
        write(self.root, "pkg/core.py", "import os\nfrom pkg import util\nfrom . import util\n")
        write(self.root, "pkg/util.py", "import requests\n")
        write(self.root, "app/main.py", "from pkg.core import run\nimport numpy.linalg\n")
        data = mapper.map_codebase(self.root)
        by_path = {f["path"]: f for f in data["files"]}
        self.assertIn("pkg/util.py", by_path["pkg/core.py"]["imports"])
        self.assertIn("pkg/core.py", by_path["app/main.py"]["imports"])
        self.assertNotIn("os", by_path["pkg/core.py"]["external"])  # stdlib is not a dependency
        self.assertIn("requests", by_path["pkg/util.py"]["external"])
        self.assertIn("numpy", by_path["app/main.py"]["external"])
        # core.py imports util twice, but fan-in counts importing files.
        self.assertEqual(by_path["pkg/util.py"]["fan_in"], 1)

    def test_sibling_script_import_resolves(self):
        write(self.root, "tools/mapper.py", "X = 1\n")
        write(self.root, "tools/render.py", "import mapper\n")
        data = mapper.map_codebase(self.root)
        by_path = {f["path"]: f for f in data["files"]}
        self.assertEqual(by_path["tools/render.py"]["imports"], ["tools/mapper.py"])

    def test_javascript_relative_imports_and_packages(self):
        write(self.root, "src/index.ts", "import { a } from './lib/a';\nimport React from 'react';\nimport fs from 'node:fs';\n")
        write(self.root, "src/lib/a.ts", "export const a = 1;\nexport * from './b';\n")
        write(self.root, "src/lib/b.js", "const c = require('../util');\n")
        write(self.root, "src/util/index.js", "module.exports = {};\n")
        data = mapper.map_codebase(self.root)
        by_path = {f["path"]: f for f in data["files"]}
        self.assertEqual(by_path["src/index.ts"]["imports"], ["src/lib/a.ts"])
        self.assertIn("src/lib/b.js", by_path["src/lib/a.ts"]["imports"])
        self.assertIn("src/util/index.js", by_path["src/lib/b.js"]["imports"])
        self.assertIn("react", by_path["src/index.ts"]["external"])
        self.assertNotIn("node:fs", by_path["src/index.ts"]["external"])  # Node built-ins are not dependencies
        self.assertIn("src/index.ts", data["entry_points"])

    def test_typescript_esm_and_multiline_imports(self):
        # ESM TypeScript names the compiled file: './plans.js' means plans.ts.
        write(self.root, "src/server.ts", (
            "import { a } from './plans.js';\n"
            "import {\n  b,\n  c,\n} from './accounts';\n"
            "export type {\n  T,\n} from './types.js';\n"
            "import type {\n  U,\n} from 'some-pkg';\n"
        ))
        write(self.root, "src/plans.ts", "export const a = 1;\n")
        write(self.root, "src/accounts.ts", "export const b = 1, c = 2;\n")
        write(self.root, "src/types.ts", "export type T = 1;\n")
        write(self.root, "src/View.tsx", "import { a } from './plans.js';\nimport { W } from './Widget.jsx';\n")
        write(self.root, "src/Widget.tsx", "export const W = 1;\n")
        data = mapper.map_codebase(self.root)
        by_path = {f["path"]: f for f in data["files"]}
        self.assertEqual(
            by_path["src/server.ts"]["imports"],
            ["src/accounts.ts", "src/plans.ts", "src/types.ts"],
        )
        self.assertIn("some-pkg", by_path["src/server.ts"]["external"])
        self.assertEqual(by_path["src/View.tsx"]["imports"], ["src/Widget.tsx", "src/plans.ts"])

    def test_stdlib_list_without_stdlib_module_names(self):
        # Python 3.9 (the macOS python3) has no sys.stdlib_module_names.
        from unittest import mock
        with mock.patch.object(sys, "stdlib_module_names", None, create=True):
            names = mapper._stdlib_names()
        for name in ("os", "json", "asyncio", "collections", "math", "tomllib"):
            self.assertIn(name, names)
        self.assertNotIn("requests", names)
        self.assertNotIn("site-packages", names)

    def test_ignores_vendor_hidden_and_binary(self):
        write(self.root, "node_modules/x/index.js", "module.exports=1")
        write(self.root, ".hidden/a.py", "x=1")
        write(self.root, "bin.py", "x=1\x00\x01")
        write(self.root, "ok.py", "x = 1\n")
        data = mapper.map_codebase(self.root)
        self.assertEqual([f["path"] for f in data["files"]], ["ok.py"])

    def test_totals_and_languages(self):
        write(self.root, "a.py", "a\nb\nc\n")
        write(self.root, "b.go", "package main\n")
        data = mapper.map_codebase(self.root)
        self.assertEqual(data["totals"]["files"], 2)
        self.assertEqual(data["totals"]["lines"], 4)
        names = {l["name"] for l in data["languages"]}
        self.assertEqual(names, {"Python", "Go"})


class ArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_layers_put_foundations_at_zero(self):
        # app -> core -> util: util is the foundation.
        write(self.root, "util/u.py", "import json\n")
        write(self.root, "core/c.py", "from util import u\n")
        write(self.root, "app/a.py", "from core import c\n")
        arch = mapper.map_codebase(self.root)["architecture"]
        self.assertEqual(arch["layer_of"], {"util": 0, "core": 1, "app": 2})
        self.assertEqual(arch["cycles"], [])

    def test_cycle_is_detected_and_shares_a_layer(self):
        write(self.root, "a/x.py", "from b import y\n")
        write(self.root, "b/y.py", "from a import x\n")
        write(self.root, "c/z.py", "from a import x\n")
        arch = mapper.map_codebase(self.root)["architecture"]
        self.assertEqual(arch["cycles"], [["a", "b"]])
        self.assertEqual(arch["layer_of"]["a"], arch["layer_of"]["b"])
        self.assertGreater(arch["layer_of"]["c"], arch["layer_of"]["a"])

    def test_fan_out_is_recorded(self):
        write(self.root, "m/a.py", "from n import b\nfrom o import c\n")
        write(self.root, "n/b.py", "")
        write(self.root, "o/c.py", "")
        data = mapper.map_codebase(self.root)
        a = next(f for f in data["files"] if f["path"] == "m/a.py")
        self.assertEqual(a["fan_out"], 2)

    def test_flat_folders_fall_back_to_file_flow(self):
        # Folders never import each other, but files inside one folder do.
        write(self.root, "scripts/a.py", "from scripts import b\n")
        write(self.root, "scripts/b.py", "from scripts import c\n")
        write(self.root, "scripts/c.py", "")
        write(self.root, "tests/t.py", "")
        arch = mapper.map_codebase(self.root)["architecture"]
        self.assertEqual(arch["granularity"], "file")
        self.assertIn("scripts/a.py", arch["layer_of"])
        self.assertGreater(arch["layer_of"]["scripts/a.py"], arch["layer_of"]["scripts/c.py"])

    def test_architecture_svg_draws_cycle_in_red(self):
        write(self.root, "a/x.py", "from b import y\n")
        write(self.root, "b/y.py", "from a import x\n")
        arch = mapper.map_codebase(self.root)["architecture"]
        svg = renderer.architecture_svg(arch)
        self.assertIn("<svg", svg)
        self.assertIn("var(--bad", svg)


class RendererTests(unittest.TestCase):
    def test_treemap_layout_fills_the_box(self):
        rects = renderer.split_layout([("a", 5, 0), ("b", 3, 1), ("c", 2, 2)], 0, 0, 100, 50)
        area = sum(w * h for *_, w, h in rects)
        self.assertAlmostEqual(area, 100 * 50, places=3)
        self.assertEqual(len(rects), 3)

    def test_html_is_standalone_and_escaped(self):
        data = {
            "name": "<evil>",
            "generated": "now",
            "totals": {"files": 2, "lines": 10, "bytes": 100, "internal_edges": 1, "external_packages": 0},
            "languages": [{"name": "Python", "files": 2, "lines": 10}],
            "external_packages": [],
            "entry_points": [],
            "files": [
                {"path": "a/x.py", "lang": "Python", "lines": 5, "bytes": 50, "imports": ["b/y.py"], "external": [], "fan_in": 0, "fan_out": 1},
                {"path": "b/y.py", "lang": "Python", "lines": 5, "bytes": 50, "imports": [], "external": [], "fan_in": 1, "fan_out": 0},
            ],
        }
        for page in (pages.render_visuals(data), pages.render_explainer(data)):
            self.assertNotIn("<evil>", page)
            self.assertIn("&lt;evil&gt;", page)
            self.assertNotIn("http://", page.replace("http://www.w3.org/2000/svg", ""))
            self.assertNotIn("https://", page)
        self.assertIn("<svg", pages.render_visuals(data))
        self.assertIn("b/y.py", pages.render_visuals(data))


class ExplainerTests(unittest.TestCase):
    def test_explainer_reads_in_order_and_flags_cycles(self):
        with tempfile.TemporaryDirectory() as root:
            write(root, "a/x.py", "from b import y\n")
            write(root, "b/y.py", "from a import x\n")
            page = pages.render_explainer(mapper.map_codebase(root))
        self.assertIn("Where to start reading", page)
        self.assertIn("depend on each other", page)


class PaletteTests(unittest.TestCase):
    """Design rule: colours stay muted, never bright or neon."""

    def test_theme_colours_are_muted(self):
        import re
        hexes = re.findall(r"#([0-9a-fA-F]{6})\b", pages.THEME)
        self.assertTrue(hexes)
        for h in hexes:
            r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
            self.assertLessEqual(max(r, g, b) - min(r, g, b), 90, f"#{h} is too saturated")

    def test_renderer_fallbacks_are_muted(self):
        import re
        src = open(os.path.join(HERE, "..", "scripts", "renderer.py"), encoding="utf-8").read()
        for h in re.findall(r"#([0-9a-fA-F]{6})\b", src):
            r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
            self.assertLessEqual(max(r, g, b) - min(r, g, b), 90, f"#{h} is too saturated")


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        write(self.root, "app/main.py", "from core import engine\n")
        write(self.root, "core/engine.py", "from util import helpers\n")
        write(self.root, "util/helpers.py", "import json\n")
        write(self.root, "util/lonely.py", "x = 1\n")
        self.data = mapper.map_codebase(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_payload_has_both_views_with_layers(self):
        p = flow.payload(self.data)
        self.assertEqual(p["defaultView"], "folder")
        folders = {n["id"]: n for n in p["views"]["folder"]["nodes"]}
        self.assertEqual(folders["util"]["layer"], 0)
        self.assertEqual(folders["app"]["layer"], 2)
        files = {n["id"]: n for n in p["views"]["file"]["nodes"]}
        self.assertNotIn("util/lonely.py", files)  # no imports either way: not drawn
        self.assertEqual(p["views"]["file"]["standalone"], 1)
        self.assertEqual(files["core/engine.py"]["fan_in"], 1)
        self.assertEqual(files["core/engine.py"]["label"], "engine.py")
        self.assertIn({"s": "app/main.py", "t": "core/engine.py", "w": 1, "cyc": False}, p["views"]["file"]["edges"])

    def test_cycles_are_marked_on_edges(self):
        write(self.root, "core/engine.py", "from util import helpers\nfrom app import main\n")
        p = flow.payload(mapper.map_codebase(self.root))
        cyc_edges = [e for e in p["views"]["file"]["edges"] if e["cyc"]]
        self.assertTrue(cyc_edges)
        self.assertTrue(p["views"]["file"]["cycles"])

    def test_page_is_standalone_and_data_cannot_break_out(self):
        data = dict(self.data, name="</script><script>alert(1)</script>")
        page = flow.render_flow(data)
        self.assertNotIn("<script>alert(1)", page)
        self.assertNotIn("https://", page)
        self.assertNotIn("http://", page.replace("http://www.w3.org/2000/svg", ""))
        start = page.index('<script type="application/json" id="flow-data">') + len('<script type="application/json" id="flow-data">')
        blob = page[start:page.index("</script>", start)]
        self.assertEqual(json.loads(blob)["name"], data["name"])
        self.assertIn('href="flow.html"', page)

    def test_flow_css_uses_theme_variables_only(self):
        import re
        css = open(os.path.join(HERE, "..", "scripts", "assets", "flow.css"), encoding="utf-8").read()
        self.assertEqual(re.findall(r"#[0-9a-fA-F]{3,6}\b", css), [])

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_flow_js_parses(self):
        js = os.path.join(HERE, "..", "scripts", "assets", "flow.js")
        r = subprocess.run(["node", "--check", js], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class CliTests(unittest.TestCase):
    def test_cli_writes_json_and_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = os.path.join(tmp, "repo")
            write(repo, "m.py", "import os\n")
            out = os.path.join(tmp, "out")
            code = deep_dive.main([repo, "--out", out])
            self.assertEqual(code, 0)
            with open(os.path.join(out, "map.json"), encoding="utf-8") as f:
                self.assertEqual(json.load(f)["totals"]["files"], 1)
            self.assertTrue(os.path.getsize(os.path.join(out, "index.html")) > 1000)
            self.assertTrue(os.path.getsize(os.path.join(out, "explainer.html")) > 1000)
            self.assertTrue(os.path.getsize(os.path.join(out, "flow.html")) > 10000)


if __name__ == "__main__":
    unittest.main()
