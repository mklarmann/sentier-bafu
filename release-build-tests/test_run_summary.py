"""A build's own account for the site (`scripts/release_build/run_summary.py`).

The site shows what a run says about itself, and types no number of its own. So what a
build says is read from its manifest and from nothing else, and it is said in the
format any run can write. These tests hold that: every figure is a number of the manifest,
a text of the run is quoted as it is, and what can't be shown is refused where it is written.
"""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from release_build import release_manifest, run_summary  # noqa: E402
from runrecord import summary  # noqa: E402
from test_release_manifest import write_run  # noqa: E402

NAMES = {"2026-v1": "BAFU:2026 v1"}


def a_manifest(tag=None, failed=None, **changes):
    with tempfile.TemporaryDirectory() as tmp:
        steps = write_run(Path(tmp), **changes)
        for step in steps:
            if step["name"] == failed:
                step.update(status="failed", reason="audit failed: 3 findings")
        data = release_manifest.manifest(Path(tmp), tag=tag, steps=steps)
    assert release_manifest.shape_errors(data) == []
    return data


def figures_of(account, name):
    step = next(step for step in account["steps"] if step["name"] == name)
    return {figure["label"]: figure["value"] for figure in step["figures"]}


class FromManifest(unittest.TestCase):
    def test_it_is_an_account_a_page_can_show_with_the_steps_of_the_run(self):
        manifest = a_manifest()
        account = run_summary.from_manifest(manifest, NAMES)
        self.assertEqual(summary.shape_errors(account), [])
        self.assertEqual(account["status"], "completed")
        self.assertEqual(
            [(s["name"], s["status"], s["seconds"]) for s in account["steps"]],
            [(s["name"], s["status"], s["seconds"]) for s in manifest["steps"]],
        )
        self.assertEqual(account["closing"], "Build completed:")
        self.assertIsNone(account["tag"])
        self.assertEqual(
            run_summary.from_manifest(a_manifest(tag="patched-2026-v1.1"), NAMES)["tag"],
            "patched-2026-v1.1",
        )

    def test_every_figure_is_a_number_of_the_manifest(self):
        manifest = a_manifest()
        account = run_summary.from_manifest(manifest, NAMES)
        release, comparison = manifest["provider_release"], manifest["comparison"]
        self.assertEqual(figures_of(account, "provider build")["datasets"], release["datasets"])
        self.assertEqual(figures_of(account, "provider build")["exchanges"], release["exchanges"])
        self.assertEqual(
            figures_of(account, "patched build")["community patches"], len(manifest["patches"])
        )
        self.assertEqual(
            figures_of(account, "patched build")["import fixes"], len(manifest["import_fixes"])
        )
        self.assertEqual(
            figures_of(account, "comparison")["differ"], comparison["exchange_rows_changed"]
        )
        self.assertEqual(
            figures_of(account, "comparison")["unexplained"], comparison["rows_no_step_explains"]
        )
        back = manifest["exports"]["patched"]["read_back_matches"]
        self.assertEqual(
            figures_of(account, "exports"),
            {"file formats": len(back), "read back the same": sum(back.values())},
        )
        # another number in the manifest, another figure in the account
        changed = copy.deepcopy(manifest)
        changed["comparison"]["exchange_rows_changed"] = 4321
        self.assertEqual(
            figures_of(run_summary.from_manifest(changed, NAMES), "comparison")["differ"], 4321
        )

    def test_what_was_in_it_and_what_blocks_it_are_the_runs_own_words(self):
        manifest = a_manifest()
        manifest["not_releasable"] = [
            "patch 0001-amount changed data and names nobody who authorised it"
        ]
        manifest["problems"] = [
            "patch 0001-amount changed data and names nobody who authorised it",
            "a `second` thing",
        ]
        account = run_summary.from_manifest(manifest, NAMES)
        self.assertEqual(
            account["blocking"],
            [
                "patch 0001-amount changed data and names nobody who authorised it",
                "a 'second' thing",
            ],
            "a thing said twice is said once",
        )
        self.assertNotIn(
            "`", "".join(account["blocking"]), "a text of the run can't open a mark of the page"
        )
        self.assertEqual(account["remarks"], [release_manifest.NOT_PUBLISHED])
        fixes, patches = len(manifest["import_fixes"]), len(manifest["patches"])
        self.assertIn(f"{fixes} import fix", account["contents"][0])
        self.assertIn(f"{patches} community patches", account["contents"][0])
        self.assertIn("which answer F1.", account["contents"][0])
        named = copy.deepcopy(manifest)
        named["provider_release"]["id"] = "2026-v1"
        self.assertTrue(
            run_summary.from_manifest(named, NAMES)["contents"][0].startswith("BAFU:2026 v1, ")
        )
        unnamed = copy.deepcopy(manifest)
        unnamed["provider_release"]["id"] = None
        self.assertTrue(
            run_summary.from_manifest(unnamed, NAMES)["contents"][0].startswith(run_summary.UNNAMED)
        )

    def test_a_step_that_failed_carries_its_reason_and_the_account_says_failed(self):
        account = run_summary.from_manifest(a_manifest(failed="patched build"), NAMES)
        self.assertEqual(account["status"], "failed")
        step = next(step for step in account["steps"] if step["name"] == "patched build")
        self.assertEqual((step["status"], step["reason"]), ("failed", "audit failed: 3 findings"))

    def test_the_files_are_those_for_lca_tools_with_their_checksums(self):
        manifest = a_manifest()
        account = run_summary.from_manifest(manifest, NAMES)
        wanted = [
            f
            for f in manifest["exports"]["patched"]["files"]
            if f["kind"] in run_summary.EXPORT_NAMES
        ]
        self.assertEqual(
            [(f["name"], f["bytes"], f["sha256"]) for f in account["files"]],
            [(f["name"], f["bytes"], f["sha256"]) for f in wanted],
        )
        self.assertTrue(all(f["same"] is True for f in account["files"]))
        self.assertEqual(
            {f["label"] for f in account["files"]},
            {run_summary.EXPORT_NAMES[f["kind"]] for f in wanted},
        )

    def test_a_long_text_of_the_run_is_cut_and_one_that_cant_be_shown_is_refused(self):
        manifest = a_manifest()
        manifest["problems"] = ["x" * 5000]
        account = run_summary.from_manifest(manifest, NAMES)
        self.assertLessEqual(len(account["blocking"][0]), summary.MAX_TEXT)
        self.assertTrue(account["blocking"][0].endswith("…"))
        manifest["problems"] = ["a line\nand a second line"]
        with self.assertRaises(ValueError):
            run_summary.from_manifest(manifest, NAMES)

    def test_the_command_writes_the_file_and_says_when_it_cant(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "manifest.json").write_text(json.dumps(a_manifest()))
            self.assertEqual(
                run_summary.main(
                    [
                        "--manifest",
                        str(tmp / "manifest.json"),
                        "--out",
                        str(tmp / "out" / "run.json"),
                    ]
                ),
                0,
            )
            self.assertEqual(
                summary.shape_errors(json.loads((tmp / "out" / "run.json").read_text())), []
            )
            (tmp / "other.json").write_text("{}")
            self.assertEqual(
                run_summary.main(
                    ["--manifest", str(tmp / "other.json"), "--out", str(tmp / "x.json")]
                ),
                1,
            )
            self.assertFalse((tmp / "x.json").exists())

    def test_the_names_of_the_releases_are_the_sites(self):
        names = run_summary.release_names()
        config = json.loads((REPOSITORY / "site/config.json").read_text())
        self.assertEqual(names, {r["id"]: r["name"] for r in config["releases"]})
        self.assertEqual(run_summary.release_names(Path("/nowhere")), {})


if __name__ == "__main__":
    unittest.main()
