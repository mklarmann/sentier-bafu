"""The label job: issues follow records. No test reaches the network.

fixtures/github/issues-bafu-finding.json is the answer of the public API to
`GET /issues?state=all&labels=bafu-finding`, saved on 13 November 2026 and cut to the fields
the job reads; labels.json is the repository's label list of the same day.
"""

import contextlib
import copy
import datetime
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import community  # noqa: E402
import frozen  # noqa: E402
import sync  # noqa: E402
from fake_github import REPOSITORY, FakeGitHub  # noqa: E402
from github_api import GitHub  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures/github"
REPO = "https://github.com/sentier-dev/sentier-bafu"
# Frozen records and a frozen release list (fixtures/frozen): the life of a real finding breaks no test.
CONFIG = community.load_config(frozen.RECORDS)
RECORDED = json.loads((FIXTURES / "issues-bafu-finding.json").read_text())
LABELS = json.loads((FIXTURES / "labels.json").read_text())
FILED = "status: needs a second measurement"


def finding(number=48, **changes):
    record = {
        "schema": 2, "id": f"F{number}", "issue": number,
        "title": "Example dataset: the amount is a thousand times its siblings'", "kind": "defect",
        "datasets": [{"code": 100000 + number, "name": f"Example {number}, at plant", "location": "CH"}],
        "scope": "", "releases": ["2026-v1"],
        "observation": "The dataset declares 1,000 kg where its siblings declare 1 kg.", "exposure": "",
        "method": "Measured on the release files.",
        "reported": {"by": "reporter", "date": "2026-11-20", "url": f"{REPO}/issues/{number}"},
        "repeated": None, "sent": None, "answer": None, "fixed_in": None, "closed": None,
        "related": [], "threads": [], "next": None, "retained": [], "notes": "",
    }
    record.update(copy.deepcopy(changes))
    return record


REPEATED = {"by": "second-person", "date": "2026-11-22", "url": f"{REPO}/issues/48#issuecomment-1", "result": "reproduced"}
SENT = {"batch": "2026-11", "date": "2026-11-25", "url": f"{REPO}/issues/48#issuecomment-2"}
ANSWER = {"date": "2026-12-01", "outcome": "confirmed", "summary": "BAFU said it will correct the amount.",
          "url": f"{REPO}/issues/48#issuecomment-3"}
FIXED = {"release": "2026-v1", "date": "2026-12-20", "url": f"{REPO}/issues/48#issuecomment-4"}
WITHDRAWN = {"as": "withdrawn", "date": "2026-11-23", "reason": "It did not hold when measured again.",
             "url": f"{REPO}/issues/48"}
PATH = [{}, {"repeated": REPEATED}, {"repeated": REPEATED, "sent": SENT},
        {"repeated": REPEATED, "sent": SENT, "answer": ANSWER},
        {"repeated": REPEATED, "sent": SENT, "answer": ANSWER, "fixed_in": FIXED}]


def issue(labels=("bafu-finding",), state="open"):
    return {"state": state, "state_reason": None, "labels": sorted(labels)}


class LabelTests(unittest.TestCase):
    def test_a_label_says_the_status_in_the_words_of_the_site(self):
        self.assertEqual(
            [sync.label_for(status["key"], "BAFU") for status in community.STATUSES],
            ["status: needs a second measurement", "status: repeated not yet reported", "status: reported to BAFU",
             "status: answered by BAFU", "status: corrected by BAFU", "status: for information", "status: withdrawn"],
        )
        self.assertEqual(sync.label_for("sent", "ADEME"), "status: reported to ADEME")

    def test_labels_fit_what_github_accepts(self):
        names = [sync.label_for(status["key"], "BAFU") for status in community.STATUSES]
        self.assertEqual(len(names), len(set(names)))
        for name in list(sync.definitions("BAFU")) + names:
            self.assertLessEqual(len(name), 50, name)
            self.assertNotIn(",", name)
        for name, (colour, description) in sync.definitions("BAFU").items():
            self.assertRegex(colour, r"\A[0-9a-f]{6}\Z")
            self.assertLessEqual(len(description), 100, name)

    def test_what_an_issue_carries(self):
        self.assertEqual(sync.expected_labels("filed", "BAFU"), {"bafu-finding", FILED, "help wanted"})
        self.assertEqual(sync.expected_labels("answered", "BAFU"), {"bafu-finding", "status: answered by BAFU"})
        self.assertEqual(sync.expected_labels(None, "BAFU"), {"bafu-finding", "needs-triage"})
        for key in community.STAGE_ORDER:
            labels = sync.expected_labels(key, "BAFU")
            self.assertEqual(sum(1 for label in labels if label.startswith("status: ")), 1, key)
            self.assertEqual("help wanted" in labels, key == "filed", key)

    def test_the_job_owns_its_labels_and_no_others(self):
        for label in (FILED, "status: anything in other words", "help wanted", "needs-triage",
                      "upstream-reported", "upstream-fixed", "informational", "handled-in-layer", "withdrawn"):
            self.assertTrue(sync.owned(label), label)
        for label in ("bafu-finding", "question", "discussion", "needs-info", "licence", "bug", "contribution"):
            self.assertFalse(sync.owned(label), label)


class PlanTests(unittest.TestCase):
    def plan(self, findings, issues):
        return sync.plan(findings, issues, CONFIG)

    def one(self, record, labels=("bafu-finding",), state="open"):
        (entry,) = self.plan([record], {record["issue"]: issue(labels, state)}) or [None]
        return entry

    def test_an_issue_that_agrees_with_its_record_is_no_difference(self):
        for n, evidence in enumerate(PATH[:4]):
            record = finding(**evidence)
            labels = sync.expected_labels(community.stage(record), "BAFU")
            self.assertEqual(self.plan([record], {48: issue(labels)}), [], n)
        fixed = finding(**PATH[4])
        self.assertEqual(self.plan([fixed], {48: issue(sync.expected_labels("fixed", "BAFU"), "closed")}), [])

    def test_a_new_record_gets_its_labels_and_one_comment(self):
        entry = self.one(finding(), ("bafu-finding", "needs-triage"))
        self.assertEqual(entry["add"], ["help wanted", FILED])
        self.assertEqual(entry["remove"], ["needs-triage"])
        self.assertTrue(entry["announce"])
        self.assertEqual(entry["marker"], "sync: F48=filed")
        self.assertIsNone(entry["close"])
        self.assertIn("/repeated reproduced", entry["comment"])
        self.assertIn("status **Needs a second measurement**", entry["comment"])
        self.assertIn("https://sentier-dev.github.io/sentier-bafu/findings/F48.html", entry["comment"])

    def test_each_step_of_the_path_changes_one_label_and_says_so_once(self):
        labels = sync.expected_labels("filed", "BAFU")
        words = ["second-person repeated the measurement on 22 November 2026 and reproduced it",
                 "Reported to BAFU on 25 November 2026, in batch 2026-11",
                 "BAFU answered on 1 December 2026 (confirmed;",
                 "The correction was checked in BAFU:2026 v1 on 20 December 2026"]
        for evidence, said in zip(PATH[1:], words):
            record = finding(**evidence)
            key = community.stage(record)
            entry = self.one(record, labels)
            self.assertEqual(entry["add"], [sync.label_for(key, "BAFU")], key)
            self.assertEqual(entry["remove"], sorted(labels - sync.expected_labels(key, "BAFU")), key)
            self.assertTrue(entry["announce"], key)
            self.assertEqual(entry["marker"], f"sync: F48={key}")
            self.assertIn(said, entry["comment"])
            self.assertEqual(entry["close"], "completed" if key == "fixed" else None)
            labels = sync.expected_labels(key, "BAFU")

    def test_the_answer_is_quoted_from_the_record_and_promises_nothing(self):
        entry = self.one(finding(**PATH[3]), sync.expected_labels("sent", "BAFU"))
        self.assertIn("> BAFU said it will correct the amount.", entry["comment"])
        self.assertIn("Whether the data changes will show in a later release.", entry["comment"])
        self.assertNotIn("@", entry["comment"])

    def test_a_final_status_closes_the_issue_with_its_reason(self):
        cases = (
            (finding(closed=WITHDRAWN), "withdrawn", "not_planned"),
            (finding(closed=dict(WITHDRAWN, **{"as": "not-a-defect"})), "not-a-defect", "not_planned"),
            (finding(**PATH[4]), "fixed", "completed"),
        )
        for record, key, reason in cases:
            entry = self.one(record, sync.expected_labels("filed", "BAFU"))
            self.assertEqual(entry["close"], reason, key)
            self.assertIn("This issue is closed. The finding stays listed on the site.", entry["comment"])
            closed = self.one(record, sync.expected_labels("filed", "BAFU"), "closed")
            self.assertIsNone(closed["close"], "an issue that is closed is not closed again")
        self.assertIn("> It did not hold when measured again.", self.one(cases[0][0])["comment"])

    def test_a_closed_issue_whose_finding_is_still_on_its_way_is_for_a_person(self):
        entry = self.one(finding(), sync.expected_labels("filed", "BAFU"), "closed")
        self.assertEqual((entry["add"], entry["remove"], entry["announce"], entry["close"]), ([], [], False, None))
        self.assertIn("#48 is closed, but F48 is still on its way (Needs a second measurement)", entry["person"][0])

    def test_a_label_set_by_hand_is_put_right_without_a_comment_when_the_status_is_unchanged(self):
        right = sync.expected_labels("sent", "BAFU")
        entry = self.one(finding(**PATH[2]), right | {"help wanted", "upstream-fixed", "question"})
        self.assertEqual((entry["add"], entry["remove"]), ([], ["help wanted", "upstream-fixed"]))
        self.assertFalse(entry["announce"])
        # A second status label set by hand goes; the right one stays.
        entry = self.one(finding(**PATH[2]), right | {"status: corrected by BAFU"})
        self.assertEqual((entry["add"], entry["remove"], entry["announce"]), ([], ["status: corrected by BAFU"], False))
        # The right label taken off by hand, another of today's put on: it reads as a change and is said once.
        entry = self.one(finding(**PATH[2]), {"bafu-finding", "status: corrected by BAFU"})
        self.assertEqual(entry["add"], ["status: reported to BAFU"])
        self.assertTrue(entry["announce"])

    def test_labels_in_other_words_are_replaced_without_a_comment(self):
        """The vocabulary of the site changed: every issue is relabelled, nobody is notified."""
        entry = self.one(finding(**PATH[2]), {"bafu-finding", "status: sent to the provider"})
        self.assertEqual(entry["add"], ["status: reported to BAFU"])
        self.assertEqual(entry["remove"], ["status: sent to the provider"])
        self.assertFalse(entry["announce"])
        self.assertIsNone(entry["comment"])

    def test_labels_of_other_people_are_left_alone(self):
        entry = self.one(finding(), ("bafu-finding", "question", "licence", "good first issue"))
        self.assertEqual(entry["remove"], [])

    def test_an_issue_shared_by_two_findings_shows_the_earlier_status(self):
        first, second = finding(8, issue=3, **PATH[3]), finding(10, issue=3)
        (entry,) = self.plan([second, first], {3: issue()})
        self.assertEqual((entry["findings"], entry["stage"]), (["F8", "F10"], "filed"))
        self.assertEqual(entry["add"], ["help wanted", FILED])
        self.assertEqual(entry["marker"], "sync: F8=answered F10=filed")
        self.assertIn("**[F8](", entry["comment"])
        self.assertIn("**[F10](", entry["comment"])
        # Closed only when both are final.
        done = dict(PATH[4])
        (entry,) = self.plan([finding(8, issue=3, **done), finding(10, issue=3)], {3: issue()})
        self.assertIsNone(entry["close"])
        (entry,) = self.plan([finding(8, issue=3, **done), finding(10, issue=3, closed=WITHDRAWN)], {3: issue()})
        self.assertEqual((entry["stage"], entry["close"]), ("fixed", "completed"))

    def test_an_issue_without_a_record_waits_for_a_maintainer(self):
        (entry,) = self.plan([], {60: issue(("bafu-finding",))})
        self.assertEqual((entry["findings"], entry["stage"], entry["add"]), ([], None, ["needs-triage"]))
        self.assertFalse(entry["announce"])
        self.assertEqual(self.plan([], {60: issue(("bafu-finding", "needs-triage"))}), [])
        self.assertEqual(self.plan([], {60: issue(("bafu-finding", "needs-triage"), "closed")}), [])
        self.assertEqual(self.plan([], {60: issue(("bafu-finding",), "closed")}), [])

    def test_a_deleted_record_takes_its_labels_with_it(self):
        labels = sync.expected_labels("answered", "BAFU")
        (entry,) = self.plan([], {48: issue(labels)})
        self.assertEqual((entry["add"], entry["remove"]), (["needs-triage"], ["status: answered by BAFU"]))
        self.assertFalse(entry["announce"])
        self.assertIsNone(entry["close"])
        (entry,) = self.plan([], {48: issue(sync.expected_labels("fixed", "BAFU"), "closed")})
        self.assertEqual((entry["add"], entry["remove"]), ([], ["status: corrected by BAFU"]))

    def test_a_record_that_names_no_issue_of_the_repository_is_for_a_person(self):
        (entry,) = self.plan([finding()], {48: None})
        self.assertEqual(entry["person"], ["F48 names issue #48, which is not an issue of this repository."])
        self.assertEqual((entry["add"], entry["remove"], entry["announce"], entry["close"]), ([], [], False, None))
        self.assertEqual(self.plan([finding(issue=None, threads=[f"{REPO}/issues/1"])], {}), [])


class RecordedTests(unittest.TestCase):
    """The records of 13 November 2026 against the issues as the public API listed them that day."""

    def setUp(self):
        self.findings = community.load_findings(frozen.RECORDS)
        self.issues = sync.snapshot_issues(FIXTURES / "issues-bafu-finding.json", self.findings)

    def test_the_recorded_list_is_what_the_api_answered(self):
        self.assertEqual(len(RECORDED), 18)
        self.assertEqual(set(self.issues), {record["issue"] for record in self.findings if record["issue"]})
        self.assertTrue(all("bafu-finding" in item["labels"] for item in self.issues.values()))

    def test_every_issue_differs_before_the_first_run(self):
        differences = sync.plan(self.findings, self.issues, CONFIG)
        self.assertEqual(len(differences), 18)
        by_issue = {entry["issue"]: entry for entry in differences}
        self.assertEqual(by_issue[3]["findings"], ["F8", "F10"])
        self.assertEqual(by_issue[3]["remove"], ["handled-in-layer"])
        self.assertEqual(by_issue[32]["close"], "not_planned")
        self.assertEqual(by_issue[32]["remove"], ["handled-in-layer", "informational"])
        self.assertEqual(by_issue[35]["close"], "completed")
        self.assertEqual(by_issue[35]["add"], ["status: corrected by BAFU"])
        self.assertEqual([n for n, entry in by_issue.items() if entry["close"]], [32, 35])
        self.assertTrue(all(entry["announce"] for entry in differences))
        self.assertFalse(any(entry["person"] for entry in differences))

    def test_after_one_run_nothing_differs_and_a_second_run_writes_nothing(self):
        fake = FakeGitHub(
            issues={item["number"]: {"labels": [label["name"] for label in item["labels"]], "state": item["state"]}
                    for item in RECORDED},
            labels=[label["name"] for label in LABELS],
        )
        api = GitHub(REPOSITORY, "token", transport=fake)
        differences = sync.plan(self.findings, sync.read_issues(api, self.findings), CONFIG)
        done, left, stopped = sync.apply(differences, api, "BAFU", pause=lambda seconds: None)
        self.assertEqual((done, left, stopped), (18, 0, None))
        self.assertEqual(sync.plan(self.findings, sync.read_issues(api, self.findings), CONFIG), [])
        self.assertEqual({n for n, item in fake.issues.items() if item["state"] == "closed"}, {32, 35})
        self.assertEqual(fake.issues[35]["state_reason"], "completed")
        self.assertEqual(fake.issues[32]["state_reason"], "not_planned")
        self.assertTrue(all(len(item["comments"]) == 1 for item in fake.issues.values()))
        for item in fake.issues.values():
            self.assertEqual(sum(1 for label in item["labels"] if label.startswith("status: ")), 1)
            self.assertFalse(set(item["labels"]) & sync.RETIRED_LABELS)
        writes = len(fake.writes())
        self.assertEqual(sync.apply([], api, "BAFU"), (0, 0, None))
        self.assertEqual(len(fake.writes()), writes)


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeGitHub(issues={48: {"labels": ["bafu-finding", "needs-triage", "question"]}},
                               labels=["bafu-finding", "needs-triage", "help wanted", "question"])
        self.api = GitHub(REPOSITORY, "token", transport=self.fake)
        self.pauses = []

    def sync(self, findings, **options):
        differences = sync.plan(findings, sync.read_issues(self.api, findings), CONFIG)
        return sync.apply(differences, self.api, "BAFU", pause=self.pauses.append, **options)

    def labels(self, number=48):
        return set(self.fake.issues[number]["labels"])

    def test_the_whole_path_one_label_and_one_comment_at_a_time(self):
        seen = []
        for evidence in PATH:
            record = finding(**evidence)
            self.sync([record])
            key = community.stage(record)
            self.assertEqual(self.labels(), sync.expected_labels(key, "BAFU") | {"question"}, key)
            seen.append(f"<!-- sync: F48={key} -->")
            self.assertEqual([body.splitlines()[0] for body in self.fake.bodies(48)], seen)
            writes = len(self.fake.writes())
            self.sync([record])
            self.assertEqual(len(self.fake.writes()), writes, "a second run writes nothing")
        self.assertEqual((self.fake.issues[48]["state"], self.fake.issues[48]["state_reason"]), ("closed", "completed"))
        self.assertEqual(self.pauses, [1] * 5)

    def test_missing_labels_are_created_with_a_colour_and_a_description(self):
        self.sync([finding()])
        created = self.fake.labels[FILED]
        self.assertEqual((created["color"], created["description"]), ("b8860b", sync.WRITTEN))
        self.assertEqual(self.fake.labels["needs-triage"]["description"],
                         "Filed as a finding; no record of it has been merged yet.")
        # Labels the job does not define are used as they are.
        self.assertEqual(self.fake.labels["help wanted"]["description"], "")
        self.assertEqual(self.fake.labels["bafu-finding"]["description"], "")
        # Every status label and the label of the contribution form exist after the first run:
        # a form applies a label only if the label exists.
        created = [call[2]["name"] for call in self.fake.writes() if call[:2] == ("POST", "/labels")]
        self.assertEqual(created, sorted(["contribution"] + list(sync.status_labels("BAFU"))))
        writes = len(self.fake.writes())
        self.sync([finding()])
        self.assertEqual(len(self.fake.writes()), writes, "and are not created twice")

    def test_no_comment_is_posted_when_asked_not_to(self):
        self.sync([finding()], comments=False)
        self.assertEqual(self.fake.bodies(48), [])
        self.assertEqual(self.labels(), sync.expected_labels("filed", "BAFU") | {"question"})
        self.sync([finding()])
        self.assertEqual(self.fake.bodies(48), [], "the labels agree, so nothing is announced later either")

    def test_a_comment_that_is_already_there_is_not_posted_again(self):
        self.fake.issues[48]["comments"].append({"id": 1, "body": "<!-- sync: F48=filed -->\nearlier run", "user": {}})
        self.sync([finding()])
        self.assertEqual(len(self.fake.bodies(48)), 1)
        self.assertEqual(self.labels(), sync.expected_labels("filed", "BAFU") | {"question"})
        self.assertEqual(self.pauses, [])

    def test_the_rate_limit_stops_the_run_and_the_next_run_goes_on(self):
        findings = [finding(n) for n in range(48, 58)]
        for n in range(49, 58):
            self.fake.add_issue(n, ["bafu-finding", "needs-triage"])
        differences = sync.plan(findings, sync.read_issues(self.api, findings), CONFIG)
        self.fake.remaining = 22  # used up in the middle of an issue
        done, left, stopped = sync.apply(differences, self.api, "BAFU", pause=self.pauses.append, reserve=0)
        self.assertEqual(stopped, "the rate limit is used up")
        self.assertEqual(done + left, 10)
        self.assertTrue(0 < done < 10)
        self.fake.remaining = 5000
        again = sync.plan(findings, sync.read_issues(self.api, findings), CONFIG)
        self.assertEqual(len(again), left)
        self.assertEqual(sync.apply(again, self.api, "BAFU", pause=self.pauses.append), (left, 0, None))
        self.assertEqual(sync.plan(findings, sync.read_issues(self.api, findings), CONFIG), [])
        for n in range(48, 58):
            self.assertEqual(len(self.fake.bodies(n)), 1, f"#{n} was told once")
            self.assertEqual(set(self.fake.issues[n]["labels"]) - {"question"}, sync.expected_labels("filed", "BAFU"))

    def test_the_job_leaves_requests_for_the_other_workflows(self):
        findings = [finding(n) for n in range(48, 53)]
        for n in range(49, 53):
            self.fake.add_issue(n, ["bafu-finding", "needs-triage"])
        differences = sync.plan(findings, sync.read_issues(self.api, findings), CONFIG)
        self.fake.remaining = 40
        done, left, stopped = sync.apply(differences, self.api, "BAFU", pause=self.pauses.append, reserve=25)
        self.assertEqual(stopped, "the rate limit is nearly used up")
        self.assertGreaterEqual(self.fake.remaining, 20)
        self.assertTrue(0 < done < 5 and left == 5 - done)

    def test_a_label_that_is_already_gone_is_no_error(self):
        differences = sync.plan([finding()], sync.read_issues(self.api, [finding()]), CONFIG)
        self.fake.issues[48]["labels"].remove("needs-triage")  # someone was faster
        self.assertEqual(sync.apply(differences, self.api, "BAFU", pause=self.pauses.append), (1, 0, None))

    def test_issues_a_record_names_are_read_even_without_the_label(self):
        self.fake.add_issue(70, ["question"])
        self.fake.add_issue(71, ["bafu-finding"], pull_request=True)
        findings = [finding(70), finding(71), finding(72)]
        issues = sync.read_issues(self.api, findings)
        self.assertEqual(issues[70]["labels"], ["question"])
        self.assertIsNone(issues[71], "a pull request is not an issue")
        self.assertIsNone(issues[72], "an issue that does not exist")
        planned = sync.plan(findings, issues, CONFIG)
        differences = {entry["issue"]: entry for entry in planned}
        self.assertEqual(differences[70]["add"], ["bafu-finding", "help wanted", FILED])
        self.assertTrue(differences[71]["person"] and differences[72]["person"])
        # What is left for a person is not counted as done, and nothing is written for it.
        self.assertEqual(sync.apply(planned, self.api, "BAFU", pause=self.pauses.append), (1, 0, None))
        self.assertEqual({call[1].split("/")[2] for call in self.fake.writes() if call[1].startswith("/issues/")}, {"70"})

    def test_more_than_a_hundred_issues_are_read_page_by_page(self):
        for n in range(100, 350):
            self.fake.add_issue(n, ["bafu-finding", "needs-triage"])
        self.assertEqual(len(sync.read_issues(self.api, [])), 251)
        self.assertEqual(sum(1 for call in self.fake.calls if call[1] == "/issues"), 3)


class MainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = frozen.workspace(Path(self.tmp.name) / "workspace")
        self.fake = FakeGitHub(
            issues={item["number"]: {"labels": [label["name"] for label in item["labels"]], "state": item["state"]}
                    for item in RECORDED},
            labels=[label["name"] for label in LABELS],
        )
        self.addCleanup(self.tmp.cleanup)
        self.pauses = []

    def run_sync(self, *args, env=None):
        out = io.StringIO()
        code = sync.main(["--root", str(self.root), *args], env or {}, self.fake,
                         lambda *parts, **options: print(*parts, file=out, **options), self.pauses.append)
        return code, out.getvalue()

    def test_without_apply_the_differences_are_printed_and_nothing_is_written(self):
        code, text = self.run_sync()
        self.assertEqual(code, 0)
        self.assertIn("Records: 23 findings; 19 are discussed in 18 issues of this repository; "
                      "4 have no issue here (F4, F5, F6, F7).", text)
        self.assertIn("Issues that differ from their record: 18.", text)
        self.assertIn('#35 (F17: Corrected by BAFU): add "status: corrected by BAFU"; remove "needs-triage"; '
                      "comment once; close as completed", text)
        self.assertIn("Nothing was written.", text)
        self.assertEqual(self.fake.writes(), [])

    def test_apply_writes_and_says_how_many(self):
        code, text = self.run_sync("--apply")
        self.assertEqual(code, 0)
        self.assertIn("sync: 18 issues brought into agreement with their records.", text)
        self.assertEqual(self.pauses, [1] * 18, "a pause after each comment")
        code, text = self.run_sync()
        self.assertIn("Issues that differ from their record: 0.", text)

    def test_a_saved_list_can_stand_in_for_the_network_but_never_for_apply(self):
        code, text = self.run_sync("--issues", str(FIXTURES / "issues-bafu-finding.json"))
        self.assertEqual(code, 0)
        self.assertIn("Issues that differ from their record: 18.", text)
        self.assertEqual(self.fake.calls, [])
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            self.run_sync("--apply", "--issues", str(FIXTURES / "issues-bafu-finding.json"))
        self.assertEqual(self.fake.calls, [])

    def test_the_summary_is_written_for_the_job_page(self):
        target = self.root / "summary.md"
        self.run_sync("--summary", str(target))
        self.assertIn("- #35 (F17: Corrected by BAFU)", target.read_text())

    def test_records_that_are_not_valid_stop_the_job_before_it_reads_anything(self):
        path = self.root / "community/findings/0/F1.json"
        path.write_text(path.read_text().replace('"schema": 2', '"schema": 3'))
        code, text = self.run_sync("--apply")
        self.assertEqual(code, 1)
        self.assertIn("The records are not valid; nothing was compared.", text)
        self.assertEqual(self.fake.calls, [])

    def test_another_repository_is_left_alone(self):
        code, text = self.run_sync("--apply", env={"GITHUB_REPOSITORY": "someone/fork"})
        self.assertEqual(code, 0)
        self.assertIn("is not the repository these records belong to", text)
        self.assertEqual(self.fake.calls, [])

    def test_a_rate_limit_is_a_warning_and_no_failure(self):
        self.fake.remaining = 30
        code, text = self.run_sync("--apply", "--no-comments")
        self.assertEqual(code, 0)
        self.assertRegex(text, r"::warning::sync stopped because the rate limit is nearly used up: \d+ issues done, \d+ left")

    def test_an_error_of_the_api_fails_the_job_and_names_the_request(self):
        self.fake.fail = ("GET", "/labels", 500)
        code, text = self.run_sync("--apply")
        self.assertEqual(code, 1)
        self.assertIn("GET /labels?per_page=100&page=1: HTTP 500", text)


class StalenessTests(unittest.TestCase):
    TODAY = datetime.date(2026, 12, 31)

    def test_waiting_is_counted_from_the_newest_evidence(self):
        state = community.staleness(finding(), self.TODAY)
        self.assertEqual(state, {"status": "filed", "since": "2026-11-20", "days": 41, "threshold": 30, "stale": True})
        state = community.staleness(finding(**PATH[1]), self.TODAY)
        self.assertEqual((state["status"], state["since"], state["days"], state["stale"]),
                         ("confirmed", "2026-11-22", 39, True))
        state = community.staleness(finding(**PATH[2]), self.TODAY)
        self.assertEqual((state["status"], state["days"], state["threshold"], state["stale"]), ("sent", 36, 90, False))

    def test_a_finding_that_has_left_the_path_does_not_wait(self):
        self.assertIsNone(community.staleness(finding(**PATH[4]), self.TODAY))
        self.assertIsNone(community.staleness(finding(closed=WITHDRAWN), self.TODAY))
        undated = finding(reported={"by": None, "date": None, "url": f"{REPO}/issues/48"})
        self.assertIsNone(community.staleness(undated, self.TODAY))

    def test_thresholds_come_from_the_site_configuration(self):
        self.assertEqual(set(community.STALE_AFTER_DAYS), set(community.OPEN_STAGES))
        self.assertFalse(community.staleness(finding(), self.TODAY, {"filed": 60})["stale"])
        self.assertTrue(community.staleness(finding(**PATH[2]), self.TODAY, {"sent": 14})["stale"])
        self.assertEqual(community.load_config(ROOT)["stale_after_days"],
                         json.loads((ROOT / "site/config.json").read_text()).get("stale_after_days", {}))

    def test_a_confirmed_finding_is_listed_for_a_release_registered_after_the_answer(self):
        config = dict(CONFIG, releases=[
            {"id": "2026-v1", "name": "BAFU:2026 v1", "date": "2026-06-30"},
            {"id": "2027-v1", "name": "BAFU:2027 v1", "date": "2027-06-30"},
            {"id": "2028-v1", "name": "BAFU:2028 v1"},
        ])
        answered = finding(**PATH[3])
        self.assertEqual(community.check_in_release(answered, config), ["2027-v1"])
        self.assertEqual(community.check_in_release(answered, CONFIG), [], "a release without a date is not listed")
        explained = finding(**dict(PATH[3], answer=dict(ANSWER, outcome="explained")))
        for record in (explained, finding(**PATH[4]), finding(**PATH[2]), finding(**dict(PATH[3], closed=WITHDRAWN))):
            self.assertEqual(community.check_in_release(record, config), [])

    def test_the_report_lists_who_waits_longest_and_sends_no_reminder(self):
        findings = [finding(48), finding(49, **dict(PATH[1], reported={"by": "reporter", "date": "2026-09-01",
                                                                       "url": f"{REPO}/issues/49"},
                                                    repeated=dict(REPEATED, date="2026-09-10")))]
        issues = {48: issue(sync.expected_labels("filed", "BAFU")), 49: issue(sync.expected_labels("confirmed", "BAFU"))}
        differences = sync.plan(findings, issues, CONFIG)
        self.assertEqual(differences, [], "waiting is no difference: nothing is written for it")
        text = sync.report(differences, findings, issues, CONFIG, today=self.TODAY)
        self.assertIn("Waiting longer than the threshold of their status: 2.", text)
        self.assertLess(text.index("F49: Repeated, not yet reported since 2026-09-10 (112 days; threshold 30)"),
                        text.index("F48: Needs a second measurement since 2026-11-20 (41 days; threshold 30)"))


if __name__ == "__main__":
    unittest.main()
