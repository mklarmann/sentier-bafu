import importlib.util
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

    def test_every_finding_is_placed_in_a_known_stage(self):
        data = triage.assemble(self.findings, REPO, {})
        self.assertEqual({f["id"] for f in data["findings"]}, {f["id"] for f in self.findings})
        self.assertTrue({f["stage"] for f in data["findings"]} <= set(triage.STAGE_ORDER))
        self.assertEqual(sum(data["counts"].values()), len(self.findings))

    def test_stage_comes_from_the_record_not_from_the_tracker(self):
        awaiting = {f["id"] for f in self.findings if f["awaiting_second_measurement"]}
        self.assertTrue(awaiting)
        for issues in ({}, {n: issue(n, ["bafu-finding"]) for n in range(1, 60)}):
            placed = triage.assemble(self.findings, REPO, issues)["findings"]
            self.assertEqual({f["id"] for f in placed if f["stage"] == "needs-triage"}, awaiting)

    def test_finding_issue_without_a_record_is_listed(self):
        data = triage.assemble(self.findings, REPO, {9999: issue(9999, ["bafu-finding"])})
        self.assertEqual([i["number"] for i in data["unlisted"]], [9999])
        closed = triage.assemble(self.findings, REPO, {9999: issue(9999, ["bafu-finding"], "closed")})
        self.assertEqual(closed["unlisted"], [])

    def test_issue_labels_that_lag_the_record_are_flagged(self):
        def differs(target, labels):
            n = target["issue_number"]
            data = triage.assemble(self.findings, REPO, {n: issue(n, labels)})
            return next(f["label_differs"] for f in data["findings"] if f["id"] == target["id"])

        placed = triage.assemble(self.findings, REPO, {})["findings"]
        reported = next(f for f in placed if f["status"] == "upstream-reported" and f["issue_number"])
        self.assertTrue(differs(reported, ["bafu-finding"]))
        self.assertFalse(differs(reported, ["bafu-finding", "upstream-reported"]))
        waiting = next(f for f in placed if f["stage"] == "needs-triage" and f["issue_number"])
        self.assertTrue(differs(waiting, ["bafu-finding"]))
        self.assertFalse(differs(waiting, ["bafu-finding", "needs-triage"]))

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
        for path in (ROOT / "community/contributions").glob("*.json"):
            self.assertTrue((self.out / f"contributions/{path.stem}.html").is_file(), path.stem)

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
            build_site.build(out, offline=True)
            self.assertFalse((out / "findings/F9999.html").exists())
            self.assertFalse((out / "kept.html").exists())
            self.assertTrue((out / "findings/F3.html").exists())

    def test_findings_list_holds_thousands(self):
        site = build_site.Site(self.out, offline=True)
        many = [dict(site.findings[0], id=f"F{n}") for n in range(1, 3001)]
        site.triage = triage.assemble(many, site.repo, {})
        self.assertEqual(site.findings_list().count("<tr id="), 3000)

    def test_unlisted_issues_show_a_number_not_their_title(self):
        site = build_site.Site(self.out, offline=True)
        site.triage = triage.assemble(site.findings, site.repo, {9999: issue(9999, ["bafu-finding"])})
        listing = site.findings_list()
        self.assertIn("#9999", listing)
        self.assertNotIn("issue 9999", listing)

    def test_missing_page_works_from_any_path(self):
        self.assertIn('<base href="https://', (self.out / "404.html").read_text())

    def test_record_links_in_documents_point_to_their_pages(self):
        site = build_site.Site(self.out, offline=True)
        self.assertEqual(site.target("findings/F8.json", "community/workflow.md"), ("findings/F8.html", True))
        self.assertEqual(site.target("findings/README.md", "community/workflow.md"), ("findings.html", True))

    def test_the_ledger_table_is_published_not_committed(self):
        rows = community.ledger_rows((self.out / "ledger.md").read_text())
        self.assertEqual(set(rows), {f["id"] for f in community.load_findings(ROOT)})
