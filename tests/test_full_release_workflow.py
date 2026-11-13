"""Rules the workflows for proposed patches and for release builds have to keep.

`.github/workflows/full-release.yml` runs on pull requests, `release-build.yml` on main,
on request and on a tag; both get BAFU's release through one composite action.
"""

import re
from pathlib import Path

from bafu_community_fixes import patches

REPO = Path(__file__).parents[1]
GITHUB = REPO / ".github"
PROPOSED = (GITHUB / "workflows" / "full-release.yml").read_text()
BUILD = (GITHUB / "workflows" / "release-build.yml").read_text()
ACTIONS = {path.parent.name: path.read_text() for path in GITHUB.glob("actions/*/action.yml")}
EVERYTHING = [PROPOSED, BUILD, *ACTIONS.values()]


def test_actions_are_pinned_by_commit_or_are_this_repositorys_own():
    uses = [action for text in EVERYTHING for action in re.findall(r"uses: (\S+)", text)]
    assert len(uses) == 14
    own = [action for action in uses if action.startswith("./")]
    assert sorted(set(own)) == ["./.github/actions/bafu-release", "./.github/actions/patch-run"]
    for action in set(uses) - set(own):
        assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", action), action
    # one commit per action, wherever it is used
    pinned = {action.split("@")[0]: action for action in uses if "@" in action}
    assert len(pinned) == len({action for action in uses if "@" in action})


def test_tokens_can_only_read_except_in_the_job_that_publishes():
    assert "\npermissions:\n  contents: read\n\n" in PROPOSED
    assert PROPOSED.count("permissions:") == 1  # no job asks for more
    assert "\npermissions: {}\n" in BUILD  # nothing, unless a job says so
    build, publish = BUILD.split("\njobs:\n")[1].split("\n  publish:\n")
    jobs = {"build": build, "publish": publish}
    assert build.startswith("  build:\n")
    assert "permissions:\n      contents: read\n" in jobs["build"]
    assert "contents: write" not in jobs["build"]
    assert "permissions:\n      contents: write" in jobs["publish"]
    assert "if: ${{ github.ref_type == 'tag' }}" in jobs["publish"]
    for text in EVERYTHING:
        assert "pull_request_target" not in text
        assert "secrets." not in text


def test_no_expression_is_part_of_a_shell_script():
    for text in EVERYTHING:
        for script in re.findall(r"run: \|\n((?:          .*\n| {8,}.*\n|\n)+)", text):
            assert "${{" not in script, script
        for line in re.findall(r"run: (?!\|)(.*)", text):
            assert "${{" not in line, line


def test_one_composite_action_gets_the_release_for_every_job_that_reads_it():
    release = ACTIONS["bafu-release"]
    assert "key: bafu-release-${{ steps.release.outputs.sha256 }}" in release
    assert "uv sync --locked" in release
    for workflow in (PROPOSED, BUILD):
        assert workflow.count("uses: ./.github/actions/bafu-release") == 1
        assert "actions/cache@" not in workflow  # only through the composite action
        assert "CHECKSUMS" not in workflow
    assert PROPOSED.count("uses: ./.github/actions/patch-run") == 1
    patch_run = ACTIONS["patch-run"]
    assert 'bafu-fixes run latest "$PATCHED" --strict --summary "$SUMMARY"' in patch_run
    assert 'scripts/check_patched_release.py "$PATCHED" --summary "$SUMMARY"' in patch_run


def test_only_summaries_and_results_without_inventory_are_uploaded():
    (upload,) = re.findall(r"uses: actions/upload-artifact@.*\n((?: {8,}.*\n)+)", PROPOSED)
    assert re.findall(r"\bpath: (.*)", upload) == ["${{ runner.temp }}/public-summaries/"]
    # Only the two summaries are ever written, and only their public form is uploaded
    assert set(re.findall(r"/summaries/([\w.-]+)", PROPOSED)) == {"head.json", "base.json"}
    uploads = re.findall(r"uses: actions/upload-artifact@.*\n((?: {8,}.*\n)+)", BUILD)
    assert [re.findall(r"\bpath: (.*)", upload) for upload in uploads] == [
        ["${{ runner.temp }}/release-run/results/"],
        ["${{ runner.temp }}/release-run/results/manifest.json"],
    ]
    for text in EVERYTHING:
        assert "--report" not in text  # the HTML report quotes the data
        assert "exports/" not in text  # the export files stay in the run folder


def test_what_is_uploaded_or_summarised_names_nobody_who_confirmed_for_the_provider():
    """A run summary says who confirmed a problem for the provider, by name. An artifact
    and a job summary are public: they get the organisation and the date."""
    public = "scripts/release_build/public_summary.py"
    # Proposed patches: the public form is written, and that folder is what is uploaded
    written = PROPOSED.index(f'{public} \\\n            "$RUNNER_TEMP/summaries" --out')
    upload = PROPOSED.index("uses: actions/upload-artifact@")
    assert written < upload
    assert '--out "$RUNNER_TEMP/public-summaries"' in PROPOSED
    assert "path: ${{ runner.temp }}/summaries/" not in PROPOSED
    # Release build: what the run set aside is checked before either upload
    check = BUILD.index(f'{public} \\\n            --check "$RUNNER_TEMP/release-run/results"')
    uploads = [match.start() for match in re.finditer("uses: actions/upload-artifact@", BUILD)]
    assert len(uploads) == 2 and all(check < upload for upload in uploads)
    # An upload that runs after a failed step waits for that check all the same
    for text in (PROPOSED, BUILD):
        for condition in re.findall(r"if: (.*)\n +uses: actions/upload-artifact@", text):
            assert (
                "!cancelled()" not in condition or "steps.public.outcome == 'success'" in condition
            )
    # The two scripts that write a job summary read their input in the public form
    scripts = REPO / "scripts"
    for script in (scripts / "full_release_table.py", scripts / "release_build" / "job_summary.py"):
        text = script.read_text()
        assert "public_summary.public(" in text, script.name
    assert "set_aside(keep, results)" in (scripts / "build_release.py").read_text()


def test_every_upload_and_job_summary_of_the_repository_is_one_we_know():
    """A new artifact or job summary has to say whether it reads a run summary."""
    sinks = {}
    for path in sorted([*GITHUB.glob("workflows/*.yml"), *GITHUB.glob("actions/*/action.yml")]):
        text = path.read_text()
        name = path.parent.name if path.name == "action.yml" else path.name
        found = re.findall(r"uses: actions/(upload-[\w-]*artifact)@", text)
        found += ["job summary"] * text.count("$GITHUB_STEP_SUMMARY")
        if found:
            sinks[name] = sorted(found)
    assert sinks == {
        # reads run summaries: through the public form (the test above)
        "full-release.yml": ["job summary", "upload-artifact"],
        "release-build.yml": ["job summary", "upload-artifact", "upload-artifact"],
        # the site, built from the records, and the result of the issue sync: no run summary
        "pages.yml": ["upload-pages-artifact"],
        "sync.yml": ["job summary"],
    }
    for script in ("build_site.py", "sync.py"):
        text = (REPO / "scripts" / script).read_text()
        assert "release-summary" not in text and "confirmed_by" not in text, script


def test_no_record_of_the_repository_names_who_confirmed_for_the_provider():
    import sys

    sys.path.insert(0, str(REPO / "scripts"))
    from release_build import public_summary

    assert public_summary.check([REPO / "community", REPO / "site"]) == []


def test_a_release_is_one_file_and_it_is_checked_before_it_is_published():
    publish = BUILD.split("\n  publish:\n")[1]
    assert 'test "$(find "$RUNNER_TEMP/release" -type f | wc -l)" -eq 1' in publish
    verify = publish.index("release_manifest.py")
    create = publish.index("gh release create")
    assert verify < create
    assert '--verify "$RUNNER_TEMP/release/manifest.json" --release' in publish
    command = publish[create:].replace("\\\n", " ")
    assets = [word for word in command.split() if word.endswith('.json"')]
    assert assets == ['"$RUNNER_TEMP/release/manifest.json"']
    assert "--verify-tag" in command
    assert BUILD.count("gh release create") == 1 and "gh release upload" not in BUILD
    assert "gh release" not in PROPOSED
    # a tag is built from a commit of main, and only a tag reaches the job that publishes
    assert 'git merge-base --is-ancestor "$GITHUB_SHA" origin/main' in BUILD
    assert 'tags: ["patched-*"]' in BUILD


def test_each_event_runs_what_it_should():
    assert re.search(r"\non:\n  pull_request:\n    paths:\n", PROPOSED)
    assert "push:" not in PROPOSED  # main and tags are the release build's
    assert "workflow_dispatch:" in PROPOSED and "workflow_dispatch:" in BUILD
    assert "pull_request" not in BUILD.split("\njobs:\n")[0]
    assert "branches: [main]" in BUILD
    # pull request: the patch run with its comparison, and the made-up whole path
    assert '--base "$RUNNER_TEMP/summaries/base.json"' in PROPOSED
    assert "-p test_whole_path.py" in PROPOSED and "pytest export-tests" in PROPOSED
    # main, request and tag: the one command, then the summary
    assert 'set -- release latest "$RUNNER_TEMP/release-run"' in BUILD
    assert 'scripts/build_release.py "$@"' in BUILD
    # one entry point, no step of the path repeated here: its path filter and its one call
    assert BUILD.count("build_release.py") == 2
    assert '--previous "$RUNNER_TEMP/previous/manifest.json"' in BUILD


def test_a_new_patch_or_a_new_layer_needs_no_change_to_a_workflow():
    folder = Path(patches.__file__).parent.relative_to(REPO)
    assert folder.as_posix() == "src/bafu_community_fixes/patches"
    for workflow in (PROPOSED, BUILD):
        assert workflow.count('- "src/bafu_community_fixes/**"') == 1
        assert workflow.count('- "community/layers/**"') == 1
        assert not re.search(r"\b\d{4}-[a-z]", workflow)  # it names no patch
        assert not re.search(r"\bC\d{3}\b", workflow)  # and no contribution
