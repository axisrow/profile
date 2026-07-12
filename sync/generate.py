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
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    sys.exit("jinja2 is required: pip install jinja2")

ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / "templates"
OUT = Path("out")


def get_stars(handle: str, repos: list[str]) -> dict[str, int]:
    """Return {repo_name: star_count} via the GitHub REST API."""
    token = os.environ.get("GH_TOKEN", "")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "axisrow-profile-sync",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    stars: dict[str, int] = {}
    for name in repos:
        url = f"https://api.github.com/repos/{handle}/{name}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read().decode())
            stars[name] = int(data.get("stargazers_count", 0))
            print(f"  {name}: {stars[name]}★", file=sys.stderr)
        except Exception as e:
            print(f"  WARNING: {name}: could not fetch stars ({e})", file=sys.stderr)
            stars[name] = 0
    return stars


def main() -> int:
    cfg = json.loads((ROOT.parent / "projects.json").read_text())
    handle = os.environ.get("HANDLE") or str(cfg["handle"])

    all_repos = [r for group in cfg["projects"].values() for r in group]
    print(f"Fetching live star counts for {len(all_repos)} repos…", file=sys.stderr)
    stars = get_stars(handle, all_repos)
    cfg["stars"] = stars  # consumed by templates

    # README — plain text/markdown, no autoescaping. Canonical README style has
    # no trailing periods in descriptions; the site uses them. Strip in-template.
    def _strip_trailing_period(s: str) -> str:
        return s[:-1] if s.endswith(".") else s

    md_env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    md_env.filters["no_period"] = _strip_trailing_period
    readme = md_env.get_template("README.md.j2").render(**cfg)
    out_readme = OUT / "axisrow" / "README.md"
    out_readme.parent.mkdir(parents=True, exist_ok=True)
    out_readme.write_text(readme)
    print(f"wrote {out_readme} ({len(readme)} bytes)", file=sys.stderr)

    # HTML fragment — autoescape on (& → &amp;) so group names render safely.
    html_env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=True,
    )
    html = html_env.get_template("projects.html.j2").render(**cfg)
    out_html = OUT / "site" / "projects.html"
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(html)
    print(f"wrote {out_html} ({len(html)} bytes)", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
