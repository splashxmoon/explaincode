#!/usr/bin/env python3
"""buildwatch: see what changed between two builds. No dependencies.

Compare two files, or two directories, such as two releases of an app, two
firmware images, or two extracted packages. It reports added, removed and
changed files. For changed and new files it lists the printable strings that
appeared or disappeared, and flags new network endpoints and secret-looking
values, which are often the first thing a reviewer wants to see.

Secret values are redacted in all output.
"""
import argparse
import hashlib
import json
import os
import re
import sys

MIN_STRING = 6
STRING_RE = re.compile(rb"[\x20-\x7e]{%d,}" % MIN_STRING)
CATEGORIES = {
    "url": re.compile(r"https?://[^\s\"'<>]+"),
    "ip": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "secret": re.compile(
        r"AKIA[0-9A-Z]{16}"
        r"|-----BEGIN [A-Z ]*PRIVATE KEY-----"
        r"|(?i:api[_-]?key|secret|token|passwd|password)\s*[=:]\s*\S{6,}"
    ),
}
SAMPLE_LIMIT = 20


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def list_files(root):
    """Map relative path -> absolute path for every regular file under root."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in filenames:
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                continue
            out[os.path.relpath(full, root)] = full
    return out


def load(old, new):
    """Return (old_map, new_map) keyed by the name shown in the report."""
    if os.path.isfile(old):
        key = os.path.basename(new)
        return {key: old}, {key: new}
    return list_files(old), list_files(new)


def strings_of(path):
    with open(path, "rb") as f:
        data = f.read()
    return {m.decode("ascii") for m in STRING_RE.findall(data)}


def hits_in(strings):
    """Return the set of (category, matched text) pairs found in strings."""
    hits = set()
    for s in strings:
        for cat, rx in CATEGORIES.items():
            for m in rx.finditer(s):
                hits.add((cat, m.group(0)))
    return hits


def redact(category, value):
    if category == "secret":
        return value[:4] + "…"
    return value


def findings_for(path, hits):
    return [
        {"file": path, "category": cat, "value": redact(cat, val)}
        for cat, val in sorted(hits)
    ]


def compare(old_map, new_map):
    report = {
        "added": [],
        "removed": [],
        "changed": {},
        "unchanged": 0,
        "findings": [],
    }
    for key in sorted(set(old_map) - set(new_map)):
        report["removed"].append(key)
    for key in sorted(set(new_map) - set(old_map)):
        report["added"].append(key)
        new_strings = strings_of(new_map[key])
        report["findings"] += findings_for(key, hits_in(new_strings))
    for key in sorted(set(old_map) & set(new_map)):
        if sha256(old_map[key]) == sha256(new_map[key]):
            report["unchanged"] += 1
            continue
        old_strings = strings_of(old_map[key])
        new_strings = strings_of(new_map[key])
        added = new_strings - old_strings
        removed = old_strings - new_strings
        report["changed"][key] = {
            "old_size": os.path.getsize(old_map[key]),
            "new_size": os.path.getsize(new_map[key]),
            "added_strings_count": len(added),
            "removed_strings_count": len(removed),
            "added_sample": _safe_sample(added),
            "removed_sample": _safe_sample(removed),
        }
        report["findings"] += findings_for(key, hits_in(added))
    # Deduplicate, keeping one line per (file, category, value).
    seen = set()
    unique = []
    for f in report["findings"]:
        k = (f["file"], f["category"], f["value"])
        if k not in seen:
            seen.add(k)
            unique.append(f)
    report["findings"] = unique
    return report


def _safe_sample(strings):
    """Sample of strings for display; lines holding secrets are left out."""
    sample = []
    for s in sorted(strings):
        if CATEGORIES["secret"].search(s):
            continue
        sample.append(s[:200])
        if len(sample) >= SAMPLE_LIMIT:
            break
    return sample


def render(report, limit):
    lines = []
    lines.append(
        f"added: {len(report['added'])}  removed: {len(report['removed'])}  "
        f"changed: {len(report['changed'])}  unchanged: {report['unchanged']}"
    )
    if report["added"]:
        lines.append("\nAdded files:")
        lines += [f"  + {p}" for p in report["added"][:limit]]
    if report["removed"]:
        lines.append("\nRemoved files:")
        lines += [f"  - {p}" for p in report["removed"][:limit]]
    if report["changed"]:
        lines.append("\nChanged files:")
        for path, d in list(report["changed"].items())[:limit]:
            lines.append(
                f"  ~ {path}  ({d['old_size']} -> {d['new_size']} bytes, "
                f"+{d['added_strings_count']} / -{d['removed_strings_count']} strings)"
            )
            for s in d["added_sample"][:5]:
                lines.append(f"      + {s}")
    if report["findings"]:
        lines.append("\nNew endpoints and secret-like values to review:")
        for f in report["findings"][:limit * 2]:
            lines.append(f"  [{f['category']}] {f['file']}: {f['value']}")
    else:
        lines.append("\nNo new endpoints or secret-like values found.")
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="buildwatch",
        description="Compare two builds (files or directories) and report what changed.",
    )
    p.add_argument("old", help="older build: file or directory")
    p.add_argument("new", help="newer build: file or directory")
    p.add_argument("--json", action="store_true", help="print the report as JSON")
    p.add_argument("--limit", type=int, default=15, help="max items per section (text output)")
    p.add_argument(
        "--fail-on-flags",
        action="store_true",
        help="exit 1 if any new endpoint or secret-like value is found (for CI)",
    )
    args = p.parse_args(argv)

    for path in (args.old, args.new):
        if not os.path.exists(path):
            p.error(f"not found: {path}")
    if os.path.isfile(args.old) != os.path.isfile(args.new):
        p.error("compare two files or two directories, not one of each")

    old_map, new_map = load(args.old, args.new)
    report = compare(old_map, new_map)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render(report, args.limit))
    return 1 if (args.fail_on_flags and report["findings"]) else 0


if __name__ == "__main__":
    sys.exit(main())
