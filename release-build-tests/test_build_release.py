"""The entry point: paths, pins, tool checkouts and step measurement.

No tool is run and nothing is downloaded: the steps themselves are covered by the other
test files and by a full run on the release.
"""

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "build_release", REPOSITORY / "scripts" / "build_release.py"
)
build_release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_release)


def options(**values) -> argparse.Namespace:
    defaults = {
        "release": Path("release"),
        "out": Path("out"),
        "no_patches": False,
        "label": None,
        "project": None,
        "brightway_dir": None,
        "pinned_data": None,
        "database": None,
        "release_name": "X:2026 v1",
    }
    return argparse.Namespace(**{**defaults, **values})


class Plan(unittest.TestCase):
    def test_a_patched_build_is_named_as_patched(self):
        paths = build_release.plan(options())
        self.assertTrue(paths["patched"])
        self.assertEqual(paths["project"], "bafu-2026-v1-patched")
        self.assertIn("patched", paths["label"])
        self.assertEqual(paths["brightway_dir"], paths["out"] / "brightway")

    def test_the_provider_release_keeps_its_own_name(self):
        paths = build_release.plan(options(no_patches=True))
        self.assertFalse(paths["patched"])
        self.assertEqual(paths["project"], "bafu-2026-v1")
        self.assertEqual(paths["database"], "bafu-2026")
        self.assertEqual(paths["residual_database"], "bafu-2026-residual")
        self.assertNotIn("patched", paths["label"])

    def test_a_patched_database_never_carries_bafus_name(self):
        paths = build_release.plan(options())
        self.assertEqual(paths["database"], "bafu-2026-v1-patched")
        self.assertEqual(paths["residual_database"], "bafu-2026-v1-patched-residual")
        self.assertEqual(build_release.plan(options(database="mine"))["database"], "mine")
        with self.assertRaisesRegex(build_release.BuildError, "BAFU's release"):
            build_release.plan(options(database="bafu-2026"))
        with self.assertRaisesRegex(build_release.BuildError, "keeps BAFU's name"):
            build_release.plan(options(no_patches=True, database="mine"))

    def layer(self, **changes) -> Path:
        import synthetic_release

        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        path = Path(folder) / "C900-direct-plant-supply.json"
        path.write_text(json.dumps(synthetic_release.LAYER | changes))
        return path

    def test_a_contribution_is_built_under_its_own_name(self):
        paths = build_release.plan(options(contribution=self.layer()))
        self.assertEqual(paths["database"], "bafu-2026-v1-c900-direct-plant-supply")
        self.assertEqual(
            paths["residual_database"], "bafu-2026-v1-c900-direct-plant-supply-residual"
        )
        self.assertEqual(paths["project"], "bafu-2026-v1-c900-direct-plant-supply")
        self.assertIn("contribution C900 (direct-plant-supply)", paths["label"])
        self.assertEqual(paths["contribution"]["contribution"], "C900")
        self.assertEqual(paths["layer_receipt"], paths["out"] / "layer-receipt.json")

    def test_a_contribution_never_goes_into_a_releases_database(self):
        with self.assertRaisesRegex(build_release.BuildError, "under its own name"):
            build_release.plan(options(contribution=self.layer(), database="bafu-2026-v1-patched"))
        for name in ("bafu-2026-v1-patched", "bafu-2026"):
            with self.assertRaisesRegex(build_release.BuildError, "built under its own name"):
                build_release.plan(options(contribution=self.layer(database=name)))
        with self.assertRaisesRegex(build_release.BuildError, "on the patched release"):
            build_release.plan(options(contribution=self.layer(), no_patches=True))
        with self.assertRaisesRegex(build_release.BuildError, "layer can't be used"):
            build_release.plan(options(contribution=self.layer(changes=[])))

    def test_the_marker_step_refuses_a_contribution_under_a_releases_name(self):
        from release_build import mark_database

        record = {"modified_data": True, "contribution": {"id": "C900"}}
        mark_database.check_name("bafu-2026-v1-c900-x", record, "bafu-2026")
        for name in ("bafu-2026-v1-patched", "bafu-2026-v1-patched-residual"):
            with self.assertRaisesRegex(mark_database.MarkError, "a database of its own name"):
                mark_database.check_name(name, record, "bafu-2026")
        # without a contribution, the patched release keeps its name
        mark_database.check_name("bafu-2026-v1-patched", {"modified_data": True}, "bafu-2026")

    def test_the_importer_finds_its_input_below_its_data_root(self):
        paths = build_release.plan(options())
        self.assertEqual(
            paths["importer_zip"].relative_to(paths["importer_root"]).as_posix(),
            "sources/bafu-2026/BAFU-2026 v1_ecoSpold v1.zip",
        )

    def test_options_override_the_defaults(self):
        paths = build_release.plan(
            options(project="mine", brightway_dir=Path("bw"), pinned_data=Path("shared"), label="x")
        )
        self.assertEqual((paths["project"], paths["label"]), ("mine", "x"))
        self.assertEqual(paths["brightway_dir"], Path("bw").resolve())
        self.assertEqual(paths["pinned_data"], Path("shared").resolve())


class Pins(unittest.TestCase):
    def test_both_tools_are_pinned_by_full_commit(self):
        pins = build_release.load_pins()
        self.assertEqual(set(pins), {"sentier-importers", "sentier-brightway"})
        for pin in pins.values():
            self.assertRegex(pin["commit"], r"^[0-9a-f]{40}$")
            self.assertTrue(pin["repository"].startswith("https://github.com/sentier-dev/"))

    def test_the_tool_command_runs_in_the_locked_environment(self):
        pin = {"commit": "0" * 40, "python": "3.12", "extra": "testing", "repository": "x"}
        tool = build_release.Tool("sentier-brightway", pin, Path("/tools/sb"), Path("/venvs"))
        self.assertEqual(
            tool.command("sentier-brightway", "db"),
            [
                *("uv", "run", "--frozen", "--project", "/tools/sb"),
                *("--python", "3.12", "--extra", "testing", "sentier-brightway", "db"),
            ],
        )
        self.assertEqual(tool.env(), {"UV_PROJECT_ENVIRONMENT": "/venvs/sentier-brightway"})
        self.assertEqual(build_release.Tool("t", pin, Path("/tools/t"), None).env(), {})


class Checkout(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name) / "tool"
        self.folder.mkdir()
        self.git("init", "--quiet")
        (self.folder / "file.txt").write_text("one\n")
        self.git("add", "file.txt")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.org", "commit", "-qm", "one")
        self.commit = self.git("rev-parse", "HEAD")

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *arguments):
        done = subprocess.run(
            ["git", "-C", str(self.folder), *arguments], check=True, capture_output=True, text=True
        )
        return done.stdout.strip()

    def tool(self, commit):
        return build_release.Tool("tool", {"commit": commit, "repository": "x"}, self.folder, None)

    def test_a_checkout_at_the_pin_is_accepted(self):
        self.assertEqual(self.tool(self.commit).ensure(False), self.commit)

    def test_another_commit_is_refused(self):
        with self.assertRaisesRegex(build_release.BuildError, "the pin is"):
            self.tool("f" * 40).ensure(False)

    def test_local_changes_are_refused(self):
        (self.folder / "file.txt").write_text("two\n")
        with self.assertRaisesRegex(build_release.BuildError, "local changes"):
            self.tool(self.commit).ensure(False)

    def test_allow_unpinned_accepts_and_says_so(self):
        (self.folder / "file.txt").write_text("two\n")
        self.assertIn("with local changes", self.tool("f" * 40).ensure(True))


class Steps(unittest.TestCase):
    def test_peak_memory_is_reported_in_megabytes(self):
        value = 512 * 1024 * 1024 if sys.platform == "darwin" else 512 * 1024
        self.assertEqual(build_release.peak_memory_mb(value), 512.0)

    def test_a_step_is_timed_and_its_memory_measured(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "step.log"
            code = "x = bytearray(64 * 1024 * 1024); print('done')"
            result = build_release.run([sys.executable, "-c", code], log=log)
            self.assertEqual(result["returncode"], 0)
            self.assertGreater(result["peak_memory_mb"], 64)
            self.assertGreaterEqual(result["seconds"], 0)
            self.assertEqual(log.read_text().strip(), "done")

    def test_a_failing_step_stops_the_build_and_shows_the_end_of_its_log(self):
        with tempfile.TemporaryDirectory() as temp:
            code = "import sys; print('the reason'); sys.exit(3)"
            with self.assertRaisesRegex(build_release.BuildError, r"exited with 3\s+the reason"):
                build_release.run([sys.executable, "-c", code], log=Path(temp) / "step.log")

    def test_an_accepted_exit_code_does_not_stop_the_build(self):
        with tempfile.TemporaryDirectory() as temp:
            command = [sys.executable, "-c", "import sys; sys.exit(1)"]
            result = build_release.run(command, log=Path(temp) / "step.log", accept=(0, 1))
            self.assertEqual(result["returncode"], 1)

    def test_the_linking_report_is_taken_from_the_install_log(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / "install.log"
            log.write_text(
                "writing method 1/25\r 50%|#\nInstalled bafu-2026: 2 processes\n\nLinked 1/2\n"
            )
            self.assertEqual(
                build_release._coverage_lines(log),
                ["Installed bafu-2026: 2 processes", "Linked 1/2"],
            )


class Refusals(unittest.TestCase):
    def test_a_build_needs_a_release_folder_and_an_empty_output_folder(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertEqual(
                build_release.main(["build", str(root / "missing"), str(root / "o")]), 1
            )
            (root / "release").mkdir()
            (root / "out").mkdir()
            (root / "out" / "something").write_text("")
            code = build_release.main(["build", str(root / "release"), str(root / "out")])
            self.assertEqual(code, 1)
            self.assertEqual([p.name for p in (root / "out").iterdir()], ["something"])


class BuildRecords(unittest.TestCase):
    record = {
        "patched": True,
        "release": {
            "name": "X:2026 v1",
            "provider_tree_sha256": "a" * 64,
            "built_tree_sha256": "b" * 64,
            "patches": {"0007-names": 2, "0001-example": 1},
            "import_fixes": {"renumber-exchanges": 3},
            "record_of_changes": ["release-report.html"],
        },
        "tools": {"this repository": "c", "sentier-importers": "d", "sentier-brightway": "e"},
        "databases": {"no_ef_3_1_flow": "bafu-2026-v1-patched-residual"},
        "data_pins": [{"name": "sentier-mappings", "commit": "f" * 40}],
    }

    def test_the_build_names_its_own_changes_for_an_export(self):
        receipt = build_release.adapter.Receipt(datasets=7)
        steps = build_release._build_steps(self.record, receipt, Path("inventory"))
        self.assertEqual([step["id"] for step in steps], ["build-ef-3.1-links"])
        self.assertIn("ffffffffffff", steps[0]["description"])
        receipt.source_observations = [{"dataset": "a"}, {"dataset": "a"}, {"dataset": "b"}]
        steps = build_release._build_steps(self.record, receipt, Path("inventory"))
        self.assertEqual(steps[1]["id"], "build-declared-flow-identity")
        self.assertEqual(steps[1]["datasets"], 2)
        self.assertIn("3 elementary exchanges", steps[1]["description"])
        for step in steps:  # the shape an export step reads
            self.assertTrue({"id", "kind", "description"} <= set(step))

    def test_the_marker_lists_the_patch_ids(self):
        marker = build_release._marker(self.record, [])
        self.assertEqual(marker["patches"], ["0001-example", "0007-names"])
        self.assertEqual(marker["import_fixes"], ["renumber-exchanges"])
        self.assertTrue(marker["patched"])


class Syntax(unittest.TestCase):
    def test_the_build_files_are_python_3_12(self):
        """The tools' environments are on 3.12; the package's own lint targets 3.14."""
        import ast

        files = [REPOSITORY / "scripts" / "build_release.py"]
        # run by the entry point with its own interpreter, or in the export's environment
        files += [REPOSITORY / "scripts" / "full_release_table.py"]
        files += [REPOSITORY / "scripts" / "export_release.py"]
        files += sorted((REPOSITORY / "export-tests").glob("*.py"))
        files += sorted((REPOSITORY / "scripts" / "release_build").glob("*.py"))
        files += sorted((REPOSITORY / "release-build-tests").glob("*.py"))
        self.assertGreater(len(files), 10)
        for file in files:
            ast.parse(file.read_text(), filename=str(file), feature_version=(3, 12))


class LatestRelease(unittest.TestCase):
    def test_latest_asks_the_patch_tool_for_the_release_folder(self):
        asked = []

        def fake(venvs):
            asked.append(venvs)
            return Path("/nowhere/bafu-2026-v1")

        original = build_release.latest_release
        build_release.latest_release = fake
        try:
            with tempfile.TemporaryDirectory() as temp:
                code = build_release.main(["build", "latest", str(Path(temp) / "out")])
        finally:
            build_release.latest_release = original
        self.assertEqual(asked, [None])
        self.assertEqual(code, 1)  # the folder the fake names does not exist


if __name__ == "__main__":
    unittest.main()
