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
    python3 scripts/release_build/public_summary.py --check PATH [PATH ...] [--names-from SUMMARY]

The first writes the public form of each JSON file (or of every `*.json` in a folder) into
FOLDER and checks what it wrote. `--check` fails, with status 1, if a JSON file below a path
holds a `confirmed_by` that is not in the public form. With `--names-from` and the run's own
summary, it also searches every file below the paths, of any kind, and every member of a zip
or bzip2 file among them, for who that summary says confirmed: a file written from the
summary (the record of changes inside an export) may carry a name outside any JSON field.
Standard library only, and it runs on the Python a runner has.
"""

import argparse
import bz2
import contextlib
import copy
import html
import json
import re
import sys
import zipfile
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


_NAME = r"[A-ZÀ-Þ][\w'’.-]*(?: [A-ZÀ-Þ][\w'’.-]*)+"


def confirmers(data, provider: str = PROVIDER) -> set[str]:
    """What a text would repeat if it named who confirmed: every `confirmed_by` of `data`
    that is not in the public form, and each run of two or more capitalised words in it,
    which is how a person's name is written. The provider's own name and a date are not
    among them. For text that has no fields to rewrite (`transcript.py`)."""
    found: set[str] = set()

    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == FIELD and isinstance(item, str) and not is_public(item, provider):
                    found.add(item)
                    found.update(re.findall(_NAME, re.sub(_DATE, " ", item)))
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(data)
    return {word for word in found if word.strip() and word != provider}


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


def contents(file: Path):
    """(where, bytes) of a file, and of each member if it is a zip or bzip2 file."""
    if zipfile.is_zipfile(file):
        with zipfile.ZipFile(file) as archive:
            for member in archive.namelist():
                yield f"{file.name}:{member}", archive.read(member)
        return
    data = file.read_bytes()
    if data[:3] == b"BZh":
        with contextlib.suppress(OSError, ValueError):  # not bzip2 after all: searched as it is
            data = bz2.decompress(data)
    yield file.name, data


def mentions(paths, names) -> list[str]:
    """Every file below `paths`, or member of one, that holds one of `names`: as written, as
    JSON writes it, or as HTML escapes it."""
    needles = set()
    for name in names:
        needles |= {name.encode(), json.dumps(name)[1:-1].encode(), html.escape(name).encode()}
    files = []
    for path in map(Path, paths):
        if path.is_dir():
            files += sorted(p for p in path.rglob("*") if p.is_file())
        elif path.is_file():
            files.append(path)
    return [
        where
        for file in files
        for where, data in contents(file)
        if any(needle in data for needle in needles)
    ]


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
    parser.add_argument(
        "--names-from",
        type=Path,
        metavar="SUMMARY",
        help="The run's own summary: also search every file for who it says confirmed",
    )
    args = parser.parse_args(argv)
    if args.check == bool(args.out):
        parser.error("give --out FOLDER to write the public form, or --check to check files")
    checked = args.paths
    if args.out:
        written = write_public(args.paths, args.out, args.provider)
        print(f"Wrote the public form of {len(written)} file(s) to {args.out}")
        checked = [args.out]
    found = check(checked, args.provider)
    if args.names_from and args.names_from.is_file():
        names = confirmers(json.loads(args.names_from.read_text(encoding="utf-8")), args.provider)
        found += [f"{place}: names who confirmed" for place in mentions(checked, names)]
    for place in found:
        print(f"names who confirmed otherwise than as {args.provider} and a date: {place}")
    return int(bool(found))


if __name__ == "__main__":
    sys.exit(main())
