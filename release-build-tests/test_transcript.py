"""What a release run printed, kept line for line (`scripts/release_build/transcript.py`),
and the lines a step prints about what it produced (`step_lines.py`).

The transcript is what the site shows of a run. So: every line passes through unchanged,
the file is written however the command ends, it is never edited, and one that names who
confirmed for the provider does not leave the machine.
"""

import io
import json
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from release_build import public_summary, step_lines, transcript  # noqa: E402
from test_release_manifest import write_run  # noqa: E402

SCRIPT = REPOSITORY / "scripts" / "release_build" / "transcript.py"
PRINTS = (
    "import sys, time\n"
    "print('[one] start', flush=True)\n"
    "time.sleep(0.3)\n"
    "print('  <b>markup</b> & \"quotes\", \\u00fcn\\u00efcode\\tand a tab')\n"
    "print('to the other stream', file=sys.stderr)\n"
    "print('')\n"
    "sys.exit(%d)\n"
)


class Recording(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.out = self.folder / "kept" / "transcript.json"

    def tearDown(self):
        self.temp.cleanup()

    def record(self, status=0):
        stream = io.StringIO()
        code = transcript.record([sys.executable, "-c", PRINTS % status], self.out, stream)
        return code, stream.getvalue(), json.loads(self.out.read_text(encoding="utf-8"))

    def test_every_line_passes_through_unchanged_and_is_kept_with_its_time(self):
        code, printed, data = self.record()
        wanted = [
            "[one] start",
            '  <b>markup</b> & "quotes", ünïcode\tand a tab',
            "to the other stream",
            "",
        ]
        self.assertEqual(code, 0)
        self.assertEqual(printed, "".join(line + "\n" for line in wanted))
        self.assertEqual([text for _, text in data["lines"]], wanted)
        times = [t for t, _ in data["lines"]]
        self.assertEqual(times, sorted(times))
        self.assertGreaterEqual(
            times[1] - times[0], 0.2, "a line carries the time it was printed at"
        )
        self.assertEqual(data["sha256"], transcript.sha256_of(wanted))
        self.assertEqual(
            (data["format"], data["exit_code"], data["cut"]), (transcript.FORMAT, 0, False)
        )
        self.assertEqual(transcript.shape_errors(data), [])

    def test_a_run_that_fails_is_kept_too_and_the_wrapper_ends_as_the_command_did(self):
        code, _, data = self.record(status=3)
        self.assertEqual((code, data["exit_code"]), (3, 3))
        self.assertEqual(len(data["lines"]), 4)
        done = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--out",
                str(self.out),
                "--",
                sys.executable,
                "-c",
                PRINTS % 5,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(done.returncode, 5)
        self.assertIn("[one] start\n", done.stdout)
        self.assertEqual(json.loads(self.out.read_text())["exit_code"], 5)

    def test_a_run_that_is_stopped_keeps_what_it_printed_until_then(self):
        waits = "import time\nprint('started', flush=True)\ntime.sleep(60)\n"
        process = subprocess.Popen(
            [
                sys.executable,
                str(SCRIPT),
                "--out",
                str(self.out),
                "--",
                sys.executable,
                "-c",
                waits,
            ],
            stdout=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(process.stdout.readline(), "started\n")
        process.send_signal(signal.SIGTERM)
        process.wait(timeout=20)
        process.stdout.close()
        data = json.loads(self.out.read_text())
        self.assertEqual(data["stopped_by"], "SIGTERM")
        self.assertEqual([text for _, text in data["lines"]], ["started"])
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(transcript.shape_errors(data), [])

    def test_more_lines_than_a_page_can_show_are_passed_on_and_recorded_as_cut(self):
        limit, transcript.shared.MAX_LINES = (
            transcript.shared.MAX_LINES,
            3,
        )  # the wrapper reads its own
        try:
            stream = io.StringIO()
            many = "for n in range(10): print('line', n)"
            transcript.record([sys.executable, "-c", many], self.out, stream)
            data = json.loads(self.out.read_text())
            self.assertEqual(stream.getvalue().count("\n"), 10)
            self.assertEqual((len(data["lines"]), data["cut"]), (3, True))
            self.assertEqual(transcript.shape_errors(data), [])
        finally:
            transcript.shared.MAX_LINES = limit

    def test_a_file_that_was_changed_is_not_a_transcript(self):
        _, _, data = self.record()
        changes = {
            "another line": lambda d: d["lines"][0].__setitem__(1, "[one] another start"),
            "a line added": lambda d: d["lines"].append([9.0, "added"]),
            "a line removed": lambda d: d["lines"].pop(),
            "time out of order": lambda d: d["lines"][0].__setitem__(0, 99.0),
            "a line with a line feed": lambda d: d["lines"][0].__setitem__(1, "a\nb"),
            "no status": lambda d: d.pop("exit_code"),
            "another format": lambda d: d.__setitem__("format", "x"),
            "lines that are no list": lambda d: d.__setitem__("lines", "text"),
        }
        for name, change in changes.items():
            with self.subTest(name):
                changed = json.loads(json.dumps(data))
                change(changed)
                self.assertNotEqual(transcript.shape_errors(changed), [])
        self.assertEqual(
            transcript.shape_errors([]), [f"not a transcript of format {transcript.FORMAT}"]
        )

    def test_a_transcript_is_set_aside_as_it_is(self):
        self.record()
        into = self.folder / "results"
        self.assertEqual(transcript.keep(self.out, into, None), [])
        self.assertEqual((into / "transcript.json").read_bytes(), self.out.read_bytes())
        self.assertEqual(transcript.main(["--keep", str(self.out), "--into", str(into)]), 0)

    def test_a_transcript_that_names_who_confirmed_is_not_kept_and_not_edited(self):
        summary = self.folder / "release-summary.json"
        summary.write_text(
            json.dumps(
                {
                    "steps": [
                        {
                            "id": "0001-x",
                            "confirmed_by": "Ada Example, BAFU, by email on 12 October 2026",
                        },
                        {"id": "0002-y", "confirmed_by": "BAFU (12 October 2026)"},
                    ]
                }
            )
        )
        named = "import sys\nprint('ok')\nprint('patch 0001-x was confirmed by Ada Example')\n"
        transcript.record([sys.executable, "-c", named], self.out, io.StringIO())
        before, into = self.out.read_bytes(), self.folder / "results"
        problems = transcript.keep(self.out, into, summary)
        self.assertEqual(problems, ["transcript.json: line 2 names who confirmed for the provider"])
        self.assertFalse((into / "transcript.json").exists())
        self.assertEqual(self.out.read_bytes(), before)
        self.assertEqual(
            transcript.main(
                ["--keep", str(self.out), "--into", str(into), "--summary", str(summary)]
            ),
            1,
        )
        # the provider's name and a date are what a public file may say, and a line may too
        transcript.record(
            [sys.executable, "-c", "print('confirmed by BAFU (12 October 2026)')"],
            self.out,
            io.StringIO(),
        )
        self.assertEqual(transcript.keep(self.out, into, summary), [])
        # a summary that can't be read can't show that nobody is named
        summary.write_text("{")
        self.assertIn(
            "is not checked", transcript.keep(self.out, self.folder / "other", summary)[0]
        )
        self.assertFalse((self.folder / "other").exists())

    def test_what_a_text_would_repeat_if_it_named_who_confirmed(self):
        summary = {
            "steps": [
                {"confirmed_by": "Ada Example, BAFU, by email on 12 October 2026"},
                {"confirmed_by": "BAFU (12 October 2026)"},
                {"confirmed_by": None},
                {"nested": [{"confirmed_by": "Federal Office for the Environment"}]},
            ]
        }
        found = public_summary.confirmers(summary)
        self.assertIn("Ada Example", found)
        self.assertIn("Ada Example, BAFU, by email on 12 October 2026", found)
        self.assertIn("Federal Office", found)
        self.assertNotIn("BAFU", found)
        self.assertFalse(any("October" in word and len(word) < 20 for word in found))
        self.assertEqual(public_summary.confirmers({"steps": [{"confirmed_by": "BAFU"}]}), set())


class StepLines(unittest.TestCase):
    """What `build_release.py release` prints when a step has ended."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.out = Path(self.temp.name)
        self.steps = write_run(self.out, contribution=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_each_step_says_what_it_produced_from_its_own_record(self):
        provider = step_lines.lines("provider build", self.out)
        self.assertRegex(
            provider[0],
            r"^  database bafu-2026 \(.+\): [\d,]+ datasets, [\d,]+ exchanges, \d+ not linked",
        )
        self.assertRegex(provider[2], r"^  audit \w+: \d+ errors, \d+ findings$")
        patched = step_lines.lines("patched build", self.out)
        self.assertRegex(
            patched[0], r"^  import fixes: \d+, of which \d+ changed data; patches: \d+$"
        )
        self.assertTrue(
            any(line.startswith("  0001-amount") and "datasets" in line for line in patched)
        )
        self.assertTrue(any("database bafu-2026-v1-patched" in line for line in patched))
        compared = step_lines.lines("comparison", self.out)
        self.assertRegex(
            compared[0],
            r"exchange rows compared with bafu-2026: [\d,]+ changed, \d+ that no step explains",
        )
        self.assertRegex(compared[-1], r"^  comparison \w+$")
        exported = step_lines.lines("exports", self.out)
        self.assertTrue(
            any(
                "bafu-2026-v1-patched-simapro.csv" in line and "read back: matches" in line
                for line in exported
            )
        )
        self.assertIn("not published", exported[-1])
        self.assertTrue(step_lines.lines("C900-other build", self.out))

    def test_a_line_is_one_line_and_holds_no_path_of_this_machine(self):
        for step in self.steps:
            for line in step_lines.lines(step["name"], self.out):
                self.assertNotIn("\n", line)
                self.assertTrue(line.startswith("  "), line)
                self.assertNotIn(str(self.out), line)

    def test_a_step_without_a_record_prints_nothing_and_never_fails(self):
        with tempfile.TemporaryDirectory() as empty:
            for name in (
                "provider build",
                "patched build",
                "comparison",
                "exports",
                "C1 build",
                "written files",
                "x",
            ):
                self.assertEqual(step_lines.lines(name, Path(empty)), [])
        (self.out / "comparison.json").write_text("{")
        (self.out / "provider" / "build.json").write_text('{"databases": 3}')
        self.assertEqual(step_lines.lines("comparison", self.out), [])
        self.assertEqual(step_lines.lines("provider build", self.out), [])

    def test_a_step_is_announced_in_words_with_a_command_a_reader_can_follow(self):
        import build_release

        for step in self.steps:
            said = build_release.step_says(step["name"])
            self.assertNotEqual(said, "started", step["name"])
            self.assertNotIn("/", said)
        self.assertEqual(build_release.step_says("something new"), "started")
        self.assertIn("contribution", build_release.step_says("C900-other comparison"))
        out = self.out
        command = [
            sys.executable,
            str(build_release.REPOSITORY / "scripts" / "build_release.py"),
            "build",
            "/home/somebody/.cache/bafu/bafu-2026-v1",
            str(out / "provider"),
            "--no-patches",
            "--pins",
            str(build_release.REPOSITORY / "scripts" / "release_build" / "pins.toml"),
            "--more",
        ]
        shown = build_release.shown_command(command, out)
        self.assertEqual(
            shown,
            "python scripts/build_release.py build .../bafu-2026-v1 run/provider "
            "--no-patches --pins ...",
        )
        self.assertNotIn(str(out), shown)
        self.assertNotIn("somebody", shown)
        self.assertEqual(build_release.shown_command(["uv", "run", "x"], out), "uv run x")

    def test_the_release_run_prints_them_when_a_step_ends(self):
        text = (REPOSITORY / "scripts" / "build_release.py").read_text()
        ended = text.index('print(f"[{name}] failed:')
        said = text.index("for line in step_lines.lines(name, out):")
        self.assertLess(ended, said)
        self.assertIn("f\"[{name}] completed in {result['seconds']} s, \"", text)
        self.assertLess(text.index('print(f"[{name}] {step_says(name)}", flush=True)'), ended)


if __name__ == "__main__":
    unittest.main()
