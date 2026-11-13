"""Tests of the site build. They check what a page does and says, read from the built
files with an HTML parser, not the exact markup a template happens to write."""

import copy
import datetime
import filecmp
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import community  # noqa: E402
import triage  # noqa: E402

IGNORED = shutil.ignore_patterns(".git", "_site", ".local", "__pycache__", ".venv")
try:
    # Frozen records, where the repository has them (community/tests/frozen.py): what the pages
    # say about a finding is then tested on a copy that does not move when a real finding does.
    import frozen
    DATA, copy_repository = frozen.repository(), frozen.copy_repository
except ModuleNotFoundError:
    DATA = ROOT

    def copy_repository(target):
        shutil.copytree(ROOT, target, ignore=IGNORED)
        return target

try:
    import build_site
    from sitebuild import findings as findings_pages
    from sitebuild import prose
except ModuleNotFoundError:  # the markdown package is a site-build dependency only
    build_site = None
spec = importlib.util.spec_from_file_location("check_site", ROOT / "scripts/check_site.py")
check_site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_site)
REPO = "https://github.com/sentier-dev/sentier-bafu"
EVIDENCE_OF_STEP = dict(zip(triage.PATH, triage.PATH))
# Words the site does not use for its own things ("import fix" is the one use of "fix").
AVOIDED = re.compile(r"\b(stage|stages|triage|ledger|layer|layers|upstream|provider|candidate|fix(?:es|ed)?)\b", re.I)
VOID = {"meta", "link", "br", "img", "input", "hr", "wbr"}


# ------------------------------------------------------------------------- helpers


class Node:
    def __init__(self, tag, attrs, parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, attrs, parent, []

    @property
    def classes(self):
        return (self.attrs.get("class") or "").split()

    def walk(self):
        for child in self.children:
            if isinstance(child, Node):
                yield child
                yield from child.walk()

    def find_all(self, tag=None, cls=None, **attrs):
        return [
            n for n in self.walk()
            if (tag is None or n.tag == tag) and (cls is None or cls in n.classes)
            and all(n.attrs.get(k.replace("_", "-")) == v for k, v in attrs.items())
        ]

    def find(self, tag=None, cls=None, **attrs):
        found = self.find_all(tag, cls, **attrs)
        return found[0] if found else None

    def text(self):
        """The text a reader sees: script and style are left out."""
        if self.tag in ("script", "style"):
            return ""
        return "".join(c.text() if isinstance(c, Node) else c for c in self.children)


class Tree(HTMLParser):
    def __init__(self):
        super().__init__()
        self.root = self.at = Node("document", {})

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs), self.at)
        self.at.children.append(node)
        if tag not in VOID:
            self.at = node

    def handle_endtag(self, tag):
        node = self.at
        while node.parent and node.tag != tag:
            node = node.parent
        if node.parent:
            self.at = node.parent

    def handle_data(self, data):
        self.at.children.append(data)


def parse(source):
    tree = Tree()
    tree.feed(source.read_text() if isinstance(source, Path) else source)
    return tree.root


def squash(text):
    return " ".join(text.split())


def issue(number, labels, state="open"):
    return dict(number=number, title=f"[Finding] issue {number}", state=state, labels=labels,
                comments=2, updated="2026-11-01", url=f"{REPO}/issues/{number}")


SUBJECTS = ["Chloride to water", "Nitrogen oxides to air", "Electricity, medium voltage", "Transport, lorry 16-32t",
            "Heat, natural gas", "Polystyrene, expandable", "Tap water, at user", "Wheat grains, at farm"]
PROBLEMS = ["has no row in the flow list", "carries a unit that differs from its supplier",
            "takes twice the input its comment states", "emits no CO₂ although it burns fuel",
            "links to a dataset that is not in the release", "repeats an exchange number"]


def synthetic_finding(n):
    """One valid finding record F<n> (n above the legacy numbers). The evidence it holds
    follows n, so that a few thousand of them cover every status and every gap."""
    day = datetime.date(2026, 1, 1) + datetime.timedelta(days=n % 280)
    later = lambda days: (day + datetime.timedelta(days=days)).isoformat()  # noqa: E731
    url = f"{REPO}/issues/{n}"
    kind = n % 12
    sent_month = (day.replace(day=1) + datetime.timedelta(days=45)).replace(day=1)
    record = {
        "schema": 2, "id": f"F{n}", "issue": n,
        "title": f"{SUBJECTS[n % len(SUBJECTS)]} {PROBLEMS[n % len(PROBLEMS)]} (case {n})",
        "kind": ("defect", "question", "difference")[n % 3],
        "datasets": [{"code": 800000 + n, "name": f"Synthetic dataset {n}", "location": ("CH", "RER", "GLO")[n % 3]}],
        "scope": "", "releases": ["2026-v1"] if n % 4 else ["2025-v2", "2026-v1"],
        "observation": f"Synthetic observation {n}: the value is 1.{n % 97:02d} where 0.{n % 89:02d} is expected.",
        "exposure": "", "method": "Counted on the release files.",
        "reported": {"by": "first-person", "date": day.isoformat(), "url": url},
        "repeated": None, "sent": None, "answer": None, "fixed_in": None, "closed": None,
        "related": [], "threads": [], "next": {"action": "Repeat the measurement.", "role": "reviewer"},
        "retained": [], "notes": "",
    }
    repeated = {"by": "second-person", "date": later(5), "url": url + "#issuecomment-1", "result": "reproduced"}
    sent = {"batch": sent_month.strftime("%Y-%m"), "date": sent_month.isoformat(), "url": url + "#issuecomment-2"}
    answer = {"date": (sent_month + datetime.timedelta(days=20)).isoformat(), "outcome": "confirmed",
              "summary": "BAFU confirmed the observation.", "url": url + "#issuecomment-3"}
    if kind == 3:
        record["repeated"] = dict(repeated, result="not-reproduced")
    elif kind == 4:
        record["repeated"] = repeated
    elif kind == 5:
        record.update(repeated=repeated, sent=sent)
    elif kind == 6:
        record.update(repeated=repeated, sent=sent, answer=answer)
    elif kind == 7:  # answered, and nobody recorded the second measurement or the report
        record["answer"] = dict(answer, outcome="explained", date=later(40))
    elif kind == 8:
        record.update(sent=sent, answer=dict(answer, outcome="declined"))
    elif kind == 9:
        record.update(repeated=repeated, sent=sent, answer=answer, fixed_in={
            "release": "2026-v1", "detail": "", "date": (sent_month + datetime.timedelta(days=60)).isoformat(),
            "url": url + "#issuecomment-4"})
    elif kind == 10:
        record["closed"] = {"as": "not-a-defect", "date": later(9), "reason": "A convention, not an error.", "url": url}
    elif kind == 11:
        record["closed"] = {"as": "withdrawn", "date": later(9), "reason": "It did not hold when measured again.", "url": url}
    return record


def add_synthetic_findings(root, count, start=1000):
    for n in range(start, start + count):
        path = Path(root) / community.record_path({"id": f"F{n}"})
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(synthetic_finding(n), indent=2, ensure_ascii=False) + "\n")


def tracker_steps(page):
    """The steps of the tracker on a finding page: {evidence name: state}."""
    tracker = parse(page).find("section", "tracker")
    return {
        li.attrs["data-step"]: next(c[3:] for c in li.classes if c.startswith("is-") and c != "is-linked")
        for li in tracker.find_all("li") if "data-step" in li.attrs
    }


# -------------------------------------------------------------------------- triage


class TriageTests(unittest.TestCase):
    def setUp(self):
        self.findings = community.load_findings(DATA)
        self.patches = community.load_patches(DATA)

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
        self.assertEqual([s["key"] for s in one["steps"]], list(triage.PATH))
        self.assertIsNone(placed["F2"]["tracker"])
        self.assertEqual(placed["F2"]["patches"], [])
        self.assertEqual(placed["F4"]["related"], ["F31"])
        self.assertIsNone(placed["F4"]["waiting_since"])
        self.assertEqual(data["without_issue"], [f["id"] for f in self.findings if not f["issue"]])
        self.assertTrue(data["without_issue"])
        # Ordered along the path, then newest number first.
        order = [(community.STAGE_ORDER[f["stage"]], -community.finding_number(f)) for f in data["findings"]]
        self.assertEqual(order, sorted(order))

    def test_a_step_is_done_only_when_the_record_holds_its_evidence(self):
        records = [dict(f) for f in self.findings] + [synthetic_finding(n) for n in range(1000, 1060)]
        seen = set()
        for record in records:
            steps = triage.steps(record)
            states = [s["state"] for s in steps]
            seen.update(states)
            for n, step in enumerate(steps):
                block = record[step["key"]]
                if step["state"] == "done":
                    self.assertTrue(block, (record["id"], step["key"]))
                    if step["key"] == "repeated":
                        self.assertEqual(block["result"], "reproduced", record["id"])
                elif step["state"] == "unrecorded":
                    # A gap: a later step is recorded, this one is not.
                    self.assertIn("done", states[n + 1:], (record["id"], step["key"]))
                    self.assertFalse(block and block.get("result", "reproduced") == "reproduced", record["id"])
            waiting = [s for s in states if s in ("now", "help")]
            self.assertLessEqual(len(waiting), 1, record["id"])
            if record["closed"] or (record["answer"] or {}).get("outcome") == "declined" or record["fixed_in"]:
                self.assertEqual(waiting, [], record["id"])
            else:
                self.assertEqual(len(waiting), 1, record["id"])
        self.assertEqual(seen, {"done", "now", "help", "unrecorded", "todo"})

    def test_the_real_records_show_no_second_measurement_that_is_not_on_record(self):
        for record in self.findings:
            repeated = {s["key"]: s["state"] for s in triage.steps(record)}["repeated"]
            self.assertEqual(repeated == "done", bool(record["repeated"]), record["id"])

    def test_finding_issue_without_a_record_is_listed(self):
        data = triage.assemble(self.findings, REPO, {9999: issue(9999, ["bafu-finding"])})
        self.assertEqual([i["number"] for i in data["unlisted"]], [9999])
        closed = triage.assemble(self.findings, REPO, {9999: issue(9999, ["bafu-finding"], "closed")})
        self.assertEqual(closed["unlisted"], [])

    def test_labels_follow_records_and_differences_are_a_list_for_maintainers(self):
        finding, wanted = triage.FINDING_LABEL, triage.HELP_LABEL
        filed, answered, sent = (triage.expected_labels(key) for key in ("filed", "answered", "sent"))
        self.assertTrue({finding, wanted} <= filed)
        self.assertEqual(len(filed), 3)
        self.assertIn(finding, answered)
        self.assertNotIn(wanted, answered)
        (is_answered,), (is_sent,) = answered - {finding}, sent - {finding}
        self.assertNotEqual(is_answered, is_sent)
        placed = {f["id"]: f for f in triage.assemble(self.findings, REPO, {})["findings"]}
        record = next(f for f in placed.values() if f["stage"] == "answered" and f["issue"])
        n = record["issue"]

        def differences(labels):
            return triage.assemble(self.findings, REPO, {n: issue(n, labels)})["label_differences"]

        self.assertEqual(differences([finding, is_answered]), [])
        (lagging,) = differences([finding, "upstream-reported", "needs-triage", is_sent, "question"])
        self.assertEqual(lagging["issue"], n)
        self.assertEqual(lagging["findings"], [record["id"]])
        self.assertEqual(lagging["add"], [is_answered])
        # Labels that are not about the status are left alone.
        self.assertEqual(lagging["remove"], sorted(["needs-triage", is_sent, "upstream-reported"]))

    def test_an_issue_shared_by_two_findings_shows_the_earlier_stage(self):
        shared = copy.deepcopy([f for f in self.findings if f["issue"] == 3])
        self.assertEqual([f["id"] for f in shared], ["F8", "F10"])
        shared[0]["answer"] = {"date": "2026-11-20", "outcome": "confirmed", "summary": "BAFU said yes.", "url": f"{REPO}/issues/3"}
        (difference,) = triage.assemble(shared, REPO, {3: issue(3, [triage.FINDING_LABEL])})["label_differences"]
        self.assertEqual(difference["findings"], ["F8", "F10"])
        self.assertEqual(difference["stage"], "filed")
        self.assertEqual(difference["add"], sorted(triage.expected_labels("filed") - {triage.FINDING_LABEL}))

    def test_a_required_tracker_that_cannot_be_read_stops_the_build(self):
        original = triage.fetch_issues
        triage.fetch_issues = lambda *a, **k: (_ for _ in ()).throw(OSError("rate limit"))
        try:
            self.assertEqual(triage.load_issues(REPO), ({}, None))
            with self.assertRaises(SystemExit):
                triage.load_issues(REPO, require=True)
        finally:
            triage.fetch_issues = original


# ---------------------------------------------------------------------- the site


@unittest.skipIf(build_site is None, "markdown is not installed")
class SiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "site"
        build_site.build(cls.out, offline=True, root=DATA)
        cls.findings = community.load_findings(DATA)
        cls.config = json.loads((DATA / "site/config.json").read_text())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def pages(self):
        return sorted(self.out.rglob("*.html"))

    def real_pages(self):
        """Every page that is not a redirect or the page for missing addresses."""
        redirects = {self.out / old for old in self.config["redirects"]}
        return [p for p in self.pages() if p not in redirects and p.name != "404.html"]

    # ---- the whole site

    def test_built_site_passes_the_link_check(self):
        self.assertEqual(check_site.check(self.out), 0)

    def test_every_record_has_a_page(self):
        for f in self.findings:
            self.assertTrue((self.out / f"findings/{f['id']}.html").is_file(), f["id"])
        for c in community.load_contributions(DATA):
            self.assertTrue((self.out / f"contributions/{c['id']}.html").is_file(), c["id"])

    def test_every_dataset_a_record_names_has_a_page_that_leads_to_its_findings(self):
        for f in self.findings:
            for d in f["datasets"]:
                page = self.out / f"datasets/{d['code']}.html"
                self.assertTrue(page.is_file(), (f["id"], d["code"]))
                links = {a.attrs.get("href") for a in parse(page).find_all("a")}
                self.assertIn(f"../findings/{f['id']}.html", links, (f["id"], d["code"]))
        # A dataset a finding only names (not its subject) is found too: F13 relabels 316743.
        self.assertIn("316743", (self.out / "datasets/316743.html").read_text())

    def test_every_release_has_a_page_with_the_findings_observed_in_it(self):
        for release in self.config["releases"]:
            page = parse(self.out / f"releases/{release['id']}.html")
            listed = {a.attrs["href"] for a in page.find_all("a", "record-title")}
            expected = {f"../findings/{f['id']}.html" for f in self.findings if release["id"] in f["releases"]}
            self.assertEqual(listed, expected, release["id"])
            self.assertIn(release["name"], page.find("h1").text())

    def test_the_list_page_ships_the_newest_rows_and_the_index_holds_every_finding(self):
        index = json.loads((self.out / "findings/index.json").read_text())
        self.assertEqual(sorted(row[0] for row in index["rows"]), sorted(community.finding_number(f) for f in self.findings))
        # The index is in the order of the page: the most recently changed first.
        changed = [row[index["columns"].index("changed")] for row in index["rows"]]
        self.assertEqual(changed, sorted(changed, reverse=True))
        listing = parse(self.out / "findings.html").find("ul", id="list")
        shown = [li.find("span", "record-id").text() for li in listing.find_all("li", "record")]
        self.assertEqual(shown, [f"F{row[0]}" for row in index["rows"][: findings_pages.PAGE]])
        self.assertEqual(listing.attrs["data-total"], str(len(self.findings)))
        self.assertTrue((self.out / listing.attrs["data-index"]).is_file())

    def test_every_status_can_be_linked_in_the_list_whether_or_not_a_finding_has_it(self):
        page = parse(self.out / "findings.html")
        ids = {n.attrs["id"] for n in page.walk() if "id" in n.attrs}
        chips = {a.attrs["data-filter"]: a.attrs["href"] for a in page.find_all("a", "chip")}
        for status in community.STATUSES:
            self.assertIn(f"stage-{status['key']}", ids)
            self.assertEqual(chips[status["key"]], f"#stage-{status['key']}")
        # The controls that need the script are not shown without it.
        self.assertIn("hidden", page.find("form", id="controls").attrs)
        self.assertIsNotNone(page.find("noscript"))

    def test_the_index_finds_a_dataset_by_its_code_whatever_its_role(self):
        index = json.loads((self.out / "findings/index.json").read_text())
        codes = {row[0]: row[index["columns"].index("codes")] for row in index["rows"]}
        for f in self.findings:
            self.assertEqual(codes[community.finding_number(f)], [d["code"] for d in f["datasets"]], f["id"])
        self.assertIn(316743, codes[13])   # a second subject
        self.assertIn(202096, codes[19])   # an affected consumer

    def test_status_is_shown_in_words_never_as_a_key(self):
        labels = {s["label"] for s in community.statuses("BAFU")}
        listing = parse(self.out / "findings.html").find("ul", id="list")
        rows = listing.find_all("li", "record")
        self.assertTrue(rows)
        by_id = {f["id"]: f for f in self.findings}
        for row in rows:
            rid = row.find("span", "record-id").text()
            self.assertIn(row.find("span", "stage-label").text(), labels)
            self.assertEqual(row.attrs["data-stage"], community.stage(by_id[rid]))
        for f in self.findings:
            page = parse(self.out / f"findings/{f['id']}.html")
            line = squash(page.find("p", "stage-line").text())
            self.assertTrue(line.startswith(community.status_label(community.stage(f), "BAFU") + "."), f["id"])
            self.assertNotIn("not-a-defect", page.find("main").text(), f["id"])

    def test_a_tracker_never_shows_a_step_as_done_without_evidence(self):
        for f in self.findings:
            steps = tracker_steps(self.out / f"findings/{f['id']}.html")
            self.assertEqual(list(steps), list(triage.PATH), f["id"])
            for name, state in steps.items():
                held = bool(f[name]) and (name != "repeated" or f[name]["result"] == "reproduced")
                self.assertEqual(state == "done", held, (f["id"], name, state))
        # Answered by BAFU without a recorded second measurement or report: both say so.
        steps = tracker_steps(self.out / "findings/F1.html")
        self.assertEqual((steps["repeated"], steps["sent"], steps["answer"]), ("unrecorded", "unrecorded", "done"))
        text = squash(parse(self.out / "findings/F1.html").find("section", "tracker").text())
        self.assertEqual(text.count("not recorded"), 4)  # twice for a reader, twice for a screen reader
        # A second measurement that is on record is shown, without a person's name.
        page = parse(self.out / "findings/F13.html")
        self.assertEqual(tracker_steps(self.out / "findings/F13.html")["repeated"], "done")
        self.assertIn("by a second person", page.find("section", "tracker").text())

    def test_the_overview_counts_are_the_counts_of_the_records(self):
        counts = triage.assemble(self.findings, REPO, {})["counts"]
        page = parse(self.out / "index.html")
        shown = {}
        for box in page.find_all(cls="path-count"):
            number = int(box.find("strong").text().replace(",", ""))
            href = box.attrs.get("href", "")
            if href:
                shown[href.split("#stage-")[1]] = number
            else:
                self.assertEqual(number, 0)
        self.assertEqual(shown, {k: v for k, v in counts.items() if k in community.OPEN_STAGES or k == "fixed"})

    def test_the_overview_claims_nothing_the_records_do_not_show(self):
        text = squash(parse(self.out / "index.html").find("main").text())
        for claim in ("repeated by a second person", "Every finding has", "each with evidence and named reviewers",
                      "apply the corrections", "Together"):
            self.assertNotIn(claim, text)
        self.assertIn("a second person is asked to repeat the measurement", text)
        self.assertIn("BAFU decides what it changes", text)
        self.assertIn("Nothing here promises that BAFU adopts a finding", text)

    def test_the_provider_is_named_and_no_placeholder_is_printed(self):
        for page in self.pages():
            text = page.read_text()
            self.assertNotIn("{provider}", text, page.name)
            self.assertNotIn("{p}", text, page.name)
            self.assertNotIn("The provider", text, page.name)
        self.assertIn("Answered by BAFU", (self.out / "findings/F1.html").read_text())

    def test_no_person_is_named_except_for_a_community_patch(self):
        logins = {f[name]["by"] for f in self.findings for name in ("reported", "repeated") if f[name] and f[name]["by"]}
        self.assertTrue(logins)
        for page in self.real_pages():
            text = parse(page).find("main").text()
            for login in logins:
                self.assertNotIn(login, text, page.name)
        # A patch names its author and who authorised it, as the registry does.
        patch = community.load_patches(DATA)["patches"][0]
        text = parse(self.out / "findings/F1.html").find("main").text()
        self.assertIn(patch["author"], text)
        self.assertIn(patch["authorised_by"], text)

    def test_generated_pages_use_the_words_of_the_site(self):
        pages = [self.out / name for name in ("index.html", "changes.html", "housekeeping.html", "404.html")]
        pages += sorted((self.out / "releases").glob("2*.html")) + sorted((self.out / "datasets").glob("[0-9]*.html"))
        for page in pages:
            main = parse(page).find("main")
            for node in main.find_all(cls="record-title") + main.find_all(cls="record-meta") + main.find_all(cls="quiet"):
                node.children = []  # the words of a record's title are the record's
            found = [w for w in AVOIDED.findall(main.text().replace("import fix", ""))]
            self.assertEqual(found, [], page.name)

    def test_every_page_has_its_own_title_and_a_description(self):
        titles = {}
        for page in self.real_pages():
            head = parse(page).find("head")
            title = head.find("title").text()
            description = head.find("meta", name="description").attrs["content"]
            self.assertTrue(description.strip(), page.name)
            self.assertNotIn(title, titles, (page.name, titles.get(title)))
            titles[title] = page.name
        head = parse(self.out / "findings/F1.html").find("head")
        self.assertTrue(head.find("title").text().startswith("F1 · "))
        self.assertIn("Status: Answered by BAFU", head.find("meta", name="description").attrs["content"])
        self.assertEqual(head.find("link", rel="alternate", type="application/json").attrs["href"], "../api/v1/findings/F1.json")
        self.assertEqual(head.find("link", rel="canonical").attrs["href"], self.config["site_url"] + "findings/F1.html")

    def test_dates_are_written_as_dates(self):
        page = parse(self.out / "findings/F1.html")
        times = {t.attrs["datetime"]: t.text() for t in page.find_all("time")}
        self.assertEqual(times["2026-10-12"], "12 Oct 2026")
        self.assertNotIn("2026-10-12", page.find("main").text())

    # ---- record pages

    def test_a_record_page_links_to_the_file_where_it_lies(self):
        page = (self.out / "findings/F31.html").read_text()
        self.assertIn(f'{REPO}/blob/main/community/findings/0/F31.json', page)
        self.assertNotIn("community/findings/F31.json", page)
        page = (self.out / "contributions/C001.html").read_text()
        self.assertIn(f'{REPO}/blob/main/community/contributions/C001.json', page)

    def test_a_finding_page_leads_on(self):
        page = parse(self.out / "findings/F3.html")
        links = {a.attrs.get("href") for a in page.find("main").find_all("a")}
        for target in ("F14.html", "F16.html", "../releases/2026-v1.html", "../patched-release.html",
                       "../findings.html#stage-answered", "../api/v1/findings/F3.json", f"{REPO}/issues/8"):
            self.assertIn(target, links)
        # The discussion is the one primary button of the page.
        primary = page.find("main").find_all("a", "primary")
        self.assertEqual([a.attrs["href"] for a in primary], [f"{REPO}/issues/8"])
        # A finding that waits for a second measurement asks for one.
        waiting = parse(self.out / "findings/F19.html").find("main").text()
        self.assertIn("Can you repeat this measurement?", waiting)
        self.assertNotIn("Can you repeat this measurement?", page.find("main").text())

    def test_bafus_answer_is_set_apart_and_marked_as_a_summary(self):
        answer = parse(self.out / "findings/F1.html").find("section", "answer")
        text = squash(answer.text())
        self.assertIn(next(f for f in self.findings if f["id"] == "F1")["answer"]["summary"], text)
        self.assertIn("not BAFU's own text", text)
        self.assertIsNone(parse(self.out / "findings/F2.html").find("section", "answer"))

    def test_a_contribution_page_says_what_kind_it_is_in_words(self):
        page = parse(self.out / "contributions/C002.html")
        text = squash(page.find("main").text())
        self.assertIn("Mapping · stands beside BAFU's numbers", text)
        self.assertNotIn("elementary-flow-crosswalk-and-method-specific-factor-policy", text)
        record = next(c for c in community.load_contributions(DATA) if c["id"] == "C002")
        # Who the work "goes to" is not printed from the record: BAFU decides, nothing is promised.
        self.assertNotIn(record["upstream_project"], text)

    def test_a_contribution_page_shows_each_required_check_with_its_result(self):
        for c in community.load_contributions(DATA):
            page = parse(self.out / f"contributions/{c['id']}.html")
            rows = page.find("ul", "checks").find_all("li")
            self.assertEqual([r.find("code").text() for r in rows], c["required_checks"])
            results = {check["id"]: check["status"] for run in c["runs"] for check in run["checks"]}
            for row in rows:
                said = row.find("span", "pill").text()
                status = results.get(row.find("code").text(), "not-run")
                self.assertEqual(said, {"passed": "Passed", "failed": "Failed"}.get(status, "Not run"))
                # A check that was not run links to no run record.
                self.assertEqual(bool(row.find("a")), status in ("passed", "failed"))

    def test_the_assessment_of_a_contribution_is_part_of_its_page(self):
        for cid, sources in self.config["assessments"].items():
            page = parse(self.out / f"contributions/{cid}.html")
            self.assertIsNotNone(page.find("h2", id="assessment"), cid)
            self.assertEqual(len(page.find_all("section", "assessment")), len(sources), cid)
            self.assertEqual(len(page.find_all("h1")), 1, cid)

    def test_patches_are_shown_from_the_snapshot_not_from_the_record(self):
        patches = community.load_patches(DATA)
        page = (self.out / "findings/F1.html").read_text()
        self.assertIn(patches["patches"][0]["url"], page)
        self.assertIn("Patch 0001", page)
        self.assertNotIn("Patch 00", (self.out / "findings/F2.html").read_text())

    # ---- lists and generated pages

    def test_unlisted_issues_show_a_number_not_their_title(self):
        site = build_site.Site(self.out, offline=True, root=DATA)
        site.triage = triage.assemble(site.findings, site.repo, {9999: issue(9999, ["bafu-finding"])})
        listing = site.findings_list()
        self.assertIn("#9999", listing)
        self.assertNotIn("issue 9999", listing)

    def test_label_differences_stay_out_of_the_pages(self):
        site = build_site.Site(self.out, offline=True, root=DATA)
        site.triage = triage.assemble(site.findings, site.repo, {35: issue(35, ["bafu-finding", "needs-triage"])})
        self.assertTrue(site.triage["label_differences"])
        page = site.finding_page(next(f for f in site.triage["findings"] if f["id"] == "F17"))
        self.assertNotIn("issue's labels", page)
        self.assertNotIn("needs-triage", page)
        # Housekeeping says which issues differ; the labels themselves are in the build log.
        from sitebuild import pages
        housekeeping = pages.housekeeping(site)
        self.assertIn(f"{REPO}/issues/35", housekeeping)
        (difference,) = site.triage["label_differences"]
        for label in difference["add"] + difference["remove"]:
            self.assertNotIn(label, housekeeping)

    def test_housekeeping_lists_what_needs_a_hand(self):
        text = squash(parse(self.out / "housekeeping.html").find("main").text())
        loose = community.patches_without_finding(community.load_patches(DATA))
        self.assertTrue(loose)
        for patch in loose:
            self.assertIn(f"Patch {patch['id']}", text)
        for f in self.findings:
            if not f["issue"]:
                self.assertIn(f["title"], text)

    def test_the_feedback_page_says_what_is_and_what_is_not_recorded(self):
        page = parse(self.out / "feedback.html")
        text = squash(page.find("main").text())
        answered = [f for f in self.findings if community.stage(f) == "answered"]
        section = {a.attrs["href"]: int(a.find("strong").text()) for a in page.find("ul", "tally").find_all("a")}
        self.assertEqual(section["#answered"], len(answered))
        self.assertEqual(section["#awaiting"], sum(community.stage(f) == "sent" for f in self.findings))
        for f in answered:
            self.assertIn(f["answer"]["summary"], text)
        if not any(f["sent"] for f in self.findings):
            self.assertIn("No report to BAFU is recorded with its date yet", text)
            self.assertIn("the date they were reported is not recorded", text)

    def test_what_changed_is_a_page_and_a_feed_from_the_dated_evidence(self):
        events = community.changes(self.findings)
        page = parse(self.out / "changes.html")
        lines = page.find("ul", "changes").find_all("li")
        self.assertEqual(len(lines), min(len(events), 200))
        self.assertEqual([li.find("time").attrs["datetime"] for li in lines], [e["date"] for e in events[:200]])
        feed = ElementTree.parse(self.out / "feed.xml").getroot()
        atom = "{http://www.w3.org/2005/Atom}"
        entries = feed.findall(atom + "entry")
        self.assertEqual(len(entries), min(len(events), 100))
        self.assertEqual(entries[0].find(atom + "updated").text[:10], events[0]["date"])
        self.assertEqual(feed.find(atom + "updated").text[:10], events[0]["date"])
        ids = [e.find(atom + "id").text for e in entries]
        self.assertEqual(len(ids), len(set(ids)))

    def test_the_sitemap_lists_every_page_and_no_redirect(self):
        root = ElementTree.parse(self.out / "sitemap.xml").getroot()
        listed = {loc.text for loc in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")}
        base = self.config["site_url"]
        expected = {base + p.relative_to(self.out).as_posix() for p in self.real_pages()}
        self.assertEqual(listed, expected)

    def test_every_old_address_leads_to_a_page(self):
        old = {"import.html", "contribute.html", "testing.html", "terms.html", "application.html", "hackathon.html",
               "mapping-review.html", "consensus.html"}
        self.assertTrue(old <= set(self.config["redirects"]))
        for source, target in self.config["redirects"].items():
            page = parse(self.out / source)
            refresh = page.find("meta", http_equiv="refresh").attrs["content"]
            url = refresh.split("url=", 1)[1]
            landing = (self.out / source).parent / url
            self.assertEqual(landing.resolve(), (self.out / target).resolve(), source)
            self.assertTrue(landing.is_file(), source)
            self.assertIsNone(parse(landing).find("meta", http_equiv="refresh"), f"{source} leads to another redirect")
            self.assertEqual(page.find("html").attrs.get("lang"), "en")
            self.assertEqual(page.find("a").attrs["href"], url)
        # A folder address that someone shortens by hand does not end on the page for missing addresses.
        for folder in ("findings", "contributions", "datasets", "releases"):
            self.assertTrue((self.out / folder / "index.html").is_file(), folder)

    def test_missing_page_works_from_any_path(self):
        page = parse(self.out / "404.html")
        self.assertIsNone(page.find("base"))
        prefix = "/sentier-bafu/"
        local = [n.attrs[k] for n in page.walk() for k in ("href", "src", "action")
                 if k in n.attrs and not n.attrs[k].startswith(("https://", "#"))]
        self.assertTrue(local)
        for address in local:
            self.assertTrue(address.startswith(prefix), address)
        self.assertEqual(page.find("form").attrs["action"], prefix + "findings.html")
        self.assertEqual(page.find("input").attrs["name"], "q")

    # ---- prose pages

    def test_record_links_in_documents_point_to_their_pages(self):
        site = build_site.Site(self.out, offline=True, root=DATA)
        self.assertEqual(site.target("findings/0/F8.json", "community/workflow.md"), ("findings/F8.html", True))
        self.assertEqual(site.target("contributions/C001.json", "community/workflow.md"), ("contributions/C001.html", True))
        self.assertEqual(site.target("findings/README.md", "community/workflow.md"), ("findings.html", True))
        # A link to a record names the file's real path; one that leads nowhere stops the build.
        for dead in ("findings/F8.json", "findings/1/F8.json", "findings/0/F9999.json"):
            with self.assertRaises(ValueError):
                site.target(dead, "community/workflow.md")

    def test_links_between_page_sources_and_to_built_files(self):
        site = build_site.Site(self.out, offline=True, root=DATA)
        # A source that became a page under another name still leads to that page.
        self.assertEqual(site.target("import.md", "site/findings.md"), ("patched-release.html", True))
        self.assertEqual(site.target("../docs/terms-of-use.md", "site/findings.md"), ("about/terms.html", True))
        self.assertEqual(site.target("findings.md#stage-filed", "site/take-part.md"), ("findings.html#stage-filed", True))
        # A file of the built site, named from the site folder.
        self.assertEqual(site.target("api/v1/findings.json", "site/data.md"), ("api/v1/findings.json", True))
        self.assertEqual(site.target("../site/feed.xml", "community/build-validation.md"), ("feed.xml", True))
        # Anything else in the repository is a link to the repository.
        url, local = site.target("../CONTRIBUTING.md", "site/take-part.md")
        self.assertEqual((url, local), (f"{REPO}/blob/main/CONTRIBUTING.md", False))

    def test_a_link_to_a_built_file_that_does_not_exist_stops_the_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_repository(Path(tmp) / "repo")
            with (root / "site/data.md").open("a") as page:
                page.write("\nSee [this](no-such-file.json).\n")
            with self.assertRaises(ValueError) as refused:
                build_site.build(Path(tmp) / "out", offline=True, root=root)
            self.assertIn("no-such-file.json", str(refused.exception))

    def test_a_page_can_ask_for_every_generated_block_and_for_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = copy_repository(Path(tmp) / "repo")
            site = build_site.Site(Path(tmp) / "out", offline=True, root=root)
            blocks = sorted(site.blocks())
            self.assertTrue({"findings-list", "contributions-list", "status-tracker", "feedback-lists", "patch-table",
                             "second-measurement-list"} <= set(blocks))
            self.assertIn("status-vocabulary", blocks)
            body = "# Everything\n\nThere are <!-- count:patches --> patches and <!-- generated: count:status:filed --> waiting.\n\n"
            # Both ways of writing a marker work.
            body += "".join(f"<!-- {'generated: ' if n % 2 else ''}{name} -->\n\n" for n, name in enumerate(blocks)
                            if name not in ("findings-list", "contributions-list"))
            (root / "site/data.md").write_text(body)
            page = site.document(next(d for d in site.docs if d["source"] == "site/data.md"))
            self.assertNotIn("<!--", page)
            text = squash(parse(page).find("main").text())
            patches = community.load_patches(DATA)["patches"]
            self.assertIn(f"There are {len(patches)} patches and {site.triage['counts']['filed']} waiting.", text)
            for patch in patches:
                self.assertIn(patch["description"].replace("`", ""), text)
            (root / "site/data.md").write_text("# X\n\n<!-- count:no-such-number -->\n")
            with self.assertRaises(ValueError):
                site.document(next(d for d in site.docs if d["source"] == "site/data.md"))
            # A comment that is not a block stays a comment.
            (root / "site/data.md").write_text("# X\n\n<!-- placeholder: content agent -->\n\ntext\n")
            self.assertIn("<!-- placeholder: content agent -->", site.document(next(d for d in site.docs if d["source"] == "site/data.md")))

    def test_a_table_becomes_labelled_rows_and_never_a_scroller(self):
        source = prose.markdown.markdown(
            "| Clause | Obligation |\n|---|---|\n| **4** | Do not paste text. |\n| **7** | Credit BAFU. sha256 "
            + "a" * 64 + " |\n", extensions=prose.EXTENSIONS)
        table = parse(prose.finish(source)).find("table")
        self.assertEqual([th.attrs["scope"] for th in table.find_all("th")], ["col", "col"])
        for row in table.find("tbody").find_all("tr"):
            self.assertEqual([td.attrs["data-label"] for td in row.find_all("td")], ["Clause", "Obligation"])
        self.assertIn("keyed", table.classes)
        self.assertTrue(table.find_all("wbr"), "a checksum in a cell may break")
        for page in self.real_pages():
            self.assertNotIn("table-scroll", page.read_text(), page.name)

    def test_a_step_table_becomes_a_step_list_with_a_state_per_step(self):
        source = prose.markdown.markdown(
            "| Step | What happens | State |\n|---|---|---|\n| 1. Release | Checked. | Works |\n"
            "| 2. Flows | Linked. | Two ways exist. They are not reconciled. |\n| 3. Exports | Files. | Planned |\n"
            "| 4. Build | A database. | ok: Builds |\n", extensions=prose.EXTENSIONS)
        steps = parse(prose.finish(source)).find("ol", "steps").find_all("li")
        self.assertEqual([[c for c in li.classes if c != "step"] for li in steps], [["ok"], ["part"], ["todo"], ["ok"]])
        self.assertEqual(steps[0].find("h3").text(), "Release")
        self.assertNotIn("ok:", steps[3].text())
        self.assertEqual(prose.tone("works on BAFU's release; not yet on the patched one")[0], "part")
        self.assertEqual(prose.tone("11 patches, 4 of them for a finding")[0], "ok")
        self.assertEqual(prose.tone("does not exist yet")[0], "todo")

    def test_record_text_never_puts_another_kind_of_address_on_a_page(self):
        site = build_site.Site(self.out, offline=True, root=DATA)
        self.assertIn('href="https://example.org/a"', site.record_text("[a](https://example.org/a)"))
        # The validation refuses these first; the renderer refuses them again.
        for text in ("[x](javascript:alert(1))", "[x][1]\n\n[1]: javascript:alert(1)", "![x](http://other.example/p.png)",
                     "[x](data:text/html,hello)", "[x](../../etc/passwd)"):
            with self.assertRaises(ValueError):
                site.record_text(text)

    def test_record_text_links_the_findings_it_names(self):
        site = build_site.Site(self.out, offline=True, root=DATA)
        linked = site.record_text("F14 and F16 are the same class as `F3`, not F9999.", up="../", link_ids=True, own="F3")
        self.assertEqual([a.attrs["href"] for a in parse(linked).find_all("a")], ["../findings/F14.html", "../findings/F16.html"])
        self.assertNotIn("<a", site.record_text("An F1 score of 0.80."))

    # ---- outputs for tools

    def test_site_builds_without_issue_data(self):
        self.assertIn('"issues": null', (self.out / "status.json").read_text())

    def test_the_ledger_table_is_published_not_committed(self):
        rows = community.ledger_rows((self.out / "ledger.md").read_text())
        self.assertEqual(set(rows), {f["id"] for f in self.findings})
        self.assertFalse((ROOT / "community/findings.md").exists())

    def test_machine_readable_outputs(self):
        findings = self.findings
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

    def test_growing_lists_are_written_one_entry_per_line(self):
        findings = self.findings
        text = (self.out / "api/v1/findings.json").read_text()
        rows = [line for line in text.splitlines() if line.startswith('{"id":"F')]
        self.assertEqual(len(rows), len(findings))
        self.assertEqual([json.loads(row.rstrip(","))["id"] for row in rows], [f["id"] for f in findings])
        text = (self.out / "api/v1/datasets.json").read_text()
        codes = [line.split(":")[0].strip('"') for line in text.splitlines() if re.match(r'"\d+":\{', line)]
        self.assertEqual(codes, list(json.loads(text)["datasets"]))
        site = build_site.Site(self.out, offline=True, root=DATA)
        with tempfile.TemporaryDirectory() as tmp:
            site.out = Path(tmp)
            site.write_json("empty.json", {"schema": "x", "findings": []}, one_per_line="findings")
            self.assertEqual(json.loads((Path(tmp) / "empty.json").read_text()), {"schema": "x", "findings": []})

    def test_no_published_file_names_who_answered_for_the_provider(self):
        for path in list(self.out.rglob("*.json")) + list(self.out.rglob("*.html")) + [self.out / "ledger.md"]:
            text = path.read_text()
            self.assertNotIn("provider_response", text, path.name)
            self.assertNotIn('"channel"', text, path.name)

    def test_the_published_files_are_the_font_subset_and_no_inventory(self):
        assets = {p.name for p in (self.out / "assets").iterdir()}
        self.assertIn("nunito-latin.woff2", assets)
        self.assertNotIn("nunito.ttf", assets)
        self.assertIn("OFL.txt", assets)  # the font's licence travels with it
        kinds = {p.suffix for p in self.out.rglob("*") if p.is_file()}
        self.assertEqual(kinds - {".html", ".json", ".xml", ".md", ".css", ".js", ".svg", ".png", ".woff2", ".txt", ""}, set())

    # ---- the build itself

    def test_the_build_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            again = Path(tmp) / "site"
            build_site.build(again, offline=True, root=DATA)

            def files(folder):
                return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())

            self.assertEqual(files(again), files(self.out))
            _, mismatch, errors = filecmp.cmpfiles(self.out, again, files(again), shallow=False)
            self.assertEqual((mismatch, errors), ([], []))

    def test_a_rebuild_drops_what_it_no_longer_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "site"
            out.mkdir()
            (out / "kept.html").write_text("not ours: no earlier build wrote this folder")
            build_site.build(out, offline=True, root=DATA)
            self.assertTrue((out / "kept.html").exists())
            stale = ["findings/F9999.html", "api/v1/findings/F9999.json", "assets/old-script.js", "old-data.json",
                     "feedback/2020-01.html", "gone/page.html"]
            for name in stale:
                (out / name).parent.mkdir(parents=True, exist_ok=True)
                (out / name).write_text("left by an earlier build")
            build_site.build(out, offline=True, root=DATA)
            for name in stale + ["kept.html"]:
                self.assertFalse((out / name).exists(), name)
            self.assertFalse((out / "gone").exists())
            self.assertTrue((out / "findings/F3.html").exists())
            self.assertTrue((out / ".nojekyll").exists())

    def test_the_day_of_the_build_can_be_fixed(self):
        import os
        before = os.environ.get("SOURCE_DATE_EPOCH")
        os.environ["SOURCE_DATE_EPOCH"] = "1794528000"  # 13 November 2026, 00:00 UTC
        try:
            self.assertEqual(build_site.build_date(), "2026-11-13")
        finally:
            if before is None:
                del os.environ["SOURCE_DATE_EPOCH"]
            else:
                os.environ["SOURCE_DATE_EPOCH"] = before
        self.assertRegex(build_site.build_date(), r"^\d{4}-\d{2}-\d{2}$")

    def test_the_site_check_refuses_what_must_not_be_published(self):
        cases = {
            "a link that leads nowhere": lambda out: (out / "changes.html").unlink(),
            "an anchor that is not there": lambda out: (out / "take-part.html").write_text(
                (out / "take-part.html").read_text().replace("</main>", '<a href="findings.html#no-such-anchor">x</a></main>')),
            "an id used twice": lambda out: (out / "housekeeping.html").write_text(
                (out / "housekeeping.html").read_text().replace("</main>", '<i id="main"></i></main>')),
            "an inventory file": lambda out: (out / "inventory.parquet").write_text("x"),
            "a release file in XML": lambda out: (out / "assets/00001.xml").write_text("<ecoSpold/>"),
            "a broken data file": lambda out: (out / "api/v1/status.json").write_text("{"),
            "a link from the root of the host that leaves the site": lambda out: (out / "404.html").write_text(
                (out / "404.html").read_text().replace("</main>", '<a href="/elsewhere/x.html">x</a></main>')),
            "a script address": lambda out: (out / "index.html").write_text(
                (out / "index.html").read_text().replace("</main>", '<a href="javascript:alert(1)">x</a></main>')),
            "a page without a description": lambda out: (out / "changes.html").write_text(
                re.sub(r'<meta name="description"[^>]*>', "", (out / "changes.html").read_text())),
        }
        for name, damage in cases.items():
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "site"
                shutil.copytree(self.out, out)
                self.assertEqual(check_site.check(out), 0, name)
                damage(out)
                self.assertEqual(check_site.check(out), 1, name)

    def test_the_page_writer_refuses_a_path_outside_the_output_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "site"
            site = build_site.Site(out, offline=True, root=DATA)
            for page in ("../escaped.html", "contributions/../../escaped.html", "/tmp/escaped.html"):
                with self.assertRaises(ValueError):
                    site.write(page, "x")
            self.assertEqual(list(Path(tmp).rglob("escaped.html")), [])
            site.write("findings/F1.html", "inside")
            self.assertTrue((out / "findings/F1.html").is_file())


# ------------------------------------------------------------------------- at scale


@unittest.skipIf(build_site is None, "markdown is not installed")
class ScaleTests(unittest.TestCase):
    """The site built from the real records and 3,000 synthetic ones, which hold every kind
    of evidence: reports to BAFU in batches, answers, corrections, gaps, closings."""

    COUNT = 3000

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = copy_repository(Path(cls.tmp.name) / "repo")
        add_synthetic_findings(cls.root, cls.COUNT)
        cls.out = Path(cls.tmp.name) / "site"
        build_site.build(cls.out, offline=True, root=cls.root)
        cls.findings = community.load_findings(cls.root)
        cls.by_id = {f["id"]: f for f in cls.findings}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_three_thousand_findings_build_and_pass_the_link_check(self):
        self.assertEqual(len(self.findings), self.COUNT + len(community.load_findings(DATA)))
        self.assertEqual(check_site.check(self.out), 0)
        for f in self.findings[:: 97]:
            self.assertTrue((self.out / f"findings/{f['id']}.html").is_file(), f["id"])

    def test_the_list_page_stays_small_and_the_index_holds_everything(self):
        page = self.out / "findings.html"
        rows = parse(page).find("ul", id="list").find_all("li", "record")
        self.assertEqual(len(rows), findings_pages.PAGE)
        self.assertLess(page.stat().st_size, 120_000)
        index = json.loads((self.out / "findings/index.json").read_text())
        self.assertEqual(len(index["rows"]), len(self.findings))
        self.assertEqual({row[0] for row in index["rows"]}, {community.finding_number(f) for f in self.findings})
        self.assertLess((self.out / "findings/index.json").stat().st_size, 400 * len(self.findings))
        # What the index says about a finding is what its record says.
        columns = index["columns"]
        keys = [s[0] for s in index["statuses"]]
        for row in index["rows"][:: 53]:
            f = self.by_id[f"F{row[0]}"]
            self.assertEqual(keys[row[columns.index("status")]], community.stage(f))
            self.assertEqual(row[columns.index("changed")], community.last_change(f))
            self.assertEqual(row[columns.index("codes")], [d["code"] for d in f["datasets"]])
            steps = row[columns.index("steps")]
            if not f["closed"]:
                self.assertEqual([c == "d" for c in steps], [s["state"] == "done" for s in triage.steps(f)])

    def test_no_tracker_at_scale_shows_a_step_without_evidence(self):
        for f in self.findings[:: 7]:
            for name, state in tracker_steps(self.out / f"findings/{f['id']}.html").items():
                held = bool(f[name]) and (name != "repeated" or f[name]["result"] == "reproduced")
                self.assertEqual(state == "done", held, (f["id"], name, state))

    def test_every_report_to_the_provider_has_a_page_with_its_findings(self):
        batches = {}
        for f in self.findings:
            if f["sent"]:
                batches.setdefault(f["sent"]["batch"], set()).add(f["id"])
        self.assertGreater(len(batches), 3)
        feedback = parse(self.out / "feedback.html")
        linked = {a.attrs["href"] for a in feedback.find("main").find_all("a")}
        for batch, ids in batches.items():
            self.assertIn(f"feedback/{batch}.html", linked)
            page = parse(self.out / f"feedback/{batch}.html")
            listed = {a.attrs["href"].rsplit("/", 1)[1][:-5] for a in page.find_all("a", "record-title")}
            self.assertEqual(listed, ids, batch)
        # A finding page leads to the report it was part of.
        sent = next(f for f in self.findings if f["sent"])
        links = {a.attrs.get("href") for a in parse(self.out / f"findings/{sent['id']}.html").find_all("a")}
        self.assertIn(f"../feedback/{sent['sent']['batch']}.html", links)

    def test_long_groups_are_cut_and_lead_to_the_filtered_list(self):
        for name in ("feedback.html", "releases/2026-v1.html", "index.html"):
            page = parse(self.out / name)
            for records in page.find_all("ul", "records"):
                self.assertLessEqual(len(records.find_all("li", "record")), 50, name)
            self.assertLess((self.out / name).stat().st_size, 600_000, name)
        release = parse(self.out / "releases/2026-v1.html")
        more = [a.attrs["href"] for a in release.find_all("a", "arrow")]
        self.assertIn("../findings.html?release=2026-v1#stage-filed", more)
        tally = {a.attrs["href"]: int(a.find("strong").text().replace(",", "")) for a in release.find("ul", "tally").find_all("a")}
        observed = [f for f in self.findings if "2026-v1" in f["releases"]]
        self.assertEqual(tally["#status-filed"], sum(community.stage(f) == "filed" for f in observed))

    def test_what_changed_shows_the_newest_and_says_how_many_there_are(self):
        events = community.changes(self.findings)
        self.assertGreater(len(events), 200)
        page = parse(self.out / "changes.html")
        self.assertEqual(len(page.find("ul", "changes").find_all("li")), 200)
        self.assertIn(f"{len(events):,} steps are recorded", squash(page.find("main").text()))
        feed = ElementTree.parse(self.out / "feed.xml").getroot()
        self.assertEqual(len(feed.findall("{http://www.w3.org/2005/Atom}entry")), 100)


# --------------------------------------------------------------- refused builds


@unittest.skipIf(build_site is None, "markdown is not installed")
class BuildRefusalTests(unittest.TestCase):
    """The build run as a program on a copy of the repository with one record made invalid.

    What `community.py check` refuses must not reach a page: the build exits non-zero, names
    the file and the rule, and writes nothing.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = copy_repository(Path(self.tmp.name) / "repo")
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

    def test_odd_but_honest_text_is_written_escaped(self):
        odd = 'Quotes "and" <5 % & an ampersand, مرحبا, 🙂, ' + "x" * 300
        self.change("community/findings/0/F2.json", title=odd)
        done = self.build()
        self.assertEqual(done.returncode, 0, done.stderr)
        for name in ("findings/F2.html", "findings.html", "index.html", "datasets/191385.html"):
            source = (self.out / name).read_text()
            self.assertNotIn("<5 %", source, name)
            if name != "index.html":
                self.assertIn("Quotes &quot;and&quot; &lt;5 % &amp; an ampersand", source, name)
        index = json.loads((self.out / "findings/index.json").read_text())
        self.assertEqual(next(row for row in index["rows"] if row[0] == 2)[1], odd)


if __name__ == "__main__":
    unittest.main()
