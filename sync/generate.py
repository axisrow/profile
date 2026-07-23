#!/usr/bin/env python3
"""Render README.md (for axisrow/axisrow) and a site Projects-fragment (for
axisrow.github.io) from projects.json, enriching per-repo star counts from the
GitHub API.

Env:
  GH_TOKEN  — token authorized to read public repos (installation token in CI,
              `gh auth token` locally). Falls back to unauthenticated requests
              (rate-limited) if unset.
  HANDLE    — override the handle from projects.json (rarely needed).

Outputs (relative to cwd):
  out/axisrow/README.md
  out/site/projects.html
  out/site/stats.json
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

# This script is invoked directly by the CI workflow (`python3 sync/...`), which
# puts its own directory on sys.path[0] instead of the repo root. Absolute
# ``from sync import ...`` needs the repo root on the path, so add it here.
_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sync import github  # noqa: E402  (path bootstrap must precede this import)

try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    sys.exit("jinja2 is required: pip install jinja2")

ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / "templates"
OUT = Path("out")


def chart_data(history: dict) -> dict:
    """Prepare a compact, responsive SVG line-chart from daily cumulative data."""
    entries = history["entries"]
    width, height = 960, 340
    left, right, top, bottom = 54, 24, 22, 42
    plot_width, plot_height = width - left - right, height - top - bottom
    maximum = max(entry["total"] for entry in entries)
    ceiling = max(10, ((maximum + 9) // 10) * 10)

    def x(index: int) -> float:
        return left + plot_width * index / max(1, len(entries) - 1)

    def y(value: int) -> float:
        return top + plot_height * (1 - value / ceiling)

    points = " ".join(f"{x(i):.1f},{y(entry['total']):.1f}" for i, entry in enumerate(entries))
    ticks = [0, ceiling // 2, ceiling]
    month_labels = []
    for index, entry in enumerate(entries):
        current = date.fromisoformat(entry["date"])
        if current.day == 1 or index == 0:
            month_labels.append({"x": f"{x(index):.1f}", "label": current.strftime("%b")})
    return {
        "points": points,
        "end_x": f"{x(len(entries) - 1):.1f}",
        "end_y": f"{y(entries[-1]['total']):.1f}",
        "latest_total": entries[-1]["total"],
        "latest_date": entries[-1]["date"],
        "ticks": [{"value": tick, "y": f"{y(tick):.1f}"} for tick in ticks],
        "months": month_labels,
        # Geometry — single source of truth shared with stars.html.j2 so the
        # grid/labels stay aligned when width/height/margins change.
        "width": width,
        "height": height,
        "left": left,
        "right": right,
        "bottom": bottom,
    }


def get_stars(handle: str, repos: list[str]) -> dict[str, int]:
    """Return {repo_name: star_count} via the GitHub REST API.

    Any network or HTTP failure for a single repo degrades to ``0`` with a
    WARNING on stderr, so one unreachable repo never aborts the whole render.
    Requests use the shared client's default 30s timeout (previously 15s when
    this owned its own urllib call).
    """
    stars: dict[str, int] = {}
    for name in repos:
        path = f"repos/{handle}/{name}"
        try:
            data, _ = github.api_get(path)
            stars[name] = int(data.get("stargazers_count", 0) if isinstance(data, dict) else 0)
            print(f"  {name}: {stars[name]}★", file=sys.stderr)
        except Exception as e:
            print(f"  WARNING: {name}: could not fetch stars ({e})", file=sys.stderr)
            stars[name] = 0
    return stars


def make_env(templates_dir: Path, *, autoescape: bool) -> Environment:
    """Build a Jinja2 Environment sharing the project's common loader/options."""
    return Environment(
        loader=FileSystemLoader(str(templates_dir)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=autoescape,
    )


def write_output(path: Path, content: str) -> Path:
    """Create parent dirs, write `content` to `path`, and log the byte count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    print(f"wrote {path} ({len(content)} bytes)", file=sys.stderr)
    return path


def load_history(cfg: dict) -> dict | None:
    """Load stars-history.json, attach chart data, and recompute stars_earned."""
    history_path = ROOT.parent / "data" / "stars-history.json"
    if not history_path.exists():
        return None
    history = json.loads(history_path.read_text())
    cfg["stats"] = dict(cfg["stats"])
    cfg["stats"]["stars_earned"] = (
        history["entries"][-1]["total"] + int(cfg["stats"]["fork_stars"])
    )
    return {**history, "chart": chart_data(history)}


def main() -> int:
    cfg = json.loads((ROOT.parent / "projects.json").read_text())
    handle = os.environ.get("HANDLE") or str(cfg["handle"])

    all_repos = [r for group in cfg["projects"].values() for r in group]
    print(f"Fetching live star counts for {len(all_repos)} repos…", file=sys.stderr)
    cfg["stars"] = get_stars(handle, all_repos)  # consumed by templates

    history = load_history(cfg)
    if history is not None:
        cfg["star_history"] = history

    # README — plain text/markdown, no autoescaping. Canonical README style has
    # no trailing periods in descriptions; the site uses them. Strip in-template.
    md_env = make_env(TEMPLATES, autoescape=False)
    md_env.filters["no_period"] = lambda s: s[:-1] if s.endswith(".") else s
    readme = md_env.get_template("README.md.j2").render(**cfg)
    write_output(OUT / "axisrow" / "README.md", readme)

    # HTML fragment — autoescape on (& → &amp;) so group names render safely.
    html_env = make_env(TEMPLATES, autoescape=True)
    html = html_env.get_template("projects.html.j2").render(**cfg)
    write_output(OUT / "site" / "projects.html", html)

    if history is not None:
        stars_html = html_env.get_template("stars.html.j2").render(**cfg)
        write_output(OUT / "site" / "stars.html", stars_html)

    # The rest of the site is maintained in axisrow.github.io, but these
    # profile-wide snapshot stats appear in its hero, metadata and timeline.
    # Keep them generated from the same source of truth as the project cards.
    out_stats = OUT / "site" / "stats.json"
    write_output(out_stats, json.dumps(cfg["stats"], ensure_ascii=False) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
