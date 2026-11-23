"""The case selector distinguishes measured patch effects from evidence alone."""

import itertools
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from sitebuild import comparison


class ComparisonScopeTests(unittest.TestCase):
    def test_counts_only_run_with_no_download_page(self):
        site = SimpleNamespace(walk_page="build.html", patched_page=None, triage={"findings": []})
        diagnostics = {
            "title": "Measured build", "states": [{"label": "Reference"}, {"label": "Rebuild"}],
            "items_count": {"all": 4}, "item": {"one": "product", "many": "products"},
            "indicators": [{"id": "test", "name": "Impact"}], "steps": [{}],
            "counts": {"total": {"test": {"classes": {"agrees": 3, "differs": 1}}}},
        }
        html = comparison.opening(site, None, diagnostics, ("build.html#run", "Run"),
                                  {"headline_indicator": "test"}, str)
        self.assertIn('href="build.html">Build</a>', html)
        self.assertIn('href="build.html#run">Build record', html)
        self.assertIn("4 products", html)
        self.assertIn("Agrees 3 · Differs 1", html)

    def test_a_zero_change_measurement_requires_a_recorded_cause(self):
        site = SimpleNamespace(label=str)
        case = {"id": "F1", "stage": "filed", "patches": [{"id": "0001", "slug": "heat"}]}
        data = {"items": {"one": "dataset", "many": "datasets"},
                "causes": [{"id": "0001-heat", "title": "Heat input", "moved": 0, "rows": 1}]}
        measured = comparison.case_result(site, case, data)
        self.assertIn("0 datasets with changed impact results", measured)
        no_cause = comparison.case_result(site, case, None)
        self.assertIn("no separate impact measurement", no_cause)
        self.assertNotIn("0 datasets", no_cause)
        self.assertIn('href="cases/F1.html#case-sources"', no_cause)


    def test_every_registered_case_selection_has_its_own_audited_build(self):
        root = Path(__file__).resolve().parents[2]
        config = json.loads((root / "site/config.json").read_text())["verified_build"]["step_diagnostics"]
        sets = json.loads((root / config["case_sets"]["snapshot"]).read_text())
        builds = {frozenset(b["patches"]): b for b in sets["builds"]}
        cases = sets["cases"]
        for size in range(len(cases) + 1):
            for chosen in itertools.combinations(cases, size):
                wanted = frozenset(p for case in chosen for p in cases[case])
                build = builds[wanted]
                self.assertEqual(len(build["inventory_sha256"]), 64)
                outcome = sets["outcomes"][build["score_sha256"]]
                self.assertEqual(set(outcome["by_indicator"]), set(sets["indicators"]))
                self.assertLessEqual(set(outcome["rows"]), set(sets["listed_datasets"]))
        # Non-adjacent cases retain their joint result, and metadata fixes still record inventory edits.
        strawberry = builds[frozenset(cases["F1"] + cases["F8"])]
        self.assertEqual(sum(sets["outcomes"][strawberry["score_sha256"]]["by_indicator"].values()), 75)
        locations = builds[frozenset(cases["F3"])]
        self.assertEqual((locations["edits"], locations["datasets_edited"]), (25, 25))
        self.assertEqual(sets["outcomes"][locations["score_sha256"]]["changed_datasets"], 0)
        with patch("sitebuild.lastrun.verified_build", return_value={"step_diagnostics": config}):
            self.assertIsNone(comparison.measured_sets(SimpleNamespace(root=root), {}, {"different": "release"}, {"steps": []}))
