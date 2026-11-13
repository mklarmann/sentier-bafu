"""The manifest of a release build: the one file a patched release publishes.

    python3 scripts/release_build/release_manifest.py --verify manifest.json [--notes notes.md]

`build_release.py release` writes the manifest from what the run left behind. It holds
checksums, counts, dataset numbers and codes, names of people, and the names and single
values that an audit finding quotes. It holds no inventory: no table of amounts, no
exchange list, no text of a dataset. A GitHub Release of a patched release holds this file
and nothing else, because BAFU's terms ask that whoever receives the data accepts them
first, and a release page can't ask for that.

The first ten fields (`CORE_KEYS`) are the manifest of a patched release as the records side
of this repository defines it (format `sentier-bafu/patched-release/1`): same names, same
kinds, same meaning. This format, `…/2`, adds what the build knows:

- `status`, `problems`, `not_releasable`: whether every step ran, and what keeps a tag from
  being published (a patch that changed data without an authoriser, a failed audit);
- `steps`: each step of the run with its result, seconds and peak memory;
- `check_against_previous`: per patch, how much it changed now and in the previous release;
- `brightway`: the two databases, their audits, the tools and data they were built with;
- `comparison`: the patched database against the provider release's;
- `declared_units`: inputs whose declared unit is not their supplier's, with their finding;
- `exports`: the name, size and SHA-256 of every export file and whether it read back;
- `contributions`: each contribution built beside the patched release, under its own name.

`--verify` checks that a file has exactly this shape, so that the job that publishes can
refuse anything else. Standard library only, and it runs on the Python a runner has: the job
that publishes installs nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

FORMAT = "sentier-bafu/patched-release/2"
CORE_KEYS = (
    "format",
    "tag",
    "built",
    "provider_release",
    "tool",
    "options",
    "import_fixes",
    "patches",
    "totals",
    "output",
)
PATCH_KEYS = (
    "id",
    "description",
    "findings",
    "author",
    "authorised_by",
    "result",
    "datasets_changed",
    "exchanges_changed",
    "values_changed",
    "datasets",
)
FIX_KEYS = ("id", "description", "result", "datasets_changed", "values_changed")
OPTION_KEYS = ("XSD schema check", "extensions in output", "only patches", "skipped patches")
RESULTS = ("applied", "not needed", "failed")
MAX_BYTES = 8_000_000
NOT_PUBLISHED = (
    "The export files are produced and read back in CI but are not published until a download "
    "exists that asks for acceptance of BAFU's terms."
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path, unreadable: list[str] | None = None) -> dict | None:
    """A JSON file's content, or None if it isn't there or can't be read.

    A file that is there and is not JSON (a step was interrupted while writing it) is
    named in `unreadable`, so that it is reported and not taken for a step that never ran.
    """
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        data = None
    if not isinstance(data, dict):
        if unreadable is not None:
            unreadable.append(f"{path.parent.name}/{path.name} is not a JSON record")
        return None
    return data


# --- The core: what the run summary says ------------------------------------------------


def result_of(step: dict) -> str:
    if step.get("error"):
        return "failed"
    return "applied" if step.get("datasets") else "not needed"


def release_id(release: dict, config: dict | None) -> str | None:
    """The id of the provider release in `site/config.json`, when that list names it."""
    for known in (config or {}).get("releases", ()):
        if not isinstance(known, dict):
            continue
        same_archive = known.get("archive_sha256") == release.get("archive_sha256")
        if (release.get("archive_sha256") and same_archive) or (
            release.get("url") and known.get("url") == release.get("url")
        ):
            return known.get("id")
    return None


def core(summary: dict, tag: str | None, revision: str | None, config: dict | None = None) -> dict:
    """The ten fields of a patched release's manifest, from the run summary alone.

    The dataset numbers of each patch come from the summary's list of changed datasets.
    """
    release, software = summary["release"], summary.get("software", {})
    numbers: dict[str, list[int]] = {}
    for dataset in summary.get("datasets") or ():
        for patch in dataset["patches"]:
            numbers.setdefault(patch, []).append(int(dataset["number"]))
    patches, fixes = [], []
    for step in summary["steps"]:
        if step["kind"] != "patch":
            fixes.append(
                {
                    "id": step["id"],
                    "description": step["description"],
                    "result": result_of(step),
                    "datasets_changed": step["datasets"],
                    "values_changed": step["changes"],
                }
            )
            continue
        patches.append(
            {
                "id": step["id"],
                "description": step["description"],
                "findings": list(step.get("findings") or []),
                "author": step["authored_by"],
                "authorised_by": step.get("authorised_by"),
                "result": result_of(step),
                "datasets_changed": step["datasets"],
                "exchanges_changed": step.get("exchanges"),
                "values_changed": step["changes"],
                "datasets": sorted(set(numbers.get(step["id"], []))),
            }
        )
    output = summary.get("output")
    return {
        "format": FORMAT,
        "tag": tag,
        "built": summary.get("finished"),
        "provider_release": {
            "id": release_id(release, config),
            "url": release.get("url"),
            "archive_sha256": release.get("archive_sha256"),
            "fingerprint": release.get("fingerprint"),
            "files": release.get("files"),
            "datasets": release.get("datasets"),
            "exchanges": release.get("exchanges"),
        },
        "tool": {
            "name": "bafu-community-fixes",
            "version": software.get("bafu-community-fixes"),
            "revision": revision or software.get("git commit"),
        },
        "options": {key: summary.get("options", {}).get(key) for key in OPTION_KEYS},
        "import_fixes": fixes,
        "patches": patches,
        "totals": dict(summary.get("totals", {})),
        "output": None
        if output is None
        else {key: output[key] for key in ("files", "bytes", "fingerprint")},
    }


def blockers(summary: dict, manifest_core: dict) -> list[str]:
    """What keeps this run from being published as a release."""
    found = []
    if summary.get("status") != "completed" or not summary.get("output"):
        found.append("the run of the patch tool did not complete")
    release = manifest_core["provider_release"]
    if not release["url"] or not release["archive_sha256"]:
        found.append("the files that were read are not a release this revision of the tool knows")
    for step in [*manifest_core["import_fixes"], *manifest_core["patches"]]:
        if step["result"] == "failed":
            found.append(f"step {step['id']} failed")
    for patch in manifest_core["patches"]:
        if patch["datasets_changed"] and not patch["authorised_by"]:
            found.append(f"patch {patch['id']} changed data and names nobody who authorised it")
        if len(patch["datasets"]) != patch["datasets_changed"]:
            found.append(
                f"patch {patch['id']}: the run counts {patch['datasets_changed']} changed "
                f"datasets, its list of changed datasets has {len(patch['datasets'])}"
            )
    return found


# --- What the build adds ----------------------------------------------------------------


def build_section(folder: Path) -> dict | None:
    """One Brightway build: its database, its audit, and what it was built with."""
    record = load(folder / "build.json")
    if record is None:
        return None
    audit = load(folder / "audit" / "audit.json")
    release = record.get("release", {})
    section = {
        "status": record.get("status"),
        "label": record.get("label"),
        "database": record.get("databases", {}).get("inventory"),
        "provider_fingerprint": release.get("provider_tree_sha256"),
        "built_from_fingerprint": release.get("built_tree_sha256"),
        "tools": {
            name: record.get("tools", {}).get(name)
            for name in ("this repository", "sentier-importers", "sentier-brightway")
        },
        "data": [
            {key: pin.get(key) for key in ("name", "commit", "pinned_by")}
            for pin in record.get("data_pins", [])
        ],
        "audit": None,
    }
    if audit is not None:
        built_from = audit.get("built_from") or {}
        section["audit"] = {
            "status": audit["status"],
            "sha256": sha256_file(folder / "audit" / "audit.json"),
            "marked_as": built_from.get("label"),
            "datasets": audit["datasets"],
            "exchanges": {
                key: audit["exchanges"][key]
                for key in ("production", "technosphere", "biosphere", "total")
            },
            "unlinked_exchanges": sum(audit["unlinked"].values()),
            "elementary_exchanges_on_an_ef_3_1_flow": audit["biosphere_targets"]["ef_3_1"],
            "elementary_exchanges_without_one": audit["biosphere_targets"]["no_ef_3_1_flow"],
            "scores_sha256": audit["scores"]["all_datasets"]["sha256"],
            "errors": list(audit["errors"]),
            "findings": list(audit["findings"]),
        }
    return section


def declared_units_section(folder: Path) -> dict | None:
    audit = load(folder / "audit" / "audit.json")
    if audit is None or "declared_units" not in audit:
        return None
    declared = audit["declared_units"]
    keys = (
        "dataset",
        "dataset_name",
        "dataset_location",
        "supplier",
        "supplier_name",
        "supplier_location",
        "declared_unit",
        "supplier_unit",
        "amount_as_built",
        "amount_brightway_uses",
        "finding",
    )
    return {
        "table": declared["table"],
        "exchanges_whose_declared_unit_is_not_the_suppliers": declared[
            "exchanges_whose_declared_unit_is_not_the_suppliers"
        ],
        "same_quantity_other_label": declared["same_quantity_other_label"],
        "another_quantity": [
            {key: row.get(key) for key in keys} for row in declared["another_quantity"]
        ],
        "recorded_differences_not_found": declared["recorded_differences_not_found"],
    }


def comparison_section(path: Path) -> dict | None:
    comparison = load(path)
    if comparison is None:
        return None
    rows = comparison["rows"]
    moved = {
        method["method"]: method["moved_by_step"]
        for method in comparison["scores"]["methods"]
        if method["datasets_moved"]
    }
    return {
        "status": comparison["status"],
        "sha256": sha256_file(path),
        "errors": list(comparison["errors"]),
        "baseline": comparison["builds"]["baseline"]["database"],
        "candidate": comparison["builds"]["candidate"]["database"],
        "exchange_rows_compared": rows["exchange_rows_compared"],
        "exchange_rows_changed": rows["exchange_rows_changed"],
        "rows_changed_by_step": {
            step: counts.get("rows", 0) for step, counts in rows["by_step"].items()
        },
        "rows_no_step_explains": rows["unexplained_count"],
        "elementary_exchanges_that_lost_their_ef_3_1_flow": comparison["elementary_flows"][
            "exchanges_that_lost_their_ef_3_1_flow"
        ],
        "methods_compared": len(comparison["scores"]["methods"]),
        "datasets_whose_score_moved_by_method_and_step": moved,
        "moved_scores_no_change_explains": comparison["scores"]["unexplained_moves"],
    }


def exports_section(folder: Path) -> dict | None:
    """The export files by name, size and checksum, and whether each read back."""
    export = load(folder / "manifest.json")
    if export is None:
        return None
    return {
        "status": export["status"],
        "manifest_sha256": sha256_file(folder / "manifest.json"),
        "label": export["label"],
        "labels_table": {key: export["labels"][key] for key in ("file", "sha256")},
        "amounts_converted": export["labels"]["amounts_converted"],
        "formats": {
            kind: {key: entry.get(key) for key in ("status", "stage", "error")}
            for kind, entry in export["formats"].items()
        },
        "read_back_matches": {kind: check["passed"] for kind, check in export["checks"].items()},
        "differences_found": {kind: check["total"] for kind, check in export["checks"].items()},
        "files": [
            {"kind": kind, **{key: entry[key] for key in ("name", "bytes", "sha256")}}
            for kind, entry in export["files"].items()
        ],
        "counts": export["counts"],
        "published": False,
    }


def contribution_section(folder: Path) -> dict:
    """One contribution built beside the patched release: `folder` holds its build."""
    receipt = load(folder / "build" / "layer-receipt.json") or {}
    record = load(folder / "build" / "build.json") or {}
    layer = record.get("contribution") or {}
    return {
        "id": layer.get("id"),
        "name": layer.get("name"),
        "title": layer.get("title"),
        "database": layer.get("database"),
        "authored_by": layer.get("authored_by"),
        "authorised_by": layer.get("authorised_by"),
        "layer": {"file": layer.get("layer_file"), "sha256": layer.get("layer_sha256")},
        "changes_declared": receipt.get("changes_declared"),
        "exchanges_changed": receipt.get("exchanges_changed"),
        "datasets_changed": receipt.get("datasets_changed", []),
        "brightway": build_section(folder / "build"),
        "comparison_with_the_patched_release": comparison_section(folder / "comparison.json"),
        "exports": exports_section(folder / "exports"),
    }


def manifest(
    out: Path,
    *,
    tag: str | None = None,
    revision: str | None = None,
    steps: list[dict] | None = None,
    config: dict | None = None,
) -> dict:
    """The manifest of the release run in `out` (as `build_release.py release` lays it out)."""
    unreadable: list[str] = []
    summary = load(out / "patched" / "release-summary.json", unreadable)
    if summary is not None and not {"release", "steps", "totals"} <= set(summary):
        unreadable.append("patched/release-summary.json is not a run summary")
        summary = None
    problems = [
        f"step {step['name']} {step['status']}: {step.get('reason') or 'see its log'}"
        for step in steps or ()
        if step["status"] not in ("completed", "skipped")
    ]
    problems += unreadable
    if summary is None:
        missing = [] if unreadable else ["the patch tool wrote no run summary"]
        return {
            **dict.fromkeys(CORE_KEYS),
            "format": FORMAT,
            "tag": tag,
            "status": "failed",
            "problems": [*problems, *missing],
            "not_releasable": [*unreadable, *missing],
            "steps": steps or [],
            "check_against_previous": None,
            "brightway": {"provider": build_section(out / "provider"), "patched": None},
            "comparison": None,
            "declared_units": None,
            "exports": {"patched": None, "published": False, "note": NOT_PUBLISHED},
            "contributions": [],
        }
    first = core(summary, tag, revision, config)
    not_releasable = blockers(summary, first)
    builds = {name: build_section(out / name) for name in ("provider", "patched")}
    for name, build in builds.items():
        audit = (build or {}).get("audit")
        if audit is None:
            not_releasable.append(f"the {name} release has no audited Brightway database")
        elif audit["status"] != "passed" or (name == "patched" and audit["findings"]):
            not_releasable.append(f"the audit of the {name} build has errors or findings")
    comparison = comparison_section(out / "comparison.json")
    if comparison is None or comparison["status"] != "passed":
        not_releasable.append("the comparison of the two builds did not pass")
    exports = exports_section(out / "exports" / "patched")
    if exports is None or exports["status"] != "completed":
        not_releasable.append("not every export was written and read back without a difference")
    contributions = [
        contribution_section(folder)
        for folder in sorted((out / "contributions").glob("*/"))
        if (folder / "build").is_dir()
    ]
    return {
        **first,
        "status": "failed" if problems else "completed",
        "problems": problems,
        "not_releasable": not_releasable,
        "steps": steps or [],
        "check_against_previous": load(out / "match-check.json"),
        "brightway": builds,
        "comparison": comparison,
        "declared_units": declared_units_section(out / "patched"),
        "exports": {"patched": exports, "published": False, "note": NOT_PUBLISHED},
        "contributions": contributions,
    }


# --- Checking that a file is a manifest and nothing else ----------------------------------

_SHA = re.compile(r"[0-9a-f]{64}")


class _Shape:
    """Collects what is wrong with a value that should have a given shape."""

    def __init__(self):
        self.errors: list[str] = []

    def fail(self, where: str, what: str) -> None:
        if len(self.errors) < 50:
            self.errors.append(f"{where}: {what}")

    def text(self, value, where, limit=2000, optional=False):
        if value is None and optional:
            return
        if not isinstance(value, str) or len(value) > limit or "\n" in value:
            self.fail(where, f"not a line of text of at most {limit} characters")

    def count(self, value, where, optional=False):
        if value is None and optional:
            return
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            self.fail(where, "not a count")

    def number(self, value, where, optional=False):
        if value is None and optional:
            return
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            self.fail(where, "not a number")
        elif not math.isfinite(value):
            self.fail(where, "not a finite number")

    def sha(self, value, where, optional=False):
        if value is None and optional:
            return
        if not isinstance(value, str) or not _SHA.fullmatch(value):
            self.fail(where, "not a SHA-256")

    def keys(self, value, where, keys, optional=False) -> bool:
        if value is None and optional:
            return False
        if not isinstance(value, dict) or set(value) != set(keys):
            self.fail(where, "holds other fields than it has")
            return False
        return True

    def texts(self, value, where, limit=200, each=2000):
        if not isinstance(value, list) or len(value) > limit:
            self.fail(where, f"not a list of at most {limit} lines")
            return
        for line in value:
            self.text(line, where, each)

    def counts(self, value, where, limit=100):
        if not isinstance(value, dict) or len(value) > limit:
            self.fail(where, "not a table of counts")
            return
        for key, count in value.items():
            self.text(key, where, 300)
            self.count(count, where)


def _check_core(shape: _Shape, data: dict) -> None:
    shape.text(data["tag"], "tag", 100, optional=True)
    if isinstance(data["tag"], str) and not re.fullmatch(r"[A-Za-z0-9._+-]+", data["tag"]):
        shape.fail("tag", "not a tag name")
    shape.text(data["built"], "built", 40, optional=True)
    release = data["provider_release"]
    names = ("id", "url", "archive_sha256", "fingerprint", "files", "datasets", "exchanges")
    if shape.keys(release, "provider_release", names):
        shape.text(release["id"], "provider_release.id", 40, optional=True)
        shape.text(release["url"], "provider_release.url", 500, optional=True)
        if isinstance(release["url"], str) and not release["url"].startswith("https://"):
            shape.fail("provider_release.url", "not an https address")
        shape.sha(release["archive_sha256"], "provider_release.archive_sha256", optional=True)
        shape.sha(release["fingerprint"], "provider_release.fingerprint", optional=True)
        for key in ("files", "datasets", "exchanges"):
            shape.count(release[key], f"provider_release.{key}", optional=True)
    if shape.keys(data["tool"], "tool", ("name", "version", "revision")):
        for key, value in data["tool"].items():
            shape.text(value, f"tool.{key}", 100, optional=True)
    options = data["options"]
    if not isinstance(options, dict) or len(options) > 10:
        shape.fail("options", "not a short table")
    else:
        for key, value in options.items():
            shape.text(key, "options", 60)
            if not isinstance(value, bool):
                shape.text(value, f"options.{key}", 200, optional=True)
    shape.counts(data["totals"], "totals", 10)
    if shape.keys(data["output"], "output", ("files", "bytes", "fingerprint"), optional=True):
        shape.count(data["output"]["files"], "output.files")
        shape.count(data["output"]["bytes"], "output.bytes")
        shape.sha(data["output"]["fingerprint"], "output.fingerprint")
    for name, keys in (("import_fixes", FIX_KEYS), ("patches", PATCH_KEYS)):
        steps = data[name]
        if not isinstance(steps, list) or len(steps) > 10000:
            shape.fail(name, "not a list of steps")
            continue
        for step in steps:
            if not shape.keys(step, name, keys):
                continue
            where = f"{name} {step['id']}" if isinstance(step["id"], str) else name
            shape.text(step["id"], f"{where}: id", 100)
            if isinstance(step["id"], str) and not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9._-]*", step["id"]
            ):
                shape.fail(where, "id is not a plain name")
            shape.text(step["description"], f"{where}: description", 1000)
            if step["result"] not in RESULTS:
                shape.fail(where, "result is not one of " + ", ".join(RESULTS))
            shape.count(step["datasets_changed"], f"{where}: datasets_changed")
            shape.count(step["values_changed"], f"{where}: values_changed")
            if name != "patches":
                continue
            shape.text(step["author"], f"{where}: author", 200)
            shape.text(step["authorised_by"], f"{where}: authorised_by", 200, optional=True)
            shape.count(step["exchanges_changed"], f"{where}: exchanges_changed", optional=True)
            findings, numbers = step["findings"], step["datasets"]
            if not isinstance(findings, list) or not all(
                isinstance(f, str) and re.fullmatch(r"F[1-9][0-9]*", f) for f in findings
            ):
                shape.fail(where, "findings are not ids like F14")
            if (
                not isinstance(numbers, list)
                or not all(isinstance(n, int) and not isinstance(n, bool) for n in numbers)
                or numbers != sorted(set(numbers))
            ):
                shape.fail(where, "datasets is not a sorted list of dataset numbers")


def _check_build(shape: _Shape, build, where: str) -> None:
    names = (
        "status",
        "label",
        "database",
        "provider_fingerprint",
        "built_from_fingerprint",
        "tools",
        "data",
        "audit",
    )
    if not shape.keys(build, where, names, optional=True):
        return
    for key in ("status", "label", "database"):
        shape.text(build[key], f"{where}.{key}", 200, optional=True)
    shape.sha(build["provider_fingerprint"], f"{where}.provider_fingerprint", optional=True)
    shape.sha(build["built_from_fingerprint"], f"{where}.built_from_fingerprint", optional=True)
    if isinstance(build["tools"], dict) and len(build["tools"]) <= 5:
        for key, value in build["tools"].items():
            shape.text(key, f"{where}.tools", 60)
            shape.text(value, f"{where}.tools.{key}", 100, optional=True)
    else:
        shape.fail(f"{where}.tools", "not a short table")
    if isinstance(build["data"], list) and len(build["data"]) <= 20:
        for pin in build["data"]:
            if shape.keys(pin, f"{where}.data", ("name", "commit", "pinned_by")):
                for key, value in pin.items():
                    shape.text(value, f"{where}.data.{key}", 200, optional=True)
    else:
        shape.fail(f"{where}.data", "not a short list")
    audit = build["audit"]
    names = (
        "status",
        "sha256",
        "marked_as",
        "datasets",
        "exchanges",
        "unlinked_exchanges",
        "elementary_exchanges_on_an_ef_3_1_flow",
        "elementary_exchanges_without_one",
        "scores_sha256",
        "errors",
        "findings",
    )
    if not shape.keys(audit, f"{where}.audit", names, optional=True):
        return
    shape.text(audit["status"], f"{where}.audit.status", 40)
    shape.text(audit["marked_as"], f"{where}.audit.marked_as", 60, optional=True)
    shape.sha(audit["sha256"], f"{where}.audit.sha256")
    shape.sha(audit["scores_sha256"], f"{where}.audit.scores_sha256")
    shape.counts(audit["exchanges"], f"{where}.audit.exchanges", 6)
    for key in names[3:8]:
        if key != "exchanges":
            shape.count(audit[key], f"{where}.audit.{key}")
    shape.texts(audit["errors"], f"{where}.audit.errors")
    shape.texts(audit["findings"], f"{where}.audit.findings")


def _check_comparison(shape: _Shape, comparison, where: str) -> None:
    names = (
        "status",
        "sha256",
        "errors",
        "baseline",
        "candidate",
        "exchange_rows_compared",
        "exchange_rows_changed",
        "rows_changed_by_step",
        "rows_no_step_explains",
        "elementary_exchanges_that_lost_their_ef_3_1_flow",
        "methods_compared",
        "datasets_whose_score_moved_by_method_and_step",
        "moved_scores_no_change_explains",
    )
    if not shape.keys(comparison, where, names, optional=True):
        return
    for key in ("status", "baseline", "candidate"):
        shape.text(comparison[key], f"{where}.{key}", 200)
    shape.sha(comparison["sha256"], f"{where}.sha256")
    shape.texts(comparison["errors"], f"{where}.errors")
    for key in (
        "exchange_rows_compared",
        "exchange_rows_changed",
        "rows_no_step_explains",
        "elementary_exchanges_that_lost_their_ef_3_1_flow",
        "methods_compared",
        "moved_scores_no_change_explains",
    ):
        shape.count(comparison[key], f"{where}.{key}")
    shape.counts(comparison["rows_changed_by_step"], f"{where}.rows_changed_by_step", 500)
    moved = comparison["datasets_whose_score_moved_by_method_and_step"]
    if not isinstance(moved, dict) or len(moved) > 200:
        shape.fail(where, "moved scores are not a table by method")
    else:
        for method, by_step in moved.items():
            shape.text(method, where, 200)
            shape.counts(by_step, f"{where}.{method}", 500)


def _check_exports(shape: _Shape, exports, where: str) -> None:
    names = (
        "status",
        "manifest_sha256",
        "label",
        "labels_table",
        "amounts_converted",
        "formats",
        "read_back_matches",
        "differences_found",
        "files",
        "counts",
        "published",
    )
    if not shape.keys(exports, where, names, optional=True):
        return
    shape.text(exports["status"], f"{where}.status", 40)
    shape.text(exports["label"], f"{where}.label", 60)
    shape.sha(exports["manifest_sha256"], f"{where}.manifest_sha256")
    if shape.keys(exports["labels_table"], f"{where}.labels_table", ("file", "sha256")):
        shape.text(exports["labels_table"]["file"], f"{where}.labels_table.file", 100, True)
        shape.sha(exports["labels_table"]["sha256"], f"{where}.labels_table.sha256", True)
    shape.count(exports["amounts_converted"], f"{where}.amounts_converted")
    if exports["published"] is not False:
        shape.fail(where, "a manifest never says that export files are published")
    formats = exports["formats"]
    if not isinstance(formats, dict) or len(formats) > 10:
        shape.fail(f"{where}.formats", "not a short table")
    else:
        for kind, entry in formats.items():
            shape.text(kind, f"{where}.formats", 40)
            if shape.keys(entry, f"{where}.formats.{kind}", ("status", "stage", "error")):
                for key, value in entry.items():
                    shape.text(value, f"{where}.formats.{kind}.{key}", 600, optional=True)
    for key in ("read_back_matches", "differences_found", "counts"):
        table = exports[key]
        if not isinstance(table, dict) or len(table) > 10:
            shape.fail(f"{where}.{key}", "not a short table")
            continue
        for kind, value in table.items():
            shape.text(kind, f"{where}.{key}", 60)
            if key == "read_back_matches":
                if not isinstance(value, bool):
                    shape.fail(f"{where}.{key}.{kind}", "not true or false")
            else:
                shape.count(value, f"{where}.{key}.{kind}")
    files = exports["files"]
    if not isinstance(files, list) or len(files) > 20:
        shape.fail(f"{where}.files", "not a short list")
        return
    for entry in files:
        if shape.keys(entry, f"{where}.files", ("kind", "name", "bytes", "sha256")):
            shape.text(entry["kind"], f"{where}.files.kind", 40)
            shape.text(entry["name"], f"{where}.files.name", 200)
            if isinstance(entry["name"], str) and "/" in entry["name"]:
                shape.fail(f"{where}.files.name", "a file name, not a path")
            shape.count(entry["bytes"], f"{where}.files.bytes")
            shape.sha(entry["sha256"], f"{where}.files.sha256")


def _check_declared_units(shape: _Shape, declared, where: str) -> None:
    names = (
        "table",
        "exchanges_whose_declared_unit_is_not_the_suppliers",
        "same_quantity_other_label",
        "another_quantity",
        "recorded_differences_not_found",
    )
    if not shape.keys(declared, where, names, optional=True):
        return
    if shape.keys(declared["table"], f"{where}.table", ("file", "sha256")):
        shape.text(declared["table"]["file"], f"{where}.table.file", 100, optional=True)
        shape.sha(declared["table"]["sha256"], f"{where}.table.sha256", optional=True)
    shape.count(declared[names[1]], f"{where}.{names[1]}")
    shape.counts(declared["same_quantity_other_label"], f"{where}.same_quantity_other_label")
    rows = declared["another_quantity"]
    keys = (
        "dataset",
        "dataset_name",
        "dataset_location",
        "supplier",
        "supplier_name",
        "supplier_location",
        "declared_unit",
        "supplier_unit",
        "amount_as_built",
        "amount_brightway_uses",
        "finding",
    )
    if not isinstance(rows, list) or len(rows) > 500:
        shape.fail(f"{where}.another_quantity", "not a list of at most 500 inputs")
    else:
        for row in rows:
            if shape.keys(row, f"{where}.another_quantity", keys):
                for key in keys[:8]:
                    shape.text(row[key], f"{where}.another_quantity.{key}", 300, optional=True)
                shape.number(row["amount_as_built"], f"{where}.amount_as_built", True)
                shape.number(row["amount_brightway_uses"], f"{where}.amount_brightway_uses", True)
                shape.text(row["finding"], f"{where}.finding", 20, optional=True)
    stale = declared["recorded_differences_not_found"]
    if not isinstance(stale, list) or len(stale) > 500:
        shape.fail(f"{where}.recorded_differences_not_found", "not a short list")
    else:
        for row in stale:
            if shape.keys(row, where, ("finding", "supplier", "declared", "supplier_unit")):
                for key, value in row.items():
                    shape.text(value, f"{where}.{key}", 200, optional=True)


def _check_previous(shape: _Shape, check, where: str) -> None:
    names = ("compared_with", "failures", "warnings", "patches")
    if not shape.keys(check, where, names, optional=True):
        return
    shape.text(check["compared_with"], f"{where}.compared_with", 300, optional=True)
    shape.texts(check["failures"], f"{where}.failures")
    shape.texts(check["warnings"], f"{where}.warnings")
    patches = check["patches"]
    if not isinstance(patches, list) or len(patches) > 10000:
        shape.fail(f"{where}.patches", "not a list of patches")
        return
    for patch in patches:
        if not shape.keys(patch, f"{where}.patches", ("id", "now", "previous", "result")):
            continue
        shape.text(patch["id"], f"{where}.patches.id", 100)
        shape.text(patch["result"], f"{where}.patches.result", 60)
        for key in ("now", "previous"):
            counts = patch[key]
            if key == "previous" and counts is None:
                continue
            if shape.keys(counts, f"{where}.{key}", ("datasets", "exchanges", "changes")):
                for name, value in counts.items():
                    shape.count(value, f"{where}.{key}.{name}", optional=True)


def shape_errors(data) -> list[str]:
    """What keeps a file from being a manifest: these fields, of these kinds, and no others."""
    extra = (
        "status",
        "problems",
        "not_releasable",
        "steps",
        "check_against_previous",
        "brightway",
        "comparison",
        "declared_units",
        "exports",
        "contributions",
    )
    shape = _Shape()
    if not isinstance(data, dict) or set(data) != {*CORE_KEYS, *extra}:
        return ["the manifest holds other fields than a manifest has"]
    if data["format"] != FORMAT:
        return [f"format is not {FORMAT}"]
    if data["provider_release"] is not None:
        _check_core(shape, data)
    shape.text(data["status"], "status", 40)
    shape.texts(data["problems"], "problems")
    shape.texts(data["not_releasable"], "not_releasable")
    steps = data["steps"]
    if not isinstance(steps, list) or len(steps) > 500:
        shape.fail("steps", "not a list of steps")
    else:
        names = ("name", "status", "seconds", "peak_memory_mb", "reason")
        for step in steps:
            if shape.keys(step, "steps", names):
                shape.text(step["name"], "steps.name", 200)
                shape.text(step["status"], "steps.status", 40)
                shape.number(step["seconds"], "steps.seconds", optional=True)
                shape.number(step["peak_memory_mb"], "steps.peak_memory_mb", optional=True)
                shape.text(step["reason"], "steps.reason", 600, optional=True)
    _check_previous(shape, data["check_against_previous"], "check_against_previous")
    if shape.keys(data["brightway"], "brightway", ("provider", "patched")):
        for name, build in data["brightway"].items():
            _check_build(shape, build, f"brightway.{name}")
    _check_comparison(shape, data["comparison"], "comparison")
    _check_declared_units(shape, data["declared_units"], "declared_units")
    if shape.keys(data["exports"], "exports", ("patched", "published", "note")):
        _check_exports(shape, data["exports"]["patched"], "exports.patched")
        shape.text(data["exports"]["note"], "exports.note", 400)
        if data["exports"]["published"] is not False:
            shape.fail("exports", "a manifest never says that export files are published")
    contributions = data["contributions"]
    names = (
        "id",
        "name",
        "title",
        "database",
        "authored_by",
        "authorised_by",
        "layer",
        "changes_declared",
        "exchanges_changed",
        "datasets_changed",
        "brightway",
        "comparison_with_the_patched_release",
        "exports",
    )
    if not isinstance(contributions, list) or len(contributions) > 1000:
        shape.fail("contributions", "not a list of contributions")
        return shape.errors
    for entry in contributions:
        if not shape.keys(entry, "contributions", names):
            continue
        where = f"contribution {entry['id']}"
        for key in names[:6]:
            shape.text(entry[key], f"{where}.{key}", 500, optional=True)
        if shape.keys(entry["layer"], f"{where}.layer", ("file", "sha256")):
            shape.text(entry["layer"]["file"], f"{where}.layer.file", 200, optional=True)
            shape.sha(entry["layer"]["sha256"], f"{where}.layer.sha256", optional=True)
        shape.count(entry["changes_declared"], f"{where}.changes_declared", optional=True)
        shape.count(entry["exchanges_changed"], f"{where}.exchanges_changed", optional=True)
        shape.texts(entry["datasets_changed"], f"{where}.datasets_changed", 100000, 100)
        _check_build(shape, entry["brightway"], f"{where}.brightway")
        _check_comparison(shape, entry["comparison_with_the_patched_release"], f"{where}.compare")
        _check_exports(shape, entry["exports"], f"{where}.exports")
    return shape.errors


def release_errors(data: dict) -> list[str]:
    """Why a manifest that has the right shape may still not be published as a release."""
    found = list(data["not_releasable"])
    if data["status"] != "completed":
        found.append(f"the run {data['status']}")
    if not data["tag"]:
        found.append("the manifest names no tag")
    return found


def notes(data: dict) -> str:
    """The text of the release: what the manifest says, in words. No inventory."""
    release, output = data["provider_release"], data["output"]
    lines = [
        f"Patched release `{data['tag']}`." if data["tag"] else "Patched release.",
        "",
        "This release publishes `manifest.json` only. It holds no inventory: build the patched "
        "release yourself with the patch tool at the revision below, and compare the "
        "fingerprint of what you built.",
        "",
        f"- Provider release: {release['url']} (archive SHA-256 `{release['archive_sha256']}`), "
        f"{release['datasets']:,} datasets",
        f"- Tool: {data['tool']['name']} {data['tool']['version'] or ''} at revision "
        f"`{data['tool']['revision']}`",
        f"- Patched release: {output['files']:,} files, fingerprint `{output['fingerprint']}`",
        f"- Import fixes: {len(data['import_fixes'])}; community patches: {len(data['patches'])}",
    ]
    for name, build in data["brightway"].items():
        if build and build["audit"]:
            audit = build["audit"]
            lines.append(
                f"- Brightway database of the {name} release: `{build['database']}`, "
                f"{audit['datasets']:,} datasets, audit {audit['status']} with "
                f"{len(audit['findings'])} finding(s)"
            )
    lines += [
        "",
        "| Patch | Findings | Author | Authorised by | Result | Datasets changed |",
        "|---|---|---|---|---|---:|",
    ]
    for patch in data["patches"]:
        cells = [
            patch["id"],
            ", ".join(patch["findings"]) or "none",
            patch["author"],
            patch["authorised_by"] or "nobody yet",
            patch["result"],
            f"{patch['datasets_changed']:,}",
        ]
        lines.append("| " + " | ".join(str(cell).replace("|", "/") for cell in cells) + " |")
    exports = data["exports"]["patched"]
    if exports:
        lines += [
            "",
            data["exports"]["note"],
            "",
            "| Export file | Bytes | SHA-256 |",
            "|---|---:|---|",
        ]
        lines += [
            f"| {entry['name']} | {entry['bytes']:,} | `{entry['sha256']}` |"
            for entry in exports["files"]
        ]
    for entry in data["contributions"]:
        lines += [
            "",
            f"Contribution {entry['id']} ({entry['name']}) was built beside the patched "
            f"release as its own database, `{entry['database']}`. It is not part of the "
            "patched release.",
        ]
    lines += [
        "",
        "A community patch is not a correction by the provider. The provider decides what "
        "it changes.",
    ]
    return "\n".join(lines) + "\n"


def write(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--verify", type=Path, metavar="MANIFEST", required=True)
    parser.add_argument("--notes", type=Path, help="Also write the text of the release here")
    parser.add_argument(
        "--release",
        action="store_true",
        help="Also require what a published release needs: a tag, a completed run, every "
        "patch that changed data authorised, audits and exports without a failure",
    )
    args = parser.parse_args(argv)
    name = args.verify.name
    try:
        if args.verify.stat().st_size > MAX_BYTES:
            print(f"{name}: larger than a manifest can be")
            return 1
        data = json.loads(args.verify.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"{name}: not a JSON file ({type(error).__name__})")
        return 1
    errors = shape_errors(data)
    if not errors and args.release:
        errors = [f"not a release: {error}" for error in release_errors(data)]
    for error in errors[:20]:
        print(f"{name}: {error}")
    if errors:
        return 1
    if args.notes:
        args.notes.write_text(notes(data), encoding="utf-8")
    print(f"{name}: a manifest of {len(data['patches'])} patches, and nothing else")
    return 0


if __name__ == "__main__":
    sys.exit(main())
