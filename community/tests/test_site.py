import copy
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import community  # noqa: E402
import triage  # noqa: E402

try:
    import build_site
except ModuleNotFoundError:  # the markdown package is a site-build dependency only
    build_site = None
spec = importlib.util.spec_from_file_location("check_site", ROOT / "scripts/check_site.py")
check_site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_site)
REPO = "https://github.com/sentier-dev/sentier-bafu"


def issue(number, labels, state="open"):
    return dict(number=number, title=f"[Finding] issue {number}", state=state, labels=labels,
                comments=2, updated="2026-11-01", url=f"{REPO}/issues/{number}")


class TriageTests(unittest.TestCase):
    def setUp(self):
        self.findings = community.load_findings(ROOT)
        self.patches = community.load_patches(ROOT)

    def test_every_finding_is_placed_in_a_known_stage(self):
        data = triage.assemble(self.findings, REPO, {})
        self.assertEqual({f["id"] for f in data["findings"]}, {f["id"] for f in self.findings})
        self.assertTrue({f["stage"] for f in data["findings"]} <= set(community.STAGE_ORDER))
        self.assertEqual(sum(data["counts"].values()), len(self.findings))

    def test_stage_comes_from_the_record_not_from_the_tracker(self):
        expected = {f["id"]: community.stage(f) for f in self.findings}
        every_label = [s["key"] for s in community.STATUSES] + sorted(triage.RETIRED_LABELS)
        for issues in ({}, {n: issue(n, ["bafu-finding"] + every_label, "closed") for n in range(1, 60)}):
            placed = triage.assemble(self.findings, REPO, issues)["findings"]
            self.assertEqual({f["id"]: f["stage"] for f in placed}, expected)

    def test_the_joined_view_carries_what_a_page_needs(self):
        data = triage.assemble(self.findings, REPO, {6: issue(6, ["bafu-finding"])}, self.patches)
        placed = {f["id"]: f for f in data["findings"]}
        one = placed["F1"]
        self.assertEqual(one["path"], "community/findings/0/F1.json")
        self.assertEqual(one["tracker"]["comments"], 2)
        self.assertEqual([p["id"] for p in one["patches"]], ["0001"])
        self.assertEqual(one["changed"], one["answer"]["date"])
        self.assertEqual(one["waiting_since"], one["answer"]["date"])
        self.assertIsNone(placed["F2"]["tracker"])
        self.assertEqual(placed["F2"]["patches"], [])
        self.assertEqual(placed["F4"]["related"], ["F31"])
        self.assertIsNone(placed["F4"]["waiting_since"])
        self.assertEqual(data["without_issue"], [f["id"] for f in self.findings if not f["issue"]])
        self.assertTrue(data["without_issue"])
        # Ordered along the path, then newest number first.
        order = [(community.STAGE_ORDER[f["stage"]], -community.finding_number(f)) for f in data["findings"]]
        self.assertEqual(order, sorted(order))

    def test_finding_issue_without_a_record_is_listed(self):
        data = triage.assemble(self.findings, REPO, {9999: issue(9999, ["bafu-finding"])})
        self.assertEqual([i["number"] for i in data["unlisted"]], [9999])
        closed = triage.assemble(self.findings, REPO, {9999: issue(9999, ["bafu-finding"], "closed")})
        self.assertEqual(closed["unlisted"], [])

    def test_labels_follow_records_and_differences_are_a_list_for_maintainers(self):
        self.assertEqual(triage.expected_labels("filed"), {"bafu-finding", "stage: filed", "help wanted"})
        self.assertEqual(triage.expected_labels("answered"), {"bafu-finding", "stage: answered"})
        placed = {f["id"]: f for f in triage.assemble(self.findings, REPO, {})["findings"]}
        answered = next(f for f in placed.values() if f["stage"] == "answered" and f["issue"])
        n = answered["issue"]

        def differences(labels):
            return triage.assemble(self.findings, REPO, {n: issue(n, labels)})["label_differences"]

        self.assertEqual(differences(["bafu-finding", "stage: answered"]), [])
        (lagging,) = differences(["bafu-finding", "upstream-reported", "needs-triage", "stage: sent", "question"])
        self.assertEqual(lagging["issue"], n)
        self.assertEqual(lagging["findings"], [answered["id"]])
        self.assertEqual(lagging["add"], ["stage: answered"])
        # Labels that are not about the stage are left alone.
        self.assertEqual(lagging["remove"], ["needs-triage", "stage: sent", "upstream-reported"])

    def test_an_issue_shared_by_two_findings_shows_the_earlier_stage(self):
        shared = copy.deepcopy([f for f in self.findings if f["issue"] == 3])
        self.assertEqual([f["id"] for f in shared], ["F8", "F10"])
        shared[0]["answer"] = {"date": "2026-11-20", "outcome": "confirmed", "summary": "BAFU said yes.", "url": f"{REPO}/issues/3"}
        (difference,) = triage.assemble(shared, REPO, {3: issue(3, ["bafu-finding"])})["label_differences"]
        self.assertEqual(difference["findings"], ["F8", "F10"])
        self.assertEqual(difference["stage"], "filed")
        self.assertEqual(difference["add"], ["help wanted", "stage: filed"])

    def test_a_required_tracker_that_cannot_be_read_stops_the_build(self):
        original = triage.fetch_issues
        triage.fetch_issues = lambda *a, **k: (_ for _ in ()).throw(OSError("rate limit"))
        try:
            self.assertEqual(triage.load_issues(REPO), ({}, None))
            with self.assertRaises(SystemExit):
                triage.load_issues(REPO, require=True)
        finally:
            triage.fetch_issues = original


@unittest.skipIf(build_site is None, "markdown is not installed")
class SiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "site"
        build_site.build(cls.out, offline=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_built_site_passes_the_link_check(self):
        self.assertEqual(check_site.check(self.out), 0)

    def test_every_record_has_a_page_and_a_list_row(self):
        listing = (self.out / "findings.html").read_text()
        for f in community.load_findings(ROOT):
            self.assertTrue((self.out / f"findings/{f['id']}.html").is_file(), f["id"])
            self.assertIn(f'<tr id="{f["id"]}"', listing)
        for c in community.load_contributions(ROOT):
            self.assertTrue((self.out / f"contributions/{c['id']}.html").is_file(), c["id"])

    def test_status_is_shown_in_words_never_as_a_key(self):
        labels = {s["label"] for s in community.statuses("BAFU")}
        pages = [self.out / "findings.html"] + sorted((self.out / "findings").glob("F*.html"))
        for page in pages:
            badges = re.findall(r'<span class="badge status-[^"]+">([^<]+)</span>', page.read_text())
            self.assertTrue(badges, page.name)
            self.assertTrue(set(badges) <= labels, (page.name, badges))
        listing = (self.out / "findings.html").read_text()
        for f in community.load_findings(ROOT):
            row = listing[listing.index(f'<tr id="{f["id"]}"'):]
            self.assertIn(f'data-stage="{community.stage(f)}"', row[: row.index("</tr>")])

    def test_the_provider_is_named_and_no_placeholder_is_printed(self):
        for page in list(self.out.glob("*.html")) + list((self.out / "findings").glob("*.html")):
            text = page.read_text()
            self.assertNotIn("{provider}", text, page.name)
            self.assertNotIn("The provider decides", text, page.name)
            self.assertNotIn("The provider shipped", text, page.name)
        self.assertIn("Answered by BAFU", (self.out / "findings/F1.html").read_text())

    def test_a_search_finds_a_dataset_the_record_lists(self):
        listing = (self.out / "findings.html").read_text()
        row = listing[listing.index('<tr id="F13"'):]
        self.assertIn("316743", row[: row.index("</tr>")])

    def test_a_record_page_links_to_the_file_where_it_lies(self):
        page = (self.out / "findings/F31.html").read_text()
        self.assertIn(f'{REPO}/blob/main/community/findings/0/F31.json', page)
        self.assertNotIn("community/findings/F31.json", page)
        page = (self.out / "contributions/C001.html").read_text()
        self.assertIn(f'{REPO}/blob/main/community/contributions/C001.json', page)

    def test_patches_are_shown_from_the_snapshot_not_from_the_record(self):
        patches = community.load_patches(ROOT)
        page = (self.out / "findings/F1.html").read_text()
        self.assertIn(patches["patches"][0]["url"], page)
        self.assertIn("Patch 0001", page)
        self.assertNotIn("Patch 00", (self.out / "findings/F2.html").read_text())

    def test_site_builds_without_issue_data(self):
        self.assertIn('"issues": null', (self.out / "status.json").read_text())

    def test_a_rebuild_drops_pages_it_no_longer_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "site"
            out.mkdir()
            (out / "kept.html").write_text("not ours: no earlier build wrote this folder")
            build_site.build(out, offline=True)
            self.assertTrue((out / "kept.html").exists())
            (out / "findings/F9999.html").write_text("left by an earlier build")
            (out / "api/v1/findings/F9999.json").write_text("{}")
            build_site.build(out, offline=True)
            self.assertFalse((out / "findings/F9999.html").exists())
            self.assertFalse((out / "api/v1/findings/F9999.json").exists())
            self.assertFalse((out / "kept.html").exists())
            self.assertTrue((out / "findings/F3.html").exists())

    def test_findings_list_holds_thousands(self):
        site = build_site.Site(self.out, offline=True)
        many = [dict(site.findings[0], id=f"F{n}", issue=n) for n in range(48, 3048)]
        site.triage = triage.assemble(many, site.repo, {})
        self.assertEqual(site.findings_list().count("<tr id="), 3000)

    def test_unlisted_issues_show_a_number_not_their_title(self):
        site = build_site.Site(self.out, offline=True)
        site.triage = triage.assemble(site.findings, site.repo, {9999: issue(9999, ["bafu-finding"])})
        listing = site.findings_list()
        self.assertIn("#9999", listing)
        self.assertNotIn("issue 9999", listing)

    def test_label_differences_stay_out_of_the_pages(self):
        site = build_site.Site(self.out, offline=True)
        site.triage = triage.assemble(site.findings, site.repo, {35: issue(35, ["bafu-finding", "needs-triage"])})
        self.assertTrue(site.triage["label_differences"])
        page = site.finding_page(next(f for f in site.triage["findings"] if f["id"] == "F17"))
        self.assertNotIn("issue's labels", page)
        self.assertNotIn("needs-triage", page)

    def test_missing_page_works_from_any_path(self):
        self.assertIn('<base href="https://', (self.out / "404.html").read_text())

    def test_record_links_in_documents_point_to_their_pages(self):
        site = build_site.Site(self.out, offline=True)
        self.assertEqual(site.target("findings/0/F8.json", "community/workflow.md"), ("findings/F8.html", True))
        self.assertEqual(site.target("contributions/C001.json", "community/workflow.md"), ("contributions/C001.html", True))
        self.assertEqual(site.target("findings/README.md", "community/workflow.md"), ("findings.html", True))
        # A link to a record names the file's real path; one that leads nowhere stops the build.
        for dead in ("findings/F8.json", "findings/1/F8.json", "findings/0/F9999.json"):
            with self.assertRaises(ValueError):
                site.target(dead, "community/workflow.md")

    def test_the_ledger_table_is_published_not_committed(self):
        rows = community.ledger_rows((self.out / "ledger.md").read_text())
        self.assertEqual(set(rows), {f["id"] for f in community.load_findings(ROOT)})
        self.assertFalse((ROOT / "community/findings.md").exists())

    def test_machine_readable_outputs(self):
        findings = community.load_findings(ROOT)
        data = json.loads((self.out / "api/v1/findings.json").read_text())
        self.assertEqual(data["schema"], "sentier-bafu/findings/1")
        self.assertEqual([s["key"] for s in data["statuses"]], [s["key"] for s in community.STATUSES])
        self.assertEqual([f["id"] for f in data["findings"]], [f["id"] for f in findings])
        one = next(f for f in data["findings"] if f["id"] == "F1")
        self.assertEqual(one["status"], "answered")
        self.assertEqual(one["status_label"], "Answered by BAFU")
        self.assertEqual(one["datasets"], [188725, 178351, 242090])
        self.assertEqual(one["patches"], ["0001"])
        self.assertEqual(one["answer_outcome"], "confirmed")
        self.assertEqual(one["answered"], "2026-10-12")
        self.assertEqual(one["url"], "https://sentier-dev.github.io/sentier-bafu/findings/F1.html")
        single = json.loads((self.out / "api/v1/findings/F1.json").read_text())
        self.assertEqual(single["record"], dict(next(f for f in findings if f["id"] == "F1")))
        self.assertEqual(single["status"], "answered")
        self.assertEqual(single["source"], f"{REPO}/blob/main/community/findings/0/F1.json")
        # The published answer names the provider only.
        self.assertEqual(set(single["record"]["answer"]), {"date", "outcome", "summary", "url"})
        datasets = json.loads((self.out / "api/v1/datasets.json").read_text())["datasets"]
        self.assertEqual(datasets["316743"]["findings"], [{"id": "F13", "role": "subject"}])
        self.assertEqual(datasets["188725"]["patches"], ["0001"])
        contributions = json.loads((self.out / "api/v1/contributions.json").read_text())
        self.assertEqual({c["id"]: c["class"] for c in contributions["contributions"]}, {"C001": "model", "C002": "mapping"})
        status = json.loads((self.out / "api/v1/status.json").read_text())
        self.assertEqual(sum(status["findings_by_status"].values()), len(findings))
        self.assertEqual(list(status["findings_by_status"]), [s["key"] for s in community.STATUSES])
        for name in ("finding", "contribution"):
            self.assertEqual((self.out / f"schema/{name}.schema.json").read_text(),
                             (ROOT / f"schema/{name}.schema.json").read_text())
        # Kept at the root for readers that have not moved.
        old = json.loads((self.out / "findings.json").read_text())
        self.assertEqual(set(old[0]), {"id", "title", "status", "stage", "release", "links", "page"})
        self.assertEqual(json.loads((self.out / "status.json").read_text())["findings"], len(findings))

    def test_no_published_file_names_who_answered_for_the_provider(self):
        for path in list(self.out.rglob("*.json")) + list(self.out.rglob("*.html")) + [self.out / "ledger.md"]:
            text = path.read_text()
            self.assertNotIn("provider_response", text, path.name)
            self.assertNotIn('"channel"', text, path.name)

    def test_record_text_never_puts_another_kind_of_address_on_a_page(self):
        site = build_site.Site(self.out, offline=True)
        self.assertIn('href="https://example.org/a"', site.record_text("[a](https://example.org/a)"))
        # The validation refuses these first; the renderer refuses them again.
        for text in ("[x](javascript:alert(1))", "[x][1]\n\n[1]: javascript:alert(1)", "![x](http://other.example/p.png)",
                     "[x](data:text/html,hello)", "[x](../../etc/passwd)"):
            with self.assertRaises(ValueError):
                site.record_text(text)

    def test_the_page_writer_refuses_a_path_outside_the_output_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "site"
            site = build_site.Site(out, offline=True)
            for page in ("../escaped.html", "contributions/../../escaped.html", "/tmp/escaped.html"):
                with self.assertRaises(ValueError):
                    site.write(page, "x")
            self.assertEqual(list(Path(tmp).rglob("escaped.html")), [])
            site.write("findings/F1.html", "inside")
            self.assertTrue((out / "findings/F1.html").is_file())


@unittest.skipIf(build_site is None, "markdown is not installed")
class BuildRefusalTests(unittest.TestCase):
    """The build run as a program on a copy of the repository with one record made invalid.

    What `community.py check` refuses must not reach a page: the build exits non-zero, names
    the file and the rule, and writes nothing.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        shutil.copytree(ROOT, self.root, ignore=shutil.ignore_patterns(".git", "_site", ".local", "__pycache__", ".venv"))
        self.out = Path(self.tmp.name) / "out" / "site"

    def tearDown(self):
        self.tmp.cleanup()

    def fresh(self):
        """A new copy of the repository, for a second case in one test."""
        self.tmp.cleanup()
        self.setUp()

    def build(self):
        return subprocess.run(
            [sys.executable, str(self.root / "scripts/build_site.py"), "--offline", "--out", str(self.out)],
            capture_output=True, text=True,
        )

    def change(self, path, **changes):
        record = json.loads((self.root / path).read_text())
        record.update(changes)
        (self.root / path).write_text(json.dumps(record))

    def assert_refused(self, done, *messages):
        self.assertNotEqual(done.returncode, 0, done.stdout)
        self.assertIn("nothing was built", done.stderr)
        for message in messages:
            self.assertIn(message, done.stderr)
        self.assertNotIn("Traceback", done.stderr)
        self.assertFalse(self.out.exists(), "the build wrote before it validated")

    def test_the_copy_builds_when_nothing_is_wrong(self):
        done = self.build()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.out / "findings/F1.html").is_file())

    def test_raw_html_in_a_finding_stops_the_build(self):
        for field in ("observation", "notes", "scope", "method"):
            self.fresh()
            self.change("community/findings/0/F2.json", **{field: "<script>alert(1)</script>"})
            self.assert_refused(self.build(), f"community/findings/0/F2.json: {field} holds raw HTML")

    def test_raw_html_in_a_contribution_stops_the_build(self):
        self.change("community/contributions/C001.json", title="Layer <img src=x onerror=alert(1)>")
        self.assert_refused(self.build(), "community/contributions/C001.json: title holds raw HTML")

    def test_a_script_address_in_a_contribution_stops_the_build(self):
        self.change("community/contributions/C001.json", evidence=["javascript:alert(1)"])
        self.assert_refused(self.build(), "community/contributions/C001.json: evidence[0] is not a plain https address")

    def test_a_contribution_id_that_is_a_path_stops_the_build_and_writes_nothing_outside(self):
        self.change("community/contributions/C001.json", id="../../escaped")
        self.assert_refused(self.build(), "community/contributions/C001.json: id does not have the required form")
        self.assertEqual(list(Path(self.tmp.name).rglob("escaped.html")), [])

    def test_a_contribution_id_that_carries_markup_stops_the_build(self):
        self.change("community/contributions/C001.json", id='C900"><img src=x onerror=alert(1)>')
        self.assert_refused(self.build(), "community/contributions/C001.json: id does not have the required form")

    def test_an_id_that_is_not_the_file_name_stops_the_build(self):
        self.change("community/contributions/C001.json", id="C900")
        self.assert_refused(self.build(), "community/contributions/C001.json: C900 belongs in a file named C900.json")
        self.fresh()
        self.change("community/findings/0/F2.json", id="F9")
        self.assert_refused(self.build(), "community/findings/0/F2.json: F9 belongs at community/findings/0/F9.json")

    def test_a_finding_id_that_is_a_path_stops_the_build(self):
        self.change("community/findings/0/F2.json", id="../../escaped")
        self.assert_refused(self.build(), "community/findings/0/F2.json: id does not have the required form")
        self.assertEqual(list(Path(self.tmp.name).rglob("escaped.html")), [])

    def test_a_broken_or_incomplete_record_stops_the_build_with_a_message_not_a_traceback(self):
        (self.root / "community/findings/0/F2.json").write_text("{not json")
        self.assert_refused(self.build(), "community/findings/0/F2.json: unreadable record")
        self.fresh()
        record = json.loads((self.root / "community/findings/0/F2.json").read_text())
        del record["kind"]
        (self.root / "community/findings/0/F2.json").write_text(json.dumps(record))
        self.assert_refused(self.build(), "community/findings/0/F2.json: kind is missing")

    def test_an_image_or_a_heading_in_a_record_stops_the_build(self):
        self.change("community/findings/0/F2.json", observation="![x](https://other.example/pixel.png)")
        self.assert_refused(self.build(), "community/findings/0/F2.json: observation embeds an image")
        self.fresh()
        self.change("community/findings/0/F2.json", observation="# A second title\n\ntext")
        self.assert_refused(self.build(), "community/findings/0/F2.json: observation has a heading")


if __name__ == "__main__":
    unittest.main()
