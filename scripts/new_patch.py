"""Start a new community patch: its module and its test, with the next free number.

    uv run python scripts/new_patch.py storage-pump-wind --finding F14
    uv run python scripts/new_patch.py pad-something --no-finding --author "Jane Doe"

The patch is registered by being in `src/bafu_community_fixes/patches/`; there is no
list to add it to. The finding must have a record (`community/findings/`), and the places
where it is discussed become the patch's references. Both new files fail until they are
written, so a patch can't be merged as a template.

When the patch is written, `python3 scripts/patches_snapshot.py` writes
`community/patches.json` from the registry: the site reads the patches from that file, and
the check of the records fails while the file differs from the registry.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import community  # noqa: E402  the finding records; standard library only

ROOT = Path(__file__).resolve().parents[1]
PATCHES = Path("src/bafu_community_fixes/patches")
TESTS = Path("tests")
NAME = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
FINDING = re.compile(r"F[1-9]\d*")

PATCH = '''"""TODO: what this patch does, in a few words."""

from bafu_community_fixes.registry import patch
from bafu_community_fixes.xml import Database

ID = "{id}"


@patch(
    ID,
    findings={findings},
    authored_by={author},
    # authorised_by: added by whoever approves the patch for the community release
    references={references},
)
def {function}(db: Database) -> None:
    """TODO: one line saying what the patch does, for `bafu-fixes list` and the report.

    TODO: why the change is needed, for data users. Say who confirmed it, if anyone.

    If a dataset isn't as expected, the patch stops: the data has changed, and the patch
    needs a review. Datasets that aren't in the input are skipped.
    """
    raise NotImplementedError(f"Patch {{ID}} isn't written yet")
'''

TEST = """import pytest

from bafu_community_fixes.patches.{module} import ID
from bafu_community_fixes.pipeline import apply_patch
from bafu_community_fixes.registry import available_patches


def _patch():
    return next(p for p in available_patches() if p.id == ID)


def test_{function}(db, dataset):
    # TODO: make the fixture dataset look like the data the patch corrects, for example
    #   dataset.number = 123456
    #   dataset.exchanges[2].location = "OCE"
    (changed,) = apply_patch(db, _patch())
    assert changed is dataset
    # TODO: assert the corrected value


def test_{function}_stops_on_unexpected_data(db, dataset):
    # TODO: the same dataset, but with a value the patch doesn't expect
    with pytest.raises(ValueError, match="expected"):
        apply_patch(db, _patch())
"""


class ScaffoldError(Exception):
    pass


def next_number(root: Path) -> int:
    numbers = [int(p.name[1:5]) for p in (root / PATCHES).glob("p[0-9][0-9][0-9][0-9]_*.py")]
    return max(numbers, default=0) + 1


def finding_links(root: Path, finding: str) -> list[str]:
    """Where a finding is discussed: its issue here, then the threads elsewhere.

    Stops if the finding has no record.
    """
    record = root / community.record_path(finding)
    if not record.is_file():
        raise ScaffoldError(f"There is no record of finding {finding} ({record.relative_to(root)})")
    repository = json.loads((root / "site" / "config.json").read_text(encoding="utf-8"))[
        "repository"
    ]
    return community.discussion_links(json.loads(record.read_text(encoding="utf-8")), repository)


def _tuple(values: list[str]) -> str:
    if not values:
        return "()"
    return "(\n" + "".join(f"        {json.dumps(v)},\n" for v in values) + "    )"


def scaffold(root: Path, name: str, finding: str | None, author: str) -> tuple[Path, Path]:
    """Write the patch module and its test; return their paths."""
    if not NAME.fullmatch(name):
        raise ScaffoldError(f"The name must look like 'storage-pump-wind', not {name!r}")
    if finding is not None and not FINDING.fullmatch(finding):
        raise ScaffoldError(f"A finding id looks like 'F14', not {finding!r}")
    references = finding_links(root, finding) if finding else []
    number = next_number(root)
    function = name.replace("-", "_")
    module = f"p{number:04d}_{function}"
    values = {
        "id": f"{number:04d}-{name}",
        "module": module,
        "function": function,
        "findings": f'("{finding}",)' if finding else "()",
        "author": json.dumps(author),
        "references": _tuple(references),
    }
    patch_file = root / PATCHES / f"{module}.py"
    test_file = root / TESTS / f"test_{module}.py"
    for path in (patch_file, test_file):
        if path.exists():
            raise ScaffoldError(f"{path} already exists")
    patch_file.write_text(PATCH.format(**values), encoding="utf-8")
    test_file.write_text(TEST.format(**values), encoding="utf-8")
    return patch_file, test_file


def _git_user() -> str | None:
    try:
        result = subprocess.run(
            ["git", "config", "user.name"], cwd=ROOT, capture_output=True, text=True
        )
    except OSError:
        return None
    return result.stdout.strip() or None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("name", help="Short name in lower case with dashes: storage-pump-wind")
    finding = parser.add_mutually_exclusive_group(required=True)
    finding.add_argument("--finding", metavar="ID", help="The finding the patch answers: F14")
    finding.add_argument(
        "--no-finding", action="store_true", help="The patch answers no recorded finding"
    )
    parser.add_argument("--author", help="Who writes the patch (default: your git user name)")
    args = parser.parse_args(argv)
    author = args.author or _git_user()
    if not author:
        parser.error("--author is needed: git has no user.name here")
    try:
        patch_file, test_file = scaffold(ROOT, args.name, args.finding, author)
    except ScaffoldError as e:
        sys.exit(str(e))
    print(f"Created {patch_file.relative_to(ROOT)}")
    print(f"Created {test_file.relative_to(ROOT)}")
    print(
        "Next: write the patch and its docstring, complete the test, then run\n"
        "  python3 scripts/patches_snapshot.py\n"
        "  uv run pytest && uv run ruff check && uv run ruff format --check\n"
        "  uv run bafu-fixes run latest output/ --strict --summary output/summary.json\n"
        "  uv run python scripts/full_release_table.py output/summary.json --check\n"
        "Open a pull request with the two files and community/patches.json, which the first\n"
        "command writes from the registry. The full release run in its checks shows what\n"
        "the patch changes. Leave `authorised_by` out; the person who approves the patch\n"
        "for the community release adds it."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
