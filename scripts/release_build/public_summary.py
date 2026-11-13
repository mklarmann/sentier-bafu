"""What of a run summary may leave the machine: no person but an author and an authoriser.

A run summary (`bafu-fixes run --summary`) repeats, for each step, who confirmed the problem
or the correction for the provider, as the patch says it: a person's name, the organisation,
how and when. A patch may say that. What a CI job uploads as an artifact or writes to its
job summary is public, and there the only persons named are the author of a patch and who
authorised it.

So every summary passes through `public` before it is uploaded or read for a job summary:
`confirmed_by` becomes the provider's organisation and the date, `BAFU (12 October 2026)`.
Nothing else of the field survives. The date is the only part that is copied, and only if
it has the shape of a date.

    python3 scripts/release_build/public_summary.py IN [IN ...] --out FOLDER
    python3 scripts/release_build/public_summary.py --check PATH [PATH ...]

The first writes the public form of each JSON file (or of every `*.json` in a folder) into
FOLDER and checks what it wrote. `--check` fails, with status 1, if a JSON file below a path
holds a `confirmed_by` that is not in the public form. Standard library only, and it runs on
the Python a runner has.
"""

import argparse
import copy
import json
import re
import sys
from pathlib import Path

PROVIDER = "BAFU"
FIELD = "confirmed_by"
_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_DATE = rf"\d{{1,2}} (?:{_MONTHS}) \d{{4}}|\d{{4}}-\d{{2}}-\d{{2}}"


def confirmed(value, provider: str = PROVIDER) -> str | None:
    """Who confirmed, for the public: the organisation and the date, never a person."""
    if not value:
        return None
    date = re.search(rf"\b({_DATE})\b", str(value))
    return f"{provider} ({date.group(1)})" if date else provider


def is_public(value, provider: str = PROVIDER) -> bool:
    """Whether a `confirmed_by` value is one `confirmed` writes."""
    if value is None or value == provider:
        return True
    return isinstance(value, str) and bool(
        re.fullmatch(rf"{re.escape(provider)} \((?:{_DATE})\)", value)
    )


def public(data, provider: str = PROVIDER):
    """A copy of a summary, or of anything read from JSON, with every `confirmed_by`,
    wherever it is, in its public form."""
    data = copy.deepcopy(data)

    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == FIELD:
                    value[key] = confirmed(item, provider)
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(data)
    return data


def named(data, provider: str = PROVIDER, where: str = "") -> list[str]:
    """Where `data` holds a `confirmed_by` that is not in the public form."""
    found = []
    if isinstance(data, dict):
        for key, item in data.items():
            path = f"{where}.{key}" if where else key
            if key == FIELD:
                found += [] if is_public(item, provider) else [path]
            else:
                found += named(item, provider, path)
    elif isinstance(data, list):
        for number, item in enumerate(data):
            found += named(item, provider, f"{where}[{number}]")
    return found


def json_files(paths) -> list[Path]:
    files = []
    for path in map(Path, paths):
        files += sorted(path.rglob("*.json")) if path.is_dir() else [path] * path.is_file()
    return files


def check(paths, provider: str = PROVIDER) -> list[str]:
    """Every place below `paths` where a JSON file names who confirmed otherwise than in
    the public form. A file that is not JSON is not a summary and is left alone."""
    found = []
    for file in json_files(paths):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except ValueError:
            continue
        found += [f"{file.name}: {place}" for place in named(data, provider)]
    return found


def write_public(paths, out: Path, provider: str = PROVIDER) -> list[Path]:
    """The public form of each JSON file of `paths`, written into `out` under its name."""
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for file in json_files(paths):
        data = public(json.loads(file.read_text(encoding="utf-8")), provider)
        target = out / file.name
        target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(target)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", type=Path, help="JSON files, or folders of them")
    parser.add_argument("--out", type=Path, help="Write the public form of each file here")
    parser.add_argument("--check", action="store_true", help="Only check; write nothing")
    parser.add_argument("--provider", default=PROVIDER, help=f"Default: {PROVIDER}")
    args = parser.parse_args(argv)
    if args.check == bool(args.out):
        parser.error("give --out FOLDER to write the public form, or --check to check files")
    checked = args.paths
    if args.out:
        written = write_public(args.paths, args.out, args.provider)
        print(f"Wrote the public form of {len(written)} file(s) to {args.out}")
        checked = [args.out]
    found = check(checked, args.provider)
    for place in found:
        print(f"names who confirmed otherwise than as {args.provider} and a date: {place}")
    return int(bool(found))


if __name__ == "__main__":
    sys.exit(main())
