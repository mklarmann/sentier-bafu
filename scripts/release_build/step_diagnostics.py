"""Build the public step explorer from completed cumulative BAFU builds.

Pass the release output (containing provider/, patched/ and before-after.json) and a
directory of audited intermediate builds: s00 is import fixes only, s01 adds the
first patch, and so on up to the state just before the full patched copy.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path

import pyarrow.parquet as parquet
from compare_builds import inventory_folder
from runrecord.before_after import rounded
from sentier_diagnostics import chain, fileformat, rule


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def scores(path, methods, codes):
    result = {method: {} for method in methods}
    with path.open(newline="") as stream:
        records = csv.DictReader(stream)
        if records.fieldnames != ["code", *methods]:
            raise ValueError(f"Different indicators in {path}")
        for row in records:
            key = row["code"]
            for method, values in result.items():
                values[key] = float(row[method])
    if records.line_num != len(codes) + 1 or result[methods[0]].keys() != codes:
        raise ValueError(f"Different, missing or duplicate datasets in {path}")
    return result


def build(run, intermediate, source_url):
    pair = read(run / "before-after.json")
    final = read(run / "patched/build.json")
    log = read(run / "patched/release-summary.json")
    patches = [p for p in log["steps"] if p["kind"] == "patch"]
    patch_ids = [p["id"] for p in patches]
    imports = [p for p in log["steps"] if p["kind"] == "import fix"]
    before = run / "provider"
    processes = parquet.read_table(
        inventory_folder(before) / "processes.parquet", columns=["process_id", "reference_unit"]
    ).to_pydict()
    units = dict(zip(processes["process_id"], processes["reference_unit"], strict=True))
    indicators = [
        {k: row[k] for k in ("id", "name", "short", "unit")} for row in pair["indicators"]
    ]
    methods = [i["id"] for i in indicators]
    states, steps, values, cache = [], [], {}, {}
    tolerance = chain.tolerance(
        pair["threshold"], "declared", "Relative threshold of the tagged build comparison."
    )
    root = Path(__file__).resolve().parents[2]
    registry = {
        f"{p['id']}-{p['slug']}": p for p in read(root / "community/patches.json")["patches"]
    }
    names = {
        item["id"]: {"name": item["name"], "place": item.get("place")} for item in pair["moved"]
    }
    source_hash = log["release"]["fingerprint"]

    def add_state(folder, key, label, prefix, patched):
        rec = read(folder / "build.json")
        rel = rec["release"]
        if (
            rec["status"] != "completed"
            or rec["audit"]["status"] != "passed"
            or rec["patched"] != patched
            or rec.get("contribution")
            or rel["provider_tree_sha256"] != source_hash
            or set(rel["patches"]) != set(prefix)
            or rec["linking"] != final["linking"]
            or rec["data_pins"] != final["data_pins"]
            or rec["tools"]["sentier-importers"] != final["tools"]["sentier-importers"]
            or rec["install"]["located"] != final["install"]["located"]
        ):
            raise ValueError(f"{folder} is not the expected cumulative build")
        if patched and (
            rec["install"] != final["install"]
            or rel["import_fixes"] != final["release"]["import_fixes"]
        ):
            raise ValueError(f"Different import preparation or flow mapping in {folder}")
        if patched:
            applied = read(folder / "release-summary.json")["steps"]
            if [p["id"] for p in applied if p["kind"] == "patch"] != prefix:
                raise ValueError(f"Unexpected patch order in {folder}")
        audit_path = folder / "audit/audit.json"
        audit = read(audit_path)
        path = folder / "audit/scores.csv"
        checksum = digest(path)
        if (
            digest(audit_path) != rec["audit"]["sha256"]
            or checksum != audit["scores"]["all_datasets"]["sha256"]
        ):
            raise ValueError(f"Audit or score digest mismatch in {folder}")
        if checksum not in cache:
            cache[checksum] = scores(path, methods, units.keys())
        values[key] = cache[checksum]
        identity = {
            "Source inventory SHA-256": source_hash,
            "Built inventory SHA-256": rel["built_tree_sha256"],
            "Score table SHA-256": checksum,
            "Import revision": rec["tools"]["sentier-importers"],
        }
        join = (
            dict(
                compared=len(units), unmatched=0, ambiguous=0, note="Matched by dataset identifier."
            )
            if states
            else None
        )
        states.append(chain.state(key, label, identity=identity, join=join, noise=chain.noise()))

    add_state(before, "provider", pair["before"]["label"], [], False)
    add_state(intermediate / "s00", "imported", "After import fixes", [], True)
    imported = sum(bool(d["import_fixes"]) for d in log["datasets"])
    import_edits = sum(s["changes"] for s in imports)
    steps.append(
        chain.step(
            "import-fixes",
            "Import fixes",
            kind="import preparation",
            tolerance=tolerance,
            link=f"{source_url}/src/bafu_community_fixes/import_fixes.py",
            about=f"{len(imports)} import fixes applied together: {import_edits:,} edits "
            f"across {imported:,} datasets.",
        )
    )
    for number, patch in enumerate(patches, 1):
        key = patch["id"]
        short = key.split("-", 1)[1].replace("-", " ").capitalize()
        short = (
            short.replace("cas", "CAS")
            .replace("Cas ", "CAS ")
            .replace("Brightway flows", "Brightway Flows")
        )
        folder = run / "patched" if number == len(patches) else intermediate / f"s{number:02d}"
        label = (
            pair["after"]["label"]
            if number == len(patches)
            else f"After {key.split('-')[0]} · {short}"
        )
        add_state(folder, key, label, patch_ids[:number], True)
        about = (
            f"{patch['description']} The patch log records {patch['changes']:,} edits across "
            f"{patch['datasets']:,} datasets, including {patch['exchanges']:,} exchange rows."
        )
        source = registry[key]["url"].split("/src/", 1)[1]
        steps.append(
            chain.step(
                key,
                short,
                about=about,
                kind="community patch",
                tolerance=tolerance,
                link=f"{source_url}/src/{source}",
            )
        )
    if len(units) != pair["items"]["compared"]:
        raise ValueError("Dataset count differs from the tagged comparison")
    for item in pair["moved"]:
        for method, endpoints in item["values"].items():
            measured = [
                rounded(values[s["id"]][method][item["id"]]) for s in (states[0], states[-1])
            ]
            if measured != endpoints:
                raise ValueError(f"Endpoint mismatch for {item['id']}, {method}")
    result = chain.build(
        "BAFU inventory, step by step",
        states=states,
        steps=steps,
        values=values,
        indicators=indicators,
        item_word=("dataset", "datasets"),
        units=units,
        names=names,
        indicator_word=("impact category", "impact categories"),
        audience="public",
        claim_lists=False,
        listed=len(units),
        about="The original inventory, import preparation and each community patch in build order.",
        notes=[
            "Each intermediate state was built and scored separately on the same provider "
            "inventory. The first and last states reproduce the tagged comparison.",
            "Counts cover every dataset in the build. The public rows show the changed datasets "
            "listed in the tagged comparison.",
        ],
    )
    for step in result["steps"]:
        counts = result["counts"]["steps"][step["id"]]
        changed = sum(sum(ind["classes"][k] for k in rule.MOVES) for ind in counts.values())
        compared = sum(ind["pairs"] for ind in counts.values())
        step["about"] += (
            f" {changed:,} of {compared:,} impact results changed above the "
            "comparison threshold at this step."
        )
        if not changed and names:
            step["about"] += " The named rows show the datasets that changed over the whole build."
    result["items"] = [item for item in result["items"] if item["id"] in names]
    if {i["id"] for i in result["items"]} != names.keys():
        raise ValueError(
            "The chain did not reproduce all changed datasets listed in the tagged comparison"
        )
    result["items_count"]["listed"] = len(result["items"])
    result["items_count"]["not_listed"] = result["items_count"]["qualifying"] - len(result["items"])
    errors = fileformat.errors(result)
    if errors:
        raise ValueError(errors)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("release", "intermediate", "out"):
        parser.add_argument(name, type=Path)
    parser.add_argument(
        "--source-url", required=True, help="Public repository tree URL for the measured patches"
    )
    args = parser.parse_args()
    chain.write(build(args.release, args.intermediate, args.source_url.rstrip("/")), args.out)
