"""Publish measured results for sets of review cases from separately audited builds.

Provide a build directory for each selection of case patches in the tagged run.
Directories are named by ordered patch numbers joined by '+' (or 'none' for
import preparation alone). Build each with build_release.py build --only and
the named patches; use --skip with all patches for the baseline. --build-from
can produce missing builds directly from a local provider inventory.

The fix_evidence input is the private fixes.json from the independent fix-builds
and fixes account (sentier-dev/sentier-bafu at a8351ac27540fcf57b5d861e74438b95b3c1d609).
Only its validated public projection is written to the output.
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pyarrow.parquet as parquet
from compare_builds import inventory_folder
from sentier_diagnostics import fixes, rule
from step_diagnostics import digest, read, scores


def measured(folder, selected, final):
    rec = read(folder / "build.json")
    log = read(folder / "release-summary.json")
    release = rec["release"]
    if (
        rec["status"] != "completed"
        or rec["audit"]["status"] != "passed"
        or not rec["patched"]
        or rec.get("contribution")
        or release["provider_tree_sha256"] != final["release"]["provider_tree_sha256"]
        or release["import_fixes"] != final["release"]["import_fixes"]
        or log["release"]["fingerprint"] != release["provider_tree_sha256"]
        or [s["id"] for s in log["steps"] if s["kind"] == "patch"] != list(selected)
        or any(rec[k] != final[k] for k in ("install", "linking", "data_pins"))
        or rec["tools"]["sentier-importers"] != final["tools"]["sentier-importers"]
    ):
        raise ValueError(f"Unexpected inventory, method or patch selection in {folder}")
    audit = folder / "audit/audit.json"
    score_file = folder / "audit/scores.csv"
    checksum = digest(score_file)
    if (
        digest(audit) != rec["audit"]["sha256"]
        or checksum != read(audit)["scores"]["all_datasets"]["sha256"]
    ):
        raise ValueError(f"Audit or score checksum mismatch in {folder}")
    return {
        "patches": list(selected),
        "inventory_sha256": release["built_tree_sha256"],
        "score_sha256": checksum,
        "datasets_edited": sum(bool(d["patches"]) for d in log["datasets"]),
        "edits": sum(s["changes"] for s in log["steps"] if s["kind"] == "patch"),
    }


def summarize(before, after, units, floors, tolerance, public_ids):
    by_indicator = dict.fromkeys(before, 0)
    changed = set()
    rows = {}
    for method, initial in before.items():
        for code, a in initial.items():
            b = after[method][code]
            kind = rule.classify(a, b, floor=floors[method, units[code]], tolerance=tolerance)
            if kind in rule.MOVES:
                by_indicator[method] += 1
                changed.add(code)
                if code in public_ids:
                    rows.setdefault(code, {"moved": []})["moved"].append(method)
    for code, row in rows.items():
        row["values"] = {
            method: [initial[code], after[method][code]] for method, initial in before.items()
        }
    return {"by_indicator": by_indicator, "changed_datasets": len(changed), "rows": rows}


def step_sets(evidence, chain_data, tables, builds):
    """Factor out only patches verified to have no score effect or interaction."""
    f = read(evidence)
    ids = [s["id"] for s in chain_data["steps"]]
    if (
        fixes.errors(f)
        or [x["id"] for x in f["fixes"]] != ids
        or not f["interactions"]["checked"]
        or f["interactions"]["pairs"]
        or any(x["requires"] != [ids[0]] for x in f["fixes"][1:])
        or any(x["tolerance"]["value"] != chain_data["rule"]["total_tolerance"] for x in f["fixes"])
    ):
        raise ValueError("Independent patch measurements cannot certify arbitrary selections")
    items = [r[0] for r in f["items"]]

    def same_table(columns, table):
        return (
            columns.keys() == table.keys()
            and len(items) == len(set(items))
            and all(
                set(items) == values.keys()
                and len(columns[method]) == len(items)
                and all(columns[method][k] == values[code] for k, code in enumerate(items))
                for method, values in table.items()
            )
        )

    base = builds[0]["score_sha256"]
    if not same_table(f["base"], tables[base]) or any(f["fixes"][0]["effect"].values()):
        raise ValueError("Independent fixes use a different baseline or import preparation")
    effective = [x["id"] for x in f["fixes"][1:] if any(x["effect"].values())]
    choices = [[]]
    for fix in effective:
        choices += [[*chosen, fix] for chosen in choices]
    outcomes = {}
    for chosen in choices:
        result = fixes.compose(f, [ids[0], *chosen])
        match = next(
            (key for key, table in tables.items() if same_table(result["results"], table)), None
        )
        if match is None:
            raise ValueError("Combined fix scores did not reproduce an audited score table")
        outcomes[",".join(chosen)] = match

    def outcome(patches):
        return outcomes[",".join(p for p in effective if p in patches)]

    for record in builds:
        if outcome(record["patches"]) != record["score_sha256"]:
            raise ValueError("Independent effects disagree with a measured case combination")
    for i, state in enumerate(chain_data["states"]):
        if outcome(ids[:i]) != state["identity"]["Score table SHA-256"]:
            raise ValueError("Independent effects disagree with a cumulative build")
    for held in f["built"]:
        result = fixes.compose(f, held["fixes"])
        if not same_table(result["results"], tables[outcome(held["fixes"])]):
            raise ValueError("A separately measured set has a different score")
    return {
        "steps": [{"id": s["id"], "label": s["label"]} for s in chain_data["steps"]],
        "required": ids[0],
        "effective": effective,
        "outcomes": outcomes,
        "evidence_sha256": digest(evidence),
    }


def build(run, directory, chain_file, fix_evidence, provider=None, tools=None, pinned_data=None):
    diagnostic = read(chain_file)
    final = read(run / "patched/build.json")
    log = read(run / "patched/release-summary.json")
    case_patches = {}
    order = []
    for step in log["steps"]:
        if step["kind"] == "patch" and step["findings"]:
            order.append(step["id"])
            for case in step["findings"]:
                case_patches.setdefault(case, []).append(step["id"])
    expected = {()}
    for patches in case_patches.values():
        expected |= {tuple(p for p in order if p in picked or p in patches) for picked in expected}
    source = final["release"]["provider_tree_sha256"]
    baseline = next(s for s in diagnostic["states"] if s["id"] == "imported")["identity"]
    if source != baseline["Source inventory SHA-256"]:
        raise ValueError("Case builds and step explorer use different provider inventories")
    processes = parquet.read_table(
        inventory_folder(run / "provider") / "processes.parquet",
        columns=["process_id", "reference_unit"],
    ).to_pydict()
    units = dict(zip(processes["process_id"], processes["reference_unit"], strict=True))
    if len(units) != diagnostic["items_count"]["all"]:
        raise ValueError("Case builds and step explorer cover different datasets")
    methods = [i["id"] for i in diagnostic["indicators"]]
    floors = {(f["indicator"], f["unit"]): f["value"] for f in diagnostic["rule"]["floors"]}
    tolerance = diagnostic["rule"]["total_tolerance"]
    public_ids = {r["id"] for r in diagnostic["items"]}
    builds, outcomes, tables = [], {}, {}
    before = None
    all_patches = [s["id"] for s in log["steps"] if s["kind"] == "patch"]
    for picked in sorted(expected, key=lambda ids: (len(ids), ids)):
        folder = directory / ("+".join(p.split("-", 1)[0] for p in picked) or "none")
        if provider is not None and not folder.exists():
            directory.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=directory) as temp:
                work = Path(temp) / "build"
                command = [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / "build_release.py"),
                    "build",
                    str(provider),
                    str(work),
                    "--linking",
                    final["linking"],
                    "--xsd-check",
                    "end",
                    "--label",
                    "Review case patches · " + folder.name,
                ]
                if tools:
                    command.extend(["--tools", str(tools)])
                if pinned_data:
                    command.extend(["--pinned-data", str(pinned_data)])
                command.extend(["--only", *picked] if picked else ["--skip", *all_patches])
                subprocess.run(command, check=True)
                measured(work, picked, final)
                work.rename(folder)
        record = measured(folder, picked, final)
        key = record["score_sha256"]
        if not picked and (
            key != baseline["Score table SHA-256"]
            or record["inventory_sha256"] != baseline["Built inventory SHA-256"]
        ):
            raise ValueError("Case baseline differs from measured import preparation")
        if key not in outcomes:
            after = scores(folder / "audit/scores.csv", methods, units.keys())
            if not picked:
                before = after
            tables[key] = after
            outcomes[key] = summarize(before, after, units, floors, tolerance, public_ids)
        builds.append(record)
    return {
        "format": "sentier-bafu/case-comparisons/1",
        "source_sha256": source,
        "step_snapshot_sha256": digest(chain_file),
        "base": "After import fixes",
        "datasets": len(units),
        "indicators": methods,
        "indicator_labels": {
            i["id"]: {"name": i["name"], "unit": i["unit"]} for i in diagnostic["indicators"]
        },
        "listed_datasets": {
            i["id"]: {"name": i["name"], "place": i.get("place")} for i in diagnostic["items"]
        },
        "cases": case_patches,
        "builds": builds,
        "outcomes": outcomes,
        "step_sets": step_sets(fix_evidence, diagnostic, tables, builds),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("release", "case_builds", "step_snapshot", "fix_evidence", "out"):
        parser.add_argument(name, type=Path)
    parser.add_argument(
        "--build-from", type=Path, help="Build missing selections from this provider folder"
    )
    parser.add_argument("--tools", type=Path, help="Shared importer tools for new builds")
    parser.add_argument("--pinned-data", type=Path, help="Shared checked data for new builds")
    args = parser.parse_args()
    data = build(
        args.release,
        args.case_builds,
        args.step_snapshot,
        args.fix_evidence,
        args.build_from,
        args.tools,
        args.pinned_data,
    )
    args.out.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
