#!/usr/bin/env python3
"""Codebase deep dive: map a repo, then write two standalone pages.

    python3 deep_dive.py /path/to/repo --out ./deep-dive

Writes into --out:
  explainer.html  the story: what it is, how it is organised, where to start
  index.html      the visuals: architecture, change risk, folders, hotspots
  flow.html       the interactive flow: drag, zoom, blast radius, import paths
  map.json        the raw map, for agents and scripts
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mapper import map_codebase  # noqa: E402
from pages import render_explainer, render_visuals  # noqa: E402
from flow import render_flow  # noqa: E402


def main(argv=None):
    p = argparse.ArgumentParser(prog="deep_dive", description=__doc__.split("\n")[0])
    p.add_argument("repo", help="folder to analyse")
    p.add_argument("--out", default="deep-dive", help="output folder")
    args = p.parse_args(argv)

    if not os.path.isdir(args.repo):
        p.error(f"not a directory: {args.repo}")

    data = map_codebase(args.repo)
    os.makedirs(args.out, exist_ok=True)
    outputs = {
        "map.json": json.dumps(data, indent=2, ensure_ascii=False),
        "index.html": render_visuals(data),
        "explainer.html": render_explainer(data),
        "flow.html": render_flow(data),
    }
    for name, content in outputs.items():
        with open(os.path.join(args.out, name), "w", encoding="utf-8") as f:
            f.write(content)

    t = data["totals"]
    print(f"mapped {t['files']} files, {t['lines']} lines, {t['internal_edges']} internal imports")
    for name in outputs:
        print(f"wrote {os.path.join(args.out, name)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
