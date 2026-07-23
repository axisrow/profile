#!/usr/bin/env python3
"""Build a durable daily history of stars on axisrow's original repositories.

GitHub exposes timestamps for current stargazers but no unstar events.  The
first run restores every available event from START_DATE; later runs preserve
that history and append newly observed events only.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

# This script is invoked directly by the CI workflow (`python3 sync/...`), which
# puts its own directory on sys.path[0] instead of the repo root. Absolute
# ``from sync import ...`` needs the repo root on the path, so add it here.
_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sync import github  # noqa: E402  (path bootstrap must precede this import)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HISTORY = ROOT / "data" / "stars-history.json"


def api_get(path: str, accept: str | None = None) -> list[dict] | dict:
    """Thin wrapper preserving the historical return shape for local callers."""
    data, _ = github.api_get(path, accept)
    if data is None:
        raise RuntimeError(f"Empty response from {path}")
    return data


def paged(path: str, accept: str | None = None) -> list[dict]:
    return github.paged(path, accept)


def installation_repositories() -> list[dict]:
    """List repositories available to a GitHub App installation token."""
    repos: list[dict] = []
    page = 1
    while True:
        payload = api_get(f"installation/repositories?per_page=100&page={page}")
        if not isinstance(payload, dict) or not isinstance(payload.get("repositories"), list):
            raise RuntimeError("Expected an installation repository response")
        batch = payload["repositories"]
        repos.extend(batch)
        if len(batch) < 100:
            return repos
        page += 1


def owned_original_repositories(handle: str) -> list[dict]:
    """List repositories visible to this token, preferring App-installation scope."""
    try:
        repos = installation_repositories()
    except urllib.error.HTTPError as error:
        if error.code not in {401, 403, 404}:
            raise
        try:
            repos = paged("user/repos?affiliation=owner&visibility=all")
        except urllib.error.HTTPError:
            repos = paged(f"users/{urllib.parse.quote(handle)}/repos?type=owner")
    return [
        repo for repo in repos
        if (
            repo.get("owner", {}).get("login", "").lower() == handle.lower()
            and not repo.get("fork")
            and int(repo.get("stargazers_count", 0)) > 0
        )
    ]


def star_dates(repo: str, start: date) -> Counter[date]:
    try:
        events = paged(f"repos/{repo}/stargazers", "application/vnd.github.star+json")
    except urllib.error.HTTPError as error:
        # Installation tokens can list a repository but still lack permission to
        # enumerate its stargazers. Existing history remains authoritative; a
        # skipped private repo must not make the daily site sync fail.
        if error.code not in {403, 404}:
            raise
        print(f"  WARNING: {repo}: cannot enumerate stargazers ({error.code})", file=sys.stderr)
        return Counter()
    dates: Counter[date] = Counter()
    for event in events:
        starred_at = event.get("starred_at")
        if not starred_at:
            continue
        starred_on = datetime.fromisoformat(starred_at.replace("Z", "+00:00")).date()
        if starred_on >= start:
            dates[starred_on] += 1
    return dates


def dates_between(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def build_history(handle: str, start: date, target_initial_total: int, history: dict | None) -> dict:
    repos = owned_original_repositories(handle)
    events: Counter[date] = Counter()
    for repo in repos:
        full_name = str(repo["full_name"])
        repo_events = star_dates(full_name, start)
        events.update(repo_events)
        print(f"  {full_name}: {sum(repo_events.values())} events since {start}", file=sys.stderr)

    today = datetime.now(UTC).date()
    if history:
        entries = list(history["entries"])
        last_date = date.fromisoformat(entries[-1]["date"])
        total = int(entries[-1]["total"])
        begin = last_date + timedelta(days=1)
    else:
        observed = sum(events.values())
        opening_balance = target_initial_total - observed
        if opening_balance < 0:
            raise RuntimeError("Recovered events exceed the declared initial total")
        entries = []
        total = opening_balance
        begin = start

    for day in dates_between(begin, today) if begin <= today else []:
        gained = events[day]
        total += gained
        entries.append({"date": day.isoformat(), "gained": gained, "total": total})

    return {
        "scope": "Original axisrow repositories; forks excluded",
        "start_date": start.isoformat(),
        "opening_balance": entries[0]["total"] - entries[0]["gained"],
        "target_initial_total": target_initial_total,
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    args = parser.parse_args()
    config = json.loads((ROOT / "projects.json").read_text())
    stats = config["stats"]
    start = date.fromisoformat(stats["star_history_start"])
    target_initial_total = int(stats["stars_earned"]) - int(stats["fork_stars"])
    prior = json.loads(args.history.read_text()) if args.history.exists() else None
    print("Fetching star events…", file=sys.stderr)
    history = build_history(str(config["handle"]), start, target_initial_total, prior)
    args.history.parent.mkdir(parents=True, exist_ok=True)
    args.history.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {args.history} ({len(history['entries'])} daily points)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
