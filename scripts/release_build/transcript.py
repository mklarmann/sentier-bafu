"""The transcript of a release run: the shared wrapper, and the check of its lines.

    python3 scripts/release_build/transcript.py --out FILE -- COMMAND [ARGUMENT ...]
    python3 scripts/release_build/transcript.py --keep FILE --into FOLDER [--summary FILE]

The first is `scripts/runrecord/transcript.py`, which says what it does: it runs COMMAND,
passes every line on and writes the lines, with the time of each, to FILE.

The second copies a transcript into the folder of the files that may leave the machine. With
the run summary of the patch tool it first checks that no line names who confirmed a problem
for the provider (`public_summary.py` says why). A transcript is never edited: one that names
somebody is not copied, and the status is 1.

Standard library only, and it runs on the Python a runner has.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runrecord import transcript as shared  # noqa: E402
from runrecord.transcript import (  # noqa: E402,F401 - what the build and its tests use
    FORMAT,
    FORMATS,
    MAX_LINE,
    MAX_LINES,
    record,
    sha256_of,
    shape_errors,
)

try:
    from release_build import public_summary
except ImportError:  # run as a script, from its own folder
    import public_summary

NAMES = "names who confirmed for the provider"


def named(data, summary) -> list[str]:
    """The lines of a transcript that repeat who confirmed for the provider, by number."""
    return shared.holding(data, public_summary.confirmers(summary))


def keep(source: Path, into: Path, summary: Path | None) -> list[str]:
    """Copy a transcript to `into`; return why it was not copied, if it was not."""
    words = ()
    if summary is not None and summary.is_file():
        try:
            words = public_summary.confirmers(json.loads(summary.read_text(encoding="utf-8")))
        except ValueError:
            # what can't be read can't be shown to name nobody
            data, problems = shared.read(source)
            problems = problems or ["the run summary can't be read, so it is not checked"]
            return [f"{source.name}: {problem}" for problem in problems]
    return shared.keep(source, into, words, NAMES)


def main(argv: list[str] | None = None) -> int:
    argv, command = shared.split(argv)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, help="Write the transcript of COMMAND here")
    parser.add_argument("--keep", type=Path, metavar="FILE", help="A transcript to set aside")
    parser.add_argument("--into", type=Path, metavar="FOLDER", help="Where --keep copies it")
    parser.add_argument("--summary", type=Path, help="The run summary whose names --keep checks")
    args = parser.parse_args(argv)
    if args.out and command and not args.keep:
        return record(command, args.out)
    if args.keep and args.into and not command:
        problems = keep(args.keep, args.into, args.summary)
        for problem in problems:
            print(f"not kept: {problem}")
        if not problems:
            print(f"Kept the transcript in {args.into}")
        return int(bool(problems))
    parser.error("give --out FILE -- COMMAND to record, or --keep FILE --into FOLDER to set aside")


if __name__ == "__main__":
    sys.exit(main())
