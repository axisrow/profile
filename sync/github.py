"""Shared GitHub REST client used by the sync tools.

Both ``generate.get_stars`` and ``stars_history.api_get`` used to carry their
own copy of the same request plumbing (headers, ``GH_TOKEN`` auth, JSON
parsing) with *diverging* error handling. This module is the single source of
truth for that network step.

Callers decide how lenient to be via ``tolerate``: HTTP codes listed there are
returned as ``(data, status)`` instead of raising ``urllib.error.HTTPError``,
so a transient 403/404 on a stargazers feed or a private repo can be handled
locally without swallowing genuine failures.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

BASE_URL = "https://api.github.com"
USER_AGENT = "axisrow-profile-sync"
DEFAULT_ACCEPT = "application/vnd.github+json"


def _headers(accept: str | None) -> dict[str, str]:
    headers = {"Accept": accept or DEFAULT_ACCEPT, "User-Agent": USER_AGENT}
    if token := os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    return headers


def api_get(
    path: str,
    accept: str | None = None,
    *,
    timeout: float = 30,
    tolerate: tuple[int, ...] = (),
) -> tuple[list | dict | None, int]:
    """GET ``path`` from the GitHub API and parse the JSON body.

    ``path`` may be a bare path (``"repos/foo/bar"``) or a full URL. Returns
    ``(parsed_body, status)``. HTTP errors whose code is in ``tolerate`` are
    returned as ``(None, code)`` instead of raised, so callers can degrade
    gracefully; any other ``HTTPError`` (and non-HTTP errors) propagate.
    """
    url = path if path.startswith("http") else f"{BASE_URL}/{path}"
    request = urllib.request.Request(url, headers=_headers(accept))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode()
            data = json.loads(raw) if raw else None
            return data, response.status
    except urllib.error.HTTPError as error:
        if error.code in tolerate:
            return None, error.code
        raise


def paged(path: str, accept: str | None = None) -> list[dict]:
    """Walk ``per_page=100`` pagination over ``path`` and concatenate rows."""
    rows: list[dict] = []
    page = 1
    while True:
        separator = "&" if "?" in path else "?"
        batch, _ = api_get(f"{path}{separator}per_page=100&page={page}", accept)
        if not isinstance(batch, list):
            raise RuntimeError(f"Expected a list from {path}")
        rows.extend(batch)
        if len(batch) < 100:
            return rows
        page += 1
