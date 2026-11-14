"""The whole path on a made-up release, from one command to the manifest.

It runs `scripts/build_release.py release` as a person or a CI job would: the provider
build, the patched build, the check of the written files and of what each patch matched,
the comparison, the exports with their read-back, a made-up contribution built beside the
patched copy with its own comparison and exports, and the manifest. The release is
eight invented datasets (`synthetic_release.py`); the flow terms, methods and mapping are
the pinned ones, so the scores can be worked by hand from EF 3.1 factors.

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
LAYER = "C900-direct-plant-supply"
CONTRIBUTION_DB = synthetic_release.LAYER["database"]
LABELS = REPOSITORY / "scripts" / "release_build" / "export_labels.toml"
sys.path.insert(0, str(REPOSITORY / "scripts"))


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
        labels = cls.root / "labels.toml"
        labels.write_text(LABELS.read_text() + synthetic_release.LABELS)
        layer = cls.root / "C900-direct-plant-supply.json"
        layer.write_text(json.dumps(synthetic_release.LAYER, indent=2))
        cls.out = cls.root / "run"
        command = [sys.executable, str(ENTRY), "release", str(release), str(cls.out)]
        command += ["--sample", str(sample), "--labels", str(labels)]
        command += ["--contribution", str(layer), "--no-layers", "--partial-release"]
        command += ["--published-results", str(cls.root / "no-such-workbook.xlsx")]
        cls.done = subprocess.run([*command, *reuse()], capture_output=True, text=True)
        cls.contribution = cls.out / "contributions" / LAYER.lower()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def load(self, *parts):
        return json.loads(self.out.joinpath(*parts).read_text())

    def scores(self, build, method):
        folder = self.contribution / "build" if build == "contribution" else self.out / build
        with (folder / "audit" / "scores.csv").open() as stream:
            return {row["code"]: float(row[method]) for row in csv.DictReader(stream)}

    def test_one_command_runs_every_step(self):
        self.assertEqual(
            self.done.returncode, 0, self.done.stdout[-3000:] + self.done.stderr[-2000:]
        )
        steps = self.load("release.json")["steps"]
        self.assertEqual(
            [step["name"] for step in steps],
            [
                "provider build",
                "patched build",
                "written files",
                "patch run",
                "comparison",
                "exports",
                f"{LAYER} build",
                f"{LAYER} comparison",
                f"{LAYER} exports",
            ],
        )
        self.assertEqual({step["status"] for step in steps}, {"completed"})
        for step in steps:  # every step ran in its own process, timed and measured
            self.assertGreaterEqual(step["seconds"], 0)
            self.assertGreater(step["peak_memory_mb"], 0)

    def test_every_step_ran_and_both_audits_pass_without_findings(self):
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
            self.assertEqual(audit["datasets"], 8)
            self.assertEqual(
                audit["exchanges"],
                {"biosphere": 8, "production": 8, "technosphere": 6, "total": 22, "other_kinds": 0},
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
        (folder,) = (self.out / "patched" / "data-root" / "sentier-inventory" / "data").iterdir()
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
        self.assertEqual(rows["exchange_rows_compared"], 22)
        self.assertEqual(rows["unexplained_count"], 0)
        self.assertEqual(rows["by_step"][AMOUNT], {"amount": 1, "rows": 1, "datasets": 1})
        self.assertEqual(rows["by_step"][RENAMED], {"name": 1, "rows": 1, "datasets": 1})
        self.assertEqual(rows["dataset_rows_changed_by_step"], {"location-codes": {"location": 1}})
        links = self.load("comparison.json")["technosphere_declared_against_linked"]
        self.assertEqual(links["baseline"]["declared_location_differs"], 1)  # ENTSO
        self.assertEqual(links["candidate"]["declared_location_differs"], 0)

    def test_the_corrected_name_is_the_label_and_the_declared_flow_travels_beside(self):
        (folder,) = (self.out / "patched" / "data-root" / "sentier-inventory" / "data").iterdir()
        beside = json.loads((folder / "source-observations.json").read_text())
        self.assertEqual(len(beside), 2)
        renamed = next(o for o in beside if o["steps"] and RENAMED in o["steps"])
        self.assertEqual(renamed["declared"]["name"], "Gas, natural/m3")
        self.assertEqual(renamed["patched"]["name"], "Gas, natural")
        steps = self.load("patched", "build-steps.json")
        self.assertEqual(
            [step["id"] for step in steps], ["build-ef-3.1-links", "build-declared-flow-identity"]
        )

    # --- The run summary is handed from the patch tool to everything after it ------------

    def test_the_build_hands_the_run_summary_on(self):
        record = self.load("patched", "build.json")
        summary = self.load("patched", "release-summary.json")
        handed = Path(record["export"]["summary"]).resolve()
        self.assertEqual(handed, (self.out / "patched" / "release-summary.json").resolve())
        self.assertEqual(summary["schema"], "bafu-community-fixes/run-summary/1")
        # the files the database was built from are the files the summary describes
        self.assertEqual(summary["output"]["fingerprint"], record["release"]["built_tree_sha256"])
        self.assertEqual(
            summary["release"]["fingerprint"], record["release"]["provider_tree_sha256"]
        )
        changed = {Path(d["file"]).stem.removeprefix("process_") for d in summary["datasets"]}
        self.assertIn("syn-berries", changed)
        self.assertEqual(self.load("comparison.json")["what_a_step_can_explain"]["layer"], None)

    def test_the_written_files_and_what_each_patch_matched_are_checked(self):
        check = self.load("match-check.json")
        results = {row["id"]: row for row in check["patches"]}
        self.assertEqual(results[AMOUNT]["now"], {"datasets": 1, "exchanges": 1, "changes": 1})
        self.assertEqual(results[AMOUNT]["result"], "no earlier run")
        self.assertEqual(results["0011-flag-aggregated"]["result"], "matched nothing")
        table = (self.out / "results" / "patch-run.md").read_text()
        self.assertIn("The input is not a full release.", table)
        self.assertIn("8 files checked", (self.out / "logs" / "written-files.log").read_text())

    # --- An input whose declared unit is another quantity than its supplier's --------------

    def test_the_declared_kwh_from_a_dataset_in_mj_is_used_as_written_and_listed(self):
        for build in ("provider", "patched"):
            declared = self.load(build, "audit", "audit.json")["declared_units"]
            self.assertEqual(declared["exchanges_whose_declared_unit_is_not_the_suppliers"], 1)
            (row,) = declared["another_quantity"]
            self.assertEqual(
                (row["dataset"], row["supplier"], row["declared_unit"], row["supplier_unit"]),
                ("syn-tomatoes", "syn-old", "kilowatt hour", "megajoule"),
            )
            self.assertEqual(row["finding"], "F900")
            self.assertAlmostEqual(row["amount_brightway_uses"], 0.5, places=6)
            # 0.5 x 0.07, not 0.5 x 3.6 x 0.07: the label is not a conversion
            self.assertAlmostEqual(self.scores(build, CLIMATE)["syn-tomatoes"], 0.035, places=6)

    # --- The exports -------------------------------------------------------------------------

    def test_every_export_of_the_patched_database_is_written_and_reads_back(self):
        manifest = self.load("exports", "patched", "manifest.json")
        self.assertEqual(manifest["status"], "completed", manifest["checks"])
        self.assertEqual(
            {kind: check["passed"] for kind, check in manifest["checks"].items()},
            {"brightway": True, "openlca": True, "ilcd": True, "simapro": True},
        )
        self.assertEqual(manifest["label"], "Modified Data")
        self.assertEqual(manifest["counts"]["activities"], 8)
        self.assertEqual(manifest["counts"]["datasets_matched_to_the_record"], 8)
        self.assertEqual(manifest["labels"]["amounts_converted"], 0)
        (row,) = manifest["declared_units"]["another_quantity_written_as_built"]
        self.assertEqual(
            (row["dataset"], row["finding"], row["amount_as_built"]), ("syn-tomatoes", "F900", 0.5)
        )
        names = {entry["name"] for entry in manifest["files"].values()}
        self.assertEqual(
            names,
            {
                "bafu-2026-v1-patched.bw2package",
                "bafu-2026-v1-patched-openlca.zip",
                "bafu-2026-v1-patched-ilcd.zip",
                "bafu-2026-v1-patched-simapro.csv",
                "MODIFICATIONS.json",
                "MODIFICATIONS.md",
            },
        )
        for name in names:
            self.assertTrue((self.out / "exports" / "patched" / name).is_file())
        steps = [step["id"] for step in manifest["modifications"]["steps"]]
        self.assertIn(AMOUNT, steps)
        self.assertEqual(steps[-2:], ["build-ef-3.1-links", "build-declared-flow-identity"])

    # --- A contribution, built beside the patched copy ------------------------------------

    def test_the_contribution_is_a_database_of_its_own_name(self):
        audit = json.loads((self.contribution / "build" / "audit" / "audit.json").read_text())
        self.assertEqual(audit["status"], "passed", audit["errors"])
        self.assertEqual(audit["findings"], [])
        self.assertEqual(audit["databases"]["inventory"], CONTRIBUTION_DB)
        self.assertEqual(audit["built_from"]["label"], "Modified Data")
        check = audit["contribution"]
        self.assertEqual((check["id"], check["name"]), ("C900", "direct-plant-supply"))
        self.assertEqual(
            (check["changes_declared"], check["changes_found_in_the_database"]), (1, 1)
        )
        self.assertEqual(check["replaced_supplier_still_an_input"], [])
        record = json.loads((self.contribution / "build" / "build.json").read_text())
        self.assertEqual(
            list(record["steps"]),
            ["patch", "adapt", "import", "layer", "label", "data", "install", "mark", "audit"],
        )
        self.assertEqual(record["contribution"]["exchanges_changed"], 1)
        (folder,) = (
            self.contribution / "build" / "data-root" / "sentier-inventory" / "data"
        ).iterdir()
        self.assertTrue(folder.name.startswith(f"{CONTRIBUTION_DB}-tree-"))
        self.assertIn("-layer-", folder.name)

    def test_the_patched_release_does_not_hold_the_contribution(self):
        patched = self.load("patched", "audit", "audit.json")
        self.assertIsNone(patched["contribution"])
        self.assertEqual(patched["databases"]["inventory"], "bafu-2026-v1-patched")
        expected = synthetic_release.EXPECTED["climate"]["syn-crop"]
        self.assertAlmostEqual(
            self.scores("patched", CLIMATE)["syn-crop"] / expected, 1.0, places=6
        )

    def test_the_comparison_says_what_the_layer_changes_against_the_patched_release(self):
        comparison = json.loads((self.contribution / "comparison.json").read_text())
        self.assertEqual(comparison["status"], "passed", comparison["errors"])
        self.assertEqual(comparison["builds"]["baseline"]["database"], "bafu-2026-v1-patched")
        self.assertEqual(comparison["builds"]["candidate"]["database"], CONTRIBUTION_DB)
        self.assertEqual(comparison["what_a_step_can_explain"]["layer"], LAYER)
        rows = comparison["rows"]
        self.assertEqual(rows["exchange_rows_changed"], 1)
        self.assertEqual(rows["unexplained_count"], 0)
        self.assertEqual(
            rows["by_step"][LAYER],
            {"flow": 1, "location": 1, "name": 1, "rows": 1, "datasets": 1},
        )
        for method in comparison["scores"]["methods"]:
            moved = [entry["code"] for entry in method["moved"]]
            if method["method"] == CLIMATE:
                self.assertEqual(moved, ["syn-crop"])
                self.assertEqual(method["moved_by_step"], {LAYER: 1})
        self.assertEqual(comparison["scores"]["unexplained_moves"], 0)
        expected = synthetic_release.EXPECTED["climate, contribution"]["syn-crop"]
        got = self.scores("contribution", CLIMATE)["syn-crop"]
        self.assertAlmostEqual(got / expected, 1.0, places=6)

    def test_the_contributions_exports_name_it_and_read_back(self):
        manifest = json.loads((self.contribution / "exports" / "manifest.json").read_text())
        self.assertEqual(manifest["status"], "completed", manifest["checks"])
        self.assertIn(f"contribution: {LAYER}", manifest["statement"])
        self.assertEqual(manifest["built_from"][CONTRIBUTION_DB]["contribution"]["id"], "C900")
        names = {entry["name"] for entry in manifest["files"].values()}
        self.assertIn(f"{CONTRIBUTION_DB}.bw2package", names)
        self.assertFalse(any(name.startswith("bafu-2026-v1-patched") for name in names))

    # --- The manifest ------------------------------------------------------------------------

    def test_the_manifest_has_the_shape_of_a_manifest_and_holds_what_the_run_found(self):
        from release_build import release_manifest

        manifest = self.load("manifest.json")
        self.assertEqual(release_manifest.shape_errors(manifest), [])
        self.assertEqual(manifest["status"], "completed", manifest["problems"])
        self.assertEqual(
            manifest["output"]["fingerprint"],
            self.load("patched", "build.json")["release"]["built_tree_sha256"],
        )
        patch = next(p for p in manifest["patches"] if p["id"] == AMOUNT)
        self.assertEqual(
            (patch["datasets"], patch["findings"], patch["result"]), ([188725], ["F1"], "applied")
        )
        self.assertEqual(patch["authorised_by"], "Chris Mutel")
        unneeded = next(p for p in manifest["patches"] if p["id"] == "0011-flag-aggregated")
        self.assertEqual((unneeded["result"], unneeded["datasets"]), ("not needed", []))
        self.assertEqual(manifest["brightway"]["patched"]["audit"]["marked_as"], "Modified Data")
        self.assertEqual(manifest["brightway"]["provider"]["database"], "bafu-2026")
        self.assertEqual(manifest["comparison"]["rows_no_step_explains"], 0)
        exports = manifest["exports"]["patched"]
        self.assertEqual(set(exports["read_back_matches"].values()), {True})
        self.assertIs(exports["published"], False)
        listed = {entry["name"]: entry["sha256"] for entry in exports["files"]}
        sums = (self.out / "exports" / "patched" / "SHA256SUMS").read_text().splitlines()
        for line in sums:
            digest, name = line.split("  ")
            if name != "manifest.json":
                self.assertEqual(listed[name], digest)
        (contribution,) = manifest["contributions"]
        self.assertEqual(contribution["database"], CONTRIBUTION_DB)
        self.assertEqual(contribution["datasets_changed"], ["syn-crop"])
        self.assertEqual(
            contribution["comparison_with_the_patched_release"]["rows_changed_by_step"], {LAYER: 1}
        )
        (row,) = manifest["declared_units"]["another_quantity"]
        self.assertEqual(row["finding"], "F900")
        # a made-up release is no release of BAFU: the manifest says why it can't be published
        self.assertIn(
            "the files that were read are not a release this revision of the tool knows",
            manifest["not_releasable"],
        )

    def test_only_files_without_inventory_are_set_aside(self):
        self.assertEqual(
            sorted(path.name for path in (self.out / "results").iterdir()),
            [
                f"{LAYER.lower()}-audit.json",
                f"{LAYER.lower()}-comparison.json",
                f"{LAYER.lower()}-exports-manifest.json",
                "comparison.json",
                "exports-manifest.json",
                "manifest.json",
                "patch-run.md",
                "patched-audit.json",
                "provider-audit.json",
                "run-summary.json",
            ],
        )


if __name__ == "__main__":
    unittest.main()
