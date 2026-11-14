"""The job summary of a build, written by `scripts/release_build/job_summary.py`.

The rules the workflows keep are in `tests/test_full_release_workflow.py`.
"""

import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from release_build import job_summary, release_manifest  # noqa: E402
from test_release_manifest import write_run  # noqa: E402


class Summary(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.run_folder = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, **options):
        steps = write_run(self.run_folder, **options)
        data = release_manifest.manifest(self.run_folder, tag="patched-x", steps=steps)
        release_manifest.write(data, self.run_folder / "manifest.json")
        (self.run_folder / "results").mkdir()
        (self.run_folder / "results" / "manifest.json").write_text("{}")
        (self.run_folder / "results" / "patch-run.md").write_text("## Full release run\n")
        return data

    def test_it_says_what_every_step_did_and_what_was_built(self):
        self.write(contribution=True)
        text = job_summary.summarise(self.run_folder)
        self.assertIn("Run **completed**, tag `patched-x`.", text)
        self.assertIn("| provider build | completed | 2 | 100 |  |", text)
        self.assertIn("### Provider release", text)
        self.assertIn("### Patched against provider release", text)
        self.assertIn("### Inputs whose declared unit is not their supplier's", text)
        self.assertIn("declared in kilowatt hour, the supplier's unit is megajoule", text)
        self.assertIn("finding F13", text)
        self.assertIn("### Exports of the patched copy", text)
        self.assertIn("| brightway | yes | matches |  |", text)
        self.assertIn("| bafu-2026-v1-patched-simapro.csv | 20 | `", text)
        self.assertIn("### Contribution C900-OTHER, beside the patched copy", text)
        self.assertIn("### C900-OTHER against the patched copy", text)
        self.assertIn("Kept from this run: manifest.json, patch-run.md", text)
        self.assertIn(release_manifest.NOT_PUBLISHED, text)
        self.assertEqual(job_summary.NOT_PUBLISHED, release_manifest.NOT_PUBLISHED)
        self.assertTrue(text.rstrip().endswith("## Full release run"))

    def test_a_tag_that_can_not_be_released_is_said_at_the_top(self):
        self.write(steps=[])  # a run of the patch tool without any step is still a run
        manifest = release_manifest.load(self.run_folder / "manifest.json")
        manifest["not_releasable"] = ["patch 0001-x changed data and names nobody"]
        release_manifest.write(manifest, self.run_folder / "manifest.json")
        text = job_summary.summarise(self.run_folder)
        self.assertIn("> [!CAUTION]\n> This run can't be published as a release:", text)
        self.assertIn("> - patch 0001-x changed data and names nobody", text)

    def test_a_run_that_did_not_start_is_said_so(self):
        text = job_summary.summarise(self.run_folder / "nothing")
        self.assertIn("The run wrote no manifest.", text)
        self.assertEqual(text.count("The build did not start."), 2)
        self.assertIn("No comparison was written.", text)
        self.assertIn("No export was written.", text)
        self.assertIn("Kept from this run: nothing", text)

    def test_the_command_appends_to_the_summary_file(self):
        self.write()
        out = self.run_folder / "summary.md"
        out.write_text("before\n")
        self.assertEqual(job_summary.main([str(self.run_folder), "--out", str(out)]), 0)
        self.assertTrue(out.read_text().startswith("before\n## Build"))


if __name__ == "__main__":
    unittest.main()
