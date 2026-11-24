---
name: codebase-deep-dive
description: "Explain a codebase and visualise it as three standalone pages: an explainer (what the project is, how it is organised, where to start reading, what to watch), a visuals page (layered architecture diagram, change-risk map, folder treemap, language mix, hotspots) and an interactive flow explorer (draggable, zoomable dependency graph with blast radius, import-path tracing, folder drill-down, search and SVG export). Use when someone asks to understand, onboard to, map, audit the shape of, or 'deep dive' a repository, asks where to start reading, what depends on what, what a change would affect, or wants a diagram, architecture view or visual of their code. Works offline with Python 3 only. Reads imports for Python and JavaScript/TypeScript; other languages get size and language stats only."
license: MIT
compatibility: Python 3.9 or later. No third-party packages, no network access.
---

# Codebase Deep Dive

Make a repo understandable at a glance. One scan produces a plain-English explainer, a set of senior-level diagrams, an interactive flow explorer, and the raw numbers. Read the numbers, explain them in words, and show the pages.

## Design rules (follow them every time)

These are not optional. They apply to the pages, to any extra diagram you draw, and to your chat summary.

1. **Muted palette only.** Use the theme variables (`--bg`, `--surface`, `--fg`, `--muted`, `--accent`, `--bad`, `--good`, `--series-1` to `--series-8`). The palette is slate, sage, sand, clay and stone. Do not add pure or saturated colours (no neon, no `#ff0000`-style reds, greens or blues, no gradient text). Red is reserved for cycles (`--bad`), and even that stays brick, not alarm red.
2. **Flow, not clutter.** Architecture is a top-to-bottom dependency flow: consumers at the top, foundations at the bottom, one arrow per dependency, with the arrow direction stated on the chart. Limit each box to a name and two numbers. Do not add decorative shapes, icons or drop shadows.
3. **Say what the picture means.** Every diagram carries a one-line caption or legend that says how to read it.
4. **Three pages, one theme.** The explainer tells the story, the visuals page shows the structure, and the flow page lets people explore it. No page loads anything from the network: scripts and styles are inlined.
5. **Quote, don't round.** Numbers come from `map.json` exactly.

## When to use

- "Explain this codebase", "where do I start?", "what does this repo do?"
- "What depends on this file?", "what would break if I change X?"
- "Show me a diagram of the architecture", "visualise the code", "flow diagram"
- Onboarding a new contributor, or reviewing a repo you don't know

## Steps

1. Run the tool. Write output to a folder outside the repo so nothing is committed by accident:

   ```sh
   python3 <skill-dir>/scripts/deep_dive.py <repo> --out /tmp/deep-dive
   ```

   It writes four files:
   - `explainer.html`: the story. Open this first for someone new to the code.
   - `index.html`: the visuals: architecture, change risk, folders, languages, hotspots.
   - `flow.html`: the interactive flow explorer. Open this when someone asks what a change affects, how two parts connect, or wants to explore.
   - `map.json`: the raw numbers, for you to read.

2. Read `map.json`. The useful fields:
   - `totals` and `languages`: scale and mix
   - `entry_points`: where to start reading
   - `architecture.layer_of`, `architecture.cycles`: the dependency flow
   - `files[*].imports`, `fan_in`, `fan_out`: what depends on what
   - `external_packages`: third-party dependencies

3. Write the explanation in chat, based on the map, not on guesses:
   - What the project is for, in one or two sentences. Confirm it with the README or the entry points.
   - The main folders and what each holds.
   - The files with the widest blast radius (highest `fan_in`), and why a change there needs care.
   - Where to start reading, in order.
   - What the map cannot show (see Limits).

4. Answer questions with the flow page, using a link that opens the exact view. The page reads its state from the URL hash:
   - `flow.html#view=file&focus=<path>`: select a file and frame it with its neighbours (blast radius shown).
   - `&mode=up` (dependencies), `&mode=both`, `&depth=1` or `&depth=2`: change what is highlighted.
   - `&trace=<other path>`: show the shortest import path from `focus` to it.
   - `#view=file&scope=<folder>`: one folder's files, with the outside files they touch drawn dashed.
   - `#view=folder`, `&layout=force`: the folder view, or the organic layout.
   Paths are repo-relative, as in `map.json`, and URL-encoded (`/` becomes `%2F`).

5. Show the pages. Serve the output folder with `python3 -m http.server` in the background and open `explainer.html`, `index.html` or a `flow.html#…` link with Friday's `show_preview`. Check the visuals and flow pages with `preview_screenshot` before you call them done: the colours must be muted, the arrows must read top to bottom, and the legend must be visible. If not, fix the renderer and rerun. Without Friday, give the file paths.

## Reading the pages

**Explainer (`explainer.html`)**
- Overview: what the project is and its shape at a glance.
- How it is organised: the dependency layers, foundations (Layer 0) up to consumers.
- Where to start reading: the entry points, then the foundation layer, so each part is read before the parts that use it.
- What to watch: circular dependencies and the most depended-on file.
- External dependencies, and how the numbers were made.

**Flow (`flow.html`)**
- Two views: **Folders** (top-level folders and the imports between them) and **Files**. Folders is the default when folders form layers. Otherwise Files is.
- **Layered** layout: one band per dependency layer, entry points at the top, foundations at the bottom, ordered to reduce crossings. **Organic** layout: a force layout that still keeps each layer at its height, so the flow stays top to bottom.
- **Click** a node: the panel shows lines, layer, direct and all-level fan-in and fan-out, a role (stable core, hub, orchestrator, leaf), what may break if it changes (grouped by steps away), what it depends on, and its external packages. The canvas highlights the blast radius (clay), the dependencies (slate) or both, to 1 hop, 2 hops or all.
- **Shift-click** a second node, or use "Trace path to…": the shortest import chain between the two, with its direction explained.
- **Drag** to rearrange (dragged nodes stay pinned), **pan**, **scroll to zoom**, use the **minimap** and **Fit**. **Double-click** a folder to open its files.
- **Find** (`/`), folder chips to hide or show folders, "Start here" for the most depended-on files, entry points and cycles.
- **Export SVG** downloads exactly what is on screen. **Copy link** copies a URL that reopens this view.
- Keys: `/` find, `F` fit, `L` layout, `1`/`2` view, `+`/`-` zoom, `Esc` clear.
- Limits: files with no in-repo imports either way are not drawn (the sidebar says how many). Above 600 linked files, the smallest are left out.

**Visuals (`index.html`)**
- **Architecture flow:** folders in dependency layers. Arrows point from a folder to what it depends on. Dashed red boxes are in a cycle and should be treated as one unit.
  If folders never import each other (common in single-package repos), the flow switches to files, and the caption says so. `map.json` records which one it used in `architecture.granularity`.
- **Change risk:** each bubble is a file. Right means it depends on many files, up means many depend on it, size is lines. The top-left stable core is safe to build on but costly to change; the top-right hub is the riskiest place to edit.
- **Where the code lives:** a treemap of folders by lines, with subfolders inside.
- **Languages** and **Hotspots:** the language mix, the largest files, and the most depended-on files.

## Limits to state when relevant

- Only static `import`, `from ... import`, `require()` and `export ... from` are followed. Dynamic imports, string-built paths, plugin loading and framework conventions (for example, file-based routing) are not.
- Python: absolute imports resolve from the repo root, `src/` or `lib/`. A bare module name is matched only when exactly one file has that name. Standard-library imports are excluded from external dependencies.
- JavaScript/TypeScript: relative imports resolve with the common extensions and `index` files. Node built-ins are excluded from external dependencies.
- Other languages (Go, Rust, Java and so on) get size and language stats only.
- `node_modules`, `venv`, `dist`, `build`, `vendor`, hidden folders and binary files are skipped. Files over 1 MB are skipped.

## Quality bar

- Don't claim a dependency or call path the map doesn't show.
- Quote numbers from `map.json` exactly.
- If the explanation depends on a README or a comment, say so.
- If you add any diagram of your own, follow the design rules above.

## Scripts

- `scripts/mapper.py`: builds the map (sizes, imports, folder layers, cycles, fan-in and fan-out). Library, no dependencies.
- `scripts/renderer.py`: the diagrams (architecture flow, change-risk quadrant, treemap, language bar, hotspots). Library, no network.
- `scripts/pages.py`: the shared theme and shell, plus the explainer and visuals pages. Library, no network, no external assets.
- `scripts/flow.py`: builds the flow graph (folder and file views, layers, cycles) and the flow page.
- `scripts/assets/flow.js`, `scripts/assets/flow.css`: the explorer (plain JavaScript, no libraries), inlined into `flow.html`.
- `scripts/deep_dive.py`: command-line entry point; writes `explainer.html`, `index.html`, `flow.html` and `map.json`.
- `tests/test_deep_dive.py`: run with `python3 -m unittest -v tests/test_deep_dive.py`.
