"""What leaves the machine names no person who confirmed for the provider.

Made-up names in made-up summaries only.
"""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_release  # noqa: E402
import full_release_table  # noqa: E402
from release_build import job_summary, public_summary  # noqa: E402
from test_release_manifest import step, summary  # noqa: E402

PERSON = "Petra Example"
CONFIRMED = f"{PERSON}, BAFU (email, 3 March 2031)"


def made_up_summary():
    """A run summary in which a made-up patch says which made-up person confirmed it."""
    steps = [
        step("0001-amount", "patch", 2, confirmed_by=CONFIRMED),
        step("0002-other", "patch", 1, confirmed_by=f"{PERSON} at the provider"),
        step("0003-nobody", "patch", 1),
    ]
    return summary(steps=steps)


class PublicForm(unittest.TestCase):
    def test_who_confirmed_becomes_the_organisation_and_the_date(self):
        self.assertEqual(public_summary.confirmed(CONFIRMED), "BAFU (3 March 2031)")
        self.assertEqual(
            public_summary.confirmed(f"{PERSON} (call, 2031-03-03)"), "BAFU (2031-03-03)"
        )
        self.assertEqual(public_summary.confirmed(f"{PERSON}, somewhere"), "BAFU")
        self.assertIsNone(public_summary.confirmed(None))
        self.assertEqual(public_summary.confirmed(CONFIRMED, "ACME"), "ACME (3 March 2031)")

    def test_nothing_but_a_date_is_copied_from_the_field(self):
        for value in (
            f"3 March 2031 {PERSON}",
            f"{PERSON} 3 March 2031 and {PERSON}",
            f"BAFU ({PERSON})",
            f"BAFU (3 March 2031) {PERSON}",
        ):
            self.assertNotIn(PERSON, public_summary.confirmed(value))
            self.assertFalse(public_summary.is_public(value), value)
        for value in (None, "BAFU", "BAFU (3 March 2031)", "BAFU (2031-03-03)"):
            self.assertTrue(public_summary.is_public(value), value)

    def test_every_confirmation_of_a_summary_is_made_public_wherever_it_is(self):
        data = made_up_summary() | {"nested": {"deep": [{"confirmed_by": PERSON}]}}
        made = public_summary.public(data)
        self.assertNotIn(PERSON, json.dumps(made))
        self.assertEqual(
            [entry["confirmed_by"] for entry in made["steps"]],
            ["BAFU (3 March 2031)", "BAFU", None],
        )
        self.assertEqual(made["nested"]["deep"][0]["confirmed_by"], "BAFU")
        # the author and the authoriser of a patch stay; the summary given is not touched
        self.assertEqual(made["steps"][0]["authored_by"], "Ann Author")
        self.assertEqual(made["steps"][0]["authorised_by"], "Rita Reviewer")
        self.assertIn(PERSON, json.dumps(data))
        self.assertEqual(public_summary.named(made), [])
        self.assertEqual(
            public_summary.named(data),
            ["steps[0].confirmed_by", "steps[1].confirmed_by", "nested.deep[0].confirmed_by"],
        )


class Files(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.raw = self.root / "summaries"
        self.raw.mkdir()
        (self.raw / "head.json").write_text(json.dumps(made_up_summary()))
        (self.raw / "base.json").write_text(json.dumps(made_up_summary()))

    def tearDown(self):
        self.temp.cleanup()

    def run_it(self, *arguments):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = public_summary.main([str(a) for a in arguments])
        return status, out.getvalue()

    def uploaded(self, folder: Path) -> str:
        return "".join(path.read_text() for path in sorted(folder.rglob("*")) if path.is_file())

    def test_the_folder_a_workflow_uploads_names_no_person_who_confirmed(self):
        public = self.root / "public-summaries"
        status, _ = self.run_it(self.raw, "--out", public)
        self.assertEqual(status, 0)
        self.assertEqual(sorted(p.name for p in public.iterdir()), ["base.json", "head.json"])
        self.assertNotIn(PERSON, self.uploaded(public))
        self.assertIn('"confirmed_by": "BAFU (3 March 2031)"', self.uploaded(public))
        self.assertEqual(public_summary.check([public]), [])

    def test_the_check_fails_on_a_file_that_names_a_person_who_confirmed(self):
        status, text = self.run_it("--check", self.raw)
        self.assertEqual(status, 1)
        self.assertIn("head.json: steps[0].confirmed_by", text)
        self.assertNotIn(PERSON, text)  # the check says where, and does not repeat the name
        public = self.root / "public"
        self.run_it(self.raw, "--out", public)
        self.assertEqual(self.run_it("--check", public)[0], 0)

    def test_a_release_run_keeps_the_summary_in_its_public_form(self):
        results = self.root / "results"
        results.mkdir()
        manifest = self.root / "manifest.json"
        manifest.write_text('{"format": "x"}\n')
        keep = {"manifest.json": manifest, "run-summary.json": self.raw / "head.json"}
        keep["not-written.json"] = self.root / "missing.json"
        self.assertEqual(build_release.set_aside(keep, results), [])
        self.assertEqual(
            sorted(p.name for p in results.iterdir()), ["manifest.json", "run-summary.json"]
        )
        self.assertNotIn(PERSON, self.uploaded(results))
        self.assertEqual((results / "manifest.json").read_bytes(), manifest.read_bytes())
        kept = json.loads((results / "run-summary.json").read_text())
        self.assertEqual(kept["steps"][0]["confirmed_by"], "BAFU (3 March 2031)")
        self.assertEqual(kept["totals"], made_up_summary()["totals"])

    def test_a_kept_file_that_names_a_person_who_confirmed_is_held_back(self):
        results = self.root / "results"
        results.mkdir()
        audit = self.root / "audit.json"
        audit.write_text(json.dumps({"status": "passed", "note": {"confirmed_by": PERSON}}))
        keep = {"patched-audit.json": audit, "run-summary.json": self.raw / "head.json"}
        held_back = build_release.set_aside(keep, results)
        self.assertEqual(held_back, ["patched-audit.json: note.confirmed_by"])
        self.assertEqual([p.name for p in results.iterdir()], ["run-summary.json"])
        self.assertNotIn(PERSON, self.uploaded(results))

    def test_a_summary_that_can_not_be_read_stays_on_the_machine(self):
        results = self.root / "results"
        results.mkdir()
        broken = self.root / "broken.json"
        broken.write_text(f'{{"confirmed_by": "{PERSON}", trunca')
        held_back = build_release.set_aside({"run-summary.json": broken}, results)
        self.assertEqual(held_back, ["run-summary.json: not a JSON record"])
        self.assertEqual(list(results.iterdir()), [])

    def test_the_table_of_a_patch_run_reads_the_summary_in_its_public_form(self):
        loaded = full_release_table.load(self.raw / "head.json")
        self.assertNotIn(PERSON, json.dumps(loaded))
        out = self.root / "table.md"
        with contextlib.redirect_stdout(io.StringIO()):
            full_release_table.main([str(self.raw / "head.json"), "--out", str(out)])
        self.assertTrue(out.read_text().strip())
        self.assertNotIn(PERSON, out.read_text())

    def test_the_job_summary_reads_its_records_in_their_public_form(self):
        self.assertNotIn(PERSON, json.dumps(job_summary.load(self.raw / "head.json")))


if __name__ == "__main__":
    unittest.main()
