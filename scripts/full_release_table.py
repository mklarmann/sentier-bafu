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

No patch says how many targets it expects, and most don't notice that a target is gone.
So this script compares, for every patch, what it changed (datasets, exchanges, values)
with what it changed in an earlier run: the base revision of a pull request (`--base`),
or the previous release (`--previous`, the manifest of a release or a run summary). A
patch that changed something before and nothing now fails the check; one that changed
less, or more, is a warning. `--matches-out` writes the comparison as JSON.

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


def counts_of(step: dict) -> dict:
    return {key: step.get(key) for key, _ in COUNTS}


def earlier_counts(earlier: dict | None) -> tuple[dict[str, dict], str | None]:
    """Per patch, what it changed in an earlier run, and what that run was.

    `earlier` is a run summary, or the manifest of a release.
    """
    if earlier is None:
        return {}, None
    if "provider_release" in earlier and "patches" in earlier:
        counts = {
            patch["id"]: {
                "datasets": patch["datasets_changed"],
                "exchanges": patch["exchanges_changed"],
                "changes": patch["values_changed"],
            }
            for patch in earlier["patches"]
        }
        tag = earlier.get("tag")
        fingerprint = (earlier["provider_release"] or {}).get("fingerprint")
        what = f"release {tag}" if tag else "the previous release build"
    else:
        counts = {step["id"]: counts_of(step) for step in patches(earlier)}
        revision = earlier.get("software", {}).get("git commit")
        fingerprint = earlier["release"]["fingerprint"]
        what = f"the run of revision {revision}" if revision else "the earlier run"
    return counts, f"{what} on the provider release {(fingerprint or 'unknown')[:12]}"


def match_check(head: dict, earlier: dict | None = None) -> dict:
    """For every patch: what it changed now and in an earlier run, and what that means.

    `failures` stop the check: a patch that stopped, or that matched nothing. `warnings`
    are for a reviewer: a patch that changed less or more than before.
    """
    before, what = earlier_counts(earlier)
    other_release = (
        earlier is not None
        and what is not None
        and (head["release"]["fingerprint"] or "")[:12] != what[-12:]
    )
    rows, failures, warnings = [], [], []
    for step in patches(head):
        now, was = counts_of(step), before.get(step["id"])
        had = bool(was and was["datasets"])
        if step.get("error"):
            result = "stopped"
        elif not now["datasets"]:
            result = "matched nothing"
            then = f" In {what} it changed {number(was['datasets'])} dataset(s)." if had else ""
            failures.append(
                f"`{step['id']}` changed nothing on the full release: its target wasn't "
                "found. Either the patch doesn't match the data, or the release already "
                f"has the correction and the patch can be retired.{then}"
            )
        elif was is None:
            result = "new" if before else "no earlier run"
        elif now == was:
            result = "as before"
        else:
            fewer = any(
                now[key] is not None and was[key] is not None and now[key] < was[key]
                for key, _ in COUNTS
            )
            result = "fewer than before" if fewer else "more than before"
            warnings.append(
                f"`{step['id']}` changed {number(now['datasets'])} dataset(s), "
                f"{number(now['exchanges'])} exchange(s) and {number(now['changes'])} value(s); "
                f"in {what} it changed {number(was['datasets'])}, {number(was['exchanges'])} "
                f"and {number(was['changes'])}."
            )
        rows.append({"id": step["id"], "now": now, "previous": was, "result": result})
    if head["status"] == "completed":
        ran = {step["id"] for step in patches(head)}
        for id in before:
            if id not in ran:
                warnings.append(f"`{id}` ran in {what} and is not among the patches now.")
    if other_release and what:
        warnings.append(f"The earlier run read another provider release: {what}.")
    return {"compared_with": what, "failures": failures, "warnings": warnings, "patches": rows}


def match_table(check: dict) -> list[str]:
    """What each patch matched, beside what it matched in the earlier run."""
    lines = ["### What each patch matched", ""]
    if check["compared_with"]:
        lines.append(f"Each patch's counts beside its counts in {check['compared_with']}:")
    else:
        lines.append(
            "There is no earlier run to compare with, so a patch is only checked for "
            "matching nothing."
        )
    lines += [
        "",
        "| Patch | Datasets | Exchanges | Values | Before: datasets | exchanges | values | |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in check["patches"]:
        was = row["previous"] or dict.fromkeys(key for key, _ in COUNTS)
        cells = [number(row["now"][key]) for key, _ in COUNTS]
        cells += [number(was[key]) for key, _ in COUNTS]
        bold = row["result"] in ("stopped", "matched nothing", "fewer than before")
        result = f"**{row['result']}**" if bold else row["result"]
        lines.append(f"| `{row['id']}` | " + " | ".join(cells) + f" | {result} |")
    return lines


def problems(summary: dict, earlier: dict | None = None, partial: bool = False) -> list[str]:
    """Why the run isn't acceptable, if it isn't.

    With `partial` the input is known to be less than a full release (a test release):
    that it isn't a known release, and that a patch finds nothing to change, is expected.
    """
    found = []
    stopped = [step for step in summary["steps"] if step.get("error")]
    for step in stopped:
        found.append(
            f"`{step['id']}` stopped the run; its target was not as expected, or it left "
            f"invalid data: {step['error']}"
        )
    if summary["status"] != "completed" and not stopped:
        found.append(f"The run {summary['status']}: {summary['error'] or 'no message'}")
    if summary["release"]["url"] is None and summary["release"]["fingerprint"] and not partial:
        found.append(
            "The input isn't a release this revision knows (input fingerprint "
            f"{short(summary['release']['fingerprint'])}). If this pull request changes the "
            "release, add its fingerprint to `download.FINGERPRINTS`."
        )
    if summary["status"] == "completed" and not partial:
        found += match_check(summary, earlier)["failures"]
    return found


def warnings(summary: dict, earlier: dict | None = None, partial: bool = False) -> list[str]:
    """What a reviewer should look at, without it being an error."""
    check = match_check(summary, earlier)
    found = [
        f"`{step['id']}` is not yet authorised, and changed {number(step['datasets'])} "
        f"dataset(s). It was written by {step['authored_by']}."
        for step in summary["steps"]
        if step["authorised_by"] is None and step["datasets"]
    ]
    if partial and summary["status"] == "completed":
        nothing = [row["id"] for row in check["patches"] if row["result"] == "matched nothing"]
        if nothing:
            found.append(
                "The input is not a full release. These patches found nothing to change in "
                "it: " + ", ".join(f"`{id}`" for id in nothing) + "."
            )
    return found + check["warnings"]


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
        if before is None and after.get("error"):
            label, counts = "new, stopped", ["–"] * len(COUNTS)
        elif before is None:
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
    if head["status"] != "completed":
        lines.append(
            f"- This revision's run {head['status']}, so steps after the one that stopped "
            "are missing below."
        )
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
    if lines[-1]:
        lines.append("")
    return [*lines, *step_changes(base, head)]


def render(
    head: dict,
    base: dict | None = None,
    compare: bool = False,
    head_revision: str | None = None,
    base_revision: str | None = None,
    head_output: Path | None = None,
    base_output: Path | None = None,
    previous: dict | None = None,
    partial: bool = False,
) -> str:
    """The Markdown. `previous` is the earlier run a patch's counts are compared with;
    without it, the base revision of a pull request is."""
    earlier = previous if previous is not None else base
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
    notes = (
        ("CAUTION", problems(head, earlier, partial)),
        ("WARNING", warnings(head, earlier, partial)),
    )
    for kind, items in notes:
        if items:
            lines += ["", f"> [!{kind}]", *(f"> - {item}" for item in items)]
    if compare:
        lines += ["", *comparison(base, head, base_revision, base_output, head_output)]
    lines += ["", *match_table(match_check(head, earlier))]
    lines += ["", "### Every step", "", *step_table(head), ""]
    lines += [
        "Datasets, exchanges and values are counts of what a step changed. A step that "
        "stops, or a patch that changes nothing, fails this check; a patch that changes "
        "less than in the earlier run is marked for the reviewer. No patch declares how "
        "many targets it has, so a target that was never matched can't be seen here. The "
        "run shows that the patches apply to BAFU's release and leave it valid EcoSpold 1. "
        "It doesn't show that a correction is right; that is for the review.",
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
        "--previous",
        type=Path,
        help="The manifest of the previous release, or an earlier run summary: what each "
        "patch changed is compared with it; if the file doesn't exist, say so",
    )
    parser.add_argument(
        "--matches-out", type=Path, help="Write what each patch matched, now and before, as JSON"
    )
    parser.add_argument(
        "--partial",
        action="store_true",
        help="The input is not a full release (a test release): an unknown input and "
        "patches that find nothing to change are said, and don't fail the check",
    )
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
    base, previous = load(args.base), load(args.previous)
    earlier = previous if previous is not None else base
    text = render(
        head,
        base,
        compare=args.base is not None,
        head_revision=args.head_revision,
        base_revision=args.base_revision,
        head_output=outputs[0],
        base_output=outputs[1],
        previous=previous,
        partial=args.partial,
    )
    if args.previous is not None and previous is None:
        text += f"\nNo earlier run at `{args.previous.name}`: nothing to compare the counts with.\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("a", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    if args.matches_out:
        args.matches_out.parent.mkdir(parents=True, exist_ok=True)
        check = match_check(head, earlier)
        args.matches_out.write_text(json.dumps(check, indent=2) + "\n", encoding="utf-8")
    found = problems(head, earlier, args.partial)
    # On GitHub, an `::error::` line becomes an annotation on the check
    prefix = "::error title=Full release run::" if os.environ.get("GITHUB_ACTIONS") else "error: "
    for problem in found:
        print(prefix + problem.replace("`", ""), file=sys.stdout if args.out else sys.stderr)
    return 1 if args.check and found else 0


if __name__ == "__main__":
    sys.exit(main())
