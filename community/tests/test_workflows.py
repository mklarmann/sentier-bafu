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
# Every workflow of the repository, and the two composite actions the build workflows share.
# What is particular to the patch run and the release build (what they upload, what a release
# publishes) is tested beside the patch tool, in tests/test_full_release_workflow.py.
EXPECTED = ("checks.yml", "full-release.yml", "intake.yml", "pages.yml", "release-build.yml", "sync.yml")
FILES = {path.name: path.read_text() for path in sorted(WORKFLOWS.glob("*.y*ml"))}
ACTIONS = {f"actions/{path.parent.name}": path.read_text() for path in sorted((ROOT / ".github/actions").glob("*/action.yml"))}
# Jobs that hold a token that can write. Each runs this repository's own code and nothing else.
WRITERS = {"intake.yml": ("record", "status"), "sync.yml": ("sync",), "release-build.yml": ("publish",)}


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
    def test_the_workflows_are_the_ones_the_documentation_describes(self):
        """One set: a workflow that is added or removed changes this list and docs/automation.md."""
        self.assertEqual(tuple(FILES), EXPECTED)
        described = (ROOT / "docs/automation.md").read_text()
        for name in EXPECTED:
            self.assertIn(f"| `{name}` |", described, name)
            self.assertIn(f"### {name}", described, name)
        for gone in ("ci.yml", "release.yml"):
            self.assertNotIn(f"`{gone}`", described, gone)

    def test_every_action_is_pinned_to_a_commit(self):
        for name, text in {**FILES, **ACTIONS}.items():
            used = re.findall(r"(?m)^\s*(?:- )?uses:\s*(\S+)(.*)$", text)
            self.assertTrue(used or name in ACTIONS, name)
            for action, rest in used:
                if action.startswith("./"):
                    continue
                self.assertRegex(action, r"\A[\w.-]+/[\w./-]+@[0-9a-f]{40}\Z", f"{name}: {action}")
                self.assertRegex(rest, r"# v\d+\.\d+\.\d+", f"{name}: {action} names its version beside the commit")

    def test_no_expression_is_ever_part_of_a_shell_script(self):
        """Values reach a script through `env:`, which a shell reads as data."""
        for name, text in {**FILES, **ACTIONS}.items():
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
            ("pages.yml", "build"): {"contents: read", "issues: read", "actions: read"},
            ("pages.yml", "deploy"): {"pages: write", "id-token: write"},
            ("release-build.yml", "build"): {"contents: read"},
            ("release-build.yml", "publish"): {"contents: write"},
        }
        for (name, job), wanted in expected.items():
            body = jobs(FILES[name])[job]
            block = re.search(r"(?m)^    permissions:\n((?:      .*\n)+)", body)
            self.assertIsNotNone(block, f"{name} {job}")
            found = {re.sub(r"\s*#.*", "", line).strip() for line in block.group(1).splitlines()}
            self.assertEqual(found, wanted, f"{name} {job}")
        for name in ("checks.yml", "full-release.yml"):
            for job, body in jobs(FILES[name]).items():
                self.assertNotIn("permissions:", body, f"{name} {job} reads only")
        # No job but the ones above can write: every `write` in a workflow is in that table.
        granted = {(name, job) for (name, job), wanted in expected.items() if any("write" in w for w in wanted)}
        for name, text in FILES.items():
            for job, body in jobs(text).items():
                if re.search(r"(?m)^\s+[a-z-]+: write\b", body):
                    self.assertIn((name, job), granted, f"{name} {job}")

    def test_no_checkout_leaves_a_token_on_disk(self):
        for name, text in FILES.items():
            self.assertEqual(text.count("actions/checkout@"), text.count("persist-credentials: false"), name)

    def test_every_workflow_says_what_runs_at_the_same_time(self):
        for name, text in FILES.items():
            self.assertIn("concurrency:", text, name)
            self.assertRegex(text, r"timeout-minutes: \d+", name)
        for name in ("intake.yml", "sync.yml", "pages.yml", "release-build.yml"):
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
        # A tag `patched-…` starts one workflow, which builds and publishes the release.
        self.assertEqual([name for name, text in FILES.items() if "patched-" in text.split("\njobs:\n")[0]],
                         ["release-build.yml"])
        self.assertIn('tags: ["patched-*"]', triggers("release-build.yml"))
        self.assertEqual([name for name, text in FILES.items() if "gh release create" in text], ["release-build.yml"])
        self.assertIn("pull_request:", triggers("checks.yml"))
        # Nothing is defined twice: what the checks run on every pull request, no other workflow runs.
        for name in ("full-release.yml", "release-build.yml", "pages.yml"):
            for command in ("community.py check", "-s community/tests", "ruff", "uv run pytest", "check_integration_receipt"):
                self.assertNotIn(command, FILES[name], f"{name}: {command} belongs to checks.yml")

    def test_a_deploy_needs_the_issues_and_a_checked_site(self):
        build = jobs(FILES["pages.yml"])["build"]
        self.assertIn("--require-issues", build)
        # The build says which repository builds it: a fork's copy then says that it is a preview.
        self.assertIn('--built-by "$GITHUB_REPOSITORY"', build)
        # Only a run on the default branch deploys, in this repository and in a fork of it.
        text = FILES["pages.yml"]
        on_default = ("if: github.event_name == 'schedule' || "
                      "github.ref == format('refs/heads/{0}', github.event.repository.default_branch)")
        self.assertEqual(text.count(on_default), 2, "the hand-over and the deploy job")
        self.assertEqual(len(re.findall(r"(?m)^\s+if: ", text)), 2)
        self.assertNotIn("refs/heads/main", text)
        self.assertLess(build.index("scripts/check_site.py"), build.index("upload-pages-artifact"))

    def test_the_release_build_keeps_what_it_printed_and_the_site_may_read_it(self):
        """The one command runs inside the wrapper that records its lines; the transcript is set
        beside the results before the check of what is kept; the site's build reads the record of
        the last run from its own repository, with a token that reads and writes nothing else."""
        build = jobs(FILES["release-build.yml"])["build"]
        wrapped = next(block for block in run_blocks(build) if 'scripts/build_release.py "$@"' in block)
        self.assertRegex(re.sub(r"\s+", " ", wrapped.replace("\\\n", " ")),
                         r'transcript\.py --out "\$RUNNER_TEMP/transcript\.json" -- uv run .* scripts/build_release\.py "\$@"')
        # Started with the runner's own Python: `uv run` would print its own lines first, and the
        # transcript would then not hold everything the step printed.
        self.assertEqual(wrapped.count("transcript.py"), 1)
        self.assertIn("          python3 scripts/release_build/transcript.py \\\n            --out", wrapped)
        keep = build.index('--keep "$RUNNER_TEMP/transcript.json" --into "$RUNNER_TEMP/release-run/results"')
        self.assertLess(build.index("transcript.py \\\n            --out"), keep)
        self.assertLess(keep, build.index('--check "$RUNNER_TEMP/release-run/results"'))
        self.assertLess(keep, build.index("uses: actions/upload-artifact@"))
        self.assertIn("schedule:", FILES["release-build.yml"].split("\njobs:\n")[0])
        publish = jobs(FILES["release-build.yml"])["publish"]
        self.assertNotIn("transcript", publish, "a release holds the manifest and nothing else")
        self.assertTrue((ROOT / "scripts/last_run.py").is_file())

    def test_a_release_is_checked_by_the_gate_before_it_is_published(self):
        """The job that publishes is the only one that can write, and it publishes what
        `release_manifest.py --verify --release` let through. What the manifest may hold is
        tested with the script; what the workflow uploads, beside the patch tool."""
        text = FILES["release-build.yml"]
        build, publish = jobs(text)["build"], jobs(text)["publish"]
        self.assertIn("git merge-base --is-ancestor", build)
        self.assertNotIn("gh release create", build)
        self.assertIn("needs: build", publish)
        verify = next(block for block in run_blocks(publish) if "--verify" in block)
        self.assertIn("python3 -I scripts/release_build/release_manifest.py", verify)
        self.assertIn("--release", verify)
        self.assertLess(publish.index("--verify"), publish.index("gh release create"))
        self.assertTrue((ROOT / "scripts/release_build/release_manifest.py").is_file())
        self.assertFalse((ROOT / "scripts/release_manifest.py").exists(), "a manifest is written in one place")


def commands(text):
    """The commands of a text, one per line: continuation lines joined, spaces single, the
    runner's scratch folder written as the folder CONTRIBUTING.md uses on a developer's machine,
    and without the variables set in front of a command (a workflow sets them under `env:`)."""
    text = re.sub(r"\\\n\s*", " ", text).replace('"$RUNNER_TEMP/', '"output/')
    found = []
    for line in text.splitlines():
        line = re.sub(r'"(output/[\w./-]+)"', r"\1", re.sub(r"\s+", " ", line.strip()))
        line = re.sub(r"^(?:[A-Z][A-Z0-9_]*=\S+ )+(?=\S)", "", line)
        if line and not line.startswith("#"):
            found.append(line)
    return found


class LocalCommandsTests(unittest.TestCase):
    """CONTRIBUTING.md is the one place that says how to run every check on your own machine,
    and the workflows run exactly those commands."""

    @classmethod
    def setUpClass(cls):
        text = (ROOT / "CONTRIBUTING.md").read_text()
        cls.local = [line for block in re.findall(r"(?ms)^```sh\n(.*?)^```", text) for line in commands(block)]

    def test_every_command_of_the_checks_is_in_contributing(self):
        ran = [line for block in run_blocks(FILES["checks.yml"]) for line in commands(block)]
        self.assertGreaterEqual(len(ran), 13)
        for line in ran:
            self.assertIn(line, self.local, "checks.yml runs a command CONTRIBUTING.md does not list")

    def test_every_command_on_the_made_up_release_is_in_contributing(self):
        job = jobs(FILES["full-release.yml"])["made-up-release"]
        ran = [line for block in run_blocks(job) for line in commands(block)]
        self.assertGreaterEqual(len(ran), 5)
        for line in ran:
            self.assertIn(line, self.local, "full-release.yml runs a command CONTRIBUTING.md does not list")
        # The variables the workflow sets for the first step stand in front of the same command.
        told = re.sub(r"\\\n\s*", " ", (ROOT / "CONTRIBUTING.md").read_text())
        (local,) = [line for line in told.splitlines() if "-p test_whole_path.py" in line]
        step = job.split("-p test_whole_path.py")[0].rsplit("- name:", 1)[1]
        for name in re.findall(r"(?m)^\s+(RELEASE_BUILD_\w+):", step):
            self.assertIn(f"{name}=", local.split("uv run")[0], name)
        self.assertEqual(len(re.findall(r"RELEASE_BUILD_\w+=", told)), 3, "set for that one command, not exported")

    def test_the_commands_on_the_full_release_are_in_contributing(self):
        """These take arguments from the workflow, so the names of the commands are compared."""
        told = "\n".join(self.local)
        for wanted in ("uv run --no-sync bafu-fixes run latest", "--strict --summary", "scripts/check_patched_release.py",
                       "scripts/full_release_table.py", "scripts/build_release.py release latest"):
            self.assertIn(wanted, told)
        used = "\n".join([FILES["full-release.yml"], FILES["release-build.yml"], *ACTIONS.values()])
        for wanted in ("bafu-fixes run latest", "scripts/check_patched_release.py", "scripts/full_release_table.py",
                       'scripts/build_release.py "$@"'):
            self.assertIn(wanted, used)

    def test_no_check_is_listed_that_no_workflow_runs(self):
        ran = set()
        for text in [*FILES.values(), *ACTIONS.values()]:
            ran.update(line for block in run_blocks(text) for line in commands(block))
        section = (ROOT / "CONTRIBUTING.md").read_text().split("## Check a change", 1)[1].split("\n## ", 1)[0]
        listed = [line for block in re.findall(r"(?ms)^```sh\n(.*?)^```", section) for line in commands(block)]
        self.assertGreaterEqual(len(listed), 18)
        # What a person does around the checks, and the three commands whose arguments differ.
        own = ("uv run --no-sync bafu-fixes run latest output/patched",
               "uv run --no-sync python scripts/check_patched_release.py output/patched",
               "uv run --no-sync python scripts/full_release_table.py output/summary.json",
               "uv run --no-project --python 3.12 python scripts/build_release.py release latest output/release-run")
        for line in listed:
            if not line.startswith(own):
                self.assertIn(line, ran, "CONTRIBUTING.md lists a check that no workflow runs")


if __name__ == "__main__":
    unittest.main()
