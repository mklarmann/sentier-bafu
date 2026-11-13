"""The manifest of a release build: its ten core fields, what the build adds, its shape.

A made-up run folder, written as `build_release.py release` lays one out. The manifest
of a real run on the made-up release is checked in `test_whole_path.py`.
"""

import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "scripts"))

from release_build import release_manifest as rm  # noqa: E402

# The fields of a patched release's manifest as the records side of the repository defines
# them (format sentier-bafu/patched-release/1, read on 13 November 2026). This manifest
# keeps every one of them, under the same name.
RECORDS_SIDE = {
    "top": {
        *("format", "tag", "built", "provider_release", "tool", "options", "import_fixes"),
        *("patches", "totals", "output"),
    },
    "patch": {
        *("id", "description", "findings", "author", "authorised_by", "result"),
        *("datasets_changed", "exchanges_changed", "values_changed", "datasets"),
    },
    "import_fix": {"id", "description", "result", "datasets_changed", "values_changed"},
    "provider_release": {
        *("id", "url", "archive_sha256", "fingerprint", "files", "datasets", "exchanges"),
    },
    "tool": {"name", "version", "revision"},
    "output": {"files", "bytes", "fingerprint"},
}
A, B, C = "a" * 64, "b" * 64, "c" * 64


def step(id, kind, datasets, **more):
    entry = {
        "id": id,
        "kind": kind,
        "description": f"What {id} does",
        "rationale": "Why.",
        "authored_by": "Ann Author",
        "authorised_by": "Rita Reviewer",
        "reported_by": None,
        "confirmed_by": None,
        "findings": [],
        "references": [],
        "datasets": datasets,
        "exchanges": datasets,
        "changes": 2 * datasets,
        "fields": {},
        "xsd_checked": None,
        "error": None,
    }
    return entry | more


def summary(**changes):
    data = {
        "schema": "bafu-community-fixes/run-summary/1",
        "status": "completed",
        "error": None,
        "started": "2026-11-13T10:00:00+01:00",
        "finished": "2026-11-13T10:03:00+01:00",
        "duration_seconds": 180.0,
        "release": {
            "url": "https://example.org/release-v1.zip",
            "archive_sha256": A,
            "fingerprint": B,
            "files": 3,
            "datasets": 3,
            "exchanges": 30,
        },
        "software": {"bafu-community-fixes": "0.1.0", "git commit": "abc1234"},
        "options": {
            "XSD schema check": "after import and after every patch",
            "extensions in output": True,
            "only patches": "all",
            "skipped patches": "none",
            "placeholders for missing data": "year 1111",
        },
        "steps": [
            step("location-codes", "import fix", 1),
            step("0001-amount", "patch", 2, findings=["F1"]),
            step("0002-nothing-here", "patch", 0),
        ],
        "totals": {"steps": 3, "datasets_changed": 2, "values_changed": 6},
        "output": {"files": 3, "bytes": 3000, "fingerprint": C},
        "datasets": [
            {
                "file": "process_x.xml",
                "number": 300,
                "import_fixes": [],
                "patches": ["0001-amount"],
            },
            {
                "file": "process_y.xml",
                "number": 200,
                "import_fixes": ["location-codes"],
                "patches": ["0001-amount"],
            },
        ],
    }
    return data | changes


def build(database, label, findings=()):
    record = {
        "status": "completed",
        "label": label,
        "databases": {"inventory": database},
        "release": {"provider_tree_sha256": B, "built_tree_sha256": C},
        "tools": {"this repository": "1" * 40, "sentier-importers": "2" * 40, "uv": "uv 1"},
        "data_pins": [{"name": "sentier-methods", "commit": "3" * 40, "pinned_by": "x", "n": 1}],
    }
    audit = {
        "status": "passed",
        "built_from": {"label": "Modified Data" if "patched" in database else "Provider release"},
        "datasets": 3,
        "exchanges": {"production": 3, "technosphere": 7, "biosphere": 20, "total": 30, "other": 0},
        "unlinked": {"technosphere": 0, "production": 0, "biosphere": 0},
        "biosphere_targets": {"ef_3_1": 19, "no_ef_3_1_flow": 1},
        "scores": {"all_datasets": {"sha256": A}},
        "errors": [],
        "findings": list(findings),
        "declared_units": {
            "table": {"file": "export_labels.toml", "sha256": A},
            "datasets_by_unit": {"kilogram": 3},
            "units_not_in_the_table": [],
            "exchanges_whose_declared_unit_is_not_the_suppliers": 1,
            "same_quantity_other_label": {},
            "another_quantity": [
                {
                    "dataset": "x",
                    "dataset_name": "User",
                    "dataset_location": "FI",
                    "kind": "technosphere",
                    "supplier": "y",
                    "supplier_name": "Plant",
                    "supplier_location": "FI",
                    "declared_unit": "kilowatt hour",
                    "supplier_unit": "megajoule",
                    "amount_as_built": 0.0157,
                    "amount_brightway_uses": 0.0157,
                    "same_quantity": False,
                    "finding": "F13",
                }
            ],
            "recorded_differences_not_found": [],
        },
    }
    return record, audit


def comparison(baseline, candidate, step_id="0001-amount"):
    return {
        "status": "passed",
        "errors": [],
        "builds": {"baseline": {"database": baseline}, "candidate": {"database": candidate}},
        "rows": {
            "exchange_rows_compared": 30,
            "exchange_rows_changed": 2,
            "by_step": {step_id: {"amount": 2, "rows": 2, "datasets": 2}},
            "unexplained_count": 0,
        },
        "elementary_flows": {"exchanges_that_lost_their_ef_3_1_flow": 0},
        "scores": {
            "methods": [
                {
                    "method": "ef-3.1:climate-change",
                    "datasets_moved": 2,
                    "moved_by_step": {step_id: 2},
                    "moved": [
                        {"name": "User", "location": "FI", "before": 2.0, "after": 1.5},
                        {"name": "Plant", "location": "FI", "before": 1.0, "after": 0.5},
                    ],
                },
                {
                    "method": "ef-3.1:land-use",
                    "datasets_moved": 0,
                    "moved_by_step": {},
                    "moved": [],
                },
            ],
            "unexplained_moves": 0,
        },
    }


def exports(name):
    kinds = ("brightway", "openlca", "ilcd", "simapro")
    return {
        "status": "completed",
        "label": "Modified Data",
        "labels": {"file": "export_labels.toml", "sha256": A, "amounts_converted": 0},
        "formats": {kind: {"status": "completed", "seconds": {"write": 1.0}} for kind in kinds},
        "checks": {kind: {"passed": True, "problems": [], "total": 0} for kind in kinds},
        "files": {
            "brightway": {"name": f"{name}.bw2package", "bytes": 10, "sha256": A},
            "simapro": {"name": f"{name}-simapro.csv", "bytes": 20, "sha256": B},
        },
        "counts": {"activities": 3, "elementary_flows": 5, "exchanges": 30},
    }


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def write_run(out, contribution=False, **summary_changes):
    """A run folder as the entry point leaves one; returns the steps it would record."""
    write(out / "patched" / "release-summary.json", summary(**summary_changes))
    for name, database, label in (
        ("provider", "bafu-2026", "provider release"),
        ("patched", "bafu-2026-v1-patched", "patched release"),
    ):
        record, audit = build(database, label)
        write(out / name / "build.json", record)
        write(out / name / "audit" / "audit.json", audit)
    write(out / "comparison.json", comparison("bafu-2026", "bafu-2026-v1-patched"))
    write(out / "exports" / "patched" / "manifest.json", exports("bafu-2026-v1-patched"))
    write(
        out / "match-check.json",
        {
            "compared_with": None,
            "failures": [],
            "warnings": [],
            "patches": [
                {
                    "id": "0001-amount",
                    "now": {"datasets": 2, "exchanges": 2, "changes": 4},
                    "previous": None,
                    "result": "no earlier run",
                }
            ],
        },
    )
    names = ["provider build", "patched build", "written files", "patch run", "comparison"]
    if contribution:
        name = "bafu-2026-v1-c900-other"
        folder = out / "contributions" / "c900-other"
        record, audit = build(name, "patched release with contribution C900 (other)")
        record["contribution"] = {
            "id": "C900",
            "name": "other",
            "title": "Another supplier",
            "database": name,
            "authored_by": "A. Tester",
            "authorised_by": None,
            "layer_file": "C900-other.json",
            "layer_sha256": A,
        }
        write(folder / "build" / "build.json", record)
        write(folder / "build" / "audit" / "audit.json", audit)
        write(
            folder / "build" / "layer-receipt.json",
            {"changes_declared": 1, "exchanges_changed": 1, "datasets_changed": ["x"]},
        )
        write(folder / "comparison.json", comparison("bafu-2026-v1-patched", name, "C900-other"))
        write(folder / "exports" / "manifest.json", exports(name))
        names += ["C900-other build"]
    return [
        {
            "name": name,
            "status": "completed",
            "seconds": 1.5,
            "peak_memory_mb": 100.0,
            "reason": None,
        }
        for name in [*names, "exports"]
    ]


class Folder(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.out = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def manifest(self, contribution=False, tag="patched-2026-v1.1", **summary_changes):
        steps = write_run(self.out, contribution, **summary_changes)
        return rm.manifest(self.out, tag=tag, revision="f" * 40, steps=steps)


class Core(Folder):
    def test_the_core_has_the_fields_of_the_records_sides_manifest_and_no_others(self):
        core = rm.core(summary(), "patched-2026-v1.1", "f" * 40)
        self.assertEqual(set(core), RECORDS_SIDE["top"])
        self.assertEqual(set(rm.CORE_KEYS), RECORDS_SIDE["top"])
        for key in ("provider_release", "tool", "output"):
            self.assertEqual(set(core[key]), RECORDS_SIDE[key], key)
        for patch in core["patches"]:
            self.assertEqual(set(patch), RECORDS_SIDE["patch"])
        for fix in core["import_fixes"]:
            self.assertEqual(set(fix), RECORDS_SIDE["import_fix"])
        self.assertEqual(set(core["options"]), set(rm.OPTION_KEYS))

    def test_the_core_says_what_the_run_summary_says(self):
        core = rm.core(summary(), "patched-2026-v1.1", "f" * 40)
        self.assertEqual(core["built"], "2026-11-13T10:03:00+01:00")
        self.assertEqual(
            core["tool"], {"name": "bafu-community-fixes", "version": "0.1.0", "revision": "f" * 40}
        )
        self.assertEqual(core["provider_release"]["archive_sha256"], A)
        self.assertIsNone(core["provider_release"]["id"])
        self.assertEqual(core["output"], {"files": 3, "bytes": 3000, "fingerprint": C})
        amount, nothing = core["patches"]
        self.assertEqual(
            amount,
            {
                "id": "0001-amount",
                "description": "What 0001-amount does",
                "findings": ["F1"],
                "author": "Ann Author",
                "authorised_by": "Rita Reviewer",
                "result": "applied",
                "datasets_changed": 2,
                "exchanges_changed": 2,
                "values_changed": 4,
                "datasets": [200, 300],  # the numbers of the datasets it changed, sorted
            },
        )
        self.assertEqual((nothing["result"], nothing["datasets"]), ("not needed", []))
        self.assertEqual(core["import_fixes"][0]["result"], "applied")
        # without a revision from the caller, the one the tool recorded
        self.assertEqual(rm.core(summary(), None, None)["tool"]["revision"], "abc1234")

    def test_the_release_is_named_when_the_sites_list_knows_its_archive(self):
        config = {
            "releases": [
                {"id": "2025-v2", "archive_sha256": C},
                {"id": "2026-v1", "archive_sha256": A},
            ]
        }
        self.assertEqual(
            rm.core(summary(), None, None, config)["provider_release"]["id"], "2026-v1"
        )
        self.assertIsNone(rm.core(summary(), None, None, {"site": "x"})["provider_release"]["id"])

    def test_what_keeps_a_run_from_being_a_release(self):
        def blockers(**changes):
            data = summary(**changes)
            return rm.blockers(data, rm.core(data, None, None))

        self.assertEqual(blockers(), [])
        unauthorised = [step("0001-amount", "patch", 2, authorised_by=None)]
        self.assertEqual(
            blockers(steps=unauthorised),
            ["patch 0001-amount changed data and names nobody who authorised it"],
        )
        # a patch nobody authorised that changed nothing blocks nothing
        self.assertEqual(blockers(steps=[step("0002-none", "patch", 0, authorised_by=None)]), [])
        self.assertIn("the run of the patch tool did not complete", blockers(status="failed"))
        unknown = summary()["release"] | {"url": None, "archive_sha256": None}
        self.assertEqual(
            blockers(release=unknown),
            ["the files that were read are not a release this revision of the tool knows"],
        )
        stopped = [step("0001-amount", "patch", 0, error="Dataset 1: expected 2")]
        self.assertIn("step 0001-amount failed", blockers(steps=stopped))
        self.assertIn(
            "patch 0001-amount: the run counts 2 changed datasets, its list of changed "
            "datasets has 1",
            blockers(datasets=summary()["datasets"][:1]),
        )


class WholeManifest(Folder):
    def test_a_good_run_gives_a_manifest_that_can_be_released(self):
        data = self.manifest()
        self.assertEqual(rm.shape_errors(data), [])
        self.assertEqual((data["format"], data["status"]), (rm.FORMAT, "completed"))
        self.assertEqual(data["problems"], [])
        self.assertEqual(data["not_releasable"], [])
        self.assertEqual(rm.release_errors(data), [])
        self.assertEqual(set(data) - set(rm.CORE_KEYS), {
            "status", "problems", "not_releasable", "steps", "check_against_previous",
            "brightway", "comparison", "declared_units", "exports", "contributions",
        })  # fmt: skip

    def test_it_says_what_the_build_found(self):
        data = self.manifest()
        patched = data["brightway"]["patched"]
        self.assertEqual(patched["database"], "bafu-2026-v1-patched")
        self.assertEqual(patched["audit"]["marked_as"], "Modified Data")
        self.assertEqual(patched["audit"]["unlinked_exchanges"], 0)
        self.assertEqual(patched["tools"]["sentier-importers"], "2" * 40)
        self.assertEqual(
            patched["data"], [{"name": "sentier-methods", "commit": "3" * 40, "pinned_by": "x"}]
        )
        self.assertEqual(data["comparison"]["rows_changed_by_step"], {"0001-amount": 2})
        self.assertEqual(
            data["comparison"]["datasets_whose_score_moved_by_method_and_step"],
            {"ef-3.1:climate-change": {"0001-amount": 2}},
        )
        (row,) = data["declared_units"]["another_quantity"]
        self.assertEqual((row["finding"], row["amount_brightway_uses"]), ("F13", 0.0157))
        self.assertNotIn("kind", row)
        exports_ = data["exports"]["patched"]
        self.assertEqual(
            exports_["files"],
            [
                {
                    "kind": "brightway",
                    "name": "bafu-2026-v1-patched.bw2package",
                    "bytes": 10,
                    "sha256": A,
                },
                {
                    "kind": "simapro",
                    "name": "bafu-2026-v1-patched-simapro.csv",
                    "bytes": 20,
                    "sha256": B,
                },
            ],
        )
        self.assertEqual(set(exports_["read_back_matches"].values()), {True})
        self.assertIs(exports_["published"], False)
        self.assertIs(data["exports"]["published"], False)
        self.assertEqual(data["check_against_previous"]["patches"][0]["id"], "0001-amount")

    def test_a_contribution_is_listed_beside_the_patched_release_and_not_in_it(self):
        data = self.manifest(contribution=True)
        self.assertEqual(rm.shape_errors(data), [])
        (entry,) = data["contributions"]
        self.assertEqual((entry["id"], entry["database"]), ("C900", "bafu-2026-v1-c900-other"))
        self.assertEqual(entry["layer"], {"file": "C900-other.json", "sha256": A})
        self.assertEqual(entry["datasets_changed"], ["x"])
        compared = entry["comparison_with_the_patched_release"]
        self.assertEqual(compared["baseline"], "bafu-2026-v1-patched")
        self.assertEqual(compared["rows_changed_by_step"], {"C900-other": 2})
        self.assertEqual(entry["exports"]["files"][0]["name"], "bafu-2026-v1-c900-other.bw2package")
        # the patched release's own sections are untouched by it
        self.assertEqual(data["brightway"]["patched"]["database"], "bafu-2026-v1-patched")
        self.assertEqual([p["id"] for p in data["patches"]], ["0001-amount", "0002-nothing-here"])

    def test_a_failed_step_fails_the_manifest_and_blocks_the_release(self):
        steps = write_run(self.out)
        steps[4] |= {"status": "failed", "reason": "2 changed row(s) no step explains"}
        (self.out / "comparison.json").unlink()
        data = rm.manifest(self.out, tag="patched-2026-v1.1", steps=steps)
        self.assertEqual(rm.shape_errors(data), [])
        self.assertEqual(data["status"], "failed")
        self.assertEqual(
            data["problems"], ["step comparison failed: 2 changed row(s) no step explains"]
        )
        self.assertIsNone(data["comparison"])
        self.assertIn("the comparison of the two builds did not pass", data["not_releasable"])
        self.assertIn("the run failed", rm.release_errors(data))

    def test_findings_of_the_patched_audit_and_failed_exports_block_a_release(self):
        write_run(self.out)
        record, audit = build(
            "bafu-2026-v1-patched", "patched", findings=["A flow lost its EF flow"]
        )
        write(self.out / "patched" / "audit" / "audit.json", audit)
        failed = exports("bafu-2026-v1-patched")
        failed["status"] = "failed"
        failed["formats"]["simapro"] = {
            "status": "failed",
            "stage": "write",
            "error": "ValueError: x",
        }
        write(self.out / "exports" / "patched" / "manifest.json", failed)
        data = rm.manifest(self.out, tag="t")
        self.assertEqual(rm.shape_errors(data), [])
        self.assertIn(
            "the audit of the patched build has errors or findings", data["not_releasable"]
        )
        self.assertIn(
            "not every export was written and read back without a difference",
            data["not_releasable"],
        )
        self.assertEqual(data["exports"]["patched"]["formats"]["simapro"]["stage"], "write")

    def test_a_run_without_a_summary_still_gives_a_manifest_that_says_so(self):
        data = rm.manifest(self.out, tag=None, steps=[])
        self.assertEqual(rm.shape_errors(data), [])
        self.assertEqual(data["status"], "failed")
        self.assertEqual(data["not_releasable"], ["the patch tool wrote no run summary"])
        self.assertIsNone(data["patches"])

    def test_a_file_that_is_not_a_record_is_said_and_not_taken_for_a_missing_step(self):
        write_run(self.out)
        (self.out / "patched" / "release-summary.json").write_text('{"schema": "x"}')
        data = rm.manifest(self.out, tag="t")
        self.assertEqual(rm.shape_errors(data), [])
        self.assertEqual(data["status"], "failed")
        self.assertEqual(data["problems"], ["patched/release-summary.json is not a run summary"])
        (self.out / "patched" / "release-summary.json").write_text("{trunca")
        data = rm.manifest(self.out, tag="t")
        self.assertEqual(data["problems"], ["patched/release-summary.json is not a JSON record"])
        self.assertIsNone(rm.load(self.out / "not-there.json"))

    def test_no_tag_is_no_release(self):
        self.assertEqual(rm.release_errors(self.manifest(tag=None)), ["the manifest names no tag"])


class Shape(Folder):
    def errors(self, change):
        data = copy.deepcopy(self.manifest(contribution=True))
        change(data)
        return rm.shape_errors(data)

    def test_a_file_with_another_field_is_not_a_manifest(self):
        def add(data):
            data["inventory"] = [{"exchange": 1}]

        self.assertEqual(self.errors(add), ["the manifest holds other fields than a manifest has"])
        self.assertEqual(
            rm.shape_errors([]), ["the manifest holds other fields than a manifest has"]
        )

        def nested(data):
            data["patches"][0]["exchanges"] = [{"name": "x", "amount": 1.0}]

        self.assertEqual(self.errors(nested), ["patches: holds other fields than it has"])

        def in_build(data):
            data["brightway"]["patched"]["audit"]["scores"] = {"x": 1.0}

        self.assertEqual(
            self.errors(in_build), ["brightway.patched.audit: holds other fields than it has"]
        )

    def test_values_of_another_kind_are_refused(self):
        def text_of_a_dataset(data):
            data["patches"][0]["description"] = "line\nline"

        self.assertIn("not a line of text", self.errors(text_of_a_dataset)[0])

        def unsorted(data):
            data["patches"][0]["datasets"] = [300, 200]

        self.assertEqual(
            self.errors(unsorted),
            ["patches 0001-amount: datasets is not a sorted list of dataset numbers"],
        )

        def not_finite(data):
            data["declared_units"]["another_quantity"][0]["amount_as_built"] = float("nan")

        self.assertEqual(
            self.errors(not_finite), ["declared_units.amount_as_built: not a finite number"]
        )

        def checksum(data):
            data["exports"]["patched"]["files"][0]["sha256"] = "abc"

        self.assertEqual(self.errors(checksum), ["exports.patched.files.sha256: not a SHA-256"])

        def a_path(data):
            data["contributions"][0]["exports"]["files"][0]["name"] = "builds/x.bw2package"

        self.assertIn("a file name, not a path", self.errors(a_path)[0])

        def format_(data):
            data["format"] = "sentier-bafu/patched-release/1"

        self.assertEqual(self.errors(format_), [f"format is not {rm.FORMAT}"])

    def test_a_manifest_never_says_that_export_files_are_published(self):
        def published(data):
            data["exports"]["patched"]["published"] = True

        self.assertEqual(
            self.errors(published),
            ["exports.patched: a manifest never says that export files are published"],
        )

        def overall(data):
            data["exports"]["published"] = True

        self.assertEqual(
            self.errors(overall), ["exports: a manifest never says that export files are published"]
        )


class Command(Folder):
    def run_main(self, *arguments):
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = rm.main(list(arguments))
        return code, stream.getvalue()

    def test_verify_accepts_a_manifest_and_writes_the_text_of_the_release(self):
        path, notes = self.out / "manifest.json", self.out / "notes.md"
        rm.write(self.manifest(contribution=True), path)
        code, said = self.run_main("--verify", str(path), "--release", "--notes", str(notes))
        self.assertEqual(code, 0, said)
        self.assertIn("a manifest of 2 patches, and nothing else", said)
        text = notes.read_text()
        self.assertIn("This release publishes `manifest.json` only.", text)
        self.assertIn(rm.NOT_PUBLISHED, text)
        self.assertIn("| bafu-2026-v1-patched-simapro.csv | 20 | `" + B + "` |", text)
        self.assertIn("| 0001-amount | F1 | Ann Author | Rita Reviewer | applied | 2 |", text)
        self.assertIn("`bafu-2026-v1-c900-other`. It is not part of the patched release.", text)
        self.assertIn("The provider decides what it changes.", text)

    def test_verify_refuses_what_is_not_a_manifest_or_not_a_release(self):
        path = self.out / "manifest.json"
        path.write_text("not json")
        self.assertEqual(self.run_main("--verify", str(path))[0], 1)
        data = self.manifest()
        data["extra"] = 1
        rm.write(data, path)
        code, said = self.run_main("--verify", str(path))
        self.assertEqual(code, 1)
        self.assertIn("holds other fields than a manifest has", said)
        rm.write(self.manifest(tag=None), path)
        self.assertEqual(self.run_main("--verify", str(path))[0], 0)
        code, said = self.run_main("--verify", str(path), "--release")
        self.assertEqual(code, 1)
        self.assertIn("not a release: the manifest names no tag", said)
        path.write_text(" " * (rm.MAX_BYTES + 1))
        code, said = self.run_main("--verify", str(path))
        self.assertEqual((code, said.strip()), (1, "manifest.json: larger than a manifest can be"))


if __name__ == "__main__":
    unittest.main()
