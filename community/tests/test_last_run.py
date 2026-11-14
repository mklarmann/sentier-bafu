"""The last build on the site: what is read from GitHub, and what the page says.

The record is GitHub's own record of the last run that ended, with the manifest and the
transcript that run kept. The tests pass recorded answers; nothing reaches the network.
What they hold:

- the run shown is the last one that ended, also when it failed;
- the token goes to the API and never to the address an artifact is stored at;
- a file of a run is data: too large, misshapen, or naming who confirmed, it is left out;
- the page states a result only if the record holds it;
- the lines on the page are the lines of the transcript, one for one.
"""

import copy
import html
import io
import json
import sys
import tempfile
import types
import unittest
import zipfile
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "release-build-tests"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import last_run  # noqa: E402
from release_build import release_manifest, run_summary, transcript  # noqa: E402
from runrecord import summary  # noqa: E402
from sitebuild import lastrun  # noqa: E402
from test_release_manifest import write_run  # noqa: E402

try:
    import build_site
except ModuleNotFoundError:  # the markdown package is a site-build dependency only
    build_site = None
try:
    import frozen
    DATA = frozen.repository()
except ModuleNotFoundError:
    DATA = ROOT

REPOSITORY = "sentier-dev/sentier-bafu"
RUN_URL = f"https://github.com/{REPOSITORY}/actions/runs/"
STORAGE = "https://storage.example/artifact.zip?signature=abc"
LINES = [
    [0.0, "[provider build] python scripts/build_release.py build ..."],
    [169.9, "[provider build] completed in 169.9 s, peak memory 1164 MB"],
    [169.9, "  database bafu-2026 (Provider release): 11,947 datasets, 420,063 exchanges"],
    [170.2, '  a line with <b>markup</b> & "quotes", ünïcode and a tab\there'],
    [594.6, "[patched build] failed: audit failed: 3 findings"],
    [594.7, "Build failed: /tmp/release-run/manifest.json"],
]


def a_transcript(lines=LINES, exit_code=1, **changes):
    data = {
        "format": transcript.FORMAT, "command": ["python", "scripts/build_release.py"],
        "started": "2026-11-13T20:11:30+00:00", "seconds": lines[-1][0] if lines else 0.0,
        "exit_code": exit_code, "stopped_by": None, "cut": False, "lines": lines,
        "sha256": transcript.sha256_of(text for _, text in lines),
    }
    return data | changes


def a_manifest(failed=None, tag=None, **summary_changes):
    """A manifest as a build writes it, from the made-up run of the build's tests."""
    with tempfile.TemporaryDirectory() as tmp:
        steps = write_run(Path(tmp), **summary_changes)
        for step in steps:
            if step["name"] == failed:
                step.update(status="failed", reason="audit failed: 3 findings")
        data = release_manifest.manifest(Path(tmp), tag=tag, steps=steps)
    assert release_manifest.shape_errors(data) == [], release_manifest.shape_errors(data)
    return data


NAMES = {"2026-v1": "BAFU:2026 v1", "2025-v2": "BAFU:2025 v2"}
RUN = {"name": "Build", "workflow": "release-build.yml", "artifact": "release-build-results",
       "tagged": {"job": "Keep", "tags": "patched-"}}


def an_account(manifest=None, **changes):
    """A run's own account, as a build writes it from its manifest."""
    return run_summary.from_manifest(a_manifest() if manifest is None else manifest, NAMES) | changes


def a_run(number, status="completed", conclusion="success", event="push"):
    return {
        "id": 1000 + number, "run_number": number, "run_attempt": 1, "html_url": f"{RUN_URL}{1000 + number}",
        "event": event, "head_branch": "main", "head_sha": "526d712f96b53aeb0392491bcc9d928c5848a6cb",
        "status": status, "conclusion": conclusion if status == "completed" else None,
        "run_started_at": "2026-11-13T20:11:20Z", "updated_at": "2026-11-13T20:25:13Z",
        "actor": {"login": "somebody"}, "triggering_actor": {"login": "somebody"},
    }


def some_jobs(failed_step=None, publish=None):
    def step(number, name):
        ended = "failure" if name == failed_step else "success"
        return {"number": number, "name": name, "conclusion": ended,
                "started_at": "2026-11-13T20:11:30Z", "completed_at": "2026-11-13T20:25:07Z"}

    names = ("Set up job", "Run the whole path", "Say what was built", "Complete job")
    jobs = [{"name": "Provider release, patched copy, exports and manifest",
             "conclusion": "failure" if failed_step else "success",
             "started_at": "2026-11-13T20:11:23Z", "completed_at": "2026-11-13T20:25:12Z",
             "steps": [step(n + 1, name) for n, name in enumerate(names)]}]
    if publish:
        jobs.append({"name": "Keep the manifest under the tag, and nothing else", "conclusion": publish,
                     "started_at": None, "completed_at": None, "steps": []})
    return {"jobs": jobs}


def an_archive(**files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as bundle:
        for name, content in files.items():
            bundle.writestr(name, content if isinstance(content, (bytes, str)) else json.dumps(content))
    return stream.getvalue()


class GitHubAnswers:
    """Recorded answers of the API. Every request is kept, with its headers."""

    def __init__(self, runs, jobs=None, artifacts=None, location=STORAGE, no_workflow=False, releases=()):
        self.runs, self.jobs = runs, jobs or some_jobs()
        self.artifacts = [{"id": 7, "name": "release-build-results", "expired": False, "size_in_bytes": 4000,
                           "expires_at": "2027-02-11T20:25:08Z"}] if artifacts is None else artifacts
        self.location, self.no_workflow, self.requests = location, no_workflow, []
        self.releases = list(releases)

    def __call__(self, method, url, headers, body):
        self.requests.append((method, url, dict(headers)))
        path = url.split(f"/repos/{REPOSITORY}", 1)[1]
        if path.startswith("/actions/workflows/"):
            if self.no_workflow:
                return 404, {}, b'{"message": "Not Found"}'
            return 200, {}, json.dumps({"workflow_runs": self.runs}).encode()
        if path.endswith("/jobs?per_page=100"):
            return 200, {}, json.dumps(self.jobs).encode()
        if path.endswith("/artifacts?per_page=100"):
            return 200, {}, json.dumps({"artifacts": self.artifacts}).encode()
        if path == "/releases?per_page=30":
            return 200, {}, json.dumps(self.releases).encode()
        if path == "/actions/artifacts/7/zip":
            if self.location is None:
                return 401, {}, b'{"message": "Requires authentication"}'
            return 302, {"location": self.location}, b""
        raise AssertionError(f"a request the reading does not make: {path}")


def read(answers, archive=None, token="a-token"):
    fetched = []

    def fetch(url):
        fetched.append(url)
        return archive

    record = last_run.fetch(REPOSITORY, RUN, token, transport=answers, fetch=fetch)
    return record, fetched


class ReadingTests(unittest.TestCase):
    def test_the_run_shown_is_the_last_one_that_ended_also_when_it_failed(self):
        manifest, lines = a_manifest(failed="patched build"), a_transcript()
        answers = GitHubAnswers(
            [a_run(9, status="in_progress"), a_run(8, conclusion="failure"), a_run(7)],
            jobs=some_jobs(failed_step="Run the whole path"),
        )
        record, fetched = read(answers, an_archive(**{"run.json": an_account(manifest), "transcript.json": lines}))
        self.assertEqual(last_run.shape_errors(record), [])
        self.assertEqual((record["state"], record["kept"]), ("read", "read"))
        self.assertEqual((record["run"]["number"], record["run"]["conclusion"]), (8, "failure"))
        self.assertEqual(record["newer"], {"url": f"{RUN_URL}1009", "status": "in_progress"})
        self.assertEqual(record["summary"]["status"], "failed")
        self.assertEqual((record["name"], record["workflow"]), ("Build", "release-build.yml"))
        self.assertEqual(record["transcript"]["lines"], LINES)
        self.assertEqual(fetched, [STORAGE])
        # one job with its steps as GitHub recorded them, and nobody is named
        self.assertEqual([s["conclusion"] for s in record["jobs"][0]["steps"]], ["success", "failure", "success", "success"])
        self.assertNotIn("somebody", json.dumps(record))

    def test_the_token_goes_to_the_api_and_never_to_where_an_artifact_is_stored(self):
        answers = GitHubAnswers([a_run(7)])
        _, fetched = read(answers, an_archive(**{"run.json": an_account()}), token="a-secret-token")
        self.assertTrue(answers.requests)
        for _, url, headers in answers.requests:
            self.assertTrue(url.startswith("https://api.github.com/repos/"), url)
            self.assertEqual(headers["Authorization"], "Bearer a-secret-token")
        self.assertEqual(fetched, [STORAGE])
        self.assertNotIn("a-secret-token", STORAGE)

    def test_a_run_that_kept_nothing_is_still_the_last_run(self):
        cases = (
            (dict(artifacts=[]), "none"),
            (dict(artifacts=[{"id": 7, "name": "release-build-results", "expired": True, "size_in_bytes": 10,
                              "expires_at": "2026-02-11T20:25:08Z"}]), "expired"),
            (dict(artifacts=[{"id": 7, "name": "release-build-results", "expired": False,
                              "size_in_bytes": last_run.MAX_ARCHIVE + 1}]), "unreadable"),
            (dict(location=None), "needs a token"),
            (dict(artifacts=[{"id": 8, "name": "something-else", "expired": False, "size_in_bytes": 10}]), "none"),
        )
        for options, kept in cases:
            with self.subTest(kept=kept, options=sorted(options)):
                record, fetched = read(GitHubAnswers([a_run(7, conclusion="failure")], **options), b"")
                self.assertEqual((record["state"], record["kept"]), ("read", kept))
                self.assertEqual(record["run"]["conclusion"], "failure")
                self.assertIsNone(record["summary"])
                self.assertIsNone(record["transcript"])
                self.assertEqual(fetched, [])
                self.assertEqual(last_run.shape_errors(record), [])

    def test_what_a_run_kept_is_data_and_is_checked_before_it_is_shown(self):
        good = an_account()
        named = copy.deepcopy(good)
        named["steps"][0]["confirmed_by"] = "A. Person, BAFU, by email on 12 October 2026"
        marked = copy.deepcopy(good)
        marked["steps"][0]["notes"] = ["a note with a control character \x1b[31m"]
        long = copy.deepcopy(good)
        long["blocking"] = ["x" * (summary.MAX_TEXT + 1)]
        other_lines = a_transcript()
        other_lines["lines"] = other_lines["lines"] + [[600.0, "a line added later"]]
        cases = {
            "not an archive": (b"not a zip", None, None),
            "an account of another shape": (an_archive(**{"run.json": {"format": "x"}}), None, None),
            "an account with a key the format does not know": (an_archive(**{"run.json": named}), None, None),
            "an account with a control character": (an_archive(**{"run.json": marked}), None, None),
            "an account with a text that is too long": (an_archive(**{"run.json": long}), None, None),
            "the manifest of a release and no account": (an_archive(**{"manifest.json": a_manifest()}), None, None),
            "a transcript whose checksum is not its lines'": (
                an_archive(**{"run.json": good, "transcript.json": other_lines}), "completed", None),
            "a transcript that is not JSON": (
                an_archive(**{"run.json": good, "transcript.json": "{"}), "completed", None),
            "only the transcript": (an_archive(**{"transcript.json": a_transcript()}), None, len(LINES)),
        }
        for name, (archive, status, lines) in cases.items():
            with self.subTest(name):
                record, _ = read(GitHubAnswers([a_run(7)]), archive)
                self.assertEqual(last_run.shape_errors(record), [])
                self.assertEqual((record["summary"] or {}).get("status"), status)
                self.assertEqual(len((record["transcript"] or {}).get("lines", [])) or None, lines)
                if status is None and lines is None:
                    self.assertEqual(record["kept"], "unreadable")

    def test_a_file_larger_than_a_record_can_be_is_left_out(self):
        limit, last_run.MAX_FILE = last_run.MAX_FILE, 200
        try:
            record, _ = read(GitHubAnswers([a_run(7)]), an_archive(**{"run.json": an_account()}))
        finally:
            last_run.MAX_FILE = limit
        self.assertEqual((record["kept"], record["summary"]), ("unreadable", None))
        self.assertIn("larger", record["kept_note"])

    def test_no_run_and_no_workflow_are_said_and_are_not_a_success(self):
        for answers in (GitHubAnswers([]), GitHubAnswers([a_run(1, status="queued")]), GitHubAnswers([], no_workflow=True)):
            record, _ = read(answers)
            self.assertEqual(record["state"], "no run")
            self.assertNotIn("run", record)
            self.assertEqual(last_run.shape_errors(record), [])

    def test_a_site_is_built_without_the_run_rather_than_not_built(self):
        offline = last_run.load(REPOSITORY, RUN, offline=True)
        self.assertEqual((offline["state"], offline["read"]), ("not read", None))
        self.assertEqual(offline, last_run.load(REPOSITORY, RUN, offline=True), "two builds of one revision are the same")
        real, last_run.fetch = last_run.fetch, lambda *a, **k: (_ for _ in ()).throw(OSError("no network"))
        try:
            with contextlib_silence():
                self.assertEqual(last_run.load(REPOSITORY, RUN)["state"], "unreadable")
        finally:
            last_run.fetch = real

    def test_the_build_log_says_which_run_a_site_shows(self):
        record, _ = read(GitHubAnswers([a_run(7, conclusion="failure")]),
                         an_archive(**{"run.json": an_account(), "transcript.json": a_transcript()}))
        self.assertEqual(last_run.said(record), "Last build: run 1007 of 2026-11-13T20:11:20Z, failure; "
                                                "its record: read (its own account and transcript)")
        nothing, _ = read(GitHubAnswers([a_run(7)], artifacts=[]))
        self.assertTrue(last_run.said(nothing).endswith("success; its record: none"))
        self.assertEqual(last_run.said(last_run.load(REPOSITORY, RUN, offline=True)),
                         "Last build: not read (this copy of the site was built without GitHub)")

    def test_a_record_from_a_file_is_refused_when_it_is_not_one(self):
        record, _ = read(GitHubAnswers([a_run(7)]), an_archive(**{"run.json": an_account(), "transcript.json": a_transcript()}))
        elsewhere = copy.deepcopy(record)
        elsewhere["run"]["url"] = "https://example.org/run"
        tampered = copy.deepcopy(record)
        tampered["transcript"]["lines"][0][1] = "another first line"
        named = copy.deepcopy(record)
        named["summary"]["steps"][0]["confirmed_by"] = "A. Person"
        with tempfile.TemporaryDirectory() as tmp:
            for name, data, good in (("good", record, True), ("elsewhere", elsewhere, False),
                                     ("tampered", tampered, False), ("named", named, False),
                                     ("other", {"format": "x"}, False)):
                file = Path(tmp) / f"{name}.json"
                file.write_text(json.dumps(data))
                with self.subTest(name):
                    if good:
                        self.assertEqual(last_run.load(REPOSITORY, RUN, file), record)
                    else:
                        with self.assertRaises(SystemExit):
                            last_run.load(REPOSITORY, RUN, file)


class contextlib_silence:
    """What a function prints is not part of a test's output."""

    def __enter__(self):
        self.real, sys.stdout = sys.stdout, io.StringIO()

    def __exit__(self, *_):
        sys.stdout = self.real


# ------------------------------------------------------------------------------ the page


class Lines(HTMLParser):
    """The text of every line of a transcript on a page, and of the page as a reader sees it."""

    def __init__(self):
        super().__init__()
        self.lines, self.text, self.clocks, self._line, self._skip = [], "", [], None, 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            self._skip += 1
        if tag == "span" and "tl" in (attrs.get("class") or "").split():
            self._line = ""
            self.clocks.append((attrs["data-t"], attrs["data-clock"]))

    def handle_endtag(self, tag):
        if tag == "script":
            self._skip -= 1
        if tag == "span" and self._line is not None:
            self.lines.append(self._line)
            self._line = None

    def handle_data(self, data):
        if self._skip:
            return
        self.text += data
        if self._line is not None:
            self._line += data


def a_site(record, findings=("F1", "F3")):
    return types.SimpleNamespace(
        last_run=record, provider="BAFU", by_id={f: {} for f in findings}, root=ROOT,
        release_name=lambda rid: {"2026-v1": "BAFU:2026 v1"}.get(rid, rid),
    )


def shown(record, **options):
    markup = lastrun.last_run(a_site(record, **options))
    page = Lines()
    page.feed(markup)
    return markup, page, " ".join(page.text.split())


def a_record(manifest="completed", lines=LINES, conclusion="success", failed_step=None, publish=None,
             releases=(), **changes):
    if manifest == "completed":
        manifest = a_manifest()
    answers = GitHubAnswers([a_run(7, conclusion=conclusion)], jobs=some_jobs(failed_step, publish), releases=releases)
    files = {}
    if manifest is not None:
        files["run.json"] = an_account(manifest)
    if lines is not None:
        files["transcript.json"] = a_transcript(lines, exit_code=0 if conclusion == "success" else 1)
    if not files:
        answers.artifacts = []
    record, _ = read(answers, an_archive(**files))
    return record | changes


class PageTests(unittest.TestCase):
    def test_the_lines_on_the_page_are_the_lines_of_the_transcript_one_for_one(self):
        markup, page, _ = shown(a_record())
        self.assertEqual([line.rstrip("\n") for line in page.lines], [text for _, text in LINES])
        self.assertTrue(all(line.endswith("\n") and line.count("\n") == 1 for line in page.lines))
        self.assertEqual(page.clocks[1], ("169.9", "02:49"))
        self.assertEqual([float(t) for t, _ in page.clocks], [t for t, _ in LINES])
        self.assertIn(transcript.sha256_of(text for _, text in LINES), markup)
        # the time of a line is drawn by the stylesheet: it is not text that could be copied as the run's
        self.assertNotIn("02:49", " ".join(page.lines))
        self.assertIn("<b>markup</b>", page.lines[3])
        self.assertNotIn("<b>markup</b>", markup)

    def test_markup_in_a_line_is_text_and_a_control_character_is_shown_not_sent(self):
        hostile = [[0.0, "</pre><script>alert(1)</script>"], [0.1, "bell \x07 and escape \x1b[31m"]]
        markup, page, _ = shown(a_record(lines=hostile))
        self.assertEqual(markup.count("<script"), 1, "the page's own script, and no other")
        self.assertNotIn("alert(1)</script>", markup.replace("&lt;", "<").split('<script src="')[1])
        self.assertEqual(page.lines[0], "</pre><script>alert(1)</script>\n")
        self.assertEqual(page.lines[1], "bell ␇ and escape ␛[31m\n")
        self.assertNotIn("\x1b", markup)

    def test_the_marks_on_a_line_add_no_character_and_take_none(self):
        """The page tells the parts of a line apart by the words alone. What a reader copies is
        still the line the run printed."""
        lines = [
            "[exports] completed in 179.0 s, peak memory 2353 MB",
            "  $ uv run --python 3.12 scripts/export_release.py --brightway-dir run/patched/brightway ...",
            "  bafu-2026-v1-patched.openlca.zip   48,280,457 bytes  sha256 50e4b53d7fe2  read back: matches",
            "[patched build] failed: audit failed: 3 findings",
            "  patch 0009 refused, 2 steps not run, 1 file differs",
            "  completed</i><script>x</script> 0123456789ab<b> $ not a command",
            "[no end of the name",
            "plain line: incompleted, unmatches, 0123456789a, abcdefabcdefg",
            "",
            "[exports] a <b>bold</b> & word after the name of a step",
            "  $ echo <script>alert(1)</script> & more",
            "[<i>] the name of a step is text as well",
        ]
        for line in lines:
            made = lastrun.marked(line)
            tags = __import__("re").sub(r"</?(?:b|i)(?: class=\"tk-[a-z]+\")?>", "", made)
            self.assertEqual(tags, lastrun.visible(line), line)
            self.assertNotIn("<script", made)
        self.assertEqual(
            lastrun.marked(lines[0]),
            '<b class="tk-step">[exports]</b> <i class="tk-ok">completed</i> in 179.0 s, peak memory 2353 MB',
        )
        self.assertTrue(lastrun.marked(lines[1]).startswith('  <i class="tk-prompt">$</i> uv run'))
        self.assertNotIn("tk-ok", lastrun.marked(lines[1]), "a command is shown as typed, not judged")
        self.assertIn('<i class="tk-sum">50e4b53d7fe2</i>', lastrun.marked(lines[2]))
        self.assertIn('<i class="tk-ok">matches</i>', lastrun.marked(lines[2]))
        self.assertEqual(lastrun.marked(lines[3]).count('<i class="tk-bad">failed</i>'), 2)
        for word in ("refused", "not run", "differs"):
            self.assertIn(f'<i class="tk-bad">{word}</i>', lastrun.marked(lines[4]))
        # a word inside another word, and a number too short for a checksum, are left alone
        self.assertEqual(lastrun.marked(lines[7]), lastrun.visible(lines[7]))
        self.assertEqual(lastrun.marked(lines[6]), lastrun.visible(lines[6]))
        self.assertEqual(lastrun.line_class(lines[0]), "tl tl-step")
        self.assertEqual(lastrun.line_class(lines[1]), "tl tl-cmd")
        self.assertEqual(lastrun.line_class(lines[2]), "tl")

    def test_a_long_line_is_wrapped_and_the_reader_can_choose_otherwise(self):
        """A line longer than the terminal was cut off at its right edge. Lines wrap unless the
        reader asks for them as printed, and the terminal can take the whole window. The switches
        need the script, so it shows them; each says what it does, for it is drawn as a mark."""
        markup, page, _ = shown(a_record())
        tools = markup.split('<span class="run-term-tools"')[1].split("</button></span>")[0]
        self.assertTrue(tools.startswith(" hidden>"), "without the script there is nothing to switch")
        for wanted in ('data-run-wrap aria-pressed="true" aria-label="Wrap long lines" title="Wrap long lines">',
                       'data-run-copy aria-label="Copy the lines as the run printed them"',
                       'data-run-full aria-pressed="false" aria-label="Full screen" title="Full screen">'):
            self.assertIn(wanted, tools)
        self.assertEqual(tools.count("<button"), 3)
        self.assertEqual(tools.count('aria-hidden="true"'), tools.count("<svg"), "a mark is no text of the page")
        self.assertNotIn("Wrap", " ".join(page.lines))
        style = (ROOT / "site" / "style.css").read_text(encoding="utf-8")
        wrapped = style.split(".prose pre.transcript {")[1].split("}")[0]
        self.assertIn("white-space: pre-wrap", wrapped)
        self.assertIn("overflow-wrap: anywhere", wrapped)
        self.assertRegex(style, r"\.run\.no-wrap pre\.transcript \{[^}]*white-space: pre;[^}]*overflow-x: auto")
        self.assertRegex(style, r"\.run\.is-full \.run-stage \{[^}]*position: fixed; inset: 0;")
        script = (ROOT / "site" / "assets" / "replay.js").read_text(encoding="utf-8")
        for name in ("data-run-wrap", "data-run-full", "no-wrap", "is-full", "aria-pressed", "Escape"):
            self.assertIn(name, script)

    def test_the_run_has_one_button_and_it_never_pauses(self):
        """The end of a replay is the page as it is, with every step and every line. So there is
        nothing to pause for: one button replays the run and, while it plays, goes to its end."""
        markup, _, text = shown(a_record())
        self.assertEqual(markup.count("data-run-play "), 1)
        self.assertIn('data-run-play hidden>', markup, "without the script nothing is replayed")
        self.assertIn("<span data-run-play-label>Replay</span>", markup)
        for gone in ("data-run-prev", "data-run-next", "run-controls", "Pause", "Continue"):
            self.assertNotIn(gone, markup)
        script = (ROOT / "site" / "assets" / "replay.js").read_text(encoding="utf-8")
        for gone in ("Pause", "Continue", "data-run-prev", "data-run-next"):
            self.assertNotIn(gone, script)
        self.assertIn('"Skip"', script)
        # without the script the page still holds every step and every line
        self.assertEqual(markup.count('<article class="run-panel"'), 6)
        self.assertEqual(len(__import__("re").findall(r'<span class="tl[ "]', markup)), len(LINES))

    def test_a_line_can_be_pointed_at_and_its_link_adds_nothing_to_what_the_run_printed(self):
        """As a line number in a log on GitHub: the time of a line is the link to it."""
        for record in (a_record(), a_record(manifest=None)):
            markup, page, _ = shown(record)
            self.assertEqual([text for _, text in LINES], [line.rstrip("\n") for line in page.lines])
            for number, (t, _) in enumerate(LINES, 1):
                self.assertEqual(markup.count(f' id="run-line-{number}" '), 1)
                self.assertIn(
                    f'<a class="tl-at" href="#run-line-{number}" tabindex="-1" aria-hidden="true" '
                    f'data-clock="{lastrun.clock(t)}"></a>', markup,
                )
            self.assertNotIn(f'id="run-line-{len(LINES) + 1}"', markup)
        self.assertIn("data-run-copy", shown(a_record())[0])
        script = (ROOT / "site" / "assets" / "replay.js").read_text(encoding="utf-8")
        self.assertIn("#run-line-", script)
        # what is copied is the text of the lines, which holds no time and no mark
        self.assertIn('lines.map(function (line) { return line.textContent; }).join("")', script)

    def test_a_run_that_worked_says_so_and_says_what_stands_in_the_way_of_its_use(self):
        _, _, text = shown(a_record())
        self.assertIn("Build 7 of 13 November 2026, 20:11 UTC, on commit 526d712 of main, after a change was accepted.", text)
        self.assertIn("Yes. All 6 steps completed, in 13 min 53 s.", text)
        self.assertIn("Nothing in this run.", text)
        self.assertIn("It has no tag. A maintainer gives a tag to the build that others should use.", text)
        self.assertIn(release_manifest.NOT_PUBLISHED, text)
        self.assertIn("It worked", text)
        self.assertNotIn("No.", text)
        self.assertNotIn("It did not work", text)

    def test_a_run_without_a_tag_ends_with_its_own_last_step(self):
        """A reader took a seventh step, "not a release" and then "not asked for", for something
        that failed or was left undone. A run that was not made for a tag has the steps the run
        itself names, and the page adds none."""
        closing = [594.7, "Build completed: /tmp/release-run/manifest.json"]
        record = a_record(lines=[*LINES[:-1], closing])
        markup, _, text = shown(record)
        own = [step["name"] for step in record["summary"]["steps"]]
        self.assertEqual(markup.count('class="run-tab '), len(own))
        self.assertEqual(markup.count('<article class="run-panel"'), len(own))
        self.assertEqual(markup.count("run-tab-bar"), len(own), "every step has a time and its bar")
        for state in ("is-not-run", "is-failed", "is-open"):
            self.assertNotIn(state, markup)
        for said in ("not a release", "not asked for", "Publication", "Step 7"):
            self.assertNotIn(said, text)
        self.assertIn(f"Step {len(own)} of {len(own)} · completed", text)
        # what the run prints after its last step is on the page, in its place after the last step's lines
        places = [int(n) for n in __import__("re").findall(r'<span class="tl[^"]*" id="run-line-\d+" data-step="(\d+)"', markup)]
        self.assertEqual(places[-1], len(own), "the script shows these lines with the last step")
        self.assertIn("Build completed: /tmp/release-run/manifest.json", text)
        # a line that begins otherwise than the run says its closing lines begin stays with its step
        self.assertEqual(lastrun.steps_of([[0.0, "[exports] x"], [1.0, "Build failed: y"]], ["exports"], "Build completed:"), [0, 0])
        # what stands in the way is said in full, where the answers are, and links to no step
        self.assertNotIn("All of it", markup)
        self.assertIn("A maintainer gives a tag to the build that others should use.", text)
        # the page's own words for this hold neither of the two words that claim more
        said = " ".join(lastrun.TAG.values())
        self.assertNotRegex(said, r"(?i)\b(release|releases|released|publication|published|publish)\b")
        words = json.loads((ROOT / "site/run-steps.json").read_text())["steps"]
        self.assertEqual(sorted(set(own) - set(words)), [], "every step of the run has its words")
        self.assertNotIn("tagged", words, "no words for a step that is none")

    def test_a_run_that_failed_is_shown_as_failed_with_the_step_and_the_reason(self):
        record = a_record(a_manifest(failed="patched build"), conclusion="failure", failed_step="Run the whole path")
        markup, _, text = shown(record)
        self.assertIn("No. 5 of 6 steps completed. Failed: patched build.", text)
        self.assertIn("Step patched build failed: audit failed: 3 findings.", text)
        self.assertNotIn("Yes.", text)
        self.assertNotIn("Nothing in this run.", text)
        self.assertIn('class="run-no"', markup)
        self.assertIn("It did not work", text)
        self.assertNotIn("It worked", text)
        # the step that failed is drawn as failed, and its place says why, in the run's words
        self.assertEqual(markup.count('class="run-tab is-failed"'), 1)
        self.assertIn('<span class="run-result is-failed">failed', markup)
        self.assertIn('<p class="run-reason">Audit failed: 3 findings.</p>', markup)
        self.assertIn("It ended with status 1.", text)

    def test_what_blocks_a_release_is_said_in_the_runs_own_words(self):
        manifest = a_manifest()
        manifest["not_releasable"] = ["patch 0001-amount changed data and names nobody who authorised it"]
        _, _, text = shown(a_record(manifest))
        self.assertIn("Yes. All 6 steps completed", text)
        self.assertIn("Patch 0001-amount changed data and names nobody who authorised it.", text)
        self.assertNotIn("Nothing in this run.", text)

    def test_a_run_without_a_record_of_its_own_says_only_what_github_recorded(self):
        record = a_record(None, None, conclusion="failure", failed_step="Run the whole path")
        self.assertEqual(record["kept"], "none")
        markup, page, text = shown(record)
        self.assertIn("No. GitHub records that the run failed at the step “Run the whole path”.", text)
        self.assertIn("The run kept no record of its own, so only what GitHub recorded is shown.", text)
        self.assertIn("Not recorded.", text)
        self.assertEqual(page.lines, [])
        self.assertNotIn("replay", markup)
        # GitHub's own steps are listed; the two that every job has are not
        self.assertIn("Run the whole path", text)
        self.assertNotIn("Set up job", text)
        ok = a_record(None, None)
        self.assertIn("GitHub records that the run succeeded.", shown(ok)[2])
        self.assertNotIn("Yes.", shown(ok)[2])

    def test_a_build_that_completed_in_a_job_that_failed_is_not_a_yes(self):
        _, _, text = shown(a_record(conclusion="failure", failed_step="Say what was built"))
        self.assertIn("No. The 6 steps of the run completed, but GitHub records that the run failed at the step “Say what was built”.", text)

    def test_a_run_made_for_a_tag_is_said_to_be_kept_only_when_the_job_that_keeps_it_succeeded(self):
        tagged = a_manifest(tag="patched-2026-v1.1")
        markup, _, text = shown(a_record(tagged, publish="success"))
        self.assertIn("for the tag patched-2026-v1.1", text)
        self.assertIn("It is kept under the tag patched-2026-v1.1: its manifest, and no file of the data.", text)
        # the steps are the run's own also here: where it stands as to its tag is said with the answers
        self.assertEqual(markup.count('class="run-tab '), 6)
        self.assertNotIn("is-not-run", markup)
        _, _, text = shown(a_record(tagged, publish="skipped"))
        self.assertIn("It was made for the tag patched-2026-v1.1, and it was not kept.", text)
        self.assertNotIn("It is kept", text)
        # on a site whose workflow keeps nothing under a tag, a tag is a fact of the run and no more
        plain = a_record(tagged, publish="success") | {"tagged": None}
        self.assertNotIn("kept under", shown(plain)[2])

    def test_what_was_in_it_comes_from_the_manifest(self):
        manifest = a_manifest()
        record = a_record(manifest)
        markup, _, text = shown(record, findings=tuple(manifest["patches"][0]["findings"]))
        release, comparison = manifest["provider_release"], manifest["comparison"]
        for value, label in ((release["datasets"], "datasets"), (release["exchanges"], "exchanges"),
                             (len(manifest["patches"]), "community patches"),
                             (comparison["exchange_rows_compared"], "exchanges compared"),
                             (comparison["exchange_rows_changed"], "differ"),
                             (comparison["rows_no_step_explains"], "unexplained")):
            self.assertIn(f"<div><dt>{label}</dt><dd>{value:,}</dd></div>", markup)
        self.assertIn(release["archive_sha256"][:12], text)
        for finding in manifest["patches"][0]["findings"]:
            self.assertIn(f'href="findings/{finding}.html"', markup)
        # a number on the page follows the record: another count in the manifest, another figure
        changed = copy.deepcopy(manifest)
        changed["comparison"]["exchange_rows_changed"] = 4321
        self.assertIn("<div><dt>differ</dt><dd>4,321</dd></div>", shown(a_record(changed))[0])
        # and the page shows what the run's own account states, whatever wrote it
        stated = copy.deepcopy(record)
        stated["summary"]["steps"][0]["figures"] = [{"value": 7654321, "label": "of anything"}, {"value": "12 GB", "label": "read"}]
        markup = shown(stated)[0]
        self.assertIn("<div><dt>of anything</dt><dd>7,654,321</dd></div>", markup)
        self.assertIn("<div><dt>read</dt><dd>12 GB</dd></div>", markup)

    def test_a_record_without_a_run_states_no_result(self):
        for state, wanted in lastrun.NOT_SHOWN.items():
            markup, page, text = shown(last_run.empty(state, REPOSITORY))
            self.assertEqual(text, "The last run" + wanted)
            self.assertEqual(page.lines, [])
            self.assertNotIn("Yes", text)
            self.assertNotIn("It worked", text)
            self.assertNotIn("replay.js", markup)

    def test_a_step_only_groups_the_lines_and_never_moves_one(self):
        names = ["provider build", "patched build", "exports"]
        lines = [[0.0, "Downloading something"], [0.1, "[provider build] a database"], [0.2, "  $ python x"],
                 [5.0, "[provider build] completed in 5 s"], [5.0, "[patched build] the patches"],
                 [9.0, "[patched build] failed: [not a step] inside"], [9.1, "[exports] not run: no database"],
                 [9.2, "Build failed: /tmp/x/manifest.json"], [9.2, "  provider build   completed"]]
        self.assertEqual(lastrun.steps_of(lines, names, "Build "), [0, 0, 0, 0, 1, 1, 2, 3, 3])
        # a run that says nothing of lines after its last step has none: they stay with the last step
        self.assertEqual(lastrun.steps_of(lines, names), [0, 0, 0, 0, 1, 1, 2, 2, 2])
        record = a_record(a_manifest(), lines=lines)
        markup, page, _ = shown(record)
        self.assertEqual([line.rstrip("\n") for line in page.lines], [text for _, text in lines])
        places = [int(n) for n in __import__("re").findall(r'<span class="tl[^"]*" data-step="(\d+)"', markup)]
        self.assertEqual(places, sorted(places), "the lines stand in the order of the run")

    def test_every_step_has_its_place_and_its_words_and_no_number_is_typed(self):
        record = a_record()
        markup, _, text = shown(record)
        steps = record["summary"]["steps"]
        total = len(steps)  # the run's own steps, and no other
        self.assertEqual(markup.count('class="run-tab '), total)
        self.assertEqual(markup.count('<article class="run-panel"'), total)
        for n in range(1, total + 1):
            self.assertIn(f'href="#run-step-{n}"', markup)
            self.assertIn(f'id="run-step-{n}"', markup)
            self.assertIn(f"Step {n} of {total}", text)
        words = json.loads((ROOT / "site/run-steps.json").read_text())["steps"]
        for step in steps:
            self.assertIn(step["name"], words, "a step of the whole path has its words")
        for name, entry in words.items():
            for key in ("short", "title", "text"):
                self.assertNotRegex(entry[key], r"\d", f"{name}: a number on the page comes from the run")
        # a step the page has no words for is still shown, under its own name
        other = copy.deepcopy(record)
        other["summary"]["steps"][2]["name"] = "something new"
        self.assertIn("something new", shown(other)[2])
        contribution = copy.deepcopy(record)
        contribution["summary"]["steps"][2]["name"] = "C900-other build"
        self.assertIn("A contribution, built beside the patched copy", shown(contribution)[2])

    def test_nothing_is_offered_for_download_that_no_release_holds(self):
        record = a_record()
        files = [f["name"] for f in record["summary"]["files"]]
        self.assertTrue(files)
        site = a_site(record)
        block, box = lastrun.packages(site), lastrun.rail_box(site)
        self.assertIn("No build has a tag yet.", block)
        for name in files:
            self.assertIn(f"<code>{name}</code>", block)
        self.assertEqual(block.count("not offered"), len(files))
        self.assertEqual(box.count("not offered"), len(files))
        self.assertIn("Files of the last build", box)
        self.assertNotRegex(html.unescape(__import__("re").sub(r"<[^>]+>", " ", block + box)), r"(?i)\breleases?\b|\bpublish")
        self.assertNotIn("Download", block + box)
        self.assertIn('data-show-after="build-files"', box)
        self.assertIn('id="build-files"', block)
        # a release that holds one of the files: that one can be downloaded, from GitHub
        base = "https://github.com/sentier-dev/sentier-bafu/releases"
        release = {"tag_name": "patched-2026-v1.1", "draft": False, "published_at": "2026-11-20T10:00:00Z",
                   "html_url": f"{base}/tag/patched-2026-v1.1",
                   "assets": [{"name": "manifest.json", "size": 2000, "browser_download_url": f"{base}/download/patched-2026-v1.1/manifest.json"},
                              {"name": files[0], "size": 16000000, "browser_download_url": f"{base}/download/patched-2026-v1.1/{files[0]}"}]}
        drafts = [{"tag_name": "patched-draft", "draft": True, "html_url": f"{base}/x", "assets": []},
                  {"tag_name": "v1.0", "draft": False, "html_url": f"{base}/y", "assets": []}]
        released = a_record(releases=[*drafts, release])
        self.assertEqual([r["tag"] for r in released["releases"]], ["patched-2026-v1.1"])
        site = a_site(released)
        block, box = lastrun.packages(site), lastrun.rail_box(site)
        self.assertNotIn("No build has a tag yet.", block)
        self.assertIn("patched-2026-v1.1", block)
        self.assertEqual(block.count(">Download</a>"), 1)
        self.assertEqual(box.count(">Download</a>"), 1)
        self.assertEqual(block.count("not offered"), len(files) - 1)
        self.assertIn(f'href="{base}/download/patched-2026-v1.1/{files[0]}"', box)
        # a file that is said to be somewhere else than on GitHub is refused with its record
        elsewhere = copy.deepcopy(released)
        elsewhere["releases"][0]["assets"][1]["url"] = "https://example.org/file.zip"
        self.assertTrue(any("not at an address on GitHub" in e for e in last_run.shape_errors(elsewhere)))
        # without a run that kept its files there is nothing to list beside the text
        self.assertEqual(lastrun.rail_box(a_site(a_record(None, None))), "")
        self.assertIn("were not read", lastrun.packages(a_site(last_run.empty("not read", REPOSITORY))))

    def test_the_file_of_the_site_is_the_record_and_holds_no_list_of_datasets(self):
        """The manifest of a release lists the datasets each patch changed. The record a site
        keeps is the run's own account, which holds no such list, and the manifest is not in it."""
        record = a_record()
        public = lastrun.public_record(record)
        self.assertEqual(public, record)
        self.assertNotIn("manifest", public)
        self.assertNotIn('"datasets":', json.dumps(public))
        self.assertEqual(summary.shape_errors(public["summary"]), [])


OTHER_RUN = {"name": "Linking run", "workflow": "link.yml", "artifact": "link-results", "tagged": None}
OTHER_LINES = [
    [0.0, "[export as shipped] checking the file against its recorded checksum"],
    [1.3, "[export as shipped] completed in 1.3 s"],
    [1.3, "  18,176 process blocks"],
    [1.3, "[licensed files] not run here: needs a licence of the reader's own"],
    [1.3, "Run ended: 1 of 3 stages ran"],
]


def another_account(**changes):
    """The account of a run of another workflow, about another dataset: steps of its own
    names, one that ran and two that this place can't run."""
    reason = "needs a licence of the reader's own"
    return summary.account(
        "completed",
        [
            summary.step("export as shipped", "completed", 1.3,
                         figures=[(3772404, "bytes"), (18176, "process blocks"), ("2,264", "removed blocks")],
                         notes=["Checksum of the file: `" + "ab" * 32 + "`.", "Named in A2 and F1, and in `manifest.csv`."]),
            summary.step("licensed files", "not run here", reason=reason),
            summary.step("link", "not run here", reason=reason),
        ],
        closing="Run ended",
        contents=["The export as shipped, without what a licence covers."],
        blocking=["two stages need a licence of the reader's own"],
    ) | changes


class AnyRunTests(unittest.TestCase):
    """The page shows the run of any workflow: the steps the run names, the figures it states,
    a step it could not run in this place, and a run that was not on GitHub."""

    def record(self, **changes):
        answers = GitHubAnswers([a_run(3)], artifacts=[{"id": 7, "name": "link-results", "expired": False, "size_in_bytes": 400}])
        archive = an_archive(**{"run.json": another_account(**changes), "transcript.json": a_transcript(OTHER_LINES, exit_code=0)})
        record = last_run.fetch(REPOSITORY, OTHER_RUN, "a-token", transport=answers, fetch=lambda url: archive)
        self.assertEqual(last_run.shape_errors(record), [])
        self.assertTrue(any("/actions/workflows/link.yml/runs" in url for _, url, _ in answers.requests))
        self.assertFalse(any(url.endswith("/releases?per_page=30") for _, url, _ in answers.requests),
                         "a workflow that keeps nothing under a tag has nothing of that kind to read")
        return record

    def test_a_run_of_another_workflow_is_shown_with_its_own_steps_and_figures(self):
        record = self.record()
        markup, page, text = shown(record, findings=("A2",))
        self.assertIn("Linking run 3 of 13 November 2026", text)
        self.assertEqual(markup.count('class="run-tab '), 3)
        for name in ("export as shipped", "licensed files", "link"):
            self.assertIn(f'<span class="run-tab-name">{name}</span>', markup)   # no words of the site: its name
        for label, value in (("bytes", "3,772,404"), ("process blocks", "18,176"), ("removed blocks", "2,264")):
            self.assertIn(f"<div><dt>{label}</dt><dd>{value}</dd></div>", markup)
        self.assertEqual([line.rstrip("\n") for line in page.lines], [text for _, text in OTHER_LINES])
        places = [int(n) for n in __import__("re").findall(r'<span class="tl[^"]*" id="run-line-\d+" data-step="(\d+)"', markup)]
        self.assertEqual(places, [0, 0, 0, 1, 3], "the closing line is the run's, after its last step")
        # a note is plain text: code between backquotes, a whole checksum shortened, a finding the site holds linked
        self.assertIn(f'<code title="{"ab" * 32}">abababababab</code>', markup)
        self.assertIn('Named in <a href="findings/A2.html">A2</a> and F1, and in <code>manifest.csv</code>.', markup)
        self.assertNotIn("kept under", text)
        self.assertNotIn("tag", text.replace("stage", ""))

    def test_a_step_this_place_cant_run_is_open_with_its_reason_and_is_no_failure(self):
        markup, _, text = shown(self.record())
        self.assertIn("It worked", text)
        self.assertIn("Yes. 1 of 3 steps completed, and none failed, in 13 min 53 s. 2 steps were not run here.", text)
        self.assertEqual(markup.count('class="run-tab is-open"'), 2)
        self.assertEqual(markup.count('<span class="run-tab-time">not run here</span>'), 2)
        self.assertEqual(markup.count("Needs a licence of the reader's own.".replace("'", "&#x27;")), 2)
        self.assertEqual(markup.count("run-tab-bar"), 1, "a step that did not run has no bar of its time")
        for state in ("is-failed", "is-not-run"):
            self.assertNotIn(state, markup)
        self.assertIn("Step 2 of 3 · not run here", text)
        # what blocks is the run's own sentence, in full, and nothing about a tag
        self.assertIn("What is blockingTwo stages need a licence of the reader's own.", text)
        self.assertNotIn("All of it", markup)
        # a step that did not run because one before it failed is another matter
        failed = self.record(status="failed")
        failed["summary"]["steps"][0]["status"] = "failed"
        failed["summary"]["steps"][1].update(status="not run", reason=None)
        markup, _, text = shown(failed)
        self.assertIn("No. 0 of 3 steps completed. Failed: export as shipped. 1 did not run.", text)
        self.assertIn('class="run-tab is-not-run"', markup)

    def test_a_run_that_was_not_on_github_is_shown_marked_as_such(self):
        account, lines = another_account(), a_transcript(OTHER_LINES, exit_code=0)
        record = last_run.local(account, lines, run=OTHER_RUN, commit="1e67bf0")
        self.assertEqual(last_run.shape_errors(record), [])
        self.assertIsNone(record["run"])
        self.assertEqual(record["jobs"], [])
        markup, page, text = shown(record)
        self.assertIn("Linking run of 13 November 2026, 20:11 UTC, on commit 1e67bf0. Not a run on GitHub.", text)
        self.assertIn("GitHub holds no record of it", text)
        self.assertNotIn("github.com", markup)
        self.assertNotIn("The run on GitHub", text)
        self.assertEqual([line.rstrip("\n") for line in page.lines], [text for _, text in OTHER_LINES])
        self.assertIn("Yes. 1 of 3 steps completed, and none failed, in 1 s. 2 steps were not run here.", text)
        self.assertEqual(last_run.said(record),
                         "Last linking run: a run of 2026-11-13T20:11:30+00:00 that was not on GitHub (its own account and transcript)")
        # such a record is the run's own two files and nothing else: without them it is refused
        with self.assertRaises(ValueError):
            last_run.local({"format": "x"}, lines, run=OTHER_RUN)
        with self.assertRaises(ValueError):
            last_run.local(account, lines | {"sha256": "0" * 64}, run=OTHER_RUN)
        with self.assertRaises(ValueError):
            last_run.local(account, lines, run=OTHER_RUN, commit="not a commit")
        self.assertTrue(last_run.shape_errors(record | {"summary": None}))
        # and the command writes the same record from the two files
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "config.json").write_text(json.dumps({"run": OTHER_RUN}))
            (tmp / "run.json").write_text(json.dumps(account))
            (tmp / "transcript.json").write_text(json.dumps(lines))
            with contextlib_silence():
                status = last_run.main(["--local", "--config", str(tmp / "config.json"), "--summary", str(tmp / "run.json"),
                                        "--transcript", str(tmp / "transcript.json"), "--commit", "1e67bf0", "--out", str(tmp / "record.json")])
            self.assertEqual(status, 0)
            self.assertEqual(json.loads((tmp / "record.json").read_text()), record)
            self.assertEqual(last_run.load(None, OTHER_RUN, tmp / "record.json"), record)

    def test_which_workflow_a_site_shows_is_said_in_its_configuration_and_is_checked(self):
        self.assertIsNone(last_run.settings({}))
        self.assertEqual(last_run.settings({"run": {k: v for k, v in OTHER_RUN.items() if k != "tagged"}}), OTHER_RUN)
        self.assertEqual(last_run.settings({"run": RUN}), RUN)
        real = json.loads((ROOT / "site/config.json").read_text())
        self.assertEqual(last_run.settings(real)["workflow"], "release-build.yml")
        self.assertTrue((ROOT / ".github/workflows" / last_run.settings(real)["workflow"]).is_file())
        for wrong in (
            {"name": "Run", "workflow": "../other/x.yml", "artifact": "a"},
            {"name": "Run", "workflow": "x.yml?per_page=1", "artifact": "a"},
            {"name": "<b>Run</b>", "workflow": "x.yml", "artifact": "a"},
            {"name": "Run", "workflow": "x.yml"},
            {"name": "Run", "workflow": "x.yml", "artifact": "a", "tagged": {"job": "Publish"}},
            {"name": "Run", "workflow": "x.yml", "artifact": "a", "more": 1},
            "release-build.yml",
        ):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                last_run.settings({"run": wrong})
        self.assertEqual(shown(last_run.empty("no run", REPOSITORY, OTHER_RUN))[2], "The last runNo linking run has run yet.")

    def test_a_text_of_a_run_is_plain_and_only_two_things_in_it_are_read(self):
        site = a_site(a_record(), findings=("F3",))
        for text, wanted in (
            ("<script>alert(1)</script> & more", "&lt;script&gt;alert(1)&lt;/script&gt; &amp; more"),
            ("`<b>` is code", "<code>&lt;b&gt;</code> is code"),
            ("one ` backquote", "one ` backquote"),
            ("F3 and F4, XF3, F33", '<a href="findings/F3.html">F3</a> and F4, XF3, F33'),
            ("`F3` in code is not a link", "<code>F3</code> in code is not a link"),
            ("a" * 64, "a" * 64),
            ("`" + "a" * 64 + "`", f'<code title="{"a" * 64}">{"a" * 12}</code>'),
        ):
            self.assertEqual(lastrun.inline(site, text), wanted)
        self.assertEqual(lastrun.sentence(site, "needs `x`"), "Needs <code>x</code>.")
        self.assertEqual(lastrun.sentence(site, "Done already!"), "Done already!")

    def test_an_account_is_refused_when_a_page_could_not_show_it(self):
        good = another_account()
        self.assertEqual(summary.shape_errors(good), [])

        def changed(path, value):
            data = copy.deepcopy(good)
            at = data
            for key in path[:-1]:
                at = at[key]
            at[path[-1]] = value
            return data

        cases = (
            (("format",), "sentier/run/2"), (("status",), "running"), (("steps",), []), (("more",), 1),
            (("steps", 0, "status"), "ok"), (("steps", 0, "name"), ""), (("steps", 0, "name"), "x" * 101),
            (("steps", 1, "name"), "export as shipped"), (("steps", 0, "seconds"), -1), (("steps", 0, "seconds"), True),
            (("steps", 0, "figures"), [{"value": 1.5, "label": "half"}]), (("steps", 0, "figures"), [{"value": 1}]),
            (("steps", 0, "figures"), [{"value": 1, "label": "x"}] * 9), (("steps", 0, "notes"), ["x"] * 13),
            (("steps", 0, "notes"), ["a line\nand another"]), (("steps", 0, "html"), "<b>"),
            (("blocking",), "one text"), (("contents",), ["x" * 601]), (("tag",), 7),
            (("files",), [{"name": "../x.zip", "label": "x", "bytes": 1, "sha256": None, "same": None}]),
            (("files",), [{"name": "x.zip", "label": "x", "bytes": 1, "sha256": "abc", "same": None}]),
            (("files",), [{"name": "x.zip", "label": "x", "bytes": -1, "sha256": None, "same": None}]),
            (("files",), [{"name": "x.zip", "label": "x", "bytes": 1, "sha256": None, "same": None, "url": "https://x"}]),
        )
        for path, value in cases:
            with self.subTest(path=path, value=str(value)[:30]):
                self.assertTrue(summary.shape_errors(changed(path, value)))
        with self.assertRaises(ValueError):
            summary.account("completed", [summary.step("a", "done")])


@unittest.skipIf(build_site is None, "the site build needs the markdown package")
class SiteTests(unittest.TestCase):
    def test_the_patched_release_page_shows_the_last_run_and_the_site_holds_its_record(self):
        record = a_record(a_manifest(failed="patched build"), conclusion="failure", failed_step="Run the whole path")
        with tempfile.TemporaryDirectory() as tmp:
            snapshot, out = Path(tmp) / "last-run.json", Path(tmp) / "site"
            snapshot.write_text(json.dumps(record))
            with contextlib_silence():
                build_site.build(out, offline=True, root=DATA, last_run_snapshot=snapshot)
            source = (out / "patch-and-build.html").read_text()
            page = Lines()
            page.feed(source)
            self.assertEqual([line.rstrip("\n") for line in page.lines], [text for _, text in LINES])
            # the run opens the page, above the text and above "On this page"; the releases come first below
            opening, columns = source.index('class="wrap page-opening"'), source.index('class="wrap page with-rail after-opening"')
            self.assertLess(opening, source.index("<h1"))
            self.assertLess(source.index("<h1"), source.index('data-run'))
            self.assertLess(source.index('data-run'), columns)
            self.assertLess(columns, source.index('aria-label="On this page"'))
            listed = __import__("re").findall(r'<li><a href="#([a-z0-9-]+)">', source.split('class="toc-list"')[1].split("</ul>")[0])
            self.assertEqual(listed[0], "builds-and-tags")
            self.assertEqual(listed[-1], "bafus-release")
            self.assertNotIn("the-last-run", listed)
            self.assertEqual(source.count("<h1"), 1)
            # the address the page had before leads on to it, so that a link someone kept still works
            old = (out / "patched-release.html").read_text()
            self.assertIn('http-equiv="refresh"', old)
            self.assertIn("patch-and-build.html", old)
            self.assertIn('aria-current="page">Patch and build</a>', source)
            self.assertIn("<title>Patch and build ·", source)
            self.assertIn('data-show-after="build-files"', source.split('aria-label="On this page"')[1])
            # the steps are told from the end, and each keeps its own number
            numbers = __import__("re").findall(r'class="step-num" aria-hidden="true">(\d+)<', source)
            self.assertEqual(numbers, sorted(numbers, reverse=True))
            self.assertIn("No. 5 of 6 steps completed. Failed: patched build.", " ".join(page.text.split()))
            self.assertTrue((out / "assets/replay.js").is_file())
            kept = json.loads((out / "api/v1/last-run.json").read_text())
            self.assertEqual(kept["transcript"]["lines"], LINES)
            self.assertEqual(kept["run"]["conclusion"], "failure")
            self.assertNotIn("&lt;", json.dumps(kept), "the file holds the lines as they are, not as HTML")
            self.assertEqual(html.unescape("&lt;b&gt;"), "<b>")

    def test_a_copy_built_by_another_repository_says_on_every_page_that_it_is_a_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib_silence():
                build_site.build(Path(tmp) / "fork", offline=True, root=DATA, built_by="someone/sentier-bafu")
                build_site.build(Path(tmp) / "own", offline=True, root=DATA, built_by=REPOSITORY)
                build_site.build(Path(tmp) / "plain", offline=True, root=DATA)
            pages = sorted((Path(tmp) / "fork").rglob("*.html"))
            shown = [p for p in pages if 'class="preview-notice"' in p.read_text()]
            redirects = [p for p in pages if 'http-equiv="refresh"' in p.read_text()]
            self.assertEqual(len(shown), len(pages) - len(redirects))
            text = (Path(tmp) / "fork" / "index.html").read_text()
            self.assertIn("This copy of the site is built from <code>someone/sentier-bafu</code>. It is not the published site.", text)
            self.assertIn('href="https://github.com/someone/sentier-bafu"', text)
            self.assertTrue(json.loads((Path(tmp) / "fork/api/v1/status.json").read_text())["preview"])
            self.assertEqual(json.loads((Path(tmp) / "fork/api/v1/last-run.json").read_text())["repository"], "someone/sentier-bafu")
            for name in ("own", "plain"):
                self.assertNotIn("preview-notice", (Path(tmp) / name / "index.html").read_text())
                self.assertEqual(json.loads((Path(tmp) / name / "api/v1/last-run.json").read_text())["repository"], REPOSITORY)
            with self.assertRaises(ValueError), contextlib_silence():
                build_site.build(Path(tmp) / "bad", offline=True, root=DATA, built_by="not a repository")

    def test_a_site_built_without_github_says_that_the_run_is_not_shown(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "site"
            with contextlib_silence():
                build_site.build(out, offline=True, root=DATA)
            text = (out / "patch-and-build.html").read_text()
            self.assertIn(lastrun.NOT_SHOWN["not read"], html.unescape(text))
            self.assertNotIn("replay.js", text)
            self.assertNotIn("data-show-after", text)
            self.assertIn("The tagged builds were not read from GitHub for this copy of the site.", text)
            self.assertEqual(json.loads((out / "api/v1/last-run.json").read_text())["state"], "not read")


if __name__ == "__main__":
    unittest.main()
