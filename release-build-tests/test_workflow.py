"""Rules the Release build workflow has to keep (`.github/workflows/release-build.yml`)."""

import re
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "scripts"))

from release_build import job_summary  # noqa: E402

WORKFLOW = (REPOSITORY / ".github" / "workflows" / "release-build.yml").read_text()
KEPT = "${{ runner.temp }}/release-build-results/"


class Workflow(unittest.TestCase):
    def test_actions_are_pinned_by_commit(self):
        uses = re.findall(r"uses: (\S+)", WORKFLOW)
        self.assertEqual(len(uses), 6)
        for action in uses:
            self.assertRegex(action, r"^[\w./-]+@[0-9a-f]{40}$")

    def test_the_token_can_only_read(self):
        self.assertIn("\npermissions:\n  contents: read\n\n", WORKFLOW)
        self.assertEqual(WORKFLOW.count("permissions:"), 1)  # no job asks for more
        self.assertNotIn("pull_request_target", WORKFLOW)
        self.assertNotIn("secrets.", WORKFLOW)

    def test_only_the_audits_and_the_comparison_are_uploaded(self):
        (upload,) = re.findall(r"uses: actions/upload-artifact@.*\n((?: {8,}.*\n)+)", WORKFLOW)
        self.assertEqual(re.findall(r"\bpath: (.*)", upload), [KEPT])
        # The builds are written elsewhere, and nothing but the summary step writes there
        self.assertEqual(WORKFLOW.count("release-build-results"), 3)  # written, named, uploaded
        self.assertIn('--results "$RUNNER_TEMP/release-build-results"', WORKFLOW)
        self.assertNotIn("release-build-results/builds", WORKFLOW)
        for build in ("provider", "patched"):
            self.assertIn(f'"$RUNNER_TEMP/builds/{build}"', WORKFLOW)

    def test_the_patched_build_fails_on_findings_and_the_release_is_checked(self):
        patched = WORKFLOW.split("name: Build and audit the patched release")[1]
        patched = patched.split("- name:")[0]
        self.assertIn("--fail-on-findings", patched)
        self.assertEqual(WORKFLOW.count("build latest"), 2)  # downloaded and checked by the tool
        self.assertIn("key: bafu-release-${{ steps.release.outputs.sha256 }}", WORKFLOW)

    def test_the_full_release_runs_on_main_and_the_made_up_one_on_pull_requests(self):
        self.assertIn("if: ${{ github.event_name == 'pull_request' }}", WORKFLOW)
        self.assertIn("if: ${{ github.event_name != 'pull_request' }}", WORKFLOW)
        self.assertIn("workflow_dispatch:", WORKFLOW)
        self.assertIn("concurrency:\n  group: release-build-${{ github.ref }}", WORKFLOW)
        self.assertEqual(WORKFLOW.count('- "scripts/release_build/**"'), 2)


class Kept(unittest.TestCase):
    def test_only_three_named_files_are_set_aside(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for build in ("provider", "patched"):
                (root / build / "audit").mkdir(parents=True)
                (root / build / "audit" / "audit.json").write_text("{}")
                (root / build / "audit" / "scores.csv").write_text("every score")
                (root / build / "build.json").write_text("{}")
            (root / "comparison.json").write_text("{}")
            written = job_summary.collect(
                root / "provider", root / "patched", root / "comparison.json", root / "kept"
            )
            names = sorted(path.name for path in (root / "kept").iterdir())
        self.assertEqual(names, ["comparison.json", "patched-audit.json", "provider-audit.json"])
        self.assertEqual(sorted(written), names)

    def test_a_build_that_did_not_start_is_said_so(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            text = job_summary.summarise(root / "a", root / "b", root / "c.json")
            self.assertEqual(job_summary.collect(root / "a", root / "b", root / "c.json", root), [])
        self.assertEqual(text.count("The build did not start."), 2)
        self.assertIn("No comparison was written.", text)


if __name__ == "__main__":
    unittest.main()
