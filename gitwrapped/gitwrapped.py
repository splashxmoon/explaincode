#!/usr/bin/env python3
"""gitwrapped: a year-in-review for your git history. No dependencies.

Reads a repo's commits for one year and prints a fun summary: streaks,
busiest day and hour, your coding persona, and your most-touched files.
It can also write a shareable SVG card. Everything runs locally; nothing is
uploaded.
"""
import argparse
import collections
import datetime as dt
import html
import json
import subprocess
import sys

MARK = "@@"
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def read_log(repo, year, author=None):
    cmd = [
        "git", "-C", repo, "log", "--numstat",
        f"--since={year}-01-01", f"--until={year + 1}-01-01",
        f"--pretty=format:{MARK}%H%x09%an%x09%aI%x09%s",
    ]
    if author:
        cmd.append(f"--author={author}")
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    return parse(out)


def parse(text):
    """Parse `git log --numstat` output produced with the MARK format."""
    commits = []
    cur = None
    for line in text.splitlines():
        if line.startswith(MARK):
            _hash, author, date, subject = line[len(MARK):].split("\t", 3)
            cur = {
                "author": author,
                "date": dt.datetime.fromisoformat(date),
                "subject": subject,
                "added": 0,
                "deleted": 0,
                "paths": [],
            }
            commits.append(cur)
        elif cur is not None and line.count("\t") == 2:
            added, deleted, path = line.split("\t")
            cur["added"] += int(added) if added.isdigit() else 0
            cur["deleted"] += int(deleted) if deleted.isdigit() else 0
            cur["paths"].append(path)
    return commits


def longest_streak(days):
    """Longest run of consecutive calendar days in a sorted list of dates."""
    if not days:
        return 0
    best = run = 1
    for prev, cur in zip(days, days[1:]):
        run = run + 1 if (cur - prev).days == 1 else 1
        best = max(best, run)
    return best


def persona(hours, total):
    """Pick a fun label from when in the day the commits happen."""
    if total == 0:
        return "Silent Observer"
    night = sum(v for h, v in hours.items() if h >= 22 or h < 5)
    morning = sum(v for h, v in hours.items() if 5 <= h < 9)
    if night / total >= 0.3:
        return "Night Owl"
    if morning / total >= 0.3:
        return "Early Bird"
    return "Steady Shipper"


def stats(commits):
    if not commits:
        return {"commits": 0, "persona": persona({}, 0)}
    days = sorted({c["date"].date() for c in commits})
    by_weekday = collections.Counter(WEEKDAYS[c["date"].weekday()] for c in commits)
    by_hour = collections.Counter(c["date"].hour for c in commits)
    by_month = collections.Counter(c["date"].strftime("%B") for c in commits)
    files = collections.Counter(p for c in commits for p in c["paths"])
    biggest = max(commits, key=lambda c: c["added"] + c["deleted"])
    return {
        "commits": len(commits),
        "active_days": len(days),
        "longest_streak_days": longest_streak(days),
        "lines_added": sum(c["added"] for c in commits),
        "lines_deleted": sum(c["deleted"] for c in commits),
        "busiest_weekday": by_weekday.most_common(1)[0][0],
        "busiest_hour": by_hour.most_common(1)[0][0],
        "busiest_month": by_month.most_common(1)[0][0],
        "top_files": files.most_common(5),
        "biggest_commit": {
            "subject": biggest["subject"],
            "lines_changed": biggest["added"] + biggest["deleted"],
        },
        "persona": persona(by_hour, len(commits)),
    }


def render_text(s, label):
    if s["commits"] == 0:
        return f"{label}: no commits found for that year."
    lines = [
        f"gitwrapped: {label}",
        "",
        f"  Persona            {s['persona']}",
        f"  Commits            {s['commits']}",
        f"  Active days        {s['active_days']}",
        f"  Longest streak     {s['longest_streak_days']} days in a row",
        f"  Lines              +{s['lines_added']} / -{s['lines_deleted']}",
        f"  Busiest day        {s['busiest_weekday']}",
        f"  Busiest hour       {s['busiest_hour']:02d}:00",
        f"  Busiest month      {s['busiest_month']}",
        f"  Biggest commit     {s['biggest_commit']['subject']} "
        f"({s['biggest_commit']['lines_changed']} lines)",
        "",
        "  Most-touched files:",
    ]
    lines += [f"    {count:>4}  {path}" for path, count in s["top_files"]]
    return "\n".join(lines)


def render_svg(s, label):
    """A 600x320 card suitable for sharing."""
    if s["commits"] == 0:
        raise ValueError("no commits to draw")
    rows = [
        ("Persona", s["persona"]),
        ("Commits", str(s["commits"])),
        ("Longest streak", f"{s['longest_streak_days']} days"),
        ("Busiest day", s["busiest_weekday"]),
        ("Lines", f"+{s['lines_added']} / -{s['lines_deleted']}"),
    ]
    body = []
    for i, (k, v) in enumerate(rows):
        y = 130 + i * 34
        body.append(
            f'<text x="40" y="{y}" fill="#8b949e" font-size="16">{html.escape(k)}</text>'
            f'<text x="260" y="{y}" fill="#e6edf3" font-size="18" font-weight="600">'
            f"{html.escape(v)}</text>"
        )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="320" viewBox="0 0 600 320">'
        '<rect width="600" height="320" rx="16" fill="#0d1117"/>'
        f'<text x="40" y="60" fill="#e6edf3" font-size="26" font-weight="700">'
        f"{html.escape(label)}</text>"
        '<text x="40" y="92" fill="#58a6ff" font-size="14">gitwrapped</text>'
        + "".join(body)
        + "</svg>"
    )


def default_author(repo):
    try:
        out = subprocess.run(
            ["git", "-C", repo, "config", "user.name"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return out or None
    except subprocess.CalledProcessError:
        return None


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="gitwrapped",
        description="A year-in-review for your git history.",
    )
    p.add_argument("repo", nargs="?", default=".", help="path to a git repo")
    p.add_argument("--year", type=int, default=dt.date.today().year)
    p.add_argument("--author", help="author name or email to match (default: your git user)")
    p.add_argument("--all-authors", action="store_true", help="include everyone")
    p.add_argument("--json", action="store_true", help="print stats as JSON")
    p.add_argument("--svg", metavar="FILE", help="write a shareable SVG card to FILE")
    args = p.parse_args(argv)

    author = None if args.all_authors else (args.author or default_author(args.repo))
    try:
        commits = read_log(args.repo, args.year, author)
    except subprocess.CalledProcessError as e:
        p.error(f"git failed in {args.repo}: {e.stderr.strip()}")

    label = f"{author or 'everyone'} in {args.year}"
    s = stats(commits)
    if args.json:
        print(json.dumps(s, indent=2, default=str))
    else:
        print(render_text(s, label))
    if args.svg:
        if s["commits"] == 0:
            print("no commits, so no card was written", file=sys.stderr)
            return 1
        with open(args.svg, "w", encoding="utf-8") as f:
            f.write(render_svg(s, label))
        print(f"\nwrote card to {args.svg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
