import contextlib
import copy
import hashlib
import importlib.util
import io
import itertools
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import frozen  # noqa: E402

# The rules are tested on frozen records, so that the life of a real finding breaks no test.
# Only the tests named "committed" read the repository's own records.
DATA = frozen.RECORDS
spec = importlib.util.spec_from_file_location("community_records", ROOT / "scripts/community.py")
records = importlib.util.module_from_spec(spec)
spec.loader.exec_module(records)
REPO = "https://github.com/sentier-dev/sentier-bafu"
RELEASES = {"2025-v2", "2026-v1"}

# One piece of evidence of each kind, dated in the order of the path.
REPEATED = {"by": "second-person", "date": "2026-11-22", "url": f"{REPO}/issues/48#issuecomment-1", "result": "reproduced"}
SENT = {"batch": "2026-11", "date": "2026-11-25", "url": f"{REPO}/issues/48#issuecomment-2"}
ANSWER = {"date": "2026-12-01", "outcome": "confirmed", "summary": "BAFU said it will correct the amount.", "url": f"{REPO}/issues/48#issuecomment-3"}
FIXED = {"release": "2026-v1", "date": "2026-12-20", "url": f"{REPO}/issues/48#issuecomment-4"}
CLOSED = {"as": "withdrawn", "date": "2026-11-23", "reason": "It did not hold when measured again.", "url": f"{REPO}/issues/48"}


def finding(**changes):
    """A valid record of a finding filed under the current rules (F48 on: the id is the issue)."""
    record = {
        "schema": 2,
        "id": "F48",
        "issue": 48,
        "title": "Example dataset: the amount is a thousand times its siblings'",
        "kind": "defect",
        "datasets": [{"code": 123456, "name": "Example, at plant", "location": "CH"}],
        "scope": "",
        "releases": ["2026-v1"],
        "observation": "The dataset declares 1,000 kg where its siblings declare 1 kg.",
        "exposure": "",
        "method": "Measured on the release files.",
        "reported": {"by": "reporter", "date": "2026-11-20", "url": f"{REPO}/issues/48"},
        "repeated": None,
        "sent": None,
        "answer": None,
        "fixed_in": None,
        "closed": None,
        "related": [],
        "threads": [],
        "next": None,
        "retained": [],
        "notes": "",
    }
    record.update(copy.deepcopy(changes))
    return record


def errors(record, path=None):
    return records.validate_finding(record, path, RELEASES)


def tree(root):
    """Every file under a folder with its content hash: what a command changed, exactly."""
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(Path(root).rglob("*"))
        if p.is_file()
    }


class ContributionTests(unittest.TestCase):
    def setUp(self):
        self.record = records.read(ROOT / "community/templates/contribution.json")
        self.record.update(
            id="C001",
            title="Test",
            status="accepted",
            evidence=["https://example.org/source"],
            required_checks=["roundtrip"],
            required_reviewers=["partner"],
            approvals=[{"reviewer": "partner", "evidence_url": "https://example.org/approval"}],
        )
        self.record["class"] = "variant"
        self.record["baseline"] = dict(
            dataset="test",
            release="1",
            import_repository="https://example.org/repo",
            import_revision="abc",
            input_hashes={"source": "hash"},
        )
        self.record["layer"]["implementation_revision"] = "def"
        self.record["layer"].update(
            kind="synthetic", implementation_url="https://example.org/layer"
        )
        self.record["approvals"][0].update(
            baseline=copy.deepcopy(self.record["baseline"]), layer_revision="def"
        )
        self.record["runs"] = [
            dict(
                baseline=copy.deepcopy(self.record["baseline"]),
                layer_revision="def",
                evidence_url="https://example.org/run",
                checks=[
                    dict(
                        id="roundtrip",
                        status="passed",
                        evidence_url="https://example.org/check",
                    )
                ],
            )
        ]

    def test_accepted_requires_passing_checks_and_approvals(self):
        self.assertFalse(records.validate(self.record))
        self.record["runs"][0]["checks"][0]["status"] = "skipped"
        self.assertTrue(records.validate(self.record))

    def test_old_run_cannot_validate_new_layer(self):
        self.record["layer"]["implementation_revision"] = "changed"
        self.assertTrue(records.validate(self.record))

    def test_missing_partner_review_is_not_consensus(self):
        self.record["approvals"] = []
        self.assertTrue(records.validate(self.record))

    def test_unresolved_objection_blocks_acceptance(self):
        self.record["objections"] = [{"reason": "boundary"}]
        self.assertTrue(records.validate(self.record))

    def test_approval_for_old_layer_is_not_consensus(self):
        self.record["approvals"][0]["layer_revision"] = "old-layer"
        self.assertTrue(records.validate(self.record))

    def test_empty_implementation_cannot_be_accepted(self):
        self.record["layer"]["implementation_revision"] = ""
        self.record["runs"][0]["layer_revision"] = ""
        self.record["approvals"][0]["layer_revision"] = ""
        self.assertTrue(records.validate(self.record))

    def test_comparison_checks_scope_metrics_units_and_finiteness(self):
        baseline = records.read(ROOT / "community/templates/run-summary.json")
        with tempfile.TemporaryDirectory() as directory:
            before, after = (
                Path(directory) / "baseline.json",
                Path(directory) / "candidate.json",
            )
            before.write_text(json.dumps(baseline))
            candidate = copy.deepcopy(baseline)
            candidate["metrics"]["processes"]["value"] = 2
            after.write_text(json.dumps(candidate))
            self.assertEqual(records.compare(before, after)["metrics"]["processes"]["delta"], 1)
            for change in [
                lambda x: x["scope"].update(method="different"),
                lambda x: x["metrics"].pop("processes"),
                lambda x: x["metrics"]["processes"].update(unit="kg"),
                lambda x: x["metrics"]["processes"].update(value=float("nan")),
            ]:
                candidate = copy.deepcopy(baseline)
                change(candidate)
                after.write_text(json.dumps(candidate))
                with self.assertRaises(ValueError):
                    records.compare(before, after)

    def test_the_whole_record_is_valid_and_its_rules_one_by_one(self):
        self.assertEqual(records.validate_contribution(self.record, "community/contributions/C001.json"), [])
        cases = {
            "an id that is not C and digits": (lambda r: r.update(id="../../escaped"), "id does not have the required form"),
            "an id that carries markup": (lambda r: r.update(id='C900"><img src=x onerror=alert(1)>'), "id does not have the required form"),
            "a class outside the vocabulary": (lambda r: r.update({"class": "D"}), "class is"),
            "a missing class": (lambda r: r.pop("class"), "class is missing"),
            "an issue that is not a number": (lambda r: r.update(issue="12"), "issue must be integer or null"),
            "a field the schema does not know": (lambda r: r.update(priority="high"), "priority is not a field"),
            "a status outside the vocabulary": (lambda r: r.update(status="done"), "status is"),
            "raw HTML in the title": (lambda r: r.update(title="A <script>alert(1)</script>"), "title holds raw HTML"),
            "raw HTML in a nested text": (lambda r: r["layer"].update(kind="<b>bold</b>"), "layer.kind holds raw HTML"),
            "raw HTML in a check name": (lambda r: r["required_checks"].append("<i>x</i>"), "required_checks[1] holds raw HTML"),
            "a script address as evidence": (lambda r: r["evidence"].append("javascript:alert(1)"), "evidence[1] is not a plain https address"),
            "a script address in a run": (lambda r: r["runs"][0].update(evidence_url="javascript:alert(1)"), "runs[0].evidence_url is not a plain https address"),
            "an implementation that is not https": (lambda r: r["layer"].update(implementation_url="http://example.org"), "layer.implementation_url is not a plain https address"),
        }
        for name, (change, message) in cases.items():
            record = copy.deepcopy(self.record)
            change(record)
            found = records.validate_contribution(record, "community/contributions/C001.json")
            self.assertTrue(any(message in e for e in found), f"{name}: {found}")

    def test_a_contribution_file_is_named_after_its_id(self):
        found = records.validate_contribution(self.record, "community/contributions/C002.json")
        self.assertTrue(any("belongs in a file named C001.json" in e for e in found), found)

    def test_classes_separate_the_patched_release_from_what_stands_beside(self):
        groups = {c["key"]: c["group"] for c in records.CONTRIBUTION_CLASSES}
        self.assertEqual({k for k, g in groups.items() if g == "patched-release"}, {"import-fix", "linking-repair", "re-declaration"})
        self.assertEqual({k for k, g in groups.items() if g == "beside"}, {"variant", "model", "mapping"})
        self.assertEqual(set(groups.values()), set(records.CONTRIBUTION_GROUPS))
        for record in records.load_contributions(ROOT):
            self.assertIn(record["class"], groups, record["id"])
            self.assertIn("issue", record)


class SchemaTests(unittest.TestCase):
    """The published schema and the code agree, and the checker reads the schema itself."""

    def setUp(self):
        self.schema = records.load_schema("finding")

    def test_fields_of_the_schema_are_the_fields_of_the_code(self):
        self.assertEqual(tuple(self.schema["required"]), records.FINDING_FIELDS)
        self.assertEqual(set(self.schema["properties"]), set(records.FINDING_FIELDS))
        template = records.read(ROOT / "community/templates/finding.json")
        self.assertEqual(tuple(template), records.FINDING_FIELDS)

    def test_vocabularies_of_the_schema_are_those_of_the_code(self):
        p = self.schema["properties"]
        self.assertEqual(p["kind"]["enum"], list(records.KINDS))
        self.assertEqual(set(p["answer"]["properties"]["outcome"]["enum"]), set(records.OUTCOMES))
        self.assertEqual(tuple(p["closed"]["properties"]["as"]["enum"]), records.CLOSED_AS)
        self.assertEqual(tuple(p["repeated"]["properties"]["result"]["enum"]), records.REPEAT_RESULTS)
        self.assertEqual(set(p["next"]["properties"]["role"]["enum"]), records.ROLES)
        self.assertEqual(set(p["retained"]["items"]["properties"]["kind"]["enum"]), records.RETAINED_KINDS)
        self.assertEqual(set(self.schema["$defs"]["dataset"]["properties"]["role"]["enum"]), set(records.DATASET_ROLES))
        contribution = records.load_schema("contribution")["properties"]
        self.assertEqual(contribution["class"]["enum"], [c["key"] for c in records.CONTRIBUTION_CLASSES])
        self.assertEqual(set(contribution["status"]["enum"]), records.STATES)
        # The stages a record can be closed as are statuses, and every status has its words.
        keys = [s["key"] for s in records.STATUSES]
        self.assertEqual(keys, ["filed", "confirmed", "sent", "answered", "fixed", "not-a-defect", "withdrawn"])
        self.assertTrue(set(records.CLOSED_AS) <= set(keys))

    def test_the_checker_reads_the_schema_file(self):
        # Loosen the schema in memory: the same record now passes. The rules are not copied in code.
        record = finding(kind="rumour")
        self.assertTrue(records.schema_errors(record, self.schema))
        loose = copy.deepcopy(self.schema)
        loose["properties"]["kind"]["enum"].append("rumour")
        self.assertEqual(records.schema_errors(record, loose), [])

    def test_a_schema_keyword_the_checker_does_not_know_is_an_error_not_a_pass(self):
        with self.assertRaises(ValueError):
            records.schema_errors({}, {"type": "object", "maxProperties": 3})
        with self.assertRaises(ValueError):
            records.schema_errors({}, {"type": "object", "additionalProperties": {"type": "string"}})

    def test_true_is_not_a_number(self):
        self.assertTrue(records.schema_errors(True, {"const": 1}))
        self.assertTrue(records.schema_errors(True, {"type": "integer"}))
        self.assertTrue(errors(finding(schema=True)))
        self.assertTrue(errors(finding(issue=True)))

    def test_checker_agrees_with_a_full_json_schema_validator(self):
        try:
            import jsonschema
        except ModuleNotFoundError:
            self.skipTest("jsonschema is not installed")
        validator = jsonschema.Draft202012Validator(self.schema)
        cases = [finding()] + [dict(r) for r in records.load_findings(ROOT)]
        for name, (change, _) in SCHEMA_RULES.items():
            record = finding()
            change(record)
            cases.append(record)
        cases += [record for record, _ in CODE_RULES.values()]
        self.assertGreater(len(cases), 100)
        for record in cases:
            ours = bool(records.schema_errors(record, self.schema))
            theirs = bool(list(validator.iter_errors(record)))
            self.assertEqual(ours, theirs, json.dumps(record)[:300])


def drop(key):
    return lambda r: r.pop(key)


def put(path, value):
    """Set a nested value: put(("reported", "url"), "x")."""
    def change(record):
        target = record
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
    return change


# Rules the schema states. Each case: a change that breaks one rule, and the message it must cause.
SCHEMA_RULES = {
    "a field of the earlier format": (put(("status",), "open"), "status is not a field"),
    "a missing field": (drop("kind"), "kind is missing"),
    "another schema version": (put(("schema",), 1), "schema must be 2"),
    "an id with a leading zero": (put(("id",), "F048"), "id does not have the required form"),
    "an issue that is text": (put(("issue",), "48"), "issue must be integer or null"),
    "an issue below one": (put(("issue",), 0), "issue must be at least 1"),
    "an empty title": (put(("title",), "  "), "title does not have the required form"),
    "a title over two lines": (put(("title",), "one\ntwo"), "title does not have the required form"),
    "a title with a line separator": (put(("title",), "one two"), "title does not have the required form"),
    "a title with a table bar": (put(("title",), "two | cells"), "title does not have the required form"),
    "raw HTML in the title": (put(("title",), "x <script>y</script>"), "title holds raw HTML"),
    "a kind outside the vocabulary": (put(("kind",), "bug"), "kind is"),
    "datasets as text": (put(("datasets",), "123456 Example (CH)"), "datasets must be array"),
    "a dataset without a name": (put(("datasets",), [{"code": 1, "location": "CH"}]), "datasets[0].name is missing"),
    "a dataset code as text": (put(("datasets", 0, "code"), "123456"), "datasets[0].code must be integer"),
    "a dataset role outside the vocabulary": (put(("datasets", 0, "role"), "victim"), "datasets[0].role is"),
    "a dataset with an unknown key": (put(("datasets", 0, "unit"), "kg"), "datasets[0].unit is not a field"),
    "raw HTML in a dataset name": (put(("datasets", 0, "name"), "<img src=x onerror=y>"), "datasets[0].name holds raw HTML"),
    "a scope over two lines": (put(("scope",), "a\nb"), "scope does not have the required form"),
    "raw HTML in the scope": (put(("scope",), "<b>all</b>"), "scope holds raw HTML"),
    "a release that is free text": (put(("releases",), ["2026 v1 (June file)"]), "releases[0] does not have the required form"),
    "a release named twice": (put(("releases",), ["2026-v1", "2026-v1"]), "releases repeats an item"),
    "an empty observation": (put(("observation",), " "), "observation is empty"),
    "raw HTML in the observation": (put(("observation",), "see <script>x</script>"), "observation holds raw HTML"),
    "raw HTML in the exposure": (put(("exposure",), "<p>x</p>"), "exposure holds raw HTML"),
    "raw HTML in the method": (put(("method",), "<p>x</p>"), "method holds raw HTML"),
    "raw HTML in the notes": (put(("notes",), "<!-- x -->"), "notes holds raw HTML"),
    "a report without a link": (lambda r: r["reported"].pop("url"), "reported.url is missing"),
    "a report link that is not https": (put(("reported", "url"), "http://example.org/x"), "reported.url does not have the required form"),
    "a link with a bracket": (put(("reported", "url"), "https://example.org/a)b"), "reported.url does not have the required form"),
    "a script address as a link": (put(("reported", "url"), "javascript:alert(1)"), "reported.url does not have the required form"),
    "raw HTML in the reporter's name": (put(("reported", "by"), "<b>x</b>"), "reported.by holds raw HTML"),
    "a date that is not YYYY-MM-DD": (put(("reported", "date"), "20 November 2026"), "reported.date does not have the required form"),
    "a second measurement without a result": (put(("repeated",), {k: v for k, v in REPEATED.items() if k != "result"}), "repeated.result is missing"),
    "a result outside the vocabulary": (put(("repeated",), dict(REPEATED, result="confirmed")), "repeated.result is"),
    "a second measurement without a person": (put(("repeated",), dict(REPEATED, by=" ")), "repeated.by does not have the required form"),
    "a second measurement without a date": (put(("repeated",), dict(REPEATED, date=None)), "repeated.date must be string"),
    "a second-measurement date in another form": (put(("repeated",), dict(REPEATED, date="22.11.2026")), "repeated.date does not have the required form"),
    "a closing date in another form": (put(("closed",), dict(CLOSED, date="23 Nov 2026")), "closed.date does not have the required form"),
    "evidence that is a word": (put(("repeated",), "yes"), "repeated must be object or null"),
    "a batch id with a space": (put(("sent",), dict(SENT, batch="first batch")), "sent.batch does not have the required form"),
    "a batch without a date": (put(("sent",), {"batch": "2026-11", "url": SENT["url"]}), "sent.date is missing"),
    "an outcome outside the vocabulary": (put(("answer",), dict(ANSWER, outcome="fixed")), "answer.outcome is"),
    "an answer without a summary": (put(("answer",), dict(ANSWER, summary="")), "answer.summary is empty"),
    "raw HTML in the answer": (put(("answer",), dict(ANSWER, summary="<i>yes</i>")), "answer.summary holds raw HTML"),
    "an answer with a person's field": (put(("answer",), dict(ANSWER, by="Someone, BAFU")), "answer.by is not a field"),
    "a correction without evidence": (put(("fixed_in",), {"release": "2026-v1", "date": "2026-12-20"}), "fixed_in.url is missing"),
    "a correction in a release named freely": (put(("fixed_in",), dict(FIXED, release="BAFU:2027 v1")), "fixed_in.release does not have the required form"),
    "closed as something else": (put(("closed",), dict(CLOSED, **{"as": "informational"})), "closed.as is"),
    "closed without a reason": (put(("closed",), dict(CLOSED, reason=" ")), "closed.reason is empty"),
    "a related id that is not an id": (put(("related",), ["#4"]), "related[0] does not have the required form"),
    "a related id named twice": (put(("related",), ["F4", "F4"]), "related repeats an item"),
    "a thread that is not https": (put(("threads",), ["gitlab.com/x/-/issues/1"]), "threads[0] does not have the required form"),
    "a thread named twice": (put(("threads",), ["https://example.org/t", "https://example.org/t"]), "threads repeats an item"),
    "a next step for an unknown role": (put(("next",), {"action": "Ask", "role": "anyone"}), "next.role is"),
    "a next step without an action": (put(("next",), {"action": "", "role": "maintainer"}), "next.action is empty"),
    "a retained item of an unknown kind": (put(("retained",), [{"kind": "rumour", "text": "t", "evidence_url": "https://example.org"}]), "retained[0].kind is"),
    "a retained item without evidence": (put(("retained",), [{"kind": "ask", "text": "t"}]), "retained[0].evidence_url is missing"),
}

# Rules a schema cannot express. Same shape; `legacy` cases start from an id that predates the format.
CODE_RULES = {
    "an id that is not the issue number": (finding(issue=49), "the id is F followed by the issue number"),
    "a new finding without an issue": (finding(issue=None, threads=["https://example.org/t"]), "the id is F followed by the issue number"),
    "a finding without any discussion": (finding(id="F5", issue=None), "needs an issue here or a thread elsewhere"),
    "a dataset code named twice": (finding(datasets=[{"code": 1, "name": "A", "location": "CH"}, {"code": 1, "name": "A", "location": "CH"}]), "names a code twice"),
    "nothing it is about": (finding(datasets=[]), "name the datasets it is about"),
    "only named datasets and no scope": (finding(datasets=[{"code": 1, "name": "A", "location": "CH", "role": "named"}]), "name the datasets it is about"),
    "a release that is not registered": (finding(releases=["2031-v1"]), "release 2031-v1 is not in the list"),
    "a new finding without a release": (finding(releases=[]), "name the release it was observed in"),
    "a new finding without a reporter": (finding(reported={"by": None, "date": "2026-11-20", "url": f"{REPO}/issues/48"}), "reported needs who and when"),
    "a new finding without a report date": (finding(reported={"by": "reporter", "date": None, "url": f"{REPO}/issues/48"}), "reported needs who and when"),
    "closed without a date": (finding(closed=dict(CLOSED, date=None)), "closed needs a date"),
    "a date that is not in the calendar": (finding(repeated=dict(REPEATED, date="2026-02-30")), "repeated.date is not a calendar date"),
    "a second measurement before the report": (finding(repeated=dict(REPEATED, date="2026-11-01")), "repeated is dated before the finding was reported"),
    "an answer before it was sent": (finding(sent=SENT, answer=dict(ANSWER, date="2026-11-24")), "the answer is dated before"),
    "a second measurement by the reporter": (finding(repeated=dict(REPEATED, by="reporter")), "someone other than the reporter"),
    "the reporter under another spelling": (finding(repeated=dict(REPEATED, by="@Reporter ")), "someone other than the reporter"),
    "a second measurement when nobody reported": (finding(id="F5", reported={"by": None, "date": None, "url": f"{REPO}/issues/48"}, repeated=REPEATED), "needs a named reporter"),
    "a correction in an unregistered release": (finding(fixed_in=dict(FIXED, release="2031-v1")), "fixed_in.release 2031-v1 is not in the list"),
    "related to itself": (finding(related=["F48"]), "not related to itself"),
    "a relative link in the observation": (finding(observation="See [the run](../runs/x.json)."), "observation has a link that is not a full https address"),
    "an http link in the notes": (finding(notes="[x](http://example.org)"), "notes has a link that is not a full https address"),
    "a relative link in the answer": (finding(answer=dict(ANSWER, summary="BAFU said [this](page.html).")), "answer.summary has a link"),
    "an image in the observation": (finding(observation="![pixel](https://other.example/p.png)"), "observation embeds an image"),
    "an image in the method": (finding(method="x ![y](https://other.example/p.png)"), "method embeds an image"),
    "a heading in the observation": (finding(observation="# Second title\n\ntext"), "observation has a heading"),
    "a heading in the notes": (finding(notes="text\n\n## Part\n\nmore"), "notes has a heading"),
    "a link defined apart from its text": (finding(observation="See [this][1].\n\n[1]: javascript:alert(1)"), "observation defines a link apart from its text"),
    "a script address in a link": (finding(observation="[click](javascript:alert(1))"), "observation has a link that is not a full https address"),
}
# What the ids that predate the format may leave open, and nobody else:
# (the same gap on an old id, which is accepted; on a new id, which is not).
NOBODY = {"by": None, "date": None, "url": f"{REPO}/issues/48"}
LEGACY_ALLOWS = {
    "an issue number that is not the id": (dict(id="F12", issue=32), dict(id="F48", issue=32)),
    "no issue, with a thread elsewhere": (
        dict(id="F5", issue=None, threads=["https://example.org/t"]),
        dict(id="F48", issue=None, threads=["https://example.org/t"]),
    ),
    "no release": (dict(id="F4", issue=4, releases=[]), dict(releases=[])),
    "no reporter and no report date": (dict(id="F6", issue=6, reported=NOBODY), dict(reported=NOBODY)),
    "closed without a date": (dict(id="F7", issue=7, closed=dict(CLOSED, date=None)), dict(closed=dict(CLOSED, date=None))),
}


class FindingRuleTests(unittest.TestCase):
    def test_the_example_record_is_valid(self):
        self.assertEqual(errors(finding(), "community/findings/0/F48.json"), [])
        whole = finding(repeated=REPEATED, sent=SENT, answer=ANSWER, fixed_in=FIXED, related=["F4"],
                        threads=["https://example.org/t"], next={"action": "Check", "role": "maintainer"},
                        datasets=finding()["datasets"] + [{"code": 2, "name": "B", "location": "DE", "role": "affected"}])
        self.assertEqual(errors(whole), [])

    def test_schema_rules_one_by_one(self):
        for name, (change, message) in SCHEMA_RULES.items():
            record = finding()
            change(record)
            found = errors(record)
            self.assertTrue(any(message in e for e in found), f"{name}: expected {message!r} in {found}")

    def test_rules_beyond_the_schema_one_by_one(self):
        for name, (record, message) in CODE_RULES.items():
            found = errors(record)
            self.assertTrue(any(message in e for e in found), f"{name}: expected {message!r} in {found}")

    def test_only_the_ids_that_predate_the_format_may_leave_these_open(self):
        for name, (old, new) in LEGACY_ALLOWS.items():
            self.assertEqual(errors(finding(**old)), [], name)
            self.assertTrue(errors(finding(**new)), name)
        self.assertEqual(records.LAST_LEGACY_NUMBER, 47)
        self.assertTrue(records.is_legacy({"id": "F47"}))
        self.assertFalse(records.is_legacy({"id": "F48"}))

    def test_where_the_older_numbering_ends_is_configuration(self):
        """`older_numbering_until` in site/config.json; 47 when the file does not say."""
        old = finding(id="F12", issue=32)
        # As this repository is configured: F12 follows the older numbering, F48 its issue.
        self.assertEqual(records.validate_finding(old, None, RELEASES, 47), [])
        self.assertEqual(records.validate_finding(old, None, RELEASES), [], "the default is 47")
        self.assertIn("from F48 on, the id is F followed by the issue number",
                      records.validate_finding(finding(id="F48", issue=32), None, RELEASES, 47)[0])
        # A repository whose findings are numbered by their issues from the first one.
        self.assertIn("from F1 on, the id is F followed by the issue number (issue: 32)",
                      records.validate_finding(old, None, RELEASES, 0)[0])
        self.assertEqual(records.validate_finding(finding(id="F1", issue=1), None, RELEASES, 0), [])
        self.assertEqual(records.validate_finding(finding(id="F12", issue=12), None, RELEASES, 0), [])
        # With 0, nothing that the older ids may leave open is accepted.
        for name, (old, _) in LEGACY_ALLOWS.items():
            self.assertEqual(records.validate_finding(finding(**old), None, RELEASES, 47), [], name)
            self.assertTrue(records.validate_finding(finding(**old), None, RELEASES, 0), name)
        self.assertTrue(records.is_legacy({"id": "F47"}, 47))
        self.assertFalse(records.is_legacy({"id": "F1"}, 0))
        self.assertTrue(records.is_legacy({"id": "F5"}, 5))
        self.assertFalse(records.is_legacy({"id": "F6"}, 5))

    def test_identity_from_f48_on_the_id_is_the_issue_number(self):
        self.assertEqual(errors(finding(id="F48", issue=48)), [])
        self.assertEqual(errors(finding(id="F3120", issue=3120)), [])
        for issue in (47, 49, None):
            self.assertTrue(errors(finding(id="F48", issue=issue, threads=["https://example.org/t"])), issue)
        # Existing ids stay for ever, with their issue recorded beside them.
        committed = {r["id"]: r for r in records.load_findings(DATA)}
        self.assertEqual(committed["F27"]["issue"], 47)
        self.assertEqual(committed["F1"]["issue"], 6)
        for record in committed.values():
            if records.finding_number(record) > records.LAST_LEGACY_NUMBER:
                self.assertEqual(record["id"], f"F{record['issue']}")

    def test_the_file_path_follows_from_the_id(self):
        self.assertEqual(records.record_path({"id": "F31"}), "community/findings/0/F31.json")
        self.assertEqual(records.record_path("F999"), "community/findings/0/F999.json")
        self.assertEqual(records.record_path("F1000"), "community/findings/1/F1000.json")
        self.assertEqual(records.record_path("F3120"), "community/findings/3/F3120.json")
        for wrong in ("community/findings/F48.json", "community/findings/1/F48.json", "community/findings/0/F49.json"):
            found = errors(finding(), wrong)
            self.assertTrue(any("F48 belongs at community/findings/0/F48.json" in e for e in found), wrong)

    def test_errors_name_the_file_when_it_is_known(self):
        found = errors(finding(kind="bug"), "community/findings/0/F48.json")
        self.assertTrue(found[0].startswith("community/findings/0/F48.json: "), found)
        self.assertTrue(errors(finding(kind="bug"))[0].startswith("F48: "))

    def test_a_record_that_is_not_an_object_is_reported(self):
        self.assertTrue(errors(["F1"], "community/findings/0/F1.json"))


class CommittedRecordTests(unittest.TestCase):
    def setUp(self):
        self.findings = records.load_findings(ROOT)

    def test_committed_records_are_valid_where_they_lie(self):
        self.assertTrue(self.findings)
        for record in self.findings:
            self.assertEqual(records.validate_finding(record, record.path), [], record["id"])
            self.assertEqual(record.path, records.record_path(record))

    def test_no_record_holds_a_status_a_flag_or_a_copied_patch(self):
        gone = {"status", "awaiting_second_measurement", "community_patch", "provider_response",
                "provider_correction_shipped", "links", "release", "validation_scope"}
        for record in self.findings:
            self.assertFalse(gone & set(record), record["id"])

    def test_a_second_measurement_names_a_second_person_a_date_and_a_place(self):
        for record in self.findings:
            repeated = record["repeated"]
            if repeated:
                self.assertTrue(repeated["by"] and repeated["date"] and repeated["url"], record["id"])
                self.assertNotEqual(repeated["by"].lower(), record["reported"]["by"].lower(), record["id"])
            else:
                self.assertNotEqual(records.stage(record), "confirmed", record["id"])

    def test_an_answer_names_the_provider_and_no_person(self):
        for record in self.findings:
            if record["answer"]:
                self.assertEqual(set(record["answer"]), {"date", "outcome", "summary", "url"}, record["id"])
                self.assertTrue(record["answer"]["summary"].startswith("BAFU "), record["id"])

    def test_every_dataset_code_a_record_is_about_is_listed(self):
        index = records.dataset_index(records.load_findings(DATA), records.load_patches(DATA))
        # 316743 was named only in prose; a search for it missed F13.
        self.assertIn({"id": "F13", "role": "subject"}, index[316743]["findings"])
        self.assertEqual({f["id"]: f["role"] for f in index[196588]["findings"]}, {"F8": "named", "F10": "subject"})
        self.assertEqual({f["role"] for f in index[435703]["findings"]}, {"affected"})

    def test_no_generated_ledger_is_kept_in_the_repository(self):
        # Two pull requests that each add a finding would conflict on a committed table.
        self.assertFalse((ROOT / "community/findings.md").exists())
        self.assertTrue((ROOT / "community/findings/README.md").is_file())


class StageTests(unittest.TestCase):
    def test_stage_on_every_combination_of_evidence(self):
        options = {
            "repeated": [None, REPEATED, dict(REPEATED, result="not-reproduced")],
            "sent": [None, SENT],
            "answer": [None, ANSWER],
            "fixed_in": [None, FIXED],
            "closed": [None, CLOSED, dict(CLOSED, **{"as": "not-a-defect"})],
        }
        seen = set()
        for values in itertools.product(*options.values()):
            evidence = dict(zip(options, values))
            # The rule, written a second time and differently: the last step reached decides.
            if evidence["closed"]:
                expected = evidence["closed"]["as"]
            else:
                expected = "filed"
                if evidence["repeated"] and evidence["repeated"]["result"] == "reproduced":
                    expected = "confirmed"
                for name, key in (("sent", "sent"), ("answer", "answered"), ("fixed_in", "fixed")):
                    if evidence[name]:
                        expected = key
            self.assertEqual(records.stage(finding(**evidence)), expected, evidence)
            seen.add(expected)
        self.assertEqual(len(list(itertools.product(*options.values()))), 72)
        self.assertEqual(seen, {s["key"] for s in records.STATUSES})

    def test_a_second_measurement_that_did_not_reproduce_confirms_nothing(self):
        self.assertEqual(records.stage(finding(repeated=dict(REPEATED, result="not-reproduced"))), "filed")

    def test_an_answer_or_a_patch_never_corrects_a_finding(self):
        # Only a release that contains the correction does.
        self.assertEqual(records.stage(finding(answer=ANSWER)), "answered")
        self.assertEqual(records.stage(finding(answer=ANSWER, fixed_in=FIXED)), "fixed")

    def test_status_words_name_the_provider_and_never_a_placeholder(self):
        for status in records.statuses("BAFU"):
            self.assertNotIn("{", status["label"] + status["description"])
            self.assertNotIn("provider", (status["label"] + status["description"]).lower())
            self.assertEqual(status["description"].count(". "), 0, "one sentence")
        self.assertEqual(records.status_label("sent", "BAFU"), "Reported to BAFU")
        self.assertEqual(records.status_label("filed", "BAFU"), "Needs a second measurement")
        self.assertEqual(records.status_label("fixed", "ecoinvent"), "Resolved")
        self.assertEqual(records.status_label("answered", "ecoinvent"), "Answered by ecoinvent")

    def test_dates_come_from_the_evidence(self):
        record = finding(repeated=REPEATED, sent=SENT)
        self.assertEqual([name for _, name, _ in records.evidence(record)], ["reported", "repeated", "sent"])
        self.assertEqual(records.last_change(record), "2026-11-25")
        self.assertEqual(records.waiting_since(record), "2026-11-25")
        self.assertEqual(records.last_change(finding()), "2026-11-20")
        done = finding(closed=CLOSED)
        self.assertEqual(records.last_change(done), "2026-11-23")
        self.assertIsNone(records.waiting_since(done))
        self.assertIsNone(records.waiting_since(finding(sent=SENT, answer=ANSWER, fixed_in=FIXED)))
        undated = finding(id="F6", issue=6, reported={"by": None, "date": None, "url": f"{REPO}/issues/6"})
        self.assertIsNone(records.last_change(undated))

    def test_changes_list_every_dated_event_newest_first(self):
        one = finding(repeated=REPEATED)
        two = finding(id="F49", issue=49, closed=dict(CLOSED, date="2026-11-21"))
        events = records.changes([one, two])
        self.assertEqual(
            [(e["date"], e["id"], e["event"], e["stage"]) for e in events],
            [("2026-11-22", "F48", "repeated", "confirmed"), ("2026-11-21", "F49", "closed", "withdrawn"),
             ("2026-11-20", "F49", "reported", "filed"), ("2026-11-20", "F48", "reported", "filed")],
        )


class JoinTests(unittest.TestCase):
    def setUp(self):
        self.findings = records.load_findings(DATA)
        self.patches = records.load_patches(DATA)

    def test_patches_are_joined_to_findings_from_the_snapshot(self):
        joined = {rid: [p["id"] for p in found] for rid, found in records.patches_by_finding(self.patches).items()}
        self.assertEqual(joined, {"F1": ["0001"], "F3": ["0002"], "F11": ["0003"], "F8": ["0011"]})
        self.assertEqual([p["id"] for p in records.patches_without_finding(self.patches)],
                         ["0004", "0005", "0006", "0007", "0008", "0009", "0010"])
        self.assertEqual(records.patch_errors(self.patches), [])
        source = self.patches["source"]
        for patch in self.patches["patches"]:
            self.assertTrue(patch["url"].startswith(f'{source["repository"]}/blob/{source["ref"]}/{source["path"]}/p{patch["id"]}_'))
            self.assertTrue(patch["author"] and patch["authorised_by"])

    def test_a_patch_that_names_a_missing_finding_is_an_error_and_one_that_names_none_a_note(self):
        patches = copy.deepcopy(self.patches)
        found, notes = records.cross_record_errors(self.findings, patches)
        self.assertEqual(found, [])
        self.assertEqual(len(notes), 1)
        self.assertIn("7 of 11 patches name no finding: 0004", notes[0])
        patches["patches"][0]["findings"] = ["F1", "F9999"]
        found, _ = records.cross_record_errors(self.findings, patches)
        self.assertEqual(found, ["patch 0001 names F9999, which has no record"])

    def test_rules_of_the_patch_snapshot_one_by_one(self):
        cases = {
            "no ref": (lambda d: d["source"].pop("ref"), "source names the repository, the ref and the folder"),
            "a repository that is not https": (lambda d: d["source"].update(repository="javascript:alert(1)"), "source names the repository"),
            "a url that leads elsewhere": (lambda d: d["patches"][0].update(url="https://example.org/blob/main/p.py"), "leads to the patch's file in this repository"),
            "a url outside the folder of the patches": (lambda d: d["patches"][0].update(url=f"{REPO}/blob/main/p.py"), "leads to the patch's file in this repository"),
            "a url that climbs out of the folder": (lambda d: d["patches"][0].update(url=d["patches"][0]["url"].replace("/patches/", "/patches/../")), "leads to the patch's file in this repository"),
            "a patch listed twice": (lambda d: d["patches"].append(copy.deepcopy(d["patches"][0])), "listed twice"),
            "a patch without an author": (lambda d: d["patches"][0].pop("author"), "needs a four-digit id"),
            "an id that is the whole slug": (lambda d: d["patches"][0].update(id="0001-strawberry"), "needs a four-digit id"),
            "findings that are not ids": (lambda d: d["patches"][0].update(findings=["#6"]), "needs a four-digit id"),
            "no list": (lambda d: d.pop("patches"), "needs a list of patches"),
            "raw HTML in a description": (lambda d: d["patches"][0].update(description="Fix <script>x</script>"), "description holds raw HTML"),
            "raw HTML in an author": (lambda d: d["patches"][0].update(author="<b>A</b>"), "author holds raw HTML"),
            "an image in a description": (lambda d: d["patches"][0].update(description="![x](https://other.example/p.png)"), "description embeds an image"),
            "a source that is not https": (lambda d: d["patches"][0].update(url="javascript:alert(1)//" + d["patches"][0]["url"]), "leads to the patch's file in this repository"),
        }
        for name, (change, message) in cases.items():
            data = copy.deepcopy(self.patches)
            change(data)
            found = records.patch_errors(data)
            self.assertTrue(any(message in e for e in found), f"{name}: {found}")

    def test_rules_between_records_one_by_one(self):
        base = [finding(), finding(id="F49", issue=49)]
        self.assertEqual(records.cross_record_errors(base), ([], []))
        missing = [finding(related=["F9999"])]
        self.assertEqual(records.cross_record_errors(missing)[0], ["F48: related names F9999, which has no record"])
        batch = [finding(sent=SENT), finding(id="F49", issue=49, sent=dict(SENT, date="2026-11-26"))]
        self.assertEqual(records.cross_record_errors(batch)[0], ["batch 2026-11 has more than one date: 2026-11-25, 2026-11-26"])
        renamed = [finding(), finding(id="F49", issue=49, datasets=[{"code": 123456, "name": "Another name", "location": "CH"}])]
        self.assertEqual(records.cross_record_errors(renamed)[0], ["F49: dataset 123456 is named differently in F48"])

    def test_related_findings_are_shown_in_both_directions(self):
        one = finding(related=["F49"])
        two = finding(id="F49", issue=49)
        three = finding(id="F50", issue=50, related=["F49", "F9999"])
        self.assertEqual(records.related([one, two, three]), {"F48": ["F49"], "F49": ["F48", "F50"], "F50": ["F49"]})
        committed = records.related(self.findings)
        self.assertEqual(committed["F3"], ["F14", "F16"])
        self.assertEqual(committed["F31"], ["F4"])
        self.assertEqual(committed["F10"], ["F8"])
        self.assertEqual(committed["F11"], ["F16"])

    def test_dataset_index_knows_roles_and_patches(self):
        index = records.dataset_index(self.findings, self.patches)
        self.assertEqual(index[188725], {
            "name": "Strawberries, conventional, unheated plastic tunnel", "location": "ES",
            "findings": [{"id": "F1", "role": "subject"}], "patches": ["0001"],
        })
        # Patch 0011 answers F8, which only names 196588: the patch does not touch that dataset.
        self.assertEqual(index[196588]["patches"], [])
        self.assertEqual(list(index), sorted(index))

    def test_release_index_lists_what_was_observed_and_what_was_corrected(self):
        config = records.load_config(DATA)
        index = records.release_index(self.findings, config)
        self.assertEqual(set(index), {"2025-v2", "2026-v1"})
        self.assertEqual(index["2026-v1"]["name"], "BAFU:2026 v1")
        self.assertIn("F1", index["2025-v2"]["findings"])
        self.assertNotIn("F3", index["2025-v2"]["findings"])
        self.assertEqual(index["2026-v1"]["corrected"], ["F17"])

    def test_the_published_table_is_generated_from_the_records(self):
        config = records.load_config(DATA)
        rows = records.ledger_rows(records.index_text(self.findings, config))
        self.assertEqual(set(rows), {r["id"] for r in self.findings})
        for record in self.findings:
            row = rows[record["id"]]
            self.assertEqual(row["status"], records.status_label(records.stage(record), "BAFU"))
            self.assertEqual(row["links"], set(records.discussion_links(record, config["repository"])))

    def test_the_table_holds_thousands_of_records(self):
        many = [finding(id=f"F{n}", issue=n) for n in range(48, 5048)]
        self.assertEqual(len(records.ledger_rows(records.index_text(many, records.load_config(DATA)))), 5000)


class ContributionTriageTests(unittest.TestCase):
    def setUp(self):
        self.record = records.read(DATA / "community/contributions/C001.json")

    def test_committed_contributions_are_valid(self):
        for record in records.load_contributions(ROOT):
            self.assertEqual(records.validate_contribution(record, record.path), [], record["id"])

    def test_open_contribution_needs_next_action_and_role(self):
        self.record["next_action"] = ""
        self.assertTrue(records.validate_contribution_triage(self.record))

    def test_accepted_contribution_needs_no_next_action(self):
        self.record.update(status="accepted", next_action=None, review_role=None)
        self.assertEqual(records.validate_contribution_triage(self.record), [])


class WorkspaceCase(unittest.TestCase):
    """A copy of the frozen records in a scratch folder, to change one thing and look at the whole."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = frozen.workspace(Path(self.tmp.name) / "workspace")

    def tearDown(self):
        self.tmp.cleanup()

    def result(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = records.check(self.root)
        return code, out.getvalue()

    def path(self, rid):
        return self.root / records.record_path(rid)

    def change(self, rid, **changes):
        record = records.read(self.path(rid))
        record.update(changes)
        self.path(rid).write_text(json.dumps(record))

    def add(self, record):
        target = self.path(record["id"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(record))
        return target


class CheckTests(WorkspaceCase):
    """The whole check, on a copy of the records with one thing wrong."""

    def test_the_frozen_records_pass(self):
        code, text = self.result()
        self.assertEqual(code, 0, text)
        self.assertIn("Validated 23 findings, 2 contribution records, 11 community patches", text)
        self.assertIn("Note: 7 of 11 patches name no finding", text)

    def test_an_edited_record_needs_no_regenerated_file(self):
        self.change("F2", title="Refrigerant R134a: edited title")
        code, text = self.result()
        self.assertEqual(code, 0, text)

    def test_records_are_found_in_every_shard(self):
        self.add(finding(id="F1001", issue=1001))
        self.add(finding(id="F3120", issue=3120, datasets=[{"code": 7, "name": "Other", "location": "DE"}]))
        code, text = self.result()
        self.assertEqual(code, 0, text)
        self.assertIn("Validated 25 findings", text)
        loaded = {r["id"]: r.path for r in records.load_findings(self.root)}
        self.assertEqual(loaded["F1001"], "community/findings/1/F1001.json")
        self.assertEqual(loaded["F3120"], "community/findings/3/F3120.json")
        self.assertEqual([r["id"] for r in records.load_findings(self.root)][-2:], ["F1001", "F3120"])

    def test_a_record_in_the_wrong_folder_is_reported(self):
        shutil.move(self.path("F2"), self.root / "community/findings/F2.json")
        code, text = self.result()
        self.assertEqual(code, 1)
        self.assertIn("community/findings/F2.json: F2 belongs at community/findings/0/F2.json", text)

    def test_duplicate_and_misnamed_record_are_reported(self):
        shutil.copy(self.path("F2"), self.root / "community/findings/0/F9000.json")
        code, text = self.result()
        self.assertEqual(code, 1)
        self.assertIn("duplicate finding F2", text)
        self.assertIn("community/findings/0/F9000.json: F2 belongs at community/findings/0/F2.json", text)

    def test_broken_file_is_named_and_does_not_stop_the_check(self):
        (self.root / "community/findings/0/F9001.json").write_text("{not json")
        (self.root / "community/findings/0/F9002.json").write_text("[1, 2]")
        code, text = self.result()
        self.assertEqual(code, 1)
        self.assertIn("community/findings/0/F9001.json: unreadable record", text)
        self.assertIn("community/findings/0/F9002.json", text)

    def test_invalid_finding_is_reported_through_check_with_its_file(self):
        self.change("F2", kind="Open")
        self.assertIn('community/findings/0/F2.json: kind is "Open"', self.result()[1])

    def test_raw_html_in_a_record_is_reported_through_check(self):
        self.change("F2", observation="<script>alert(1)</script>")
        self.assertIn("community/findings/0/F2.json: observation holds raw HTML", self.result()[1])

    def test_an_unregistered_release_is_reported_through_check(self):
        config = records.read(self.root / "site/config.json")
        config["releases"] = [r for r in config["releases"] if r["id"] != "2025-v2"]
        (self.root / "site/config.json").write_text(json.dumps(config))
        self.assertIn("community/findings/0/F1.json: release 2025-v2 is not in the list", self.result()[1])

    def test_references_between_records_are_checked(self):
        self.change("F2", related=["F9999"])
        self.assertIn("F2: related names F9999, which has no record", self.result()[1])

    def test_a_patch_for_a_finding_without_a_record_fails_the_check(self):
        self.path("F8").unlink()
        self.change("F10", related=[])
        code, text = self.result()
        self.assertEqual(code, 1)
        self.assertIn("patch 0011 names F8, which has no record", text)

    def test_a_broken_patch_snapshot_fails_the_check(self):
        data = records.read(self.root / "community/patches.json")
        data["patches"][0]["url"] = "https://example.org/unpinned.py"
        (self.root / "community/patches.json").write_text(json.dumps(data))
        self.assertIn("patch 0001: the source url leads to the patch's file in this repository", self.result()[1])

    def test_a_patch_snapshot_that_cannot_be_read_is_named_not_raised(self):
        cases = {
            "{not json": "community/patches.json: unreadable (JSONDecodeError",
            "[1, 2]": "community/patches.json: needs a list of patches",
            '{"patches": [{"id": 5}]}': "patch 5: needs a four-digit id",
        }
        for broken, message in cases.items():
            (self.root / "community/patches.json").write_text(broken)
            code, text = self.result()
            self.assertEqual(code, 1, broken)
            self.assertIn(message, text)

    def test_contribution_without_next_action_is_reported_through_check(self):
        path = self.root / "community/contributions/C001.json"
        record = records.read(path)
        record["next_action"] = ""
        path.write_text(json.dumps(record))
        self.assertIn("community/contributions/C001.json: C001: open contribution needs a next action", self.result()[1])

    def test_a_contribution_with_a_bad_id_or_markup_is_reported_through_check(self):
        path = self.root / "community/contributions/C001.json"
        record = records.read(path)
        for change, message in (
            ({"id": "../../escaped"}, "id does not have the required form"),
            ({"id": "C002"}, "C002 belongs in a file named C002.json"),
            ({"title": "<script>alert(1)</script>"}, "title holds raw HTML"),
        ):
            path.write_text(json.dumps(dict(record, **change)))
            code, text = self.result()
            self.assertEqual(code, 1)
            self.assertIn(f"community/contributions/C001.json: {message}", text)


class CommandTests(WorkspaceCase):
    """The commands for people: each writes the named record and nothing else."""

    def run_command(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            try:
                code = records.main(["--root", str(self.root), *args])
            except SystemExit as stop:
                code = stop.code if isinstance(stop.code, int) else 1
                out.write(str(stop.code))
        return code, out.getvalue()

    def changed(self, before):
        after = tree(self.root)
        self.assertEqual(set(before), set(after), "no file was added or removed")
        return sorted(name for name in after if before[name] != after[name])

    def test_repeat_records_a_second_person_and_writes_one_file(self):
        before = tree(self.root)
        code, text = self.run_command("repeat", "F19", "--by", "second-person", "--date", "2026-11-14",
                                      "--url", f"{REPO}/issues/41#issuecomment-9", "--result", "reproduced")
        self.assertEqual(code, 0, text)
        self.assertEqual(self.changed(before), ["community/findings/0/F19.json"])
        record = records.read(self.path("F19"))
        self.assertEqual(record["repeated"], {"by": "second-person", "date": "2026-11-14",
                                              "url": f"{REPO}/issues/41#issuecomment-9", "result": "reproduced"})
        self.assertEqual(records.stage(record), "confirmed")
        self.assertEqual(tuple(record), records.FINDING_FIELDS)
        self.assertIn("Needs a second measurement -> Repeated, not yet reported", text)
        self.assertEqual(self.result()[0], 0)

    def test_repeat_refuses_the_reporter(self):
        before = tree(self.root)
        reporter = records.read(self.path("F19"))["reported"]["by"]
        for name in (reporter, reporter.upper(), f"@{reporter}"):
            code, text = self.run_command("repeat", "F19", "--by", name, "--date", "2026-11-14",
                                          "--url", f"{REPO}/issues/41#issuecomment-9", "--result", "reproduced")
            self.assertNotEqual(code, 0)
            self.assertIn("must come from someone else", text)
        self.assertEqual(self.changed(before), [])

    def test_a_result_that_was_not_reproduced_is_recorded_and_confirms_nothing(self):
        code, _ = self.run_command("repeat", "F19", "--by", "second-person", "--date", "2026-11-14",
                                   "--url", f"{REPO}/issues/41#issuecomment-9", "--result", "not-reproduced")
        self.assertEqual(code, 0)
        self.assertEqual(records.stage(records.read(self.path("F19"))), "filed")

    def test_send_records_a_batch_on_each_named_record_only(self):
        before = tree(self.root)
        code, text = self.run_command("send", "--batch", "2026-11", "--date", "2026-11-20",
                                      "--url", f"{REPO}/issues/28#issuecomment-9", "F13", "F15")
        self.assertEqual(code, 0, text)
        self.assertEqual(self.changed(before), ["community/findings/0/F13.json", "community/findings/0/F15.json"])
        for rid in ("F13", "F15"):
            record = records.read(self.path(rid))
            self.assertEqual(record["sent"], {"batch": "2026-11", "date": "2026-11-20", "url": f"{REPO}/issues/28#issuecomment-9"})
            self.assertEqual(records.stage(record), "sent")
        self.assertEqual(self.result()[0], 0)

    def test_send_writes_the_whole_batch_or_nothing(self):
        before = tree(self.root)
        for bad in (["F13", "F9999"], ["F13", "F13"], ["F13", "not-an-id"]):
            code, _ = self.run_command("send", "--batch", "2026-11", "--date", "2026-11-20",
                                       "--url", f"{REPO}/issues/28#issuecomment-9", *bad)
            self.assertNotEqual(code, 0, bad)
        # A date before one of the findings was reported: the valid one is not written either.
        code, text = self.run_command("send", "--batch", "2026-10", "--date", "2026-10-20",
                                      "--url", f"{REPO}/issues/28#issuecomment-9", "F13", "F19")
        self.assertNotEqual(code, 0)
        self.assertIn("sent is dated before the finding was reported", text)
        self.assertEqual(self.changed(before), [])

    def test_answer_records_the_outcome_in_our_words(self):
        before = tree(self.root)
        code, text = self.run_command("answer", "F2", "--outcome", "explained", "--date", "2026-11-18",
                                      "--summary", "BAFU said the factor comes from an older source.",
                                      "--url", f"{REPO}/issues/7#issuecomment-9")
        self.assertEqual(code, 0, text)
        self.assertEqual(self.changed(before), ["community/findings/0/F2.json"])
        record = records.read(self.path("F2"))
        self.assertEqual(record["answer"]["outcome"], "explained")
        self.assertEqual(records.stage(record), "answered")
        code, text = self.run_command("answer", "F9", "--outcome", "maybe", "--date", "2026-11-18",
                                      "--summary", "x", "--url", f"{REPO}/issues/9")
        self.assertNotEqual(code, 0)

    def test_evidence_already_recorded_is_kept_unless_replaced(self):
        before = tree(self.root)
        args = ["answer", "F1", "--outcome", "declined", "--date", "2026-11-18", "--summary", "BAFU said no.",
                "--url", f"{REPO}/issues/6#issuecomment-9"]
        code, text = self.run_command(*args)
        self.assertNotEqual(code, 0)
        self.assertIn("already recorded", text)
        self.assertEqual(self.changed(before), [])
        code, _ = self.run_command(*args, "--replace")
        self.assertEqual(code, 0)
        self.assertEqual(records.read(self.path("F1"))["answer"]["outcome"], "declined")

    def test_fixed_names_a_registered_release_and_ends_the_next_step(self):
        before = tree(self.root)
        code, text = self.run_command("fixed", "F1", "--release", "2027-v1", "--date", "2027-03-01",
                                      "--url", f"{REPO}/issues/6#issuecomment-9")
        self.assertNotEqual(code, 0)
        self.assertIn("fixed_in.release 2027-v1 is not in the list", text)
        self.assertEqual(self.changed(before), [])
        code, text = self.run_command("fixed", "F1", "--release", "2026-v1", "--detail", "corrected files of March",
                                      "--date", "2027-03-01", "--url", f"{REPO}/issues/6#issuecomment-9")
        self.assertEqual(code, 0, text)
        self.assertEqual(self.changed(before), ["community/findings/0/F1.json"])
        record = records.read(self.path("F1"))
        self.assertEqual(records.stage(record), "fixed")
        self.assertEqual(record["fixed_in"]["detail"], "corrected files of March")
        self.assertIsNone(record["next"])

    def test_close_gives_a_reason_and_points_to_the_issue(self):
        before = tree(self.root)
        code, text = self.run_command("close", "F9", "--as", "withdrawn", "--date", "2026-11-19",
                                      "--reason", "The report table was misread.")
        self.assertEqual(code, 0, text)
        self.assertEqual(self.changed(before), ["community/findings/0/F9.json"])
        record = records.read(self.path("F9"))
        self.assertEqual(record["closed"], {"as": "withdrawn", "date": "2026-11-19",
                                            "reason": "The report table was misread.", "url": f"{REPO}/issues/9"})
        self.assertEqual(records.stage(record), "withdrawn")
        self.assertIsNone(record["next"])
        code, _ = self.run_command("close", "F2", "--as", "informational", "--date", "2026-11-19", "--reason", "x")
        self.assertNotEqual(code, 0)

    def test_a_command_that_would_leave_an_invalid_record_writes_nothing(self):
        before = tree(self.root)
        for args in (
            ["repeat", "F19", "--by", "second-person", "--date", "2026-02-30", "--url", f"{REPO}/issues/41", "--result", "reproduced"],
            ["repeat", "F19", "--by", "second-person", "--date", "2026-11-14", "--url", "not a link", "--result", "reproduced"],
            ["answer", "F2", "--outcome", "confirmed", "--date", "2026-11-18", "--summary", "<b>BAFU</b> agreed", "--url", f"{REPO}/issues/7"],
            ["answer", "F2", "--outcome", "confirmed", "--date", "2026-01-01", "--summary", "BAFU agreed.", "--url", f"{REPO}/issues/7"],
            ["close", "F2", "--as", "withdrawn", "--date", "2026-11-19", "--reason", " "],
            ["repeat", "F9999", "--by", "x", "--date", "2026-11-14", "--url", f"{REPO}/issues/1", "--result", "reproduced"],
        ):
            code, text = self.run_command(*args)
            self.assertNotEqual(code, 0, args)
        self.assertEqual(self.changed(before), [])

    def test_commands_find_records_in_any_shard_and_can_set_the_next_step(self):
        self.add(finding(id="F3120", issue=3120))
        before = tree(self.root)
        code, text = self.run_command("repeat", "F3120", "--by", "second-person", "--date", "2026-11-22",
                                      "--url", f"{REPO}/issues/3120#issuecomment-1", "--result", "reproduced",
                                      "--next", "Report it to BAFU.", "--role", "maintainer")
        self.assertEqual(code, 0, text)
        self.assertEqual(self.changed(before), ["community/findings/3/F3120.json"])
        self.assertEqual(records.read(self.path("F3120"))["next"], {"action": "Report it to BAFU.", "role": "maintainer"})

    def test_index_command_writes_the_table_where_it_is_told(self):
        out = self.root / "build/ledger.md"
        done = subprocess.run(
            [sys.executable, str(ROOT / "scripts/community.py"), "index", "--out", str(out)],
            capture_output=True, text=True,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(set(records.ledger_rows(out.read_text())), {r["id"] for r in records.load_findings(ROOT)})
        missing = subprocess.run(
            [sys.executable, str(ROOT / "scripts/community.py"), "index"], capture_output=True, text=True
        )
        self.assertNotEqual(missing.returncode, 0)

    def test_the_command_line_runs_as_a_program(self):
        done = subprocess.run(
            [sys.executable, str(ROOT / "scripts/community.py"), "--root", str(self.root), "repeat", "F21",
             "--by", "second-person", "--date", "2026-11-14", "--url", f"{REPO}/issues/42#issuecomment-9",
             "--result", "reproduced"],
            capture_output=True, text=True,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(records.stage(records.read(self.path("F21"))), "confirmed")
        refused = subprocess.run(
            [sys.executable, str(ROOT / "scripts/community.py"), "--root", str(self.root), "repeat", "F29",
             "--by", records.read(self.path("F29"))["reported"]["by"], "--date", "2026-11-14",
             "--url", f"{REPO}/issues/43#issuecomment-9", "--result", "reproduced"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("must come from someone else", refused.stderr)


MODULE = """from bafu_community_fixes.registry import patch

ID = "{id}"
ISSUE = "https://github.com/sentier-dev/sentier-bafu/issues/48"


@patch(
    ID,
    findings={findings},
    authored_by="A. Author",
    authorised_by={authorised},
    reported_by="A Reporter, Some Company",
    confirmed_by="Someone, BAFU (email)",
    references=(ISSUE, "https://example.org/elsewhere"),
)
def example(db):
    \"\"\"{description}

    The longer reason, which is not the description.
    \"\"\"
"""


class PatchRegistryTests(WorkspaceCase):
    """community/patches.json is written from the patch registry and compared with it.

    The registry here is made up: a folder of patch modules as the patch tool has them, read
    from their source, because the tool itself is not installed where the records are checked.
    """

    @classmethod
    def setUpClass(cls):
        cls.snapshot = records.registry_module()

    def module(self, key, findings=(), authorised='"An Authoriser"', description="Correct the example amount."):
        folder = self.root / self.snapshot.PATCH_FOLDER
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"p{key.replace('-', '_')}.py"
        path.write_text(MODULE.format(id=key, findings=repr(tuple(findings)), authorised=authorised, description=description))
        return path

    def write(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = self.snapshot.main(["--root", str(self.root), *args])
        return code, out.getvalue()

    def registry(self):
        """Two patches: one answers F1, one answers nothing and is not yet authorised."""
        self.module("0001-example-patch", ["F1"])
        self.module("0002-other-patch", authorised="None", description="Add a missing number.")
        (self.root / "src/bafu_community_fixes/patches/__init__.py").write_text("")
        code, text = self.write()
        self.assertEqual(code, 0, text)
        return records.read(self.root / "community/patches.json")

    def test_a_patch_module_is_read_from_its_decorator(self):
        source = MODULE.format(id="0042-example-patch", findings='("F48",)', authorised="None",
                               description="Correct the example amount.")
        ((key, arguments, description),) = self.snapshot.registered(source, "p0042_example_patch.py")
        self.assertEqual(key, "0042-example-patch")
        self.assertEqual(description, "Correct the example amount.")
        self.assertEqual(arguments, {
            "findings": ("F48",),
            "authored_by": "A. Author",
            "authorised_by": None,
            "references": ("https://github.com/sentier-dev/sentier-bafu/issues/48", "https://example.org/elsewhere"),
        })

    def test_the_file_is_written_from_the_registry_and_names_author_and_authoriser_only(self):
        data = self.registry()
        self.assertEqual(data["schema"], "sentier-bafu/patches/2")
        self.assertEqual(data["source"], {"repository": REPO, "ref": "main", "path": "src/bafu_community_fixes/patches"})
        first, second = data["patches"]
        self.assertEqual(first, {
            "id": "0001", "slug": "example-patch", "description": "Correct the example amount.", "findings": ["F1"],
            "author": "A. Author", "authorised_by": "An Authoriser",
            "url": f"{REPO}/blob/main/src/bafu_community_fixes/patches/p0001_example_patch.py",
        })
        self.assertEqual((second["findings"], second["authorised_by"]), ([], None))
        text = json.dumps(data)
        for words in ("A Reporter", "Someone, BAFU", "(email)", "example.org/elsewhere", str(self.root)):
            self.assertNotIn(words, text)
        self.assertEqual(records.patch_errors(data), [])

    def test_the_ref_of_the_addresses_comes_from_the_site_configuration(self):
        config = records.read(self.root / "site/config.json")
        (self.root / "site/config.json").write_text(json.dumps(dict(config, source_ref="trunk")))
        data = self.registry()
        self.assertEqual(data["source"]["ref"], "trunk")
        self.assertIn("/blob/trunk/src/", data["patches"][0]["url"])
        self.assertEqual(self.result()[0], 0)

    def test_the_check_passes_while_the_file_is_what_the_registry_gives_and_says_how_it_was_read(self):
        self.registry()
        code, text = self.result()
        self.assertEqual(code, 0, text)
        self.assertIn("2 community patches", text)
        self.assertIn("Note: community/patches.json is what the patch registry gives (read from the source of the patch modules)", text)
        self.assertEqual(self.write("--check")[0], 0)

    def test_a_tree_without_the_patch_tool_has_nothing_to_compare(self):
        code, text = self.result()
        self.assertEqual(code, 0, text)
        self.assertNotIn("registry", text)
        self.assertEqual(self.write(), (1, "src/bafu_community_fixes/patches is not in this tree: there is no registry to read\n"))

    def test_what_makes_the_file_differ_from_the_registry_fails_the_check(self):
        self.registry()
        original = (self.root / "community/patches.json").read_text()

        def edited(change):
            data = json.loads(original)
            change(data)
            (self.root / "community/patches.json").write_text(json.dumps(data, indent=2) + "\n")

        cases = {
            "a finding added by hand": (lambda: edited(lambda d: d["patches"][1].update(findings=["F3"])), "patch 0002 differs in findings"),
            "another authoriser": (lambda: edited(lambda d: d["patches"][0].update(authorised_by="Someone Else")), "patch 0001 differs in authorised_by"),
            "a field the script does not write": (lambda: edited(lambda d: d["patches"][0].update(confirmed_by="A Person")), "patch 0001 differs in confirmed_by"),
            "a patch removed by hand": (lambda: edited(lambda d: d["patches"].pop()), "patch 0002 is in the registry and not in the file"),
            "a hand-kept block": (lambda: edited(lambda d: d.update(declared_findings={})), "its header (schema, note or source) is not the one the script writes"),
            "a new patch without a new file": (lambda: self.module("0003-new-patch", ["F3"]), "patch 0003 is in the registry and not in the file"),
            "a patch that now answers a finding": (lambda: self.module("0002-other-patch", ["F3"], "None", "Add a missing number."), "patch 0002 differs in findings"),
            "a patch that was authorised": (lambda: self.module("0002-other-patch", description="Add a missing number."), "patch 0002 differs in authorised_by"),
            "a patch that was removed": (lambda: (self.root / "src/bafu_community_fixes/patches/p0002_other_patch.py").unlink(), "patch 0002 is in the file and not in the registry"),
            "no file": (lambda: (self.root / "community/patches.json").unlink(), "community/patches.json is missing, and src/bafu_community_fixes/patches holds patches"),
        }
        for name, (change, message) in cases.items():
            with self.subTest(name):
                change()
                code, text = self.result()
                self.assertEqual(code, 1, name)
                self.assertIn(message, text)
                self.assertIn("run `python3 scripts/patches_snapshot.py`", text)
                if name != "no file":
                    self.assertEqual(self.write("--check")[0], 1)
                # The script puts it right, and nothing else is needed.
                self.assertEqual(self.write()[0], 0)
                self.assertEqual(self.result()[0], 0, name)
                # Back to the two patches of the registry.
                self.module("0001-example-patch", ["F1"])
                self.module("0002-other-patch", authorised="None", description="Add a missing number.")
                third = self.root / "src/bafu_community_fixes/patches/p0003_new_patch.py"
                third.unlink(missing_ok=True)
                (self.root / "community/patches.json").write_text(original)

    def test_a_patch_that_names_a_finding_without_a_record_fails_the_check(self):
        self.module("0001-example-patch", ["F9999"])
        self.assertEqual(self.write()[0], 0)
        code, text = self.result()
        self.assertEqual(code, 1)
        self.assertIn("patch 0001 names F9999, which has no record", text)

    def test_a_patch_that_names_no_finding_is_allowed_and_reported(self):
        self.registry()
        self.assertIn("Note: 1 of 2 patches name no finding: 0002", self.result()[1])

    def test_a_module_that_cannot_be_read_from_its_source_is_named_and_left_to_the_tool(self):
        self.registry()
        path = self.root / "src/bafu_community_fixes/patches/p0002_other_patch.py"
        path.write_text(path.read_text().replace("findings=(),", "findings=tuple(FOUND),"))
        code, text = self.result()
        self.assertEqual(code, 0, text)
        self.assertIn("Note: community/patches.json was not compared with the patch registry: "
                      "src/bafu_community_fixes/patches/p0002_other_patch.py cannot be read without the patch tool", text)
        self.assertIn("uv run python scripts/community.py check", text)
        code, text = self.write()
        self.assertEqual(code, 1)
        self.assertIn("cannot be read without the patch tool", text)

    def test_the_listing_of_the_patch_tool_gives_the_same_file(self):
        from_source = self.registry()
        listing = [
            {"id": "location-codes", "kind": "import fix", "description": "x", "authored_by": "A", "authorised_by": "A",
             "references": [], "reported_by": None, "confirmed_by": None, "findings": [], "source": "src/x.py"},
            {"id": "0002-other-patch", "kind": "patch", "description": "Add a missing number.", "authored_by": "A. Author",
             "authorised_by": None, "references": [], "reported_by": "A Reporter", "confirmed_by": "Someone, BAFU (email)",
             "findings": [], "source": "src/bafu_community_fixes/patches/p0002_other_patch.py"},
            {"id": "0001-example-patch", "kind": "patch", "description": "Correct the example amount.",
             "authored_by": "A. Author", "authorised_by": "An Authoriser", "references": ["https://example.org/elsewhere"],
             "reported_by": "A Reporter", "confirmed_by": None, "findings": ["F1"],
             "source": "src/bafu_community_fixes/patches/p0001_example_patch.py"},
        ]
        given = self.root / "listing.json"
        given.write_text(json.dumps(listing))
        self.assertEqual(self.write("--listing", str(given), "--check")[0], 0)
        wanted, how = self.snapshot.expected(self.root, json.dumps(listing))
        self.assertEqual((wanted, how), (from_source, "the listing given"))
        given.write_text("not a listing")
        self.assertEqual(self.write("--listing", str(given)), (1, "not the output of `bafu-fixes list --json` (JSONDecodeError)\n"))

    def test_a_patch_tool_installed_from_another_checkout_is_not_asked(self):
        """An installed tool says what its own checkout registers, not what this tree does."""
        import types
        elsewhere = types.ModuleType("bafu_community_fixes")
        elsewhere.__file__ = str(Path(self.tmp.name) / "another/src/bafu_community_fixes/__init__.py")
        cli = types.ModuleType("bafu_community_fixes.cli")
        cli.main = lambda argv: self.fail("the tool of another checkout was asked")
        elsewhere.cli = cli
        with unittest.mock.patch.dict(sys.modules, {"bafu_community_fixes": elsewhere, "bafu_community_fixes.cli": cli}):
            self.assertIsNone(self.snapshot.from_package(self.root))
            self.registry()
            self.assertEqual(self.snapshot.listing(self.root)[1], "the source of the patch modules")


LAYER = {
    "schema": "sentier-bafu/contribution-layer/1", "contribution": "C001", "name": "other-supplier",
    "database": "bafu-2026-v1-c001-other-supplier", "title": "A made-up change of one supplier",
    "authored_by": "A. Author", "authorised_by": None,
    "changes": [{
        "kind": "supplier-substitution",
        "dataset": {"code": "a", "name": "Made-up crop", "location": "CH"},
        "replaced_supplier": {"code": "b", "name": "Made-up mix", "location": "CH"},
        "new_supplier": {"code": "c", "name": "Made-up plant", "location": "CH"},
    }],
}


class OlderNumberingTests(unittest.TestCase):
    """The whole check under both values of `older_numbering_until`."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def workspace(self, until, name):
        root = frozen.workspace(Path(self.tmp.name) / name)
        config = records.read(root / "site/config.json")
        if until is not None:
            config["older_numbering_until"] = until
        (root / "site/config.json").write_text(json.dumps(config))
        return root

    def result(self, root):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = records.check(root)
        return code, out.getvalue()

    def test_the_frozen_records_pass_with_47_and_without_the_key(self):
        for until in (47, None):
            root = self.workspace(until, f"with-{until}")
            self.assertEqual(records.load_config(root)["older_numbering_until"], 47)
            self.assertEqual(self.result(root)[0], 0, until)

    def test_a_repository_that_starts_at_issue_1_sets_0(self):
        root = self.workspace(0, "sibling")
        # The records of this repository do not fit: F1 is issue 6 here.
        code, text = self.result(root)
        self.assertEqual(code, 1)
        self.assertIn("community/findings/0/F1.json: from F1 on, the id is F followed by the issue number (issue: 6)", text)
        # Records numbered by their issues from the first one do.
        shutil.rmtree(root / "community/findings")
        (root / "community/patches.json").unlink()
        for number in (1, 2, 31):
            record = finding(id=f"F{number}", issue=number, datasets=[{"code": 100000 + number, "name": "Example", "location": "CH"}])
            path = root / records.record_path(record)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record))
        code, text = self.result(root)
        self.assertEqual(code, 0, text)
        self.assertIn("Validated 3 findings", text)

    def test_a_value_that_is_no_number_is_named(self):
        for wrong in (-1, "47", 4.5, True, None):
            root = self.workspace(47, f"wrong-{wrong}")
            config = records.read(root / "site/config.json")
            config["older_numbering_until"] = wrong
            (root / "site/config.json").write_text(json.dumps(config))
            with self.assertRaisesRegex(ValueError, "older_numbering_until is a whole number, 0 or more"):
                records.load_config(root)

    def test_committed_configuration_says_where_the_older_numbering_ends(self):
        self.assertEqual(records.read(ROOT / "site/config.json")["older_numbering_until"], 47)


class LayerTests(WorkspaceCase):
    """A contribution that changes the inventory names its layer file in community/layers."""

    FILE = "community/layers/C001-other-supplier.json"

    def name_it(self, file=FILE, rid="C001"):
        path = self.root / f"community/contributions/{rid}.json"
        record = records.read(path)
        record["layer"]["file"] = file
        path.write_text(json.dumps(record))

    def layer(self, name="C001-other-supplier.json", **changes):
        folder = self.root / "community/layers"
        folder.mkdir(exist_ok=True)
        (folder / name).write_text(json.dumps(dict(LAYER, **changes)))

    def test_a_record_that_names_a_layer_that_is_there_and_parses_passes(self):
        self.layer()
        self.name_it()
        code, text = self.result()
        self.assertEqual(code, 0, text)

    def test_a_folder_with_its_readme_and_no_layer_is_fine(self):
        (self.root / "community/layers").mkdir()
        (self.root / "community/layers/README.md").write_text("# Contribution layers\n")
        self.assertEqual(self.result()[0], 0)

    def test_what_is_wrong_with_a_layer_or_its_record_fails_the_check(self):
        def unreadable():
            (self.root / self.FILE).write_text("{not json")

        cases = {
            "the file is not there": (lambda: self.name_it(), "C001: layer.file names community/layers/C001-other-supplier.json, which is not there"),
            "the file is not JSON": (lambda: (self.layer(), self.name_it(), unreadable()), "C001: community/layers/C001-other-supplier.json: "),
            "the file breaks a rule of the build": (lambda: (self.layer(database="bafu-2026-v1-patched"), self.name_it()),
                                                    "is the name of BAFU's release or of the patched release"),
            "the file has no change": (lambda: (self.layer(changes=[]), self.name_it()), "`changes` must list at least one change"),
            "the file is another contribution's": (lambda: (self.layer(contribution="C002", database="bafu-2026-v1-c002-x"), self.name_it()),
                                                   "is the layer of C002, not of C001"),
            "no record names the file": (lambda: self.layer(), "community/layers/C001-other-supplier.json: no contribution record names this file"),
            "two records name one file": (lambda: (self.layer(), self.name_it(), self.name_it(rid="C002")), "layer.file must be community/layers/C002-<name>.json"),
            "a file outside the folder": (lambda: self.name_it("community/contributions/C001.json"), "layer.file does not have the required form"),
            "a path that climbs out": (lambda: self.name_it("community/layers/../C001-x.json"), "layer.file does not have the required form"),
        }
        for name, (change, message) in cases.items():
            with self.subTest(name):
                self.tearDown()
                self.setUp()
                change()
                code, text = self.result()
                self.assertEqual(code, 1, name)
                self.assertIn(message, text, name)

    def test_the_rules_of_a_layer_are_the_builds_own(self):
        """One definition: the check reads a layer with the module the build reads it with."""
        module = records.layer_module()
        self.assertEqual(Path(module.__file__).resolve(), ROOT / "scripts/release_build/layer.py")
        self.assertEqual(module.validate(dict(LAYER))["contribution"], "C001")

    def test_committed_records_name_only_layers_that_are_there(self):
        self.assertEqual(records.layer_errors(ROOT, records.load_contributions(ROOT)), [])
        self.assertTrue((ROOT / "community/layers/README.md").is_file())


class CommittedPatchesTests(unittest.TestCase):
    def test_the_committed_file_names_no_one_but_author_and_authoriser(self):
        patches = records.load_patches(ROOT)
        for patch in patches["patches"]:
            self.assertEqual(set(patch), {"id", "slug", "description", "findings", "author", "authorised_by", "url"})
        self.assertEqual(set(patches), {"schema", "note", "source", "patches"})
        self.assertIn("Do not edit this file", patches["note"])

    def test_the_committed_file_is_what_the_registry_of_this_repository_gives(self):
        snapshot = records.registry_module()
        wanted, how = snapshot.expected(ROOT)
        self.assertIsNotNone(wanted, "the patch tool is in this repository")
        self.assertEqual(snapshot.differences(records.load_patches(ROOT), wanted), [], how)


if __name__ == "__main__":
    unittest.main()
