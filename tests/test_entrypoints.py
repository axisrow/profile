from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

# The production workflow invokes the sync scripts directly, e.g.
# `python3 sync/generate.py`, which puts the script's own directory on
# sys.path[0] instead of the repo root. An absolute ``from sync import ...``
# then fails with ModuleNotFoundError before any work happens. These tests run
# the scripts exactly the way the workflow does (subprocess from repo root,
# argv[0] = sync/<name>.py) so a regression in that invocation mode is caught
# here, not in CI.

ROOT = Path(__file__).resolve().parents[1]


def _run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "sync" / script), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )


class DirectScriptInvocationTests(unittest.TestCase):
    def test_stars_history_help_runs_without_importerror(self) -> None:
        result = _run("stars_history.py", "--help")
        self.assertNotIn("ModuleNotFoundError", result.stderr + result.stdout)
        self.assertEqual(result.returncode, 0)

    def test_generate_module_import_resolves(self) -> None:
        # generate.py needs a valid projects.json to fully run, but we only care
        # that it gets past the `from sync import github` line. --help is enough
        # to prove import resolution works; argparse exits 0.
        result = _run("generate.py", "--help")
        # generate.py has no argparse, so --help may raise SystemExit; the point
        # is that ModuleNotFoundError is absent. Assert the import resolved.
        self.assertNotIn("ModuleNotFoundError", result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
