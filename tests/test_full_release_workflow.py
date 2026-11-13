"""Rules the Full release workflow has to keep (`.github/workflows/full-release.yml`)."""

import re
from pathlib import Path

from bafu_community_fixes import patches

REPO = Path(__file__).parents[1]
WORKFLOW = (REPO / ".github" / "workflows" / "full-release.yml").read_text()


def test_actions_are_pinned_by_commit():
    uses = re.findall(r"uses: (\S+)", WORKFLOW)
    assert len(uses) == 4
    assert all(re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", action) for action in uses)


def test_token_can_only_read():
    assert "\npermissions:\n  contents: read\n\n" in WORKFLOW
    assert WORKFLOW.count("permissions:") == 1  # no job asks for more
    assert "pull_request_target" not in WORKFLOW
    assert "secrets." not in WORKFLOW


def test_only_the_summaries_are_uploaded():
    (upload,) = re.findall(r"uses: actions/upload-artifact@.*\n((?: {8,}.*\n)+)", WORKFLOW)
    assert re.findall(r"\bpath: (.*)", upload) == ["${{ runner.temp }}/summaries/"]
    # Only the two summaries are ever written to that folder
    assert set(re.findall(r"summaries/([\w.-]+)", WORKFLOW)) == {"head.json", "base.json"}
    assert "--report" not in WORKFLOW  # the HTML report quotes the data


def test_a_new_patch_needs_no_change_to_the_workflow():
    folder = Path(patches.__file__).parent.relative_to(REPO)
    assert folder.as_posix() == "src/bafu_community_fixes/patches"
    assert WORKFLOW.count('- "src/bafu_community_fixes/**"') == 2  # pull requests and main
    assert not re.search(r"\b\d{4}-[a-z]", WORKFLOW)  # and it names no patch
