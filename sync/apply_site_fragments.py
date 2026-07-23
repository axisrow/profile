#!/usr/bin/env python3
"""Apply generated profile fragments to the portfolio using stable markers.

This intentionally owns only generated Projects/Stars blocks and numeric
profile values. Presentation JavaScript and all other site markup stay under
the portfolio repository's control.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# Single source of truth for the profile snapshot counters: the order also
# fixes the rendered summary string, so adding a counter is a one-line change.
PROFILE_VALUE_KEYS: tuple[str, ...] = ("stars_earned", "merged_upstream_prs", "starred_projects")
SUMMARY_FORMAT = "{merged_upstream_prs} merged upstream PRs · {stars_earned} stars · {starred_projects} starred projects."


def _summary_regex(format_str: str) -> str:
    """Build a matcher from the format string: placeholders become ``\\d+`` and
    surrounding literal text is escaped, so the regex can never drift from the
    rendered summary text."""
    parts = re.split(r"(\{[^}]+\})", format_str)
    return "".join(r"\d+" if part.startswith("{") else re.escape(part) for part in parts)


def replace_marker(html: str, name: str, fragment: str) -> str:
    marker = re.escape(name.upper())
    pattern = re.compile(
        rf"(?ms)(^[ \t]*<!-- PROFILE:{marker}:START -->[ \t]*$).*?"
        rf"(^[ \t]*<!-- PROFILE:{marker}:END -->[ \t]*$)"
    )
    replacement = lambda match: f"{match.group(1)}\n{fragment.rstrip()}\n{match.group(2)}"
    updated, count = pattern.subn(replacement, html)
    if count != 1:
        raise ValueError(f"expected exactly one PROFILE:{name.upper()} marker block")
    return updated


def update_profile_values(html: str, stats: dict[str, int]) -> str:
    updated = html
    for key in PROFILE_VALUE_KEYS:
        value = str(int(stats[key]))
        pattern = re.compile(
            rf'(?s)(<span\b[^>]*\bdata-profile-value="{re.escape(key)}"[^>]*>).*?(</span>)'
        )

        def replace_value(match: re.Match[str]) -> str:
            opening = re.sub(r'(\bdata-target=")\d+(")', rf'\g<1>{value}\2', match.group(1))
            return f"{opening}{value}{match.group(2)}"

        updated, count = pattern.subn(replace_value, updated)
        if count < 1:
            raise ValueError(f"missing data-profile-value for {key}")

    summary = SUMMARY_FORMAT.format(**{k: int(stats[k]) for k in PROFILE_VALUE_KEYS})
    summary_pattern = re.compile(_summary_regex(SUMMARY_FORMAT))
    updated, count = summary_pattern.subn(summary, updated)
    if count < 1:
        raise ValueError("missing profile summary metadata")
    return updated


def apply_site_fragments(
    html: str,
    projects_fragment: str,
    stars_fragment: str,
    stats: dict[str, int],
) -> str:
    updated = replace_marker(html, "projects", projects_fragment)
    updated = replace_marker(updated, "stars", stars_fragment)
    return update_profile_values(updated, stats)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    parser.add_argument("--projects", type=Path, required=True)
    parser.add_argument("--stars", type=Path, required=True)
    parser.add_argument("--stats", type=Path, required=True)
    args = parser.parse_args()

    original = args.target.read_text()
    updated = apply_site_fragments(
        original,
        args.projects.read_text(),
        args.stars.read_text(),
        json.loads(args.stats.read_text()),
    )
    if updated != original:
        args.target.write_text(updated)
        print(f"updated {args.target}")
    else:
        print(f"unchanged {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
