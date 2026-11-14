"""Check a patched copy as it is on disk: every file against the EcoSpold 1 schema.

    uv run python scripts/check_patched_release.py output/ --summary output/summary.json

`bafu-fixes run --strict` checks the models before it writes them. This reads the
files it wrote, so it covers the writing too. With `--summary`, the files must also be
the ones the summary describes: the same number of files, with the same fingerprint.
"""

import argparse
import json
import sys
from pathlib import Path

from lxml import etree

from bafu_community_fixes.compliance import schema
from bafu_community_fixes.summary import fingerprint
from bafu_community_fixes.xml import find_files

MAX_ERRORS_SHOWN = 20


def check(folder: Path, summary: Path | None = None) -> tuple[int, list[str]]:
    """The number of files checked, and what is wrong with them."""
    root, files = find_files(folder)
    xsd, errors = schema(), []
    for path in files:
        if not xsd.validate(etree.parse(str(path))):
            errors.extend(f"{path.name}: line {e.line}: {e.message}" for e in xsd.error_log)
    if summary is not None:
        output = json.loads(summary.read_text(encoding="utf-8"))["output"]
        if output is None:
            errors.append(f"{summary.name} describes a run that wrote nothing")
        elif (len(files), fingerprint(root, files)[0]) != (output["files"], output["fingerprint"]):
            errors.append(f"The files in {folder} are not the ones {summary.name} describes")
    return len(files), errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path, help="Folder with the patched copy")
    parser.add_argument("--summary", type=Path, help="The run's summary, to compare with")
    args = parser.parse_args(argv)
    count, errors = check(args.folder, args.summary)
    for error in errors[:MAX_ERRORS_SHOWN]:
        print(error)
    if len(errors) > MAX_ERRORS_SHOWN:
        print(f"... and {len(errors) - MAX_ERRORS_SHOWN} more")
    if errors:
        print(f"{count:,} files checked: not a valid patched copy")
        return 1
    described = " and are the ones the summary describes" if args.summary else ""
    print(f"{count:,} files checked: all are valid EcoSpold 1{described}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
