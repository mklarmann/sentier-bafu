"""The whole path on a made-up release: patch tool, adapter, importer, install, audit.

It runs `scripts/build_release.py` as a person or a CI job would, for the provider release
and for the patched release, and compares the two. The release is seven invented datasets
(`synthetic_release.py`); the flow terms, methods and mapping are the pinned ones, so the
scores can be worked by hand from EF 3.1 factors.

It needs `uv`, `git` and, the first time, the network: the two tools are cloned at their
pinned commits and the pinned data is downloaded (37 MB). So it only runs when asked:

    RELEASE_BUILD_WHOLE_PATH=1 python3 -m unittest discover -s release-build-tests \
        -p test_whole_path.py

`RELEASE_BUILD_TOOLS`, `RELEASE_BUILD_VENVS` and `RELEASE_BUILD_PINNED_DATA` name folders
to reuse between runs (the entry point's `--tools`, `--venvs` and `--pinned-data`).
"""

import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import synthetic_release  # noqa: E402

ENTRY = REPOSITORY / "scripts" / "build_release.py"
CLIMATE, FOSSILS = "ef-3.1:climate-change", "ef-3.1:resource-use-fossils"
RENAMED = "0007-flow-names"
MOVED = "0008-flow-compartments"
AMOUNT = "0001-strawberry-polyethylene-disposal"


def reuse() -> list[str]:
    options = []
    for flag, variable in (
        ("--tools", "RELEASE_BUILD_TOOLS"),
        ("--venvs", "RELEASE_BUILD_VENVS"),
        ("--pinned-data", "RELEASE_BUILD_PINNED_DATA"),
    ):
        if os.environ.get(variable):
            options += [flag, os.environ[variable]]
    return options


@unittest.skipUnless(
    os.environ.get("RELEASE_BUILD_WHOLE_PATH") == "1",
    "set RELEASE_BUILD_WHOLE_PATH=1 to run the whole path (needs uv, git and the network)",
)
class WholePath(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        release = synthetic_release.write_release(cls.root / "release")
        sample = cls.root / "sample.json"
        sample.write_text(json.dumps(synthetic_release.SAMPLE))
        shared = reuse()
        if "--tools" not in shared:  # clone the tools once, for both builds
            shared += ["--tools", str(cls.root / "tools")]
        if "--pinned-data" not in shared:
            shared += ["--pinned-data", str(cls.root / "pinned-data")]
        cls.runs = {}
        for name, options in (("provider", ["--no-patches"]), ("patched", [])):
            command = [sys.executable, str(ENTRY), "build", str(release), str(cls.root / name)]
            command += [*options, "--sample", str(sample), *shared]
            command += ["--published-results", str(cls.root / "no-such-workbook.xlsx")]
            cls.runs[name] = subprocess.run(command, capture_output=True, text=True)
        tools = shared[shared.index("--tools") : shared.index("--tools") + 2]
        venvs = shared[shared.index("--venvs") :][:2] if "--venvs" in shared else []
        command = [sys.executable, str(ENTRY), "compare", str(cls.root / "provider")]
        command += [str(cls.root / "patched"), "--out", str(cls.root / "comparison.json")]
        cls.runs["compare"] = subprocess.run(
            [*command, *tools, *venvs], capture_output=True, text=True
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def load(self, *parts):
        return json.loads(self.root.joinpath(*parts).read_text())

    def scores(self, build, method):
        with (self.root / build / "audit" / "scores.csv").open() as stream:
            return {row["code"]: float(row[method]) for row in csv.DictReader(stream)}

    def test_every_step_ran_and_both_audits_pass_without_findings(self):
        for name in ("provider", "patched", "compare"):
            done = self.runs[name]
            self.assertEqual(done.returncode, 0, done.stdout[-2000:] + done.stderr[-2000:])
        provider, patched = self.load("provider", "build.json"), self.load("patched", "build.json")
        self.assertEqual(
            list(provider["steps"]), ["adapt", "import", "data", "install", "mark", "audit"]
        )
        self.assertEqual(
            list(patched["steps"]),
            ["patch", "adapt", "import", "label", "data", "install", "mark", "audit"],
        )
        for record in (provider, patched):
            self.assertEqual(record["status"], "completed")
            self.assertEqual(record["audit"]["status"], "passed")
            self.assertEqual(record["audit"]["errors"], [])
            self.assertEqual(record["audit"]["findings"], [])
            self.assertEqual(record["published_results"]["status"], "skipped")
            self.assertIn("not in this repository", record["published_results"]["reason"])

    def test_counts(self):
        for build in ("provider", "patched"):
            audit = self.load(build, "audit", "audit.json")
            self.assertEqual(audit["datasets"], 7)
            self.assertEqual(
                audit["exchanges"],
                {"biosphere": 8, "production": 7, "technosphere": 5, "total": 20, "other_kinds": 0},
            )
            self.assertEqual(set(audit["unlinked"].values()), {0})
            self.assertEqual(audit["biosphere_targets"]["no_ef_3_1_flow"], 0)
            self.assertEqual(audit["elementary_flows"]["not_in_the_pinned_flow_terms"]["flows"], 0)

    def test_the_two_databases_cannot_be_taken_for_one_another(self):
        provider = self.load("provider", "audit", "audit.json")
        patched = self.load("patched", "audit", "audit.json")
        self.assertEqual(provider["databases"]["inventory"], "bafu-2026")
        self.assertEqual(provider["built_from"]["label"], "Provider release")
        self.assertEqual(provider["built_from"]["patches"], [])
        self.assertEqual(patched["databases"]["inventory"], "bafu-2026-v1-patched")
        self.assertEqual(patched["built_from"]["label"], "Modified Data")
        self.assertIs(patched["built_from"]["modified_data"], True)
        for patch in (AMOUNT, "0002-supplier-locations", RENAMED, MOVED):
            self.assertIn(patch, patched["built_from"]["patches"])
        self.assertIn("renumber-exchanges", patched["built_from"]["import_fixes"])
        record = self.load("patched", "build.json")
        self.assertEqual(record["export"]["databases"][0], "bafu-2026-v1-patched")
        (folder,) = (self.root / "patched" / "data-root" / "sentier-inventory" / "data").iterdir()
        metadata = json.loads((folder / "metadata.json").read_text())
        self.assertEqual(metadata["source"], "bafu-2026-v1-patched")
        self.assertEqual(metadata["label"], "Modified Data")
        self.assertTrue(folder.name.startswith("bafu-2026-v1-patched-tree-"))

    def test_scores_equal_the_hand_worked_ones(self):
        expected = synthetic_release.EXPECTED
        for build in ("provider", "patched"):
            climate, fossils = self.scores(build, CLIMATE), self.scores(build, FOSSILS)
            wanted = dict(expected["climate"])
            if build == "patched":
                wanted |= expected["climate, patched"]
            for code, value in wanted.items():  # 32-bit amounts: six digits
                self.assertAlmostEqual(climate[code] / value, 1.0, places=6, msg=(build, code))
            for code, value in expected["fossils"].items():
                self.assertAlmostEqual(fossils[code], value, places=4, msg=(build, code))

    def test_renamed_and_moved_flows_stay_on_their_ef_flow(self):
        comparison = self.load("comparison.json")
        self.assertEqual(comparison["status"], "passed", comparison["errors"])
        self.assertEqual(comparison["elementary_flows"]["exchanges_that_lost_their_ef_3_1_flow"], 0)
        observed = comparison["linked_on_the_declared_flow"]
        self.assertEqual((observed["exchanges"], observed["unexplained"]), (2, 0))
        by_step = {flow["steps"][0]: flow for flow in observed["flows"]}
        self.assertEqual(by_step[RENAMED]["declared"][0], "Gas, natural/m3")
        self.assertEqual(by_step[RENAMED]["patched"][0], "Gas, natural")
        self.assertEqual(by_step[RENAMED]["ef_3_1_flow"], ["Natural Gas"])
        self.assertEqual(by_step[MOVED]["declared"][2], "biotic")
        self.assertTrue(all(flow["linked_to_ef_3_1"] for flow in observed["flows"]))
        # The gas dataset's fossil resource score would be zero had the link been lost
        self.assertAlmostEqual(self.scores("patched", FOSSILS)["syn-gas"], 35.98, places=4)

    def test_only_the_corrected_amount_moves_a_score(self):
        comparison = self.load("comparison.json")
        for method in comparison["scores"]["methods"]:
            moved = [entry["code"] for entry in method["moved"]]
            if method["method"] in (CLIMATE, "ef-3.1:climate-change-fossil"):
                self.assertEqual(moved, ["syn-berries"], method["method"])
                self.assertEqual(method["moved_by_step"], {AMOUNT: 1})
            else:
                self.assertEqual(moved, [], method["method"])
        self.assertEqual(comparison["scores"]["unexplained_moves"], 0)

    def test_every_changed_row_is_explained(self):
        rows = self.load("comparison.json")["rows"]
        self.assertEqual(rows["exchange_rows_compared"], 20)
        self.assertEqual(rows["unexplained_count"], 0)
        self.assertEqual(rows["by_step"][AMOUNT], {"amount": 1, "rows": 1, "datasets": 1})
        self.assertEqual(rows["by_step"][RENAMED], {"name": 1, "rows": 1, "datasets": 1})
        self.assertEqual(rows["dataset_rows_changed_by_step"], {"location-codes": {"location": 1}})
        links = self.load("comparison.json")["technosphere_declared_against_linked"]
        self.assertEqual(links["baseline"]["declared_location_differs"], 1)  # ENTSO
        self.assertEqual(links["candidate"]["declared_location_differs"], 0)

    def test_the_corrected_name_is_the_label_and_the_declared_flow_travels_beside(self):
        (folder,) = (self.root / "patched" / "data-root" / "sentier-inventory" / "data").iterdir()
        beside = json.loads((folder / "source-observations.json").read_text())
        self.assertEqual(len(beside), 2)
        renamed = next(o for o in beside if o["steps"] and RENAMED in o["steps"])
        self.assertEqual(renamed["declared"]["name"], "Gas, natural/m3")
        self.assertEqual(renamed["patched"]["name"], "Gas, natural")
        steps = self.load("patched", "build-steps.json")
        self.assertEqual(
            [step["id"] for step in steps], ["build-ef-3.1-links", "build-declared-flow-identity"]
        )


if __name__ == "__main__":
    unittest.main()
