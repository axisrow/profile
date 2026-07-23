from __future__ import annotations

import unittest
from pathlib import Path

from sync.apply_site_fragments import (
    PROFILE_VALUE_KEYS,
    SUMMARY_FORMAT,
    _summary_regex,
    apply_site_fragments,
    replace_marker,
)


class SiteSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html = """<head>
<meta content="1 merged upstream PRs · 2 stars · 3 starred projects.">
</head>
<body>
    <!-- PROFILE:PROJECTS:START -->
    <section id="projects">old</section>
    <!-- PROFILE:PROJECTS:END -->
    <span data-profile-value="stars_earned" data-target="2">2</span>
    <span data-profile-value="merged_upstream_prs" data-target="1">1</span>
    <span class="proof-stage-number"><span data-profile-value="merged_upstream_prs" data-target="1">1</span></span>
    <span data-profile-value="starred_projects" data-target="3">3</span>
    <!-- PROFILE:STARS:START -->
    <section id="stars">old</section>
    <!-- PROFILE:STARS:END -->
</body>
"""
        self.stats = {
            "stars_earned": 104,
            "merged_upstream_prs": 37,
            "starred_projects": 7,
        }

    def test_apply_is_marker_scoped_and_idempotent(self) -> None:
        projects = '    <section id="projects">new projects</section>\n'
        stars = '    <section id="stars">new stars</section>\n'
        once = apply_site_fragments(self.html, projects, stars, self.stats)
        twice = apply_site_fragments(once, projects, stars, self.stats)
        self.assertEqual(twice, once)
        self.assertIn("new projects", once)
        self.assertIn("new stars", once)
        self.assertIn('data-target="104">104</span>', once)
        self.assertEqual(once.count('data-profile-value="merged_upstream_prs" data-target="37">37'), 2)
        self.assertIn("37 merged upstream PRs · 104 stars · 7 starred projects.", once)

    def test_missing_marker_fails_without_guessing(self) -> None:
        with self.assertRaisesRegex(ValueError, "PROFILE:PROJECTS"):
            replace_marker("<main></main>", "projects", "<section></section>")

    def test_duplicate_marker_fails_without_partial_replacement(self) -> None:
        duplicated = self.html.replace("</body>", self.html.split("<body>", 1)[1])
        with self.assertRaisesRegex(ValueError, "PROFILE:PROJECTS"):
            replace_marker(duplicated, "projects", "<section></section>")

    def test_generated_sections_keep_the_new_visual_order_numbers(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        projects = (project_root / "sync/templates/projects.html.j2").read_text()
        stars = (project_root / "sync/templates/stars.html.j2").read_text()
        self.assertIn('<span>01</span> Momentum', stars)
        self.assertIn('<span>02</span> Selected Work', projects)

    def test_summary_format_is_single_source_of_truth(self) -> None:
        # The rendered summary and its matcher must derive from SUMMARY_FORMAT,
        # and every counter must be a placeholder so adding a key can't drift them.
        for key in PROFILE_VALUE_KEYS:
            self.assertIn("{" + key + "}", SUMMARY_FORMAT)
        self.assertEqual(
            _summary_regex(SUMMARY_FORMAT),
            r"\d+\ merged\ upstream\ PRs\ ·\ \d+\ stars\ ·\ \d+\ starred\ projects\.",
        )

    def test_stars_chart_geometry_is_not_hardcoded(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        stars = (project_root / "sync/templates/stars.html.j2").read_text()
        # Geometry must come from chart_data, not duplicated literals.
        self.assertNotIn("viewBox=\"0 0 960 340\"", stars)
        self.assertNotIn("x1=\"54\" x2=\"936\"", stars)
        self.assertNotIn("y=\"322\"", stars)
        self.assertIn("viewBox=\"0 0 {{ star_history.chart.width }} {{ star_history.chart.height }}\"", stars)
        self.assertIn("{{ star_history.chart.left }}", stars)
        self.assertIn("{{ star_history.chart.width - star_history.chart.right }}", stars)


if __name__ == "__main__":
    unittest.main()
