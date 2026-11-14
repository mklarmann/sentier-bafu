"""The intake: an issue form becomes a record, a /repeated comment becomes a second measurement.

No test reaches the network. The issue bodies under fixtures/github/ are the public issues
#47, #35 (filed with the earlier form) and #32 (not filed with a form), saved once.
"""

import contextlib
import copy
import io
import json
import re
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
import intake  # noqa: E402
from fake_github import BOT, REPOSITORY, FakeGitHub  # noqa: E402
from github_api import ApiError, GitHub  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures/github"
REPO = "https://github.com/sentier-dev/sentier-bafu"
# The rules are tested on frozen records and a frozen release list (fixtures/frozen), so that
# the life of a real finding breaks no test. Only the form file is compared with the
# repository's own site/config.json.
CONFIG = community.load_config(frozen.RECORDS)
LIVE = community.load_config(ROOT)
FORM_TEXT = (ROOT / intake.FORM_FILE).read_text()
PERSON = {"login": "second-person", "type": "User"}
# What a hostile reporter might try. None of it may leave the record's own text.
HOSTILE = '$(touch /tmp/pwned) `id` ; rm -rf / && echo "x" || true > out ::set-output name=x::y @everyone'


def saved(number):
    return json.loads((FIXTURES / f"issue-{number}.json").read_text())


def form_body(**changes):
    """An issue body as GitHub writes it for the finding form."""
    values = {
        "kind": "Defect: something in the data looks wrong (an amount, a unit, a link, a label)",
        "releases": "2026-v1",
        "datasets": "```text\n123456 | Example, at plant | CH\n```",
        "scope": "_No response_",
        "observation": "The dataset declares 1,000 kg where its siblings declare 1 kg.",
        "method": "Read the ecoSpold XML of 2026 v1 and compared the amounts of the five siblings.",
        "exposure": "_No response_",
        "notes": "_No response_",
    }
    values.update(changes)
    return "".join(
        f"### {heading}\n\n{values[field]}\n\n" for field, heading, _ in intake.FORM if values[field] is not None
    ).rstrip("\n")


def issue(number=48, body=None, title="[Finding] Example dataset: the amount is a thousand times its siblings'",
          login="reporter", labels=("bafu-finding", "needs-triage"), **changes):
    return {
        "number": number,
        "title": title,
        "body": form_body(**changes) if body is None else body,
        "state": "open",
        "created_at": "2026-11-20T09:30:00Z",
        "user": {"login": login, "type": "User"},
        "author_association": "NONE",
        "labels": [{"name": name} for name in labels],
    }


def opened(item, action="opened"):
    return {"action": action, "issue": item, "repository": {"default_branch": "main"}}


def commented(item, text, user=PERSON, association="NONE", cid=7001, action="created"):
    return {
        "action": action,
        "issue": item,
        "comment": {"id": cid, "body": text, "user": user, "author_association": association,
                    "created_at": "2026-11-22T10:00:00Z"},
        "repository": {"default_branch": "main"},
    }


def made(item, known=None):
    return intake.record_from_issue(item, CONFIG, known)


def form_fields(text):
    """(id, label, required) of every field of an issue form file, read line by line."""
    fields, current = [], None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- type:"):
            current = {"type": stripped.split(":", 1)[1].strip(), "required": False}
            fields.append(current)
        elif current is not None:
            for key in ("id", "label"):
                if stripped.startswith(f"{key}:"):
                    current[key] = stripped.split(":", 1)[1].strip().strip('"')
            if stripped == "required: true":
                current["required"] = True
    return [(f["id"], f["label"], f["required"]) for f in fields if f["type"] != "markdown"]


# A token, a home folder or a private key. The folder name is joined from two parts so that this
# file does not contain the string it searches for.
PRIVATE = r"gh[pousr]_[A-Za-z0-9]{20,}|/" + "Users/|BEGIN [A-Z ]*PRIVATE KEY"

class FormFileTests(unittest.TestCase):
    def test_the_form_and_the_script_name_the_same_fields(self):
        self.assertEqual(tuple(form_fields(FORM_TEXT)), intake.FORM)

    def test_every_field_a_record_takes_from_the_form_has_a_field(self):
        ids = {field for field, _, _ in intake.FORM}
        self.assertEqual(ids, {"kind", "releases", "datasets", "scope", "observation", "method", "exposure", "notes"})
        # Title, reporter and date come from the issue itself; everything else is evidence.
        self.assertTrue(ids | {"title"} >= set(intake.FORM_FIELDS))

    def test_no_heading_belongs_to_both_forms(self):
        headings = [heading for form in intake.FORMS.values() for _, heading, _ in form]
        self.assertEqual(len(headings), len(set(headings)))

    def test_the_release_list_is_the_list_of_site_config(self):
        self.assertEqual(intake.form_with_releases(FORM_TEXT, LIVE), FORM_TEXT)
        block = FORM_TEXT.split("# releases:start", 1)[1].split("# releases:end", 1)[0]
        listed = re.findall(r'- "([^"]+)"', block)
        self.assertEqual(listed, [release["id"] for release in reversed(LIVE["releases"])])

    def test_a_new_release_reaches_the_form_with_one_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".github/ISSUE_TEMPLATE").mkdir(parents=True)
            (root / "site").mkdir()
            shutil.copy(ROOT / intake.FORM_FILE, root / intake.FORM_FILE)
            config = json.loads((ROOT / "site/config.json").read_text())
            config["releases"].append({"id": "8888-v1", "name": "BAFU:8888 v1"})
            (root / "site/config.json").write_text(json.dumps(config))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(intake.main(["--root", str(root), "form", "--check"]), 1)
                self.assertEqual(intake.main(["--root", str(root), "form"]), 0)
                self.assertEqual(intake.main(["--root", str(root), "form", "--check"]), 0)
            written = (root / intake.FORM_FILE).read_text()
            listed = re.findall(r'- "([^"]+)"', written.split("# releases:start", 1)[1].split("# releases:end", 1)[0])
            self.assertEqual(listed, ["8888-v1"] + [release["id"] for release in reversed(LIVE["releases"])])
            # Nothing else in the file changed.
            self.assertEqual(written.replace('        - "8888-v1"\n', ""), FORM_TEXT)

    def test_the_forms_set_the_labels_the_workflows_look_for(self):
        self.assertIn('labels: ["bafu-finding", "needs-triage"]', FORM_TEXT)
        contribution = (ROOT / ".github/ISSUE_TEMPLATE/community-contribution.yml").read_text()
        self.assertIn('labels: ["contribution"]', contribution)

    def test_the_form_says_what_happens_next(self):
        for words in ("What happens next", "proposed as a pull request", "issue 48 is finding F48",
                      "/repeated reproduced", "BAFU decides what it changes"):
            self.assertIn(words, FORM_TEXT)

    def test_the_forms_are_well_formed_issue_forms(self):
        try:
            import yaml
        except ModuleNotFoundError:
            self.skipTest("needs PyYAML")
        for path in sorted((ROOT / ".github/ISSUE_TEMPLATE").glob("*.yml")):
            form = yaml.safe_load(path.read_text())
            self.assertTrue({"name", "description", "body"} <= set(form), path.name)
            ids = [item["id"] for item in form["body"] if "id" in item]
            self.assertEqual(len(ids), len(set(ids)), path.name)
            for item in form["body"]:
                self.assertIn(item["type"], {"markdown", "input", "textarea", "dropdown", "checkboxes"}, path.name)
                if item["type"] == "markdown":
                    self.assertTrue(item["attributes"]["value"].strip())
                else:
                    self.assertTrue(re.fullmatch(r"[a-z][a-z0-9_-]*", item["id"]), path.name)
                    self.assertTrue(item["attributes"]["label"].strip())
                if item["type"] == "dropdown":
                    self.assertTrue(item["attributes"]["options"])
        finding = yaml.safe_load(FORM_TEXT)
        fields = [
            (item["id"], item["attributes"]["label"], bool(item.get("validations", {}).get("required")))
            for item in finding["body"] if item["type"] != "markdown"
        ]
        self.assertEqual(tuple(fields), intake.FORM)
        releases = next(item for item in finding["body"] if item.get("id") == "releases")
        self.assertEqual(releases["attributes"]["options"], [r["id"] for r in reversed(LIVE["releases"])])
        self.assertTrue(releases["attributes"]["multiple"])
        kinds = next(item for item in finding["body"] if item.get("id") == "kind")
        self.assertEqual(
            [option.split(":")[0].lower() for option in kinds["attributes"]["options"]], list(community.KINDS)
        )


class SavedIssueTests(unittest.TestCase):
    """The pure functions on the bodies of real issues."""

    def test_issues_47_and_35_follow_the_earlier_form(self):
        for number in (47, 35):
            form = intake.parse_form(saved(number)["body"])
            self.assertEqual(form["version"], 1, number)
            self.assertEqual(form["problems"], [], number)
            self.assertEqual(set(form["fields"]), {field for field, _, _ in intake.EARLIER_FORM})
            self.assertTrue(all(form["fields"][field] for field, _, required in intake.EARLIER_FORM if required))

    def test_issue_32_was_not_filed_with_the_form(self):
        self.assertEqual(made(saved(32)), {"result": "not-form"})

    def test_issue_47_becomes_a_record_that_needs_a_second_measurement(self):
        outcome = made(saved(47))
        self.assertEqual(outcome["result"], "record")
        record = outcome["record"]
        self.assertEqual(tuple(record), community.FINDING_FIELDS)
        self.assertEqual((record["schema"], record["id"], record["issue"]), (2, "F47", 47))
        self.assertEqual(record["reported"], {"by": "mklarmann", "date": "2026-11-12", "url": f"{REPO}/issues/47"})
        self.assertEqual(record["releases"], ["2026-v1"])
        self.assertEqual(record["kind"], "defect")
        self.assertTrue(record["title"].startswith("389238 Production, washing machine, V-ZUG (CH): the 2026"))
        self.assertNotIn("[Finding]", record["title"])
        for name in ("repeated", "sent", "answer", "fixed_in", "closed"):
            self.assertIsNone(record[name])
        self.assertEqual(community.stage(record), "filed")
        self.assertEqual(community.status_label(community.stage(record), "BAFU"), "Needs a second measurement")
        self.assertEqual(community.validate_finding(record, community.record_path(record)), [])
        self.assertEqual(record["scope"], "389238 Production, washing machine, V-ZUG (CH, hr; `a` in BAFU:2025 v2)")
        self.assertIn("1,653 of 1,654 are identical", record["observation"])
        self.assertIn("Only the label changed.", record["observation"])
        self.assertTrue(record["method"].startswith("ecoSpold XML, `process_67a9453e"))
        self.assertTrue(record["exposure"].startswith("No consumers:"))
        self.assertTrue(record["notes"].startswith("Suggested correction: Restore the reference unit"))
        self.assertEqual(len(outcome["notes"]), 2)

    def test_issue_35_becomes_a_record(self):
        record = made(saved(35))["record"]
        self.assertEqual((record["id"], record["issue"], record["releases"]), ("F35", 35, ["2026-v1"]))
        self.assertEqual(record["reported"]["date"], "2026-10-21")
        self.assertEqual(record["datasets"], [])
        self.assertTrue(record["scope"].startswith("Release-wide: the published LCIA results workbook"))
        self.assertEqual(community.validate_finding(record, community.record_path(record)), [])

    def test_nothing_the_reporter_wrote_is_lost(self):
        """Every line of a saved body that is not a heading or a fence is in a field of the record."""
        for number in (47, 35):
            item = saved(number)
            record = made(item)["record"]
            held = "\n".join(record[key] for key in ("scope", "observation", "method", "exposure", "notes"))
            headings = {f"### {heading}" for _, heading, _ in intake.EARLIER_FORM}
            # The name of a release is in `releases`; whatever else that field said is kept as text.
            names = {release["name"] for release in CONFIG["releases"]}
            for line in item["body"].splitlines():
                if line.strip() and line not in headings | names and not line.startswith("```"):
                    self.assertIn(line.strip(), held, (number, line))
        self.assertIn("Release, as the issue states it: BAFU:2026 v1 (workbook dated June 2026",
                      made(saved(35))["record"]["method"])
        self.assertNotIn("Release, as the issue states it", made(saved(47))["record"]["method"])

    def test_the_saved_bodies_hold_nothing_private(self):
        for path in sorted(FIXTURES.glob("*.json")):
            text = path.read_text()
            self.assertIsNone(re.search(PRIVATE, text), path.name)
            # The only address in them is the provider's public contact, in a label's description.
            self.assertEqual(set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", text)) - {"lca@bafu.admin.ch"}, set(), path.name)


class FormTests(unittest.TestCase):
    def test_a_form_becomes_a_record_with_the_number_of_its_issue(self):
        outcome = made(issue(48))
        self.assertEqual(outcome["result"], "record", outcome)
        record = outcome["record"]
        self.assertEqual(record["id"], "F48")
        self.assertEqual(record["title"], "Example dataset: the amount is a thousand times its siblings'")
        self.assertEqual(record["datasets"], [{"code": 123456, "name": "Example, at plant", "location": "CH"}])
        self.assertEqual(record["reported"], {"by": "reporter", "date": "2026-11-20", "url": f"{REPO}/issues/48"})
        self.assertEqual((record["scope"], record["exposure"], record["notes"]), ("", "", ""))
        self.assertEqual(record["next"]["role"], "reviewer")
        self.assertIn("A second person repeats the measurement on BAFU's release files", record["next"]["action"])
        self.assertEqual(community.stage(record), "filed")
        self.assertEqual(community.validate_finding(record, "community/findings/0/F48.json"), [])
        self.assertEqual(outcome["notes"], [])
        self.assertEqual(made(issue(3120))["record"]["id"], "F3120")

    def test_kinds_and_releases_come_from_the_lists_of_the_form(self):
        for option, kind in (("Question: what does the data mean or intend?", "question"),
                             ("Difference: a difference in method, scope or convention, not an error", "difference")):
            self.assertEqual(made(issue(kind=option))["record"]["kind"], kind)
        self.assertEqual(made(issue(releases="2026-v1, 2025-v2"))["record"]["releases"], ["2025-v2", "2026-v1"])
        self.assertEqual(made(issue(releases="BAFU:2025 v2"))["record"]["releases"], ["2025-v2"])
        for bad in ("2031-v9", "2026-v1, later", "the newest"):
            outcome = made(issue(releases=bad))
            self.assertEqual(outcome["result"], "incomplete", bad)
            self.assertIn("choose from the form's list (2025-v2, 2026-v1)", outcome["problems"][0])
        outcome = made(issue(kind="Opinion: I do not like it"))
        self.assertIn('"What kind of finding is it?": choose one of the options of the form.', outcome["problems"])

    def test_datasets_are_read_one_per_line(self):
        lines = "```text\n123456 | Example, at plant | CH\n\n 654321|Other, at farm|RER \n```"
        record = made(issue(datasets=lines))["record"]
        self.assertEqual(record["datasets"], [
            {"code": 123456, "name": "Example, at plant", "location": "CH"},
            {"code": 654321, "name": "Other, at farm", "location": "RER"},
        ])
        for bad, words in (
            ("123456 Example, at plant (CH)", "separated by bars"),
            ("123456 | Example, at plant", "separated by bars"),
            ("abc | Example | CH", "separated by bars"),
            ("0 | Example | CH", "separated by bars"),
            ("123456 | | CH", "separated by bars"),
            ("123456 | Example | CH\n123456 | Example | CH", "dataset 123456 is listed twice"),
            ("123456", "no record lists dataset 123456 yet"),
        ):
            outcome = made(issue(datasets=bad))
            self.assertEqual(outcome["result"], "incomplete", bad)
            self.assertTrue(any(words in problem for problem in outcome["problems"]), (bad, outcome))
        many = "\n".join(f"{100000 + n} | Example {n} | CH" for n in range(intake.MAX_DATASETS + 1))
        self.assertIn("lists more than 200 datasets", made(issue(datasets=many))["problems"][0])

    def test_a_dataset_another_record_lists_takes_its_name_from_that_record(self):
        known = {123456: {"name": "Example, at regional storage", "location": "RER"}}
        outcome = made(issue(datasets="123456 | example at plant | CH\n222222 | New one | CH"), known)
        self.assertEqual(outcome["record"]["datasets"][0],
                         {"code": 123456, "name": "Example, at regional storage", "location": "RER"})
        self.assertEqual(outcome["record"]["datasets"][1], {"code": 222222, "name": "New one", "location": "CH"})
        self.assertEqual(len(outcome["notes"]), 1)
        # A number alone is enough for a dataset the records know.
        alone = made(issue(datasets="123456"), known)
        self.assertEqual(alone["record"]["datasets"][0]["name"], "Example, at regional storage")

    def test_a_finding_names_a_dataset_or_says_what_else_it_concerns(self):
        outcome = made(issue(datasets="_No response_"))
        self.assertIn('Name at least one dataset, or say under "What else it concerns"', outcome["problems"][0])
        record = made(issue(datasets="_No response_", scope="1,289 datasets whose name starts with xx"))["record"]
        self.assertEqual((record["datasets"], record["scope"]), ([], "1,289 datasets whose name starts with xx"))

    def test_an_empty_required_field_is_named(self):
        for field in ("kind", "releases", "observation", "method"):
            for empty in ("_No response_", "", "None", "   "):
                outcome = made(issue(**{field: empty}))
                self.assertEqual(outcome["result"], "incomplete", (field, empty))
                self.assertIn(f'"{intake.HEADING_OF[field]}" is empty.', outcome["problems"])
        outcome = made(issue(title="[Finding]   "))
        self.assertIn("The title is empty. Say in one line what was observed.", outcome["problems"])
        every = made(issue(kind="", releases="", observation="", method="", datasets="", title="[Finding] "))
        self.assertEqual(len(every["problems"]), 6)

    def test_a_body_with_a_broken_form_says_what_is_broken(self):
        cases = {
            "The heading \"How you measured it\" is missing.": form_body(method=None),
            "The heading \"What the data says\" appears twice.": form_body() + "\n\n### What the data says\n\nagain",
            "There is text before the first heading of the form.": "Hello,\n\n" + form_body(),
            "The issue mixes the headings of the form with those of the earlier form.":
                form_body() + "\n\n### Where you looked\n\nthe XML",
        }
        for words, body in cases.items():
            outcome = made(issue(body=body))
            self.assertEqual(outcome["result"], "incomplete", words)
            self.assertIn(words, outcome["problems"])

    def test_a_body_without_any_heading_of_the_form_is_not_a_form(self):
        for body in ("", None, "It looks wrong.", "### Something else\n\ntext", "## What the data says\n\nx"):
            self.assertEqual(made(issue(body=body or "")), {"result": "not-form"}, body)

    def test_windows_line_ends_and_missing_optional_headings_are_read(self):
        body = form_body(exposure=None, notes=None, scope=None).replace("\n", "\r\n")
        self.assertEqual(made(issue(body=body))["record"]["observation"],
                         "The dataset declares 1,000 kg where its siblings declare 1 kg.")

    def test_a_field_that_is_too_long_is_refused_and_never_cut(self):
        long = "x" * 100_000
        outcome = made(issue(observation=long))
        self.assertEqual(outcome["result"], "incomplete")
        self.assertEqual(outcome["problems"], ["The issue text is longer than 65,536 characters."])
        for field, limit in (("observation", 20000), ("method", 10000), ("exposure", 5000), ("notes", 5000),
                             ("scope", 500)):
            outcome = made(issue(**{field: "y" * (limit + 1)}))
            self.assertEqual(outcome["result"], "incomplete", field)
            self.assertIn(f"is longer than {limit:,} characters", outcome["problems"][0])
            self.assertEqual(made(issue(**{field: "y" * limit}))["result"], "record", field)
        outcome = made(issue(title="[Finding] " + "t" * 301))
        self.assertIn("The title is longer than 300 characters.", outcome["problems"][0])
        self.assertFalse(any("ttttt" in problem or "yyyyy" in problem for problem in outcome["problems"]))

    def test_what_a_record_refuses_is_said_in_the_reporters_words(self):
        cases = (
            ("observation", "see <script>alert(1)</script>", "holds raw HTML"),
            ("observation", "<!-- hidden -->", "holds raw HTML"),
            ("method", "a line\n# a heading\nmore", 'has a line that starts with "#"'),
            ("method", "![chart](https://example.org/x.png)", "embeds an image"),
            ("notes", "[here](/relative)", "has a link that is not a full https address"),
            ("notes", "[here](javascript:alert(1))", "has a link that is not a full https address"),
            ("exposure", "[x][1]\n\n[1]: https://example.org", "defines a link apart from its text"),
            ("scope", "a | b", 'must be one line without a bar'),
        )
        for field, text, words in cases:
            outcome = made(issue(**{field: text}))
            self.assertEqual(outcome["result"], "incomplete", text)
            self.assertTrue(
                any(problem.startswith(f'"{intake.HEADING_OF[field]}"') and words in problem
                    for problem in outcome["problems"]), (text, outcome))
            # A message says what is wrong; it never repeats what the reporter wrote.
            self.assertFalse(any(text in problem or "alert" in problem for problem in outcome["problems"]))
        outcome = made(issue(title="[Finding] a <b>bold</b> | title"))
        self.assertEqual(len(outcome["problems"]), 2)

    def test_shell_and_runner_syntax_is_only_ever_text(self):
        outcome = made(issue(title=f"[Finding] {HOSTILE.replace('|', '/')}", observation=HOSTILE, method=HOSTILE,
                             exposure=HOSTILE, notes=HOSTILE, scope=HOSTILE.replace("|", "/"),
                             datasets=f"123456 | {HOSTILE.replace('|', '/')} | CH"))
        self.assertEqual(outcome["result"], "record", outcome)
        record = outcome["record"]
        self.assertEqual(record["observation"], HOSTILE)
        self.assertEqual(record["datasets"][0]["name"], HOSTILE.replace("|", "/"))
        self.assertEqual(json.loads(intake.record_text(record)), record)

    def test_control_characters_are_dropped(self):
        record = made(issue(observation="one\x00 two\x1b[31m three\x07"))["record"]
        self.assertEqual(record["observation"], "one two[31m three")

    def test_who_and_when_come_from_the_issue_and_must_be_plain(self):
        for change in ({"user": {"login": "a b; rm"}}, {"user": None}, {"created_at": "yesterday"},
                       {"created_at": None}):
            item = dict(issue(), **change)
            self.assertEqual(made(item), {"result": "incomplete",
                                          "problems": ["The issue does not say who filed it and when."]}, change)
        for change in ({"number": "48"}, {"number": 0}, {"number": True}, {"number": -3}, {"number": None}):
            item = dict(issue(), **change)
            self.assertEqual(made(item), {"result": "incomplete", "problems": ["The issue has no number."]}, change)


class CommandTests(unittest.TestCase):
    def test_a_command_is_the_first_line_and_nothing_else_on_it(self):
        cases = {
            "/repeated reproduced": ("repeated", "reproduced", None),
            "/repeated not-reproduced\n\nI got 12.": ("repeated", "not-reproduced", None),
            "/repeated  reproduced \r\nI measured it.": ("repeated", "reproduced", None),
            "/repeated reproduced F10": ("repeated", "reproduced", "F10"),
            "/repeated": ("repeated", None, None),
            "/repeated yes": ("repeated", None, None),
            "/repeated reproduced and more": ("repeated", None, None),
            "/repeated REPRODUCED": ("repeated", None, None),
            "/record": ("record", None, None),
            "/record now": None,
            "/repeatedly, this happens": None,
            " /repeated reproduced": None,
            "I did it.\n/repeated reproduced": None,
            "": None,
            None: None,
        }
        for text, expected in cases.items():
            self.assertEqual(intake.command(text), expected, text)

    def record(self, **changes):
        return dict(made(issue(41))["record"], **changes)

    def comment(self, login="second-person", cid=7001):
        return {"id": cid, "user": {"login": login, "type": "User"}, "created_at": "2026-11-22T23:59:59Z"}

    def test_a_second_person_gives_the_record_a_second_measurement(self):
        outcome = intake.second_measurement(self.record(), self.comment(), 41, REPO, "reproduced")
        self.assertEqual(outcome["result"], "repeated")
        self.assertEqual(outcome["record"]["repeated"], {
            "by": "second-person", "date": "2026-11-22",
            "url": f"{REPO}/issues/41#issuecomment-7001", "result": "reproduced",
        })
        self.assertEqual(community.stage(outcome["record"]), "confirmed")
        other = intake.second_measurement(self.record(), self.comment(), 41, REPO, "not-reproduced")
        self.assertEqual(community.stage(other["record"]), "filed")

    def test_the_reporter_is_refused_however_the_login_is_written(self):
        for login in ("reporter", "Reporter", "REPORTER"):
            outcome = intake.second_measurement(self.record(), self.comment(login), 41, REPO, "reproduced")
            self.assertEqual(outcome, {"result": "refused", "why": "reporter"})

    def test_what_else_is_refused(self):
        cases = (
            ({"repeated": {"by": "x", "date": "2026-11-21", "url": f"{REPO}/issues/41", "result": "reproduced"}}, "already"),
            ({"closed": {"as": "withdrawn", "date": "2026-11-21", "reason": "No.", "url": f"{REPO}/issues/41"}}, "closed"),
            ({"reported": {"by": None, "date": None, "url": f"{REPO}/issues/41"}}, "no-reporter"),
        )
        for change, why in cases:
            outcome = intake.second_measurement(self.record(**change), self.comment(), 41, REPO, "reproduced")
            self.assertEqual(outcome, {"result": "refused", "why": why})
        for comment in (dict(self.comment(), id="7001"), dict(self.comment(), user={"login": "a b"})):
            outcome = intake.second_measurement(self.record(), comment, 41, REPO, "reproduced")
            self.assertEqual(outcome, {"result": "refused", "why": "invalid"})


class Workspace(unittest.TestCase):
    """A copy of the frozen records in a scratch folder, and a stand-in for GitHub."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = frozen.workspace(Path(self.tmp.name) / "workspace")
        self.fake = FakeGitHub(
            issues={48: {"labels": ["bafu-finding", "needs-triage"]}, 49: {"labels": ["bafu-finding", "needs-triage"]},
                    41: {"labels": ["bafu-finding", "needs-triage"]}, 3: {"labels": ["bafu-finding"]},
                    47: {"labels": ["bafu-finding", "needs-triage"]}},
            files={path.relative_to(self.root).as_posix(): path.read_text()
                   for path in sorted((self.root / "community/findings").rglob("F*.json"))},
        )
        self.api = GitHub(REPOSITORY, "token", transport=self.fake)

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self, event, name="issues"):
        return intake.plan(name, event, self.root)

    def publish(self, event, name="issues"):
        return intake.publish(self.plan(event, name), self.api)

    def check_with(self, path, text):
        """The whole check on the tree with one file written, as the workflow's checks run it."""
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = community.check(self.root)
        return code, out.getvalue()


class PlanTests(Workspace):
    def test_an_opened_form_is_proposed_as_one_new_file(self):
        planned = self.plan(opened(issue(48)))
        self.assertEqual((planned["action"], planned["why"], planned["kind"]), ("write", "propose", "new"))
        self.assertEqual((planned["finding"], planned["branch"], planned["base"]), ("F48", "intake/F48", "main"))
        self.assertEqual(planned["path"], "community/findings/0/F48.json")
        self.assertFalse((self.root / planned["path"]).exists(), "a plan writes nothing")
        record = json.loads(planned["content"])
        self.assertEqual(tuple(record), community.FINDING_FIELDS)
        self.assertEqual(community.stage(record), "filed")
        self.assertEqual(self.check_with(planned["path"], planned["content"])[0], 0)
        self.assertEqual(planned["marker"], "intake: proposed F48")
        self.assertIn("This report is finding **F48**", planned["comment"])
        self.assertIn("{pull}", planned["comment"])
        self.assertEqual(planned["remove_labels"], [])

    def test_the_folder_follows_the_number(self):
        planned = self.plan(opened(issue(3120)))
        self.assertEqual(planned["path"], "community/findings/3/F3120.json")
        self.assertEqual(self.check_with(planned["path"], planned["content"])[0], 0)

    def test_merging_the_pull_request_does_not_close_the_issue(self):
        closing = re.compile(r"\b(clos(e|es|ed)|fix(es|ed)?|resolv(e|es|ed))\b[^.\n]{0,20}#\d+", re.I)
        for event, name in ((opened(issue(48)), "issues"),
                            (commented(issue(41), "/repeated reproduced"), "issue_comment")):
            planned = self.plan(event, name)
            for key in ("commit", "title", "body", "comment"):
                self.assertIsNone(closing.search(planned[key]), (key, planned[key]))

    def test_what_the_issue_says_reaches_the_record_and_nothing_else(self):
        item = issue(48, title=f"[Finding] {HOSTILE.replace('|', '/')}", observation=HOSTILE, method=HOSTILE,
                     notes=HOSTILE, login="reporter")
        planned = self.plan(opened(item))
        self.assertEqual(planned["action"], "write")
        self.assertIn("touch /tmp/pwned", planned["content"])
        for key, value in planned.items():
            if key != "content":
                self.assertNotIn("pwned", json.dumps(value), key)
                self.assertNotIn("set-output", json.dumps(value), key)
        self.assertEqual(self.check_with(planned["path"], planned["content"])[0], 0)

    def test_only_issues_labelled_as_findings_are_read(self):
        self.assertEqual(self.plan(opened(issue(48, labels=("question",))))["why"], "not-a-finding")
        self.assertEqual(self.plan(opened(issue(48, labels=())))["why"], "not-a-finding")
        self.assertEqual(self.plan(opened(dict(issue(48), pull_request={})))["why"], "pull-request")
        self.assertEqual(self.plan(opened(issue(48), action="labeled"))["why"], "not-opened-or-edited")
        self.assertEqual(self.plan({"action": "opened"})["why"], "no-issue")
        self.assertEqual(self.plan(opened(issue(48)), "push")["why"], "other-event")

    def test_an_issue_not_filed_with_the_form_gets_one_clear_answer(self):
        planned = self.plan(opened(dict(saved(32), number=60)))
        self.assertEqual((planned["action"], planned["why"]), ("reply", "not-form"))
        self.assertEqual(planned["marker"], "intake: not-form")
        self.assertIn("was not filed with the finding form", planned["comment"])
        self.assertIn(f"{REPO}/issues/new?template=bafu-data-finding.yml", planned["comment"])
        self.assertEqual(planned["add_labels"], ["needs-info"])

    def test_an_incomplete_form_is_answered_with_what_is_missing(self):
        planned = self.plan(opened(issue(48, observation="_No response_", releases="_No response_")))
        self.assertEqual((planned["action"], planned["why"]), ("reply", "incomplete"))
        self.assertIn('- "What the data says" is empty.\n', planned["comment"])
        self.assertIn('- "BAFU release it was observed in" is empty.\n', planned["comment"])
        self.assertEqual(planned["add_labels"], ["needs-info"])
        same = self.plan(opened(issue(48, observation="_No response_", releases="_No response_"), "edited"))
        self.assertEqual(same["marker"], planned["marker"], "the same problems are said once")
        other = self.plan(opened(issue(48, observation="_No response_"), "edited"))
        self.assertNotEqual(other["marker"], planned["marker"], "other problems are said again")

    def test_an_edit_after_the_record_was_merged_changes_nothing(self):
        planned = self.plan(opened(saved(47), "edited"))
        self.assertEqual((planned["action"], planned["why"]), ("reply", "recorded"))
        self.assertEqual(planned["marker"], "intake: recorded")
        self.assertIn("already recorded as **F27**", planned["comment"])
        self.assertIn(f"{REPO}/blob/main/community/findings/0/F27.json", planned["comment"])
        self.assertEqual(self.plan(opened(saved(47)))["action"], "nothing")

    def test_an_issue_from_before_the_numbering_is_left_to_a_maintainer(self):
        self.assertEqual(community.load_config(self.root)["older_numbering_until"], 47)
        planned = self.plan(opened(issue(33)))
        self.assertEqual((planned["action"], planned["why"]), ("reply", "legacy"))
        self.assertIn("issue 48", planned["comment"])

    def test_where_the_older_numbering_ends_comes_from_the_site_configuration(self):
        """A repository whose findings are numbered by their issues from the first one sets 0."""
        def configured(until):
            config = community.read(self.root / "site/config.json")
            config["older_numbering_until"] = until
            (self.root / "site/config.json").write_text(json.dumps(config))

        configured(45)
        planned = self.plan(opened(issue(46)))
        self.assertEqual((planned["action"], planned["why"]), ("write", "propose"))
        self.assertEqual(json.loads(planned["content"])["id"], "F46")
        late = self.plan(opened(issue(40)))
        self.assertEqual((late["action"], late["why"]), ("reply", "legacy"))
        self.assertIn("issue 46", late["comment"])
        # Starting at issue 1: the frozen records, numbered the older way, are taken out first.
        configured(0)
        shutil.rmtree(self.root / "community/findings")
        (self.root / "community/patches.json").unlink()
        first = self.plan(opened(issue(1)))
        self.assertEqual((first["action"], first["why"]), ("write", "propose"))
        self.assertEqual((json.loads(first["content"])["id"], first["path"]), ("F1", "community/findings/0/F1.json"))
        self.assertEqual(self.check_with(first["path"], first["content"])[0], 0)

    def test_a_record_that_would_break_the_tree_is_not_proposed(self):
        # A patch names F48 as a finding it answers only once F48 exists; a related record must exist.
        record = json.loads(self.plan(opened(issue(48)))["content"])
        record["related"] = ["F9999"]
        errors = intake.tree_errors(record, community.load_findings(self.root), None, {"2026-v1", "2025-v2"})
        self.assertEqual(errors, ["F48: related names F9999, which has no record"])

    def test_a_second_measurement_by_comment(self):
        planned = self.plan(commented(issue(41), "/repeated reproduced\n\nI read the XML and got the same 14 of 20."),
                            "issue_comment")
        self.assertEqual((planned["action"], planned["why"], planned["kind"]), ("write", "repeat", "repeat"))
        self.assertEqual((planned["finding"], planned["branch"]), ("F19", "repeat/F19"))
        self.assertEqual(planned["path"], "community/findings/0/F19.json")
        record = json.loads(planned["content"])
        before = community.read(self.root / planned["path"])
        self.assertEqual(record["repeated"], {"by": "second-person", "date": "2026-11-22",
                                              "url": f"{REPO}/issues/41#issuecomment-7001", "result": "reproduced"})
        self.assertEqual({k: v for k, v in record.items() if k != "repeated"},
                         {k: v for k, v in before.items() if k != "repeated"})
        self.assertIn("(reproduced)", planned["title"])
        self.assertIn(f"{REPO}/issues/41#issuecomment-7001", planned["body"])
        self.assertNotIn("14 of 20", json.dumps({k: v for k, v in planned.items() if k != "content"}))
        self.assertEqual(planned["marker"], "intake: reply 7001")
        other = self.plan(commented(issue(41), "/repeated not-reproduced"), "issue_comment")
        self.assertIn("(not reproduced)", other["title"])
        self.assertEqual(community.stage(json.loads(other["content"])), "filed")
        self.assertEqual(self.check_with(planned["path"], planned["content"])[0], 0)

    def test_the_reporter_is_refused_politely(self):
        reporter = community.read(self.root / "community/findings/0/F19.json")["reported"]["by"]
        for login in (reporter, reporter.upper()):
            planned = self.plan(commented(issue(41), "/repeated reproduced", {"login": login, "type": "User"}),
                                "issue_comment")
            self.assertEqual((planned["action"], planned["why"]), ("reply", "reporter"))
            self.assertIn("Thank you for measuring again.", planned["comment"])
            self.assertIn("someone other than the person who reported", planned["comment"])
            self.assertEqual(planned["add_labels"], [])

    def test_comments_that_are_answered_and_comments_that_are_not(self):
        def why(item, text, **more):
            planned = self.plan(commented(item, text, **more), "issue_comment")
            return planned["action"], planned["why"]

        self.assertEqual(why(issue(48), "/repeated reproduced"), ("reply", "no-record"))
        self.assertEqual(why(issue(41), "/repeated"), ("reply", "usage"))
        self.assertEqual(why(issue(41), "/repeated maybe"), ("reply", "usage"))
        self.assertEqual(why(issue(3), "/repeated reproduced"), ("reply", "which"))
        self.assertEqual(why(issue(3), "/repeated reproduced F10"), ("write", "repeat"))
        self.assertEqual(why(issue(3), "/repeated reproduced F19"), ("reply", "other-issue"))
        self.assertEqual(why(issue(28), "/repeated reproduced"), ("reply", "already"))
        self.assertEqual(why(issue(32), "/repeated reproduced"), ("reply", "closed"))
        # Not a command, not created, not by a person, not on an issue: nothing at all.
        self.assertEqual(why(issue(41), "I repeated it and it reproduced."), ("nothing", "no-command"))
        self.assertEqual(why(issue(41), "/repeatedly"), ("nothing", "no-command"))
        self.assertEqual(why(issue(41), "/repeated reproduced", action="edited"), ("nothing", "not-created"))
        self.assertEqual(why(issue(41), "/repeated reproduced", action="deleted"), ("nothing", "not-created"))
        self.assertEqual(why(issue(41), "/repeated reproduced", user=BOT), ("nothing", "bot"))
        self.assertEqual(why(dict(issue(41), pull_request={}), "/repeated reproduced"), ("nothing", "pull-request"))

    def test_the_named_finding_of_a_shared_issue_is_the_one_changed(self):
        planned = self.plan(commented(issue(3), "/repeated reproduced F10"), "issue_comment")
        self.assertEqual((planned["finding"], planned["branch"], planned["path"]),
                         ("F10", "repeat/F10", "community/findings/0/F10.json"))

    def test_record_is_for_maintainers_and_keeps_the_evidence(self):
        item = saved(47)
        refused = self.plan(commented(item, "/record"), "issue_comment")
        self.assertEqual((refused["action"], refused["why"]), ("reply", "maintainer"))
        for association in ("OWNER", "MEMBER", "COLLABORATOR"):
            planned = self.plan(commented(item, "/record", association=association), "issue_comment")
            self.assertEqual((planned["action"], planned["why"], planned["kind"]), ("write", "repropose", "update"))
        self.assertEqual((planned["finding"], planned["branch"], planned["path"]),
                         ("F27", "intake/F27", "community/findings/0/F27.json"))
        before = community.read(self.root / planned["path"])
        after = json.loads(planned["content"])
        self.assertEqual(after["id"], "F27")
        for key in after:
            if key not in intake.FORM_FIELDS:
                self.assertEqual(after[key], before[key], key)
        self.assertNotEqual(after["observation"], before["observation"])
        self.assertEqual(self.check_with(planned["path"], planned["content"])[0], 0)
        self.assertTrue(planned["forced"])

    def test_record_on_an_issue_that_is_not_a_finding_or_already_says_the_same(self):
        planned = self.plan(commented(issue(48, labels=("question",)), "/record", association="OWNER"), "issue_comment")
        self.assertEqual((planned["action"], planned["why"]), ("reply", "not-finding"))
        new = self.plan(commented(issue(48), "/record", association="OWNER"), "issue_comment")
        self.assertEqual((new["action"], new["kind"], new["forced"]), ("write", "new", True))
        self.check_with(new["path"], new["content"])
        same = self.plan(commented(issue(48), "/record", association="OWNER"), "issue_comment")
        self.assertEqual((same["action"], same["why"]), ("reply", "unchanged"))


class PublishTests(Workspace):
    def test_a_proposal_is_one_branch_one_file_one_pull_request_one_comment(self):
        done = self.publish(opened(issue(48)))
        self.assertEqual((done["done"], done["ref"]), ("written", "intake/F48"))
        self.assertTrue(intake.SHA.fullmatch(done["sha"]))
        (pull,) = self.fake.pulls
        self.assertEqual((pull["head"], pull["base"], pull["state"]), ("intake/F48", "main", "open"))
        self.assertEqual(pull["title"], "findings: propose F48 from issue #48")
        changed = {path for path, text in self.fake.branches["intake/F48"].items()
                   if self.fake.branches["main"].get(path) != text}
        self.assertEqual(changed, {"community/findings/0/F48.json"})
        (comment,) = self.fake.bodies(48)
        self.assertTrue(comment.startswith("<!-- intake: proposed F48 -->\n"))
        self.assertIn(f"proposed in #{pull['number']}", comment)
        self.assertNotIn("community/findings/0/F48.json", self.fake.branches["main"])

    def test_the_same_event_twice_writes_nothing_new(self):
        first = self.publish(opened(issue(48)))
        writes = len(self.fake.writes())
        second = self.publish(opened(issue(48)))
        self.assertEqual(second["done"], "unchanged")
        self.assertEqual(second["sha"], first["sha"])
        self.assertEqual(len(self.fake.writes()), writes)
        self.assertEqual((len(self.fake.pulls), len(self.fake.bodies(48))), (1, 1))

    def test_two_people_filing_at_once_do_not_meet(self):
        self.publish(opened(issue(48)))
        self.publish(opened(issue(49, login="someone-else")))
        self.assertEqual(sorted(pull["head"] for pull in self.fake.pulls), ["intake/F48", "intake/F49"])
        for pull in self.fake.pulls:
            self.fake.merge(pull["number"])
        for path in ("community/findings/0/F48.json", "community/findings/0/F49.json"):
            self.assertIn(path, self.fake.branches["main"])
            self.check_with(path, self.fake.branches["main"][path])
        self.assertEqual(self.check_with("community/findings/0/F48.json",
                                         self.fake.branches["main"]["community/findings/0/F48.json"])[0], 0)

    def test_an_edit_before_the_merge_updates_the_same_pull_request(self):
        self.publish(opened(issue(48)))
        done = self.publish(opened(issue(48, observation="The dataset declares 2,000 kg."), "edited"))
        self.assertEqual(done["done"], "written")
        self.assertEqual(len(self.fake.pulls), 1)
        self.assertEqual(len(self.fake.bodies(48)), 1)
        record = json.loads(self.fake.branches["intake/F48"]["community/findings/0/F48.json"])
        self.assertEqual(record["observation"], "The dataset declares 2,000 kg.")
        self.assertEqual(self.fake.heads["intake/F48"], done["sha"])

    def test_a_proposal_changed_by_hand_is_never_overwritten(self):
        self.publish(opened(issue(48)))
        path = "community/findings/0/F48.json"
        by_hand = self.fake.branches["intake/F48"][path].replace("1,000 kg", "1,000 kg (checked by a maintainer)")
        self.fake.commit("intake/F48", path, by_hand, {"login": "maintainer", "type": "User"})
        done = self.publish(opened(issue(48, observation="Something else."), "edited"))
        self.assertEqual((done["done"], done["why"]), ("reply", "by-hand"))
        self.assertEqual(self.fake.branches["intake/F48"][path], by_hand)
        self.assertIn("was changed by hand after it was proposed", self.fake.bodies(48)[-1])
        again = self.publish(opened(issue(48, observation="And again."), "edited"))
        self.assertEqual(again["why"], "by-hand")
        self.assertEqual(len(self.fake.bodies(48)), 2, "said once")

    def test_a_proposal_a_maintainer_closed_stays_closed_until_a_maintainer_asks(self):
        self.publish(opened(issue(48)))
        self.fake.pulls[0]["state"] = "closed"
        writes = len(self.fake.writes())
        done = self.publish(opened(issue(48, observation="Please look again."), "edited"))
        self.assertEqual((done["done"], done["why"]), ("nothing", "closed-before"))
        self.assertEqual(len(self.fake.writes()), writes)
        done = self.publish(commented(issue(48, observation="Please look again."), "/record", association="MEMBER"),
                            "issue_comment")
        self.assertEqual(done["done"], "written")
        self.assertEqual([pull["state"] for pull in self.fake.pulls], ["closed", "open"])
        # The branch starts from main again: it holds the one new file and nothing stale.
        record = json.loads(self.fake.branches["intake/F48"]["community/findings/0/F48.json"])
        self.assertEqual(record["observation"], "Please look again.")

    def test_a_deleted_record_is_not_proposed_again_by_an_edit(self):
        self.publish(opened(issue(48)))
        self.fake.merge(self.fake.pulls[0]["number"])
        del self.fake.branches["main"]["community/findings/0/F48.json"]
        done = self.publish(opened(issue(48), "edited"))
        self.assertEqual((done["done"], done["why"]), ("nothing", "closed-before"))

    def test_a_second_measurement_becomes_a_pull_request_and_a_thank_you(self):
        done = self.publish(commented(issue(41), "/repeated reproduced"), "issue_comment")
        self.assertEqual((done["done"], done["ref"]), ("written", "repeat/F19"))
        (pull,) = self.fake.pulls
        self.assertEqual(pull["title"], "findings: record the second measurement of F19 (reproduced)")
        record = json.loads(self.fake.branches["repeat/F19"]["community/findings/0/F19.json"])
        self.assertEqual(record["repeated"]["by"], "second-person")
        self.assertIsNone(json.loads(self.fake.branches["main"]["community/findings/0/F19.json"])["repeated"])
        (comment,) = self.fake.bodies(41)
        self.assertTrue(comment.startswith("<!-- intake: reply 7001 -->\nThank you."))
        # The same comment again (a job run twice): nothing new.
        writes = len(self.fake.writes())
        self.publish(commented(issue(41), "/repeated reproduced"), "issue_comment")
        self.assertEqual(len(self.fake.writes()), writes)

    def test_a_second_claim_while_the_first_waits_is_answered_not_recorded(self):
        self.publish(commented(issue(41), "/repeated reproduced"), "issue_comment")
        before = self.fake.branches["repeat/F19"]["community/findings/0/F19.json"]
        done = self.publish(commented(issue(41), "/repeated not-reproduced", {"login": "third", "type": "User"},
                                      cid=7002), "issue_comment")
        self.assertEqual((done["done"], done["why"]), ("reply", "pending"))
        self.assertEqual(self.fake.branches["repeat/F19"]["community/findings/0/F19.json"], before)
        self.assertIn("is already proposed in #", self.fake.bodies(41)[-1])
        self.assertEqual(len(self.fake.pulls), 1)

    def test_the_reporters_own_claim_writes_one_comment_and_no_branch(self):
        reporter = community.read(self.root / "community/findings/0/F19.json")["reported"]["by"]
        done = self.publish(commented(issue(41), "/repeated reproduced", {"login": reporter, "type": "User"}),
                            "issue_comment")
        self.assertEqual((done["done"], done["why"]), ("reply", "reporter"))
        self.assertEqual(list(self.fake.heads), ["main"])
        self.assertEqual(self.fake.pulls, [])
        self.assertEqual([call[1] for call in self.fake.writes()], ["/issues/41/comments"])
        self.publish(commented(issue(41), "/repeated reproduced", {"login": reporter, "type": "User"}),
                     "issue_comment")
        self.assertEqual(len(self.fake.bodies(41)), 1)

    def test_needs_info_is_set_while_the_form_is_incomplete_and_taken_off_after(self):
        self.publish(opened(issue(48, observation="_No response_")))
        self.assertIn("needs-info", self.fake.issues[48]["labels"])
        self.assertEqual(self.fake.pulls, [])
        self.assertIn('"What the data says" is empty.', self.fake.bodies(48)[0])
        self.publish(opened(issue(48, observation="_No response_"), "edited"))
        self.assertEqual(len(self.fake.bodies(48)), 1)
        done = self.publish(opened(issue(48, labels=("bafu-finding", "needs-triage", "needs-info")), "edited"))
        self.assertEqual(done["done"], "written")
        self.assertNotIn("needs-info", self.fake.issues[48]["labels"])
        self.assertEqual(len(self.fake.pulls), 1)

    def test_a_request_that_fails_stops_the_run_and_the_next_run_finishes(self):
        self.fake.fail = ("POST", "/pulls", 502)
        with self.assertRaises(ApiError) as raised:
            self.publish(opened(issue(48)))
        self.assertNotIn("token", str(raised.exception))
        self.assertEqual(self.fake.pulls, [])
        done = self.publish(opened(issue(48)))
        self.assertEqual(done["done"], "written")
        self.assertEqual((len(self.fake.pulls), len(self.fake.bodies(48))), (1, 1))

    def test_the_checks_are_reported_under_the_names_of_a_pull_requests_checks(self):
        done = self.publish(opened(issue(48)))
        self.assertTrue(intake.post_statuses(self.api, done["sha"], "success", "https://github.com/x/y/actions/runs/1"))
        self.assertEqual([(s["context"], s["state"]) for s in self.fake.statuses],
                         [("Records and unit tests", "success"), ("Site build and links", "success"),
                          ("Tests hold through a finding's life", "success"), ("Patch tool lint and tests", "success")])
        self.assertTrue(all(s["sha"] == done["sha"] and s["target_url"].endswith("/runs/1") for s in self.fake.statuses))
        for result in ("failure", "cancelled", "skipped", ""):
            self.fake.statuses.clear()
            self.assertFalse(intake.post_statuses(self.api, done["sha"], result))
            self.assertEqual({s["state"] for s in self.fake.statuses}, {"failure"})
        with self.assertRaises(ValueError):
            intake.post_statuses(self.api, "main; echo", "success")


class RunTests(Workspace):
    """`intake.py run` and `intake.py status` as the workflow starts them."""

    def run_event(self, event, name="issues", repository=REPOSITORY):
        folder = Path(self.tmp.name) / "runner"
        folder.mkdir(exist_ok=True)
        (folder / "event.json").write_text(json.dumps(event))
        env = {"GITHUB_REPOSITORY": repository, "GITHUB_EVENT_NAME": name, "GITHUB_TOKEN": "token",
               "GITHUB_EVENT_PATH": str(folder / "event.json"), "GITHUB_OUTPUT": str(folder / "output"),
               "GITHUB_STEP_SUMMARY": str(folder / "summary")}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = intake.run(env, self.root, self.fake)
        output = (folder / "output").read_text() if (folder / "output").exists() else ""
        if (folder / "output").exists():
            (folder / "output").unlink()
        return code, out.getvalue(), output

    def test_run_proposes_and_hands_the_commit_to_the_checks(self):
        code, printed, output = self.run_event(opened(issue(48)))
        self.assertEqual(code, 0)
        pull = self.fake.pulls[0]["number"]
        self.assertEqual(printed, f"intake: issue #48: written (propose), pull request #{pull}\n")
        self.assertEqual(output, f"sha={self.fake.heads['intake/F48']}\nref=intake/F48\n")

    def test_run_hands_over_nothing_when_nothing_was_proposed(self):
        code, printed, output = self.run_event(opened(issue(48, observation="")))
        self.assertEqual((code, output), (0, ""))
        self.assertEqual(printed, "intake: issue #48: reply (incomplete)\n")

    def test_what_the_issue_says_is_never_printed(self):
        item = issue(48, title=f"[Finding] {HOSTILE.replace('|', '/')}", observation=HOSTILE, method=HOSTILE)
        for event in (opened(item), opened(dict(item, body="::error::x\n" + HOSTILE)),
                      opened(issue(48, observation="<script>::add-mask::</script>"))):
            _, printed, output = self.run_event(event)
            self.assertRegex(printed, r"\Aintake: issue #48: [a-z]+ \([a-z-]+\)(, pull request #\d+)?\n\Z")
            self.assertNotIn("pwned", printed + output)

    def test_another_repository_is_left_alone(self):
        code, printed, output = self.run_event(opened(issue(48)), repository="someone/fork")
        self.assertEqual((code, output), (0, ""))
        self.assertIn("is not the repository these records belong to", printed)
        self.assertEqual(self.fake.calls, [])

    def test_status_reads_the_commit_and_the_result_from_the_environment(self):
        done = self.publish(opened(issue(48)))
        env = {"GITHUB_REPOSITORY": REPOSITORY, "GITHUB_TOKEN": "token", "INTAKE_SHA": done["sha"],
               "INTAKE_CHECKS": "success", "GITHUB_SERVER_URL": "https://github.com", "GITHUB_RUN_ID": "123"}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(intake.status(env, self.root, self.fake), 0)
        self.assertEqual(self.fake.statuses[0]["target_url"], f"https://github.com/{REPOSITORY}/actions/runs/123")
        with self.assertRaises(ValueError):
            intake.status(dict(env, INTAKE_SHA="$(id)"), self.root, self.fake)

    def test_the_plan_command_writes_the_plan_to_a_file_and_prints_fixed_words(self):
        folder = Path(self.tmp.name)
        (folder / "event.json").write_text(json.dumps(opened(issue(48, observation=HOSTILE))))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = intake.main(["--root", str(self.root), "plan", str(folder / "event.json"), "--name", "issues",
                                "--out", str(folder / "plan.json")])
        self.assertEqual(code, 0)
        self.assertNotIn("pwned", out.getvalue())
        self.assertEqual(json.loads((folder / "plan.json").read_text())["branch"], "intake/F48")


class ApiClientTests(unittest.TestCase):
    def test_a_token_is_sent_only_over_https_or_to_this_machine(self):
        for api in ("http://example.org", "ftp://api.github.com", "https://api.github.com/x y", "file:///etc"):
            with self.assertRaises(ValueError):
                GitHub(REPOSITORY, "token", api=api)
        for api in ("https://api.github.com", "http://127.0.0.1:8123", "http://localhost:8123"):
            GitHub(REPOSITORY, "token", api=api)
        with self.assertRaises(ValueError):
            GitHub("not a repository", "token")

    def test_text_from_outside_is_made_plain_before_it_is_printed(self):
        from github_api import plain
        self.assertEqual(plain("::error::bad\n@everyone <b>`x`</b>"), ": :error: :bad everyone b x /b")
        self.assertEqual(len(plain("x" * 500)), 201)


if __name__ == "__main__":
    unittest.main()
