# profile

**Single source of truth for my GitHub profile** — the README on
[`github.com/axisrow`](https://github.com/axisrow) and the Projects section on
[axisrow.github.io](https://axisrow.github.io) are **generated from here**.

## How it works

```
projects.json  ──▶ sync/generate.py  ──▶  out/axisrow/README.md        ──▶  axisrow/axisrow
                       (live stars        out/site/projects.html        ──▶  axisrow.github.io
                        from GitHub API)
```

- Edit `projects.json` (descriptions, grouping, contributions, stats) — commit to `main`.
- A GitHub Actions workflow (`.github/workflows/sync.yml`) runs on every push to
  `projects.json`/`sync/**`, on a weekly cron, and on manual dispatch.
- It mints a short-lived GitHub App installation token via [`pat`](https://github.com/etopro/plugin-marketplace/tree/main/plugins/pat)
  (CI mode — PEM from the `APP_PRIVATE_KEY` secret, **no Bitwarden in CI**),
  pulls live star counts, renders both outputs, and cross-pushes them to the two
  output repos as `axisrow-ci[bot]`.

## Edit content

Change `projects.json` only. The generated files live in `out/` (gitignored) and
in the output repos — never edit them there directly.

To preview locally:

```bash
GH_TOKEN="$(bash /path/to/pat/scripts/pat.sh token)" python3 sync/generate.py
diff out/axisrow/README.md <(gh api repos/axisrow/axisrow/contents/README.md -q .content | base64 -d)
```

## Secrets (in `axisrow/profile` → Settings → Secrets)

- `APP_PRIVATE_KEY` — the `axisrow-ci` GitHub App private key (PEM). One-time,
  never expires; `pat` mints a fresh 1h token from it on every run.
- `PAT_APP_ID` — `4278593` (the App ID; not secret).

## Honest numbers

`projects.json` tracks a fixed set of repos (the starred ones). New repos are not
added automatically — only the ones listed. Per-repo star counts are pulled live
from the GitHub API on each run; the aggregate stats (`stars_earned`,
`merged_upstream_prs`) are verified snapshots that you refresh manually.
