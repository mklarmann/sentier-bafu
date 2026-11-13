import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("community_records", ROOT / "scripts/community.py")
records = importlib.util.module_from_spec(spec)
spec.loader.exec_module(records)


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


class FindingRecordTests(unittest.TestCase):
    def setUp(self):
        self.findings = {r["id"]: r for r in records.load_findings(ROOT)}

    def errors(self, rid):
        return records.validate_finding(self.findings[rid], f"{rid}.json")

    def test_committed_records_are_valid(self):
        self.assertTrue(self.findings)
        for rid in self.findings:
            self.assertEqual(self.errors(rid), [], rid)

    def test_index_is_generated_from_the_records(self):
        rows = records.ledger_rows(records.index_text(list(self.findings.values())))
        self.assertEqual(set(rows), set(self.findings))
        for rid, row in rows.items():
            self.assertEqual(row["status"], self.findings[rid]["status"])
            self.assertEqual(row["links"], set(self.findings[rid]["links"]))

    def test_no_generated_ledger_is_kept_in_the_repository(self):
        # Two pull requests that each add a finding would conflict on a committed table.
        self.assertFalse((ROOT / "community/findings.md").exists())
        self.assertTrue((ROOT / "community/findings/README.md").is_file())

    def test_unknown_status_is_reported(self):
        self.findings["F2"]["status"] = "Open"
        self.assertTrue(self.errors("F2"))

    def test_patch_cannot_mark_a_finding_fixed(self):
        self.findings["F1"]["status"] = "upstream-fixed"
        self.assertTrue(self.errors("F1"))
        self.findings["F1"]["provider_correction_shipped"] = {
            "release": "BAFU:2027 v1",
            "evidence_url": "https://example.org/release",
        }
        self.assertEqual(self.errors("F1"), [])

    def test_shipped_correction_requires_upstream_fixed(self):
        self.findings["F9"]["provider_correction_shipped"] = {
            "release": "BAFU:2027 v1",
            "evidence_url": "https://example.org/release",
        }
        self.assertTrue(self.errors("F9"))

    def test_open_record_needs_next_action_and_role(self):
        self.findings["F9"]["review_role"] = "anyone"
        self.assertTrue(self.errors("F9"))

    def test_provider_response_needs_public_evidence(self):
        self.findings["F3"]["provider_response"]["evidence_url"] = ""
        self.assertTrue(self.errors("F3"))

    def test_patch_needs_pinned_url_and_authorisation(self):
        self.findings["F1"]["community_patch"]["authorisation"] = {}
        self.assertTrue(self.errors("F1"))

    def test_retained_items_need_evidence(self):
        self.findings["F14"]["retained"][0]["evidence_url"] = ""
        self.assertTrue(self.errors("F14"))

    def test_malformed_record_is_reported_not_raised(self):
        del self.findings["F9"]["provider_correction_shipped"]
        self.assertTrue(self.errors("F9"))

    def test_record_needs_a_thread_and_one_line_fields(self):
        self.findings["F2"]["links"] = []
        self.assertTrue(self.errors("F2"))
        self.setUp()
        self.findings["F2"]["title"] = "two | cells"
        self.assertTrue(self.errors("F2"))

    def test_file_name_must_match_the_id(self):
        self.assertTrue(records.validate_finding(self.findings["F2"], "F3.json"))

    def test_rules_one_by_one(self):
        cases = {
            "patch without an id": lambda r: r["community_patch"].pop("id"),
            "patch without a url": lambda r: r["community_patch"].pop("url"),
            "patch that is not an object": lambda r: r.update(community_patch="0001"),
            "link that is not https": lambda r: r.update(links=["http://example.org/x"]),
            "link with a bracket": lambda r: r.update(links=["https://example.org/a)b"]),
            "empty title": lambda r: r.update(title=" "),
            "title over two lines": lambda r: r.update(title="one\ntwo"),
            "title with a line separator": lambda r: r.update(title="one\u2028two"),
            "raw HTML in the observation": lambda r: r.update(observation="see <script>x</script>"),
            "raw HTML in the datasets": lambda r: r.update(datasets="<img src=x onerror=y>"),
            "retained item of an unknown kind": lambda r: r["retained"].append(
                {"kind": "rumour", "text": "t", "evidence_url": "https://example.org"}
            ),
            "id that is not F and a number": lambda r: r.update(id="F01"),
            "awaiting flag that is not a boolean": lambda r: r.update(awaiting_second_measurement="no"),
            "awaiting a second measurement after being reported": lambda r: r.update(
                awaiting_second_measurement=True
            ),
            "status that is a list": lambda r: r.update(status=["open"]),
        }
        for name, change in cases.items():
            self.setUp()
            record = self.findings["F1"]  # upstream-reported, with a patch
            change(record)
            self.assertTrue(records.validate_finding(record), name)

    def test_shipped_correction_needs_release_and_evidence(self):
        self.findings["F17"]["provider_correction_shipped"].pop("evidence_url")
        self.assertTrue(self.errors("F17"))

    def test_a_record_that_is_not_an_object_is_reported(self):
        self.assertTrue(records.validate_finding(["F1"], "F1.json"))

    def test_index_holds_thousands_of_records(self):
        many = [dict(self.findings["F2"], id=f"F{n}") for n in range(1, 5001)]
        self.assertEqual(len(records.ledger_rows(records.index_text(many))), 5000)


class ContributionTriageTests(unittest.TestCase):
    def setUp(self):
        self.record = records.read(ROOT / "community/contributions/C001.json")

    def test_committed_contributions_carry_triage_fields(self):
        for path in (ROOT / "community/contributions").glob("*.json"):
            self.assertEqual(
                records.validate_contribution_triage(records.read(path)), [], path.name
            )

    def test_open_contribution_needs_next_action_and_role(self):
        self.record["next_action"] = ""
        self.assertTrue(records.validate_contribution_triage(self.record))

    def test_accepted_contribution_needs_no_next_action(self):
        self.record.update(status="accepted", next_action=None, review_role=None)
        self.assertEqual(records.validate_contribution_triage(self.record), [])


class CheckTests(unittest.TestCase):
    """The whole check, on a copy of the records with one thing wrong."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shutil.copytree(ROOT / "community", self.root / "community")

    def tearDown(self):
        self.tmp.cleanup()

    def result(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = records.check(self.root)
        return code, out.getvalue()

    def test_committed_tree_passes(self):
        self.assertEqual(self.result()[0], 0)

    def test_an_edited_record_needs_no_regenerated_file(self):
        path = self.root / "community/findings/F2.json"
        record = records.read(path)
        record["title"] += " (edited)"
        path.write_text(json.dumps(record))
        code, text = self.result()
        self.assertEqual(code, 0, text)

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

    def test_duplicate_and_misnamed_record_are_reported(self):
        shutil.copy(self.root / "community/findings/F2.json", self.root / "community/findings/F9000.json")
        code, text = self.result()
        self.assertEqual(code, 1)
        self.assertIn("duplicate finding F2", text)
        self.assertIn("the file is named F9000.json", text)

    def test_broken_file_is_named_and_does_not_stop_the_check(self):
        (self.root / "community/findings/F9001.json").write_text("{not json")
        (self.root / "community/findings/F9002.json").write_text("[1, 2]")
        code, text = self.result()
        self.assertEqual(code, 1)
        self.assertIn("F9001.json: unreadable record", text)
        self.assertIn("F9002.json", text)

    def test_invalid_finding_is_reported_through_check(self):
        path = self.root / "community/findings/F2.json"
        record = records.read(path)
        record["status"] = "Open"
        path.write_text(json.dumps(record))
        self.assertIn("F2: invalid status", self.result()[1])

    def test_contribution_without_next_action_is_reported_through_check(self):
        path = self.root / "community/contributions/C001.json"
        record = records.read(path)
        record["next_action"] = ""
        path.write_text(json.dumps(record))
        self.assertIn("open contribution needs a next action", self.result()[1])

    def test_finding_template_is_a_valid_start(self):
        template = records.read(ROOT / "community/templates/finding.json")
        self.assertEqual(set(template), records.FINDING_FIELDS)
