"""Turn run summaries (`bafu-fixes run --summary`) into a table a reviewer can read.

    python scripts/full_release_table.py head.json
    python scripts/full_release_table.py head.json --base base.json \
        --head-output head-out/ --base-output base-out/ --check

Prints Markdown: the release that was read, each step with who is behind it and how
much it changed, and a line for every step that needs a second look. With `--base`
(the summary of the revision a pull request starts from), it also says what the pull
request changes. With both output folders, it counts the files of the patched release
that differ.

`--check` makes the exit status 1 if the run isn't acceptable: it didn't complete, it
didn't read a known release, or a patch changed nothing (its target wasn't there).

Only the standard library is used, and only counts, checksums and file names are
printed, so the result can be published.
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

MAX_FILES_SHOWN = 20
MAX_FIELDS_SHOWN = 3
COUNTS = (("datasets", "Datasets"), ("exchanges", "Exchanges"), ("changes", "Values"))


def number(value: int | None) -> str:
    return "–" if value is None else f"{value:,}"


def short(checksum: str | None) -> str:
    return f"`{checksum[:12]}…`" if checksum else "not available"


def megabytes(size: int) -> str:
    return f"{size / 1e6:,.1f} MB"


def cell(text: object) -> str:
    """Text that is safe in a Markdown table cell."""
    return str(text).replace("|", "\\|").replace("\n", " ")


def load(path: Path | None) -> dict | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def patches(summary: dict) -> list[dict]:
    return [step for step in summary["steps"] if step["kind"] == "patch"]


def release_name(summary: dict) -> str:
    url = summary["release"]["url"]
    return f"`{Path(url).name.removesuffix('.zip')}`" if url else "an unknown input"


def problems(summary: dict) -> list[str]:
    """Why the run isn't acceptable, if it isn't."""
    found = []
    stopped = [step for step in summary["steps"] if step.get("error")]
    for step in stopped:
        found.append(
            f"`{step['id']}` stopped the run; its target was not as expected, or it left "
            f"invalid data: {step['error']}"
        )
    if summary["status"] != "completed" and not stopped:
        found.append(f"The run {summary['status']}: {summary['error'] or 'no message'}")
    if summary["release"]["url"] is None and summary["release"]["fingerprint"]:
        found.append(
            "The input isn't a release this revision knows (input fingerprint "
            f"{short(summary['release']['fingerprint'])}). If this pull request changes the "
            "release, add its fingerprint to `download.FINGERPRINTS`."
        )
    if summary["status"] == "completed":
        for step in patches(summary):
            if not step["datasets"]:
                found.append(
                    f"`{step['id']}` changed nothing on the full release: its target wasn't "
                    "found. Either the patch doesn't match the data, or the release already "
                    "has the correction and the patch can be retired."
                )
    return found


def warnings(summary: dict) -> list[str]:
    """What a reviewer should look at, without it being an error."""
    return [
        f"`{step['id']}` is not yet authorised, and changed {number(step['datasets'])} "
        f"dataset(s). It was written by {step['authored_by']}."
        for step in summary["steps"]
        if step["authorised_by"] is None and step["datasets"]
    ]


def fields(step: dict) -> str:
    """The fields a step changed, most changed first, by the end of their XML path."""
    names = sorted(step.get("fields", {}).items(), key=lambda item: (-item[1], item[0]))
    shown = [
        f"`{'/'.join(name.split('/')[-2:])}` ({number(count)})"
        for name, count in names[:MAX_FIELDS_SHOWN]
    ]
    if len(names) > MAX_FIELDS_SHOWN:
        shown.append(f"and {len(names) - MAX_FIELDS_SHOWN} more")
    return ", ".join(shown) or "–"


def step_table(summary: dict) -> list[str]:
    lines = [
        "| Step | Kind | Findings | Written by | Authorised by | Datasets | Exchanges | Values "
        "| Fields changed |",
        "|---|---|---|---|---|---:|---:|---:|---|",
    ]
    for step in summary["steps"]:
        if step.get("error"):
            counts = ["stopped", "", ""]
        else:
            counts = [number(step.get(key)) for key, _ in COUNTS]
        row = [
            f"`{step['id']}`",
            step["kind"],
            ", ".join(step.get("findings") or []) or "–",
            step["authored_by"],
            step["authorised_by"] or "**not yet authorised**",
            *counts,
            fields(step),
        ]
        lines.append("| " + " | ".join(cell(value) for value in row) + " |")
    return lines


def delta(old: int | None, new: int | None) -> str:
    if old is None or new is None:
        return f"{number(old)} → {number(new)}"
    return f"{number(old)} → {number(new)} ({new - old:+,})"


def step_changes(base: dict, head: dict) -> list[str]:
    """Steps that are new, gone, or whose counts differ between two summaries."""
    old = {step["id"]: step for step in base["steps"]}
    new = {step["id"]: step for step in head["steps"]}
    rows = []
    for id in [*new, *(i for i in old if i not in new)]:
        before, after = old.get(id), new.get(id)
        if before is None:
            label = "new"
            counts = [f"+{number(after.get(key))}" for key, _ in COUNTS]
        elif after is None:
            label = "removed"
            counts = [f"−{number(before.get(key))}" for key, _ in COUNTS]
        elif any(before.get(key) != after.get(key) for key, _ in COUNTS):
            label = "changed"
            counts = [
                delta(before.get(key), after.get(key))
                if before.get(key) != after.get(key)
                else number(after.get(key))
                for key, _ in COUNTS
            ]
        else:
            continue
        rows.append(f"| `{id}` | {label} | " + " | ".join(counts) + " |")
    if not rows:
        return ["No step is new or removed, and every step changes as much as before."]
    return [
        "| Step | | " + " | ".join(title for _, title in COUNTS) + " |",
        "|---|---|---:|---:|---:|",
        *rows,
    ]


def _checksums(folder: Path) -> dict[str, str]:
    return {
        str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


def output_changes(base: Path, head: Path) -> list[str]:
    """How many files of the patched release differ between two output folders."""
    old, new = _checksums(base), _checksums(head)
    differ = sorted(name for name in old.keys() & new.keys() if old[name] != new[name])
    added, removed = sorted(new.keys() - old.keys()), sorted(old.keys() - new.keys())
    lines = [
        f"- Files of the patched release that differ: **{number(len(differ))}** of "
        f"{number(len(new))}; new: {number(len(added))}; no longer written: "
        f"{number(len(removed))}."
    ]
    for label, names in (("Differ", differ), ("New", added), ("No longer written", removed)):
        if names:
            shown = ", ".join(f"`{name}`" for name in names[:MAX_FILES_SHOWN])
            rest = len(names) - MAX_FILES_SHOWN
            more = f", and {number(rest)} more" if rest > 0 else ""
            lines.append(f"  - {label}: {shown}{more}")
    return lines


def comparison(
    base: dict | None,
    head: dict,
    base_revision: str | None,
    base_output: Path | None,
    head_output: Path | None,
) -> list[str]:
    lines = ["### What this pull request changes", ""]
    revision = f" (`{base_revision[:12]}`)" if base_revision else ""
    if base is None:
        return [
            *lines,
            f"The base revision{revision} has no run summary, so there is nothing to compare "
            "with: it has no patch tool, or one from before `--summary`. The table below "
            "describes this revision alone.",
        ]
    lines.append(f"Compared with a run of the base revision{revision} on the same runner:")
    lines.append("")
    if base["status"] != "completed":
        lines.append(f"- The base revision's run {base['status']}: {base['error']}")
    if base["release"]["fingerprint"] != head["release"]["fingerprint"]:
        lines.append(
            f"- **The input differs.** The base revision read {release_name(base)} "
            f"({short(base['release']['fingerprint'])}), this revision "
            f"{release_name(head)} ({short(head['release']['fingerprint'])})."
        )
    if base["output"] and head["output"]:
        same = base["output"]["fingerprint"] == head["output"]["fingerprint"]
        lines.append(
            "- The patched release is **byte for byte the same** as before "
            f"({short(head['output']['fingerprint'])})."
            if same
            else "- The patched release **changes**: fingerprint "
            f"{short(base['output']['fingerprint'])} → {short(head['output']['fingerprint'])}."
        )
        if not same and base_output and head_output:
            lines += output_changes(base_output, head_output)
    lines += ["", *step_changes(base, head)]
    return lines


def render(
    head: dict,
    base: dict | None = None,
    compare: bool = False,
    head_revision: str | None = None,
    base_revision: str | None = None,
    head_output: Path | None = None,
    base_output: Path | None = None,
) -> str:
    release, software = head["release"], head["software"]
    revision = head_revision[:12] if head_revision else software.get("git commit", "unknown")
    done = head["status"] == "completed"
    lines = [
        "## Full release run",
        "",
        f"**{'Completed' if done else head['status'].capitalize()}** on {release_name(head)}: "
        f"{number(release['datasets'])} datasets and {number(release['exchanges'])} exchanges "
        f"in {number(release['files'])} files.",
        "",
        f"- Input: archive SHA-256 {short(release['archive_sha256'])}, "
        f"fingerprint of the files read {short(release['fingerprint'])}",
        f"- Tool: revision `{revision}`, bafu-community-fixes "
        f"{software.get('bafu-community-fixes', '?')}, Python {software.get('Python', '?')}",
        f"- Schema check: {head['options'].get('XSD schema check', 'unknown')}",
    ]
    if head["output"]:
        output = head["output"]
        lines.append(
            f"- Patched release: {number(output['files'])} files, {megabytes(output['bytes'])}, "
            f"fingerprint {short(output['fingerprint'])}; "
            f"{number(head['totals']['datasets_changed'])} datasets and "
            f"{number(head['totals']['values_changed'])} values changed by "
            f"{number(head['totals']['steps'])} steps"
        )
    else:
        lines.append("- Patched release: nothing written")
    for kind, items in (("CAUTION", problems(head)), ("WARNING", warnings(head))):
        if items:
            lines += ["", f"> [!{kind}]", *(f"> - {item}" for item in items)]
    if compare:
        lines += ["", *comparison(base, head, base_revision, base_output, head_output)]
    lines += ["", "### Every step", "", *step_table(head), ""]
    lines += [
        "Datasets, exchanges and values are counts of what a step changed. A step that "
        "stops, or a patch that changes nothing, fails this check. The run shows that the "
        "patches apply to BAFU's release and leave it valid EcoSpold 1. It doesn't show "
        "that a correction is right; that is for the review.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("head", type=Path, help="Summary of the revision to describe")
    parser.add_argument(
        "--base",
        type=Path,
        help="Summary of the revision to compare with; if the file doesn't exist, say so",
    )
    parser.add_argument("--head-revision", help="Commit of the revision, for the heading")
    parser.add_argument("--base-revision", help="Commit of the base revision")
    parser.add_argument("--head-output", type=Path, help="Folder with the patched release")
    parser.add_argument("--base-output", type=Path, help="The same, of the base revision")
    parser.add_argument("--out", type=Path, help="Append the Markdown to this file")
    parser.add_argument(
        "--check", action="store_true", help="Exit with status 1 if the run isn't acceptable"
    )
    args = parser.parse_args(argv)

    head = load(args.head)
    if head is None:
        print(f"No summary at {args.head}: the run didn't get as far as writing one", flush=True)
        return 1
    outputs = (args.head_output, args.base_output)
    if not all(folder and folder.is_dir() for folder in outputs):
        outputs = (None, None)
    text = render(
        head,
        load(args.base),
        compare=args.base is not None,
        head_revision=args.head_revision,
        base_revision=args.base_revision,
        head_output=outputs[0],
        base_output=outputs[1],
    )
    if args.out:
        with args.out.open("a", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    found = problems(head)
    # On GitHub, an `::error::` line becomes an annotation on the check
    prefix = "::error title=Full release run::" if os.environ.get("GITHUB_ACTIONS") else "error: "
    for problem in found:
        print(prefix + problem.replace("`", ""), file=sys.stdout if args.out else sys.stderr)
    return 1 if args.check and found else 0


if __name__ == "__main__":
    sys.exit(main())
