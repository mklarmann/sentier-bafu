"""A release run's own account for the site: `run.json`, written from the manifest.

    python3 scripts/release_build/run_summary.py --manifest FILE --out FILE

The site walks through the last run step by step (`scripts/sitebuild/lastrun.py`). What it
shows about a step it reads from the account the run wrote of itself, in the format any run
can write (`scripts/runrecord/summary.py`): the page types no number and words no result.
This is where a release run says, in its own words, what each of its steps did.

Everything here is read from the manifest of the run (`release_manifest.py`). A number is
copied, never computed anew, and a text of the run (a problem, the note of a check) is quoted
as it is. `site/config.json` gives the name of a provider release, as the site writes it.

Standard library only.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runrecord import summary  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CLOSING = "Release run "  # how the lines begin that a release run prints after its last step
EXPORT_NAMES = {
    "brightway": "Brightway",
    "openlca": "openLCA",
    "ilcd": "ILCD",
    "simapro": "SimaPro",
}
UNNAMED = "A release this site does not name"


def plural(n, word, many=None):
    return f"{n:,} {word if n == 1 else many or word + 's'}"


def quoted(text, limit=300):
    """A text of the run inside a sentence: as it is, without what the page reads as a mark."""
    text = str(text).replace("`", "'").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def release_names(root: Path = ROOT) -> dict:
    """The names of the provider's releases, as the site writes them: {id: name}."""
    try:
        config = json.loads((root / "site" / "config.json").read_text(encoding="utf-8"))
    except OSError:
        return {}
    except ValueError:
        return {}
    return {r["id"]: r["name"] for r in config.get("releases") or () if "id" in r and "name" in r}


def release_name(manifest, names) -> str:
    release = manifest.get("provider_release") or {}
    return names.get(release["id"], release["id"]) if release.get("id") else UNNAMED


def answered(patches) -> str:
    """The findings a list of patches answers, the shortest number first: F1, F3, F11."""
    found = sorted({f for patch in patches for f in patch["findings"]}, key=lambda f: (len(f), f))
    return ", ".join(found)


def figures(name, manifest) -> list:
    """The numbers of one step, from the manifest: [(value, what it counts)]."""
    out = []

    def add(value, label):
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            return
        out.append((value, label))

    if name == "provider build":
        release = manifest.get("provider_release") or {}
        add(release.get("datasets"), "datasets")
        add(release.get("exchanges"), "exchanges")
        audit = ((manifest.get("brightway") or {}).get("provider") or {}).get("audit")
        if audit:
            add(len(audit["errors"]) + len(audit["findings"]), "noted by the check")
    elif name == "patched build":
        if manifest.get("import_fixes") is not None:
            add(len(manifest["import_fixes"]), "import fixes")
            add(len(manifest["patches"]), "community patches")
        add((manifest.get("totals") or {}).get("datasets_changed"), "datasets changed")
    elif name == "written files":
        output = manifest.get("output") or {}
        add(output.get("files"), "files written")
        if isinstance(output.get("bytes"), int):
            add(f"{output['bytes'] / 1e6:,.0f} MB", "in all")
    elif name == "patch run":
        check = manifest.get("check_against_previous")
        if check:
            add(len(check.get("patches") or []), "patches checked")
            add(len(check.get("failures") or []), "stopped the run")
            add(len(check.get("warnings") or []), "to look at")
    elif name == "comparison":
        comparison = manifest.get("comparison")
        if comparison:
            add(comparison["exchange_rows_compared"], "exchanges compared")
            add(comparison["exchange_rows_changed"], "differ")
            add(comparison["rows_no_step_explains"], "unexplained")
    elif name == "exports":
        exports = (manifest.get("exports") or {}).get("patched")
        if exports:
            back = exports["read_back_matches"]
            add(len(back), "file formats")
            add(sum(1 for ok in back.values() if ok), "read back the same")
    return out


def notes(name, manifest, names) -> list:
    """What else the manifest says about one step, as short lines."""
    found = []
    builds = manifest.get("brightway") or {}
    if name == "provider build":
        release = manifest.get("provider_release") or {}
        if release.get("archive_sha256"):
            checksum = release["archive_sha256"]
            found.append(f"{release_name(manifest, names)}. Checksum of the archive: `{checksum}`.")
        audit = (builds.get("provider") or {}).get("audit")
        noted = [*audit["errors"], *audit["findings"]] if audit else []
        if noted:
            more = f" And {len(noted) - 1:,} more." if len(noted) > 1 else ""
            found.append(f"The check noted: “{quoted(noted[0])}”.{more}")
    elif name == "patched build":
        patches = manifest.get("patches") or []
        links = answered(patches)
        without = sum(1 for patch in patches if not patch["findings"])
        if links:
            found.append(
                f"The patches answer {links}."
                + (
                    f" {plural(without, 'patch names', 'patches name')} no finding."
                    if without
                    else ""
                )
            )
        build = builds.get("patched") or {}
        audit = build.get("audit")
        if audit:
            noted = len(audit["errors"]) + len(audit["findings"])
            found.append(f"The same check of the patched database noted {noted:,}.")
            database, mark = quoted(build.get("database"), 80), quoted(audit["marked_as"], 80)
            found.append(f"The database is named `{database}` and marked “{mark}”.")
    elif name == "written files":
        output = manifest.get("output") or {}
        if output.get("fingerprint"):
            found.append(f"Fingerprint of the written files: `{output['fingerprint']}`.")
    elif name == "patch run":
        check = manifest.get("check_against_previous")
        if check:
            earlier = check.get("compared_with")
            found.append(
                f"Compared with `{quoted(earlier, 100)}`."
                if earlier
                else "There is no earlier release to compare with yet."
            )
    elif name == "comparison":
        comparison = manifest.get("comparison")
        if comparison:
            by = comparison["rows_changed_by_step"]
            if by:
                parts, left = [], len(by)
                for step, rows in by.items():
                    part = f"`{quoted(step, 80)}` ({rows:,})"
                    if sum(map(len, parts)) + len(part) > 480:
                        break
                    parts.append(part)
                    left -= 1
                found.append(
                    "Changed by " + ", ".join(parts) + (f", and {left:,} more." if left else ".")
                )
            unexplained = comparison["moved_scores_no_change_explains"]
            found.append(
                f"{plural(comparison['methods_compared'], 'impact method')} compared; "
                f"{unexplained:,} moved scores that nothing explains."
            )
    elif name == "exports":
        exports = (manifest.get("exports") or {}).get("patched")
        for file in (exports or {}).get("files", []):
            if file["kind"] in EXPORT_NAMES:
                found.append(f"`{quoted(file['name'], 200)}`, {file['bytes'] / 1e6:,.1f} MB")
    return found[: summary.MAX_NOTES]


def contents(manifest, names) -> list:
    """What was in the run: the provider's release and what was applied to it."""
    if manifest.get("provider_release") is None:
        return ["The run did not record what it read."]
    fixes, patches = manifest.get("import_fixes") or [], manifest.get("patches") or []
    links = answered(patches)
    return [
        f"{release_name(manifest, names)}, {plural(len(fixes), 'import fix', 'import fixes')} and "
        f"{plural(len(patches), 'community patch', 'community patches')}"
        + (f", which answer {links}." if links else ".")
    ]


def files(manifest) -> list:
    """The files for LCA tools the run wrote, each with whether it read back the same."""
    exports = (manifest.get("exports") or {}).get("patched")
    return [
        {
            "name": file["name"],
            "label": EXPORT_NAMES[file["kind"]],
            "bytes": file["bytes"],
            "sha256": file["sha256"],
            "same": exports["read_back_matches"].get(file["kind"]),
        }
        for file in (exports or {}).get("files", [])
        if file["kind"] in EXPORT_NAMES
    ]


def from_manifest(manifest, names=None) -> dict:
    """The run's own account, from its manifest. Raises ValueError for a manifest whose
    texts a page could not show."""
    names = release_names() if names is None else names
    said = []
    for text in [*manifest["problems"], *manifest["not_releasable"]]:
        if quoted(text, summary.MAX_TEXT) not in said:
            said.append(quoted(text, summary.MAX_TEXT))
    exports = manifest.get("exports") or {}
    remarks = (
        [quoted(exports["note"], summary.MAX_TEXT)]
        if exports.get("published") is False and exports.get("note")
        else []
    )
    steps = [
        summary.step(
            step["name"],
            step["status"],
            step["seconds"] if summary.is_number(step.get("seconds")) else None,
            quoted(step["reason"], summary.MAX_TEXT) if step.get("reason") else None,
            figures(step["name"], manifest),
            notes(step["name"], manifest, names),
        )
        for step in manifest["steps"]
    ]
    return summary.account(
        "completed" if manifest["status"] == "completed" else "failed",
        steps,
        tag=manifest.get("tag"),
        closing=CLOSING,
        contents=contents(manifest, names),
        blocking=said[: summary.LISTS["blocking"]],
        remarks=remarks,
        files=files(manifest),
    )


def write(manifest, path: Path, names=None) -> Path:
    return summary.write(from_manifest(manifest, names), path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--manifest", type=Path, required=True, help="The manifest of a release run"
    )
    parser.add_argument("--out", type=Path, required=True, help="Where to write run.json")
    args = parser.parse_args(argv)
    try:
        write(json.loads(args.manifest.read_text(encoding="utf-8")), args.out)
    except (OSError, ValueError, KeyError) as error:
        print(f"not written: {error}")
        return 1
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
