"""The case selector distinguishes measured patch effects from evidence alone."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

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
                                  {"headline_indicator": "test", "reference_url": "reference.html",
                                   "reference_label": "Published reference results"}, str)
        self.assertIn('href="build.html">Build</a>', html)
        self.assertIn('href="build.html#run">Build record', html)
        self.assertIn('href="reference.html">Published reference results</a>', html)
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
