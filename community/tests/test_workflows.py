"""Rules the workflows keep, read from the files themselves: no YAML package is needed.

What only a run on GitHub can show is listed in docs/automation.md.
"""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import intake  # noqa: E402

WORKFLOWS = ROOT / ".github/workflows"
FILES = {path.name: path.read_text() for path in sorted(WORKFLOWS.glob("*.yml"))}
# Jobs that hold a token that can write. Each runs this repository's own code and nothing else.
WRITERS = {"intake.yml": ("record", "status"), "sync.yml": ("sync",), "release.yml": ("publish",)}


def run_blocks(text):
    """The script of every `run:` step, by its indentation."""
    lines, blocks, n = text.split("\n"), [], 0
    while n < len(lines):
        match = re.match(r"^(\s*)(- )?run:\s*(.*)$", lines[n])
        n += 1
        if not match:
            continue
        indent = len(match.group(1)) + (2 if match.group(2) else 0)
        if not match.group(3).startswith(("|", ">")):
            blocks.append(match.group(3))
            continue
        body = []
        while n < len(lines) and (not lines[n].strip() or len(lines[n]) - len(lines[n].lstrip()) > indent):
            body.append(lines[n])
            n += 1
        blocks.append("\n".join(body))
    return blocks


def jobs(text):
    """{job id: its text} of a workflow file."""
    body = text.split("\njobs:\n", 1)[1]
    parts = re.split(r"(?m)^  ([A-Za-z_][\w-]*):\n", body)
    return dict(zip(parts[1::2], parts[2::2]))


class WorkflowTests(unittest.TestCase):
    def test_the_workflows_of_this_branch_are_the_five(self):
        self.assertEqual(sorted(FILES), ["checks.yml", "intake.yml", "pages.yml", "release.yml", "sync.yml"])

    def test_every_action_is_pinned_to_a_commit(self):
        for name, text in FILES.items():
            used = re.findall(r"(?m)^\s*(?:- )?uses:\s*(\S+)(.*)$", text)
            self.assertTrue(used, name)
            for action, rest in used:
                if action.startswith("./"):
                    continue
                self.assertRegex(action, r"\A[\w.-]+/[\w./-]+@[0-9a-f]{40}\Z", f"{name}: {action}")
                self.assertRegex(rest, r"# v\d+\.\d+\.\d+", f"{name}: {action} names its version beside the commit")

    def test_no_expression_is_ever_part_of_a_shell_script(self):
        """Values reach a script through `env:`, which a shell reads as data."""
        for name, text in FILES.items():
            blocks = run_blocks(text)
            self.assertTrue(blocks, name)
            for block in blocks:
                self.assertNotIn("${{", block, f"{name}: {block[:60]}")

    def test_what_an_issue_says_is_read_by_the_script_only(self):
        for name, text in FILES.items():
            for field in ("issue.title", "issue.body", "comment.user", "issue.user", "head_ref", "head.ref",
                          "pull_request.title", "pull_request.body", "discussion", "review.body"):
                self.assertNotIn(f"github.event.{field}", text, name)
            # The one use of a comment's text: the condition that keeps a runner from starting.
            for use in re.findall(r"\S*github\.event\.comment\.body\S*\s*\S*", text):
                self.assertRegex(use, r"\A\(?startsWith\(github\.event\.comment\.body, '/[a-z]+'\)", name)

    def test_no_workflow_runs_code_of_a_pull_request_with_a_token_that_can_write(self):
        for name, text in FILES.items():
            self.assertNotIn("pull_request_target", text, name)
            self.assertNotIn("workflow_run", text, name)
        for name, writers in WRITERS.items():
            for job in writers:
                body = jobs(FILES[name])[job]
                self.assertNotRegex(body, r"(?m)^\s+ref:", f"{name} {job}: checks out the default branch or the tag")
                for block in run_blocks(body):
                    self.assertNotRegex(block, r"\b(uv|pip|npm|curl|wget)\b", f"{name} {job} installs nothing")

    def test_a_token_is_given_to_the_job_that_needs_it_and_no_other(self):
        for name, text in FILES.items():
            top = re.search(r"(?m)^permissions:(.*)\n((?:  .*\n)*)", text)
            self.assertIsNotNone(top, name)
            granted = (top.group(1) + top.group(2)).strip()
            self.assertIn(granted, ("{}", "contents: read"), name)
            self.assertNotRegex(text, r"write-all|read-all", name)
        expected = {
            ("intake.yml", "record"): {"contents: write", "pull-requests: write", "issues: write"},
            ("intake.yml", "checks"): {"contents: read"},
            ("intake.yml", "status"): {"contents: read", "statuses: write"},
            ("sync.yml", "sync"): {"contents: read", "issues: write"},
            ("pages.yml", "build"): {"contents: read", "issues: read"},
            ("pages.yml", "deploy"): {"pages: write", "id-token: write"},
            ("release.yml", "build"): {"contents: read"},
            ("release.yml", "publish"): {"contents: write"},
        }
        for (name, job), wanted in expected.items():
            body = jobs(FILES[name])[job]
            block = re.search(r"(?m)^    permissions:\n((?:      .*\n)+)", body)
            self.assertIsNotNone(block, f"{name} {job}")
            found = {re.sub(r"\s*#.*", "", line).strip() for line in block.group(1).splitlines()}
            self.assertEqual(found, wanted, f"{name} {job}")
        for job, body in jobs(FILES["checks.yml"]).items():
            self.assertNotIn("permissions:", body, f"checks.yml {job} reads only")

    def test_no_checkout_leaves_a_token_on_disk(self):
        for name, text in FILES.items():
            self.assertEqual(text.count("actions/checkout@"), text.count("persist-credentials: false"), name)

    def test_every_workflow_says_what_runs_at_the_same_time(self):
        for name, text in FILES.items():
            self.assertIn("concurrency:", text, name)
            self.assertRegex(text, r"timeout-minutes: \d+", name)
        for name in ("intake.yml", "sync.yml", "pages.yml", "release.yml"):
            self.assertIn("cancel-in-progress: false", FILES[name], f"{name}: a run that writes is never cut off")

    def test_the_intake_reports_the_checks_under_the_names_of_the_checks(self):
        names = re.findall(r"(?m)^    name: (.+)$", FILES["checks.yml"])
        self.assertEqual(tuple(names), intake.CHECK_CONTEXTS)
        self.assertIn("uses: ./.github/workflows/checks.yml", FILES["intake.yml"])
        self.assertIn("workflow_call:", FILES["checks.yml"])

    def test_triggers(self):
        def triggers(name):
            return FILES[name].split("\non:\n", 1)[1].split("\npermissions:", 1)[0]

        self.assertRegex(triggers("intake.yml"), r"issues:\n    types: \[opened, edited\]\n  issue_comment:\n    types: \[created\]")
        self.assertNotIn("pull_request", triggers("intake.yml"))
        pages = triggers("pages.yml")
        self.assertIn("types: [opened, closed, reopened]", pages)
        for gone in ("labeled", "unlabeled", "pull_request"):
            self.assertNotIn(gone, pages)
        self.assertIn("schedule:", pages)
        sync = triggers("sync.yml")
        for wanted in ('"community/findings/**"', "schedule:", "workflow_dispatch:", "branches: [main]"):
            self.assertIn(wanted, sync)
        self.assertIn('tags: ["patched-*"]', triggers("release.yml"))
        self.assertIn("pull_request:", triggers("checks.yml"))

    def test_a_deploy_needs_the_issues_and_a_checked_site(self):
        build = jobs(FILES["pages.yml"])["build"]
        self.assertIn("--require-issues", build)
        self.assertLess(build.index("scripts/check_site.py"), build.index("upload-pages-artifact"))

    def test_a_release_publishes_the_manifest_and_nothing_else(self):
        text = FILES["release.yml"]
        build, publish = jobs(text)["build"], jobs(text)["publish"]
        self.assertEqual(re.findall(r"(?m)^\s+path: (.+)$", build),
                         ["${{ steps.release.outputs.cache }}", "${{ runner.temp }}/release/manifest.json"])
        self.assertIn("--verify", publish)
        created = next(block for block in run_blocks(publish) if "gh release create" in block)
        self.assertEqual(re.findall(r'"\$RUNNER_TEMP/[^"]+"', created),
                         ['"$RUNNER_TEMP/release/manifest.json"', '"$RUNNER_TEMP/release/notes.md"'])
        self.assertIn("git merge-base --is-ancestor", build)
        self.assertLess(build.index("--strict"), build.index("release_manifest.py"))


if __name__ == "__main__":
    unittest.main()
