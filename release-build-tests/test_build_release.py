"""The entry point: paths, pins, tool checkouts and step measurement.

No tool is run and nothing is downloaded: the steps themselves are covered by the other
test files and by a full run on the release.
"""

import argparse
import contextlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for synthetic_release
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
        with self.assertRaisesRegex(build_release.BuildError, "on the patched copy"):
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
        # without a contribution, the patched copy keeps its name
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
    def test_the_importer_is_pinned_by_full_commit_and_the_installer_is_in_this_repository(self):
        pins = build_release.load_pins()
        self.assertEqual(set(pins), {"sentier-importers", "sentier-brightway"})
        importer, installer = pins["sentier-importers"], pins["sentier-brightway"]
        self.assertRegex(importer["commit"], r"^[0-9a-f]{40}$")
        self.assertTrue(importer["repository"].startswith("https://github.com/sentier-dev/"))
        # the installer has no checkout to pin: its code is a folder of this repository,
        # and the pin says where it came from
        self.assertNotIn("commit", installer)
        self.assertNotIn("repository", installer)
        folder = build_release.REPOSITORY / installer["folder"]
        self.assertTrue((folder / "pyproject.toml").is_file())
        self.assertTrue((folder / "uv.lock").is_file())
        self.assertTrue((folder / "src/sentier_brightway/sources.toml").is_file())
        self.assertRegex(installer["moved_at"], r"^[0-9a-f]{40}$")
        self.assertTrue(installer["moved_from"].startswith("https://github.com/sentier-dev/"))

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

    def test_a_tool_of_this_repository_runs_from_its_folder_here(self):
        pin = build_release.load_pins()["sentier-brightway"]
        tool = build_release.Tool("sentier-brightway", pin, Path("/tools/sb"), Path("/venvs"))
        folder = build_release.REPOSITORY / "brightway-installer"
        # the folder for checkouts is not where it is, and nothing is cloned there
        self.assertEqual(tool.folder, folder)
        self.assertEqual(
            tool.command("sentier-brightway", "db")[:5],
            ["uv", "run", "--frozen", "--project", str(folder)],
        )
        self.assertEqual(tool.env(), {"UV_PROJECT_ENVIRONMENT": "/venvs/sentier-brightway"})
        # it is at this repository's commit, whatever --allow-unpinned says
        self.assertEqual(tool.ensure(False), build_release._repository_commit())
        self.assertEqual(tool.ensure(True), build_release._repository_commit())

    def test_a_tool_of_this_repository_that_is_missing_stops_the_build(self):
        tool = build_release.Tool("gone", {"folder": "no-such-folder"}, Path("/tools/x"), None)
        with self.assertRaisesRegex(build_release.BuildError, "is not in this repository"):
            tool.ensure(True)
        self.assertFalse(Path("/tools/x").exists())


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

    def test_the_linking_report_is_the_file_the_installer_wrote(self):
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / "install-report.json"
            lines = ["Installed bafu-2026: 2 processes", "Linked 1/2"]
            report.write_text(json.dumps({"linking": "sentier-mappings", "lines": lines}))
            self.assertEqual(build_release._linking_report(report), lines)
            # what the installer printed is not read: no report, or one without lines, stops
            report.write_text(json.dumps({"lines": "Installed"}))
            with self.assertRaisesRegex(build_release.BuildError, "holds no lines"):
                build_release._linking_report(report)
            report.unlink()
            with self.assertRaisesRegex(build_release.BuildError, "wrote no report"):
                build_release._linking_report(report)


class WholePathRecord(unittest.TestCase):
    """`release` with its steps replaced by stand-ins: what is recorded when one fails."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "release").mkdir()
        self.calls = []
        self.real_run = build_release.run
        build_release.run = self.stand_in
        self.addCleanup(setattr, build_release, "run", self.real_run)
        self.addCleanup(self.temp.cleanup)
        self.fails = set()

    def stand_in(self, command, env=None, log=None, accept=(0,)):
        """Every step 'runs' and writes one line to its log; some of them fail."""
        name = log.stem
        self.calls.append(name)
        failed = name in self.fails
        log.write_text(f"{name} went wrong\n" if failed else "fine\n")
        return {
            "command": command,
            "seconds": 1.0,
            "peak_memory_mb": 10.0,
            "returncode": int(failed),
        }

    def release(self, *more):
        arguments = ["release", str(self.root / "release"), str(self.root / "run"), "--no-layers"]
        return build_release.main([*arguments, *more])

    def steps(self):
        record = json.loads((self.root / "run" / "release.json").read_text())
        return {step["name"]: step for step in record["steps"]}

    def test_a_failed_step_is_recorded_and_the_command_ends_with_1(self):
        self.fails = {"patched-build"}
        self.assertEqual(self.release(), 1)
        steps = self.steps()
        self.assertEqual(steps["provider build"]["status"], "completed")
        self.assertEqual(steps["patched build"]["status"], "failed")
        # the stand-ins wrote no build, so the reason is the build's own: it has no record
        self.assertEqual(steps["patched build"]["reason"], "the build wrote no record")
        # steps whose input is missing are not run, and say why
        self.assertEqual(steps["written files"]["status"], "not run")
        self.assertEqual(steps["written files"]["reason"], "the patch tool wrote no patched copy")
        self.assertEqual(
            steps["comparison"]["reason"], "a build has no audited database to compare"
        )
        self.assertEqual(
            steps["exports"]["reason"], "the patched build wrote no database to export"
        )
        self.assertEqual(self.calls, ["provider-build", "patched-build"])
        manifest = json.loads((self.root / "run" / "manifest.json").read_text())
        self.assertEqual(manifest["status"], "failed")
        self.assertIn("step patched build failed: the build wrote no record", manifest["problems"])
        self.assertIn(
            "step exports not run: the patched build wrote no database to export",
            manifest["problems"],
        )
        # what is kept of a run that failed: its manifest, and its own account for the site
        self.assertEqual(
            sorted(p.name for p in (self.root / "run" / "results").iterdir()),
            ["manifest.json", "run.json"],
        )
        account = json.loads((self.root / "run" / "results" / "run.json").read_text())
        self.assertEqual(account["status"], "failed")
        said = {step["name"]: (step["status"], step["reason"]) for step in account["steps"]}
        self.assertEqual(said["patched build"], ("failed", "the build wrote no record"))
        self.assertEqual(
            said["exports"], ("not run", "the patched build wrote no database to export")
        )
        self.assertIn("step patched build failed: the build wrote no record", account["blocking"])

    def test_a_step_that_fails_without_a_record_gives_the_end_of_its_log(self):
        patched = self.root / "run" / "patched"
        (patched / "release").mkdir(parents=True)
        (patched / "release-summary.json").write_text("{}")
        self.fails = {"written-files"}
        # the run folder must be empty when the run starts: let the first stand-in write it
        shutil.rmtree(self.root / "run")
        real = self.stand_in

        def writes_the_patched_release(command, env=None, log=None, accept=(0,)):
            if log.stem == "patched-build":
                (patched / "release").mkdir(parents=True)
                (patched / "release-summary.json").write_text("not a summary")
            return real(command, env, log, accept)

        build_release.run = writes_the_patched_release
        self.assertEqual(self.release(), 1)
        steps = self.steps()
        self.assertEqual(steps["written files"]["status"], "failed")
        self.assertEqual(steps["written files"]["reason"], "written-files went wrong")
        self.assertEqual(steps["patch run"]["status"], "completed")  # later steps still run
        # a summary that can't be read is said, and the manifest is still written
        manifest = json.loads((self.root / "run" / "manifest.json").read_text())
        self.assertEqual(manifest["status"], "failed")
        self.assertIn("patched/release-summary.json is not a JSON record", manifest["problems"])
        self.assertIn("step written files failed: written-files went wrong", manifest["problems"])

    def test_a_release_run_starts_in_an_empty_folder_and_needs_a_release(self):
        (self.root / "run").mkdir()
        (self.root / "run" / "something").write_text("x")
        self.assertEqual(self.release(), 1)
        self.assertEqual(self.calls, [])
        shutil.rmtree(self.root / "run")
        arguments = ["release", str(self.root / "missing"), str(self.root / "run"), "--no-layers"]
        self.assertEqual(build_release.main(arguments), 1)
        self.assertEqual(self.calls, [])

    def test_a_layer_that_is_no_layer_stops_before_anything_runs(self):
        layer = self.root / "C900-x.json"
        layer.write_text("{}")
        self.assertEqual(self.release("--contribution", str(layer)), 1)
        self.assertEqual(self.calls, [])

    def layers(self) -> Path:
        """A layers folder with one layer somebody authorised and one nobody has."""
        folder = self.root / "layers"
        folder.mkdir()
        for number, by in ((901, "Rita Reviewer"), (902, None)):
            layer = {
                "schema": "sentier-bafu/contribution-layer/1",
                "contribution": f"C{number}",
                "name": "made-up",
                "database": f"bafu-2026-v1-c{number}-made-up",
                "title": "A made-up layer",
                "authored_by": "Ann Author",
                "authorised_by": by,
                "changes": [
                    {
                        "kind": "supplier-substitution",
                        "dataset": {"code": "a", "name": "A", "location": "CH"},
                        "replaced_supplier": {"code": "b", "name": "B", "location": "CH"},
                        "new_supplier": {"code": "c", "name": "C", "location": "CH"},
                    }
                ],
            }
            (folder / f"C{number}-made-up.json").write_text(json.dumps(layer))
        return folder

    def run_with_layers(self, *more):
        arguments = ["release", str(self.root / "release"), str(self.root / "run")]
        build_release.main([*arguments, "--layers", str(self.layers()), *more])
        return self.steps()

    def test_a_release_run_builds_only_layers_that_name_who_authorised_them(self):
        steps = self.run_with_layers()
        self.assertIn("C901-made-up-build", self.calls)
        self.assertNotIn("C902-made-up-build", self.calls)
        self.assertEqual(steps["C901-made-up build"]["status"], "completed")  # a stand-in
        skipped = steps["C902-made-up build"]
        self.assertEqual(skipped["status"], "skipped")
        self.assertIn("nobody has authorised the layer C902-made-up.json", skipped["reason"])
        self.assertNotIn("C902-made-up comparison", steps)
        self.assertNotIn("C902-made-up exports", steps)
        # a skipped layer is no problem of the run, and no contribution of the manifest
        manifest = json.loads((self.root / "run" / "manifest.json").read_text())
        self.assertFalse(any("C902" in problem for problem in manifest["problems"]))
        self.assertEqual(manifest["contributions"], [])

    def test_an_unauthorised_layer_is_built_when_it_is_named(self):
        named = self.root / "layers" / "C902-made-up.json"
        steps = self.run_with_layers("--contribution", str(named))
        self.assertIn("C902-made-up-build", self.calls)
        self.assertIn("C901-made-up-build", self.calls)
        self.assertEqual(self.calls.count("C902-made-up-build"), 1)  # named and found: once
        self.assertNotEqual(steps["C902-made-up build"]["status"], "skipped")

    def test_which_layers_a_release_run_builds(self):
        yes, no = {"authorised_by": "Rita Reviewer"}, {"authorised_by": None}
        build, left = build_release.layers_of_a_release_run(
            [("named", no)], [("named", no), ("found", yes), ("waiting", no)]
        )
        self.assertEqual([path for path, _ in build], ["named", "found"])
        self.assertEqual([path for path, _ in left], ["waiting"])


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

    def test_the_build_says_which_way_the_flows_were_linked(self):
        receipt = build_release.adapter.Receipt(datasets=7)
        by_mapping = build_release._build_steps(self.record, receipt, Path("inventory"))[0]
        self.assertIn("through sentier-mappings at ffffffffffff", by_mapping["description"])
        linked = self.record | {"linking": "brightway-flows"}
        step = build_release._build_steps(linked, receipt, Path("inventory"))[0]
        # the same step, with what this linking does: which flow, which conversion, which factors
        self.assertEqual(step["id"], "build-ef-3.1-links")
        for words in (
            "through the links of patch 0010",
            "only where Brightway Flows states the conversion",
            "takes the factors of the EF 3.1 flow",
            "bafu-2026-v1-patched-residual",
        ):
            self.assertIn(words, step["description"])
        self.assertNotIn("sentier-mappings", step["description"])

    def test_the_mapping_is_the_default_and_the_other_linking_has_its_file(self):
        parser = build_release.arguments()
        plain = parser.parse_args(["build", "release", "out"])
        self.assertEqual(plain.linking, "sentier-mappings")
        chosen = parser.parse_args(["build", "release", "out", "--linking", "brightway-flows"])
        self.assertEqual(chosen.linking, "brightway-flows")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(["build", "release", "out", "--linking", "something-else"])
        # `release` builds with the mapping: it has no such option
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(["release", "release", "out", "--linking", "brightway-flows"])
        # the file is committed, one row for each row of the crosswalk patch 0010 uses
        crosswalk = (
            build_release.REPOSITORY
            / "src/bafu_community_fixes/data/brightway-flows-crosswalk-bafu-2026-v1.csv"
        )
        self.assertTrue(build_release.FLOW_LINKS.is_file())
        self.assertEqual(
            len(build_release.FLOW_LINKS.read_text().splitlines()),
            len(crosswalk.read_text().splitlines()),
        )

    def test_the_comparison_refuses_a_build_of_the_other_linking(self):
        with tempfile.TemporaryDirectory() as temp:
            mapped, linked = Path(temp) / "provider", Path(temp) / "patched"
            for folder, linking in ((mapped, "sentier-mappings"), (linked, "brightway-flows")):
                folder.mkdir()
                (folder / "build.json").write_text(json.dumps({"linking": linking}))
            self.assertEqual(build_release.linking_of(mapped), "sentier-mappings")
            self.assertEqual(build_release.linking_of(linked), "brightway-flows")
            # a build from before the option says nothing, and was linked through the mapping
            (mapped / "build.json").write_text("{}")
            self.assertEqual(build_release.linking_of(mapped), "sentier-mappings")
            out = str(Path(temp) / "comparison.json")
            for pair in ((mapped, linked), (linked, mapped)):
                with contextlib.redirect_stderr(io.StringIO()) as said:
                    arguments = ["compare", str(pair[0]), str(pair[1]), "--out", out]
                    code = build_release.main(arguments)
                self.assertEqual(code, 1)
                self.assertIn("was linked through brightway-flows", said.getvalue())
            self.assertFalse(Path(out).exists())

    def test_a_contribution_says_whether_somebody_authorised_it(self):
        self.assertEqual(
            build_release.standing({"authorised_by": None}), "proposed, not authorised"
        )
        self.assertEqual(
            build_release.standing({"authorised_by": "Rita Reviewer"}),
            "authorised by Rita Reviewer",
        )
        contribution = {
            "step": "C900-made-up",
            "title": "A made-up layer",
            "exchanges_changed": 1,
            "datasets_changed": 1,
            "layer_file": "C900-made-up.json",
            "authored_by": "Ann Author",
            "authorised_by": None,
            "standing": build_release.standing({"authorised_by": None}),
            "references": [],
        }
        record = self.record | {"contribution": contribution}
        receipt = build_release.adapter.Receipt(datasets=7)
        step = build_release._build_steps(record, receipt, Path("inventory"))[-1]
        self.assertEqual(step["kind"], "contribution")
        self.assertIn("The contribution is proposed, not authorised.", step["description"])
        self.assertEqual(
            build_release._marker(record, [])["contribution"]["standing"],
            "proposed, not authorised",
        )

    def test_the_marker_lists_the_patch_ids(self):
        marker = build_release._marker(self.record, [])
        self.assertEqual(marker["patches"], ["0001-example", "0007-names"])
        self.assertEqual(marker["import_fixes"], ["renumber-exchanges"])
        self.assertTrue(marker["patched"])


class ExportCommand(unittest.TestCase):
    """The command of the export step, from what a build recorded for it."""

    RECORD = {
        "brightway_dir": "/run/patched/brightway",
        "project": "bafu-2026-v1-patched",
        "databases": ["bafu-2026-v1-patched", "ef-3.1-biosphere"],
        "summary": "/run/patched/release-summary.json",
        "extra_steps": "/run/patched/build-steps.json",
        "release": "X:2026 v1",
        "labels": "/labels.toml",
        "name": "bafu-2026-v1-patched",
    }

    def command(self, **changes):
        with tempfile.TemporaryDirectory() as folder:
            record = {"export": self.RECORD | changes}
            (Path(folder) / "build.json").write_text(json.dumps(record))
            return build_release.export_command(Path(folder), Path("/run/exports"))

    def test_the_patched_copy_is_exported_with_the_files_the_patch_run_wrote(self):
        command = self.command(ecospold="/run/patched/release")
        self.assertEqual(command[command.index("--ecospold") + 1], "/run/patched/release")
        self.assertEqual(command[-2:], ["--out", "/run/exports"])

    def test_a_build_without_such_files_is_exported_without_them(self):
        # a contribution's build records none, and so does a record of an earlier revision
        self.assertNotIn("--ecospold", self.command(ecospold=None))
        self.assertNotIn("--ecospold", self.command())

    def test_a_build_that_wrote_no_summary_is_not_exported(self):
        self.assertIsNone(self.command(summary=None))


class Syntax(unittest.TestCase):
    def test_the_build_files_are_python_3_12(self):
        """The tools' environments are on 3.12; the package's own lint targets 3.14."""
        import ast

        files = [REPOSITORY / "scripts" / "build_release.py"]
        # run by the entry point with its own interpreter, or in the export's environment
        files += [REPOSITORY / "scripts" / "full_release_table.py"]
        files += [REPOSITORY / "scripts" / "export_release.py"]
        # read by the checks of the records, which run without the package's environment
        files += [REPOSITORY / "scripts" / "new_patch.py"]
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
