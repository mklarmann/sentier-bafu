"""A supplemental public step chain must belong to the exact tagged comparison."""

import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from sitebuild import lastrun


@unittest.skipUnless(importlib.util.find_spec("sentier_diagnostics"), "requires the site renderer")
class TaggedStepMeasurements(unittest.TestCase):
    def setUp(self):
        config = json.loads((ROOT / "site/config.json").read_text())["verified_build"]
        self.snapshot = config["step_diagnostics"]["snapshot"]
        data = json.loads((ROOT / self.snapshot).read_text())
        self.pair = {"items": {"compared": data["items_count"]["all"]},
                     "indicators": [{"id": i["id"]} for i in data["indicators"]],
                     "moved": [{"id": i["id"]} for i in data["items"]]}
        self.site = SimpleNamespace(root=ROOT)

    def add(self, pair, matching=True):
        canonical = json.dumps(pair, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        settings = {"snapshot": self.snapshot, "comparison_sha256": hashlib.sha256(canonical).hexdigest()}
        record = {"before_after": pair}
        with patch.object(lastrun, "verified_build", return_value={"step_diagnostics": settings} if matching else None):
            lastrun.add_reviewed_steps(self.site, record)
        return record

    def test_reviewed_steps_and_rows_match_the_measured_endpoints(self):
        data = self.add(self.pair)["diagnostics"]
        self.assertEqual(len(data["steps"]) + 1, len(data["states"]))
        self.assertTrue(all(s["link"].startswith("https://") for s in data["steps"]))
        self.assertEqual({i["id"] for i in data["items"]}, {i["id"] for i in self.pair["moved"]})
        self.assertNotIn("diagnostics", self.add(self.pair, matching=False))

    def test_changing_the_published_example_list_cannot_expose_different_rows(self):
        with self.assertRaisesRegex(ValueError, "do not cover"):
            self.add(self.pair | {"moved": []})

    def test_an_unmatched_comparison_uses_its_own_results(self):
        settings = {"snapshot": "missing.json", "comparison_sha256": "0" * 64}
        record = {"before_after": self.pair}
        with patch.object(lastrun, "verified_build", return_value={"step_diagnostics": settings}):
            lastrun.add_reviewed_steps(self.site, record)
        self.assertNotIn("diagnostics", record)
