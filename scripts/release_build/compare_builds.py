"""Compare two builds made by `build_release.py`: what changed, and which step changed it.

The baseline is the provider release and the candidate a patched release; or the baseline
is the patched release and the candidate a contribution built beside it. Reads, for both:

- the inventory tables sentier-importers wrote (`processes.parquet`, `exchanges.parquet`),
  compared row by row: an exchange is identified by its dataset and its position in it;
- the scores of every dataset for every method (`scores.csv` from the audit);
- the candidate's adapter receipt, which lists the import fixes and patches the patch tool
  recorded on each dataset; its run summary, which says which fields each step changed; and,
  for a contribution, the receipt of its layer.

It answers three questions and fails if it can't answer one of them:

1. Which rows differ, and is every difference explained by a step recorded on that dataset?
2. Which elementary flows changed identity, and are they still linked to an EF 3.1 flow?
3. Which scores moved, and does every moved dataset have a changed dataset in its supply
   chain whose change can affect that method?

Run it in the environment that holds sentier-brightway (pandas, and the bridge and method
readers). The output holds dataset codes, names, counts and scores; no inventory amounts
other than the before and after values of changed exchanges.
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

MOVE_TOLERANCE = 1e-6  # relative; the two builds are solved separately (noise is near 1e-7)
LISTED = 50  # moved datasets listed per method in the output

# Importer-visible fields each step is known to change, from the step's own description.
# Every changed row is checked against this table, so a step that starts changing something
# else shows up as an unexplained row instead of being attributed by assumption. A step that
# is not listed here (a new patch) needs no entry: what it can explain is taken from the run
# summary, which counts the fields it changed in this run (`step_fields`).
STEP_FIELDS = {
    "0001-strawberry-polyethylene-disposal": {"exchange": {"amount"}, "process": set()},
    "0002-supplier-locations": {"exchange": {"location"}, "process": set()},
    "0007-flow-names": {"exchange": {"flow", "name"}, "process": set()},
    "0008-flow-compartments": {"exchange": {"flow"}, "process": set()},
    "location-codes": {"exchange": {"location"}, "process": {"location"}},
}
# What a changed attribute of an exchange in the release files means in the importer's
# tables: the groups below. `number` names the supplier of a technosphere input.
EXCHANGE_ATTRIBUTES = {
    "meanValue": {"amount"},
    "uncertaintyType": {"amount"},
    "standardDeviation95": {"amount"},
    "minValue": {"amount"},
    "maxValue": {"amount"},
    "mostLikelyValue": {"amount"},
    "location": {"location"},
    "name": {"flow", "name"},
    "category": {"flow"},
    "subCategory": {"flow"},
    "unit": {"flow", "unit"},
    "number": {"flow"},
}
EXCHANGE_ELEMENTS = {"inputGroup": {"kind"}, "outputGroup": {"kind"}}
# The same for a dataset's own fields: the columns of processes.parquet they reach
PROCESS_FIELDS = {
    "geography/@location": {"location"},
    "referenceFunction/@name": {"name", "reference_product"},
    "referenceFunction/@unit": {"reference_unit"},
    "referenceFunction/@amount": {"reference_amount"},
    "referenceFunction/@category": {"sector", "comment"},
    "referenceFunction/@subCategory": {"sector", "comment"},
    "technology/@text": {"technology"},
}
# Import fixes whose changes the adapter takes back before the importer reads the files
UNDONE_BY_THE_ADAPTER = {"renumber-exchanges"}
# What a contribution's supplier substitution changes on an input
LAYER_FIELDS = {"exchange": {"flow", "name", "location"}, "process": set()}
# Columns of exchanges.parquet, grouped by what a change to them means
EXCHANGE_GROUPS = {
    "flow": ("flow",),  # the flow's identity: name, compartment, subcompartment and unit
    "name": ("flow_name",),
    "amount": ("amount", "uncertainty_type", "loc", "scale", "minimum", "maximum"),
    "location": ("location",),
    "unit": ("unit",),
    "kind": ("flow_type", "direction"),
}
# Dataset columns that name the release a build was made from, not the dataset
RELEASE_NAME_COLUMNS = ("process_id", "source", "source_version")
# Changes that can move a score. A name or a declared location alone does not: technosphere
# inputs are linked by dataset number, elementary flows by their identity.
SCORE_RELEVANT = {"flow", "amount", "unit", "kind"}


class CompareError(Exception):
    pass


# --- Pure helpers ----------------------------------------------------------------------


def derived_fields(changed: dict[str, int]) -> dict[str, set[str]]:
    """What a step can explain, from the XML fields the run summary says it changed."""
    exchange, process = set(), set()
    for path in changed:
        if path.startswith("flowData/exchange/@"):
            exchange |= EXCHANGE_ATTRIBUTES.get(path.rpartition("@")[2], set())
        elif path.startswith("flowData/exchange/"):
            exchange |= EXCHANGE_ELEMENTS.get(path.rpartition("/")[2], set())
        else:
            for ending, columns in PROCESS_FIELDS.items():
                if path.endswith("/" + ending):
                    process |= columns
    return {"exchange": exchange, "process": process}


def step_fields(summary: dict | None, layer: dict | None = None) -> dict[str, dict]:
    """`STEP_FIELDS`, plus every other step of the run with what it changed, plus the layer."""
    fields = {step: dict(groups) for step, groups in STEP_FIELDS.items()}
    for step in (summary or {}).get("steps", ()):
        if step["id"] in fields or step["id"] in UNDONE_BY_THE_ADAPTER:
            continue
        derived = derived_fields(step.get("fields") or {})
        if derived["exchange"] or derived["process"]:
            fields[step["id"]] = derived
    if layer:
        fields[layer["step"]] = LAYER_FIELDS
    return fields


def explain(
    groups: set[str], steps: list[str], table: str, fields: dict[str, dict] | None = None
) -> list[str]:
    """The recorded steps that account for a change to `groups`, or [] if none does."""
    fields = STEP_FIELDS if fields is None else fields
    known = {step: fields[step][table] for step in steps if step in fields}
    # A step that changes exactly these fields explains the row better than one that
    # could also have changed others: renaming a flow changes its name and identity,
    # moving its compartment changes the identity only.
    for matches in (lambda fields: groups == fields, lambda fields: groups <= fields):
        single = [step for step, fields in known.items() if matches(fields)]
        if single:
            return single
    together = set().union(*known.values()) if known else set()
    return sorted(known) if groups <= together else []


def downstream(seeds: set[str], consumers: dict[str, set[str]]) -> set[str]:
    """Every dataset whose supply chain contains one of `seeds`, the seeds included."""
    found, todo = set(seeds), list(seeds)
    while todo:
        for consumer in consumers.get(todo.pop(), ()):
            if consumer not in found:
                found.add(consumer)
                todo.append(consumer)
    return found


def attribute(moved: set[str], reach: dict[str, set[str]]) -> dict[str, list[str]]:
    """Per moved dataset, the steps with a relevant changed dataset in its supply chain."""
    return {code: sorted(step for step, codes in reach.items() if code in codes) for code in moved}


# --- Reading ---------------------------------------------------------------------------


def inventory_folder(build: Path) -> Path:
    folders = sorted((build / "data-root" / "sentier-inventory" / "data").glob("*/"))
    if len(folders) != 1:
        raise CompareError(f"{build}: expected one inventory folder, found {len(folders)}")
    return folders[0]


def read_inventory(build: Path):
    import pandas as pd

    folder = inventory_folder(build)
    processes = pd.read_parquet(folder / "processes.parquet")
    exchanges = pd.read_parquet(folder / "exchanges.parquet")
    exchanges["position"] = exchanges.groupby("process_id").cumcount()
    return processes, exchanges


def read_scores(build: Path):
    import pandas as pd

    return pd.read_csv(build / "audit" / "scores.csv").set_index("code")


def read_json(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.is_file() else None


def read_steps(build: Path) -> dict[str, list[str]]:
    """Per dataset, the steps recorded on it: import fixes, patches, and a layer's changes."""
    data = read_json(build / "adapter-receipt.json") or {}
    steps = {
        code: [*recorded["import_fixes"], *recorded["patches"]]
        for code, recorded in data.get("steps_by_dataset", {}).items()
    }
    layer = read_json(build / "layer-receipt.json")
    for code in (layer or {}).get("datasets_changed", ()):
        steps.setdefault(code, []).append(layer["step"])
    return steps


# --- 1. Rows ---------------------------------------------------------------------------


def _differs(before, after):
    import numpy as np
    import pandas as pd

    if pd.api.types.is_float_dtype(before) and pd.api.types.is_float_dtype(after):
        return ~np.isclose(
            before.astype(float), after.astype(float), rtol=1e-12, atol=0, equal_nan=True
        )
    return ~((before == after) | (before.isna() & after.isna())).to_numpy(dtype=bool)


def compare_rows(base, cand, steps: dict[str, list[str]], fields: dict | None = None) -> dict:
    """Row-level differences of the two inventories, each attributed to recorded steps."""
    base_processes, base_exchanges = base
    cand_processes, cand_exchanges = cand
    keys = ["process_id", "position"]
    merged = base_exchanges.merge(
        cand_exchanges, on=keys, how="outer", suffixes=("_before", "_after"), indicator=True
    )
    only = merged["_merge"].value_counts().to_dict()
    both = merged[merged["_merge"] == "both"].reset_index(drop=True)
    import numpy as np

    changed_groups = {}
    for group, columns in EXCHANGE_GROUPS.items():
        mask = np.zeros(len(both), dtype=bool)
        for column in columns:
            if f"{column}_before" in both:
                mask |= _differs(both[f"{column}_before"], both[f"{column}_after"])
        changed_groups[group] = mask
    any_change = np.zeros(len(both), dtype=bool)
    for mask in changed_groups.values():
        any_change |= mask
    changed = both[any_change].copy()
    changed["groups"] = [
        frozenset(g for g, mask in changed_groups.items() if mask[i]) for i in changed.index
    ]

    by_step, unexplained, rows = defaultdict(Counter), [], []
    for row in changed.itertuples(index=False):
        found = explain(set(row.groups), steps.get(row.process_id, []), "exchange", fields)
        label = " + ".join(found) if found else "unexplained"
        for group in sorted(row.groups):
            by_step[label][group] += 1
        by_step[label]["rows"] += 1
        rows.append((row, found))
        if not found:
            unexplained.append({"dataset": row.process_id, "fields": sorted(row.groups)})
    datasets_by_step = defaultdict(set)
    for row, found in rows:
        datasets_by_step[" + ".join(found) if found else "unexplained"].add(row.process_id)

    process_keys = set(base_processes.process_id) ^ set(cand_processes.process_id)
    paired = base_processes.merge(cand_processes, on="process_id", suffixes=("_before", "_after"))
    process_changes, process_unexplained = defaultdict(Counter), []
    for column in base_processes.columns:
        if column in RELEASE_NAME_COLUMNS or f"{column}_after" not in paired:
            continue
        differs = _differs(paired[f"{column}_before"], paired[f"{column}_after"])
        for code in paired.loc[differs, "process_id"]:
            found = explain({column}, steps.get(code, []), "process", fields)
            process_changes[" + ".join(found) if found else "unexplained"][column] += 1
            if not found:
                process_unexplained.append({"dataset": code, "fields": [column]})
    return {
        "summary": {
            "exchange_rows_compared": int(len(both)),
            "exchange_rows_only_in_baseline": int(only.get("left_only", 0)),
            "exchange_rows_only_in_candidate": int(only.get("right_only", 0)),
            "exchange_rows_changed": int(len(changed)),
            "datasets_only_in_one_build": len(process_keys),
            "by_step": {
                step: dict(sorted(counts.items())) | {"datasets": len(datasets_by_step[step])}
                for step, counts in sorted(by_step.items())
            },
            "dataset_rows_changed_by_step": {
                step: dict(sorted(counts.items()))
                for step, counts in sorted(process_changes.items())
            },
            "unexplained": [*unexplained, *process_unexplained][:LISTED],
            "unexplained_count": len(unexplained) + len(process_unexplained),
        },
        "rows": rows,
    }


def declared_against_linked(processes, exchanges) -> dict:
    """Technosphere inputs whose declared name, location or unit is not the linked dataset's.

    The importer links an input by number, so what the exchange declares and what it is
    linked to can differ. A unit that differs is either another spelling (`p` and `unit`)
    or a quantity nobody converts.
    """
    inputs = exchanges[exchanges["flow_type"] == "technosphere"]
    columns = [c for c in ("process_id", "name", "location", "reference_unit") if c in processes]
    linked = inputs.merge(
        processes[columns],
        left_on="flow",
        right_on="process_id",
        how="left",
        suffixes=("", "_supplier"),
    )
    declared = linked["location"].notna()
    result = {
        "technosphere_inputs": int(len(inputs)),
        "without_a_linked_dataset": int(linked["name"].isna().sum()),
        "declared_name_differs": int((linked["flow_name"] != linked["name"]).sum()),
        "no_declared_location": int((~declared).sum()),
        "declared_location_differs": int(
            (declared & (linked["location"] != linked["location_supplier"])).sum()
        ),
    }
    if "reference_unit" in linked and "unit" in linked:
        differs = linked[linked["name"].notna() & (linked["unit"] != linked["reference_unit"])]
        pairs = differs.groupby(["unit", "reference_unit"]).size()
        result["declared_unit_differs"] = int(len(differs))
        result["declared_and_linked_units"] = {
            f"{unit} for a dataset in {reference}": int(count)
            for (unit, reference), count in pairs.items()
        }
    return result


# --- 2. Elementary flows -----------------------------------------------------------------


def effective_factors(bridge, methods) -> dict[str, dict[str, float]]:
    """Per BAFU flow id: `{method id: conversion factor x characterisation factor}`."""
    factors = {m.method_id: dict(m.cfs) for m in methods}
    out = {}
    for code, entry in bridge.items():
        out[code] = {
            method_id: entry.conversion_factor * values[entry.target_code]
            for method_id, values in factors.items()
            if entry.target_code in values
        }
    return out


def _target_name(entry, ef_names: dict[str, str]) -> str | None:
    """The EF 3.1 flow's name, or its code where the pinned flow terms don't name it."""
    if entry is None:
        return None
    return ef_names.get(entry.target_code, f"EF 3.1 flow {entry.target_code}")


def compare_flows(rows, bridge, effective, ef_names: dict[str, str]) -> dict:
    """Elementary flows whose identity changed: are they still on an EF 3.1 flow?"""
    groups = defaultdict(lambda: {"exchanges": 0, "datasets": set(), "steps": set()})
    for row, found in rows:
        if "flow" not in row.groups or row.flow_type_before != "biosphere":
            continue
        key = (row.flow_name_before, row.flow_name_after, row.flow_before, row.flow_after)
        groups[key]["exchanges"] += 1
        groups[key]["datasets"].add(row.process_id)
        groups[key]["steps"].update(found or ["unexplained"])
    flows, lost, lost_flows = [], 0, set()
    for (name_before, name_after, id_before, id_after), group in sorted(groups.items()):
        before, after = bridge.get(id_before), bridge.get(id_after)
        changed_methods = sorted(
            method
            for method in set(effective.get(id_before, {})) | set(effective.get(id_after, {}))
            if effective.get(id_before, {}).get(method, 0.0)
            != effective.get(id_after, {}).get(method, 0.0)
        )
        if before is not None and after is None:
            lost += group["exchanges"]
            lost_flows.add(id_after)
        flows.append(
            {
                "name_before": name_before,
                "name_after": name_after,
                "steps": sorted(group["steps"]),
                "exchanges": group["exchanges"],
                "datasets": len(group["datasets"]),
                "linked_to_ef_3_1_before": before is not None,
                "linked_to_ef_3_1_after": after is not None,
                "ef_3_1_flow_before": _target_name(before, ef_names),
                "ef_3_1_flow_after": _target_name(after, ef_names),
                "methods_with_a_factor_before": sorted(
                    m for m, v in effective.get(id_before, {}).items() if v
                ),
                "methods_whose_factor_changes": changed_methods,
            }
        )
    return {
        "flows_that_changed_identity": flows,
        "exchanges_that_lost_their_ef_3_1_flow": lost,
        "flows_that_lost_their_ef_3_1_flow": len(lost_flows),
    }


def declared_flows(
    receipt: dict, exchanges, steps: dict, bridge, ef_names: dict, fields: dict | None = None
) -> dict:
    """Elementary exchanges a patch corrected, linked on the flow as BAFU declared it."""
    observations = receipt.get("source_observations", [])
    flow_of = {
        (owner, position): flow
        for owner, position, flow in zip(
            exchanges["process_id"], exchanges["position"], exchanges["flow"], strict=True
        )
    }
    groups = defaultdict(lambda: {"exchanges": 0, "datasets": set(), "steps": set(), "on": set()})
    for observation in observations:
        declared, patched = observation["declared"], observation["patched"]
        changed = {"flow", "name"} if declared["name"] != patched["name"] else {"flow"}
        found = explain(changed, steps.get(observation["dataset"], []), "exchange", fields)
        key = (tuple(declared.values()), tuple(patched.values()))
        group = groups[key]
        group["exchanges"] += 1
        group["datasets"].add(observation["dataset"])
        group["steps"].update(found or ["unexplained"])
        entry = bridge.get(flow_of.get((observation["dataset"], observation["position"])))
        group["on"].add(_target_name(entry, ef_names))
    flows = [
        {
            "declared": list(declared),
            "patched": list(patched),
            "steps": sorted(group["steps"]),
            "exchanges": group["exchanges"],
            "datasets": len(group["datasets"]),
            "ef_3_1_flow": sorted(str(name) for name in group["on"]),
            "linked_to_ef_3_1": None not in group["on"],
        }
        for (declared, patched), group in sorted(groups.items())
    ]
    return {
        "exchanges": len(observations),
        "datasets": len({o["dataset"] for o in observations}),
        "unexplained": sum(f["exchanges"] for f in flows if "unexplained" in f["steps"]),
        "flows": flows,
    }


def published_results(baseline: Path, candidate: Path) -> dict | None:
    """Both builds against BAFU's published results, side by side, if both were compared."""
    files = [build / "published-results.json" for build in (baseline, candidate)]
    if not all(file.is_file() for file in files):
        return None
    base, cand = (json.loads(file.read_text()) for file in files)
    return {
        "joined": {"baseline": base["joined"], "candidate": cand["joined"]},
        "not_joined": {"baseline": base["not_joined"], "candidate": cand["not_joined"]},
        "within_1_percent": {
            category: {
                "baseline": base["categories"][category].get("within_1_percent"),
                "candidate": cand["categories"].get(category, {}).get("within_1_percent"),
            }
            for category in base["categories"]
        },
    }


# --- 3. Scores -------------------------------------------------------------------------


def relevant_seeds(rows, effective, methods: list[str]) -> dict[str, dict[str, set[str]]]:
    """`{method: {step: datasets with a change that can move that method's score}}`."""
    seeds = {method: defaultdict(set) for method in methods}
    for row, found in rows:
        if not (row.groups & SCORE_RELEVANT):
            continue
        labels = found or ["unexplained"]
        if row.flow_type_before == "biosphere" and row.flow_type_after == "biosphere":
            before = effective.get(row.flow_before, {})
            after = effective.get(row.flow_after, {})
            for method in methods:
                changes = before.get(method, 0.0) * row.amount_before != (
                    after.get(method, 0.0) * row.amount_after
                )
                if changes:
                    for label in labels:
                        seeds[method][label].add(row.process_id)
        else:  # a technosphere or production change reaches every method
            for method in methods:
                for label in labels:
                    seeds[method][label].add(row.process_id)
    return seeds


def consumer_graph(*exchange_tables) -> dict[str, set[str]]:
    consumers = defaultdict(set)
    for exchanges in exchange_tables:
        inputs = exchanges[(exchanges["flow_type"] == "technosphere") & (exchanges["amount"] != 0)]
        for supplier, consumer in zip(inputs["flow"], inputs["process_id"], strict=True):
            consumers[supplier].add(consumer)
    return consumers


def compare_scores(base_scores, cand_scores, seeds, consumers, names: dict[str, dict]) -> dict:
    import numpy as np

    if list(base_scores.columns) != list(cand_scores.columns):
        raise CompareError("The two builds were scored with different methods")
    codes = sorted(set(base_scores.index) & set(cand_scores.index))
    base_scores, cand_scores = base_scores.loc[codes], cand_scores.loc[codes]
    closures: dict[frozenset, set[str]] = {}
    out, unexplained_total = [], 0
    for method in base_scores.columns:
        before = base_scores[method].to_numpy(dtype=float)
        after = cand_scores[method].to_numpy(dtype=float)
        scale = np.maximum(np.abs(before), np.abs(after))
        with np.errstate(invalid="ignore", divide="ignore"):
            relative = np.where(scale == 0, 0.0, np.abs(after - before) / scale)
        moved_index = np.flatnonzero(relative > MOVE_TOLERANCE)
        moved = {codes[i] for i in moved_index}
        reach = {}
        for step, datasets in seeds[method].items():
            key = frozenset(datasets)
            if key not in closures:
                closures[key] = downstream(set(datasets), consumers)
            reach[step] = closures[key]
        attribution = attribute(moved, reach)
        counts = Counter(
            " + ".join(steps) if steps else "unexplained" for steps in attribution.values()
        )
        unexplained_total += counts.get("unexplained", 0)
        order = sorted(moved_index, key=lambda i: -relative[i])
        listed = [
            {
                "code": codes[i],
                "name": names.get(codes[i], {}).get("name"),
                "location": names.get(codes[i], {}).get("location"),
                "before": float(before[i]),
                "after": float(after[i]),
                "change_percent": (
                    None if before[i] == 0 else float((after[i] - before[i]) / abs(before[i]) * 100)
                ),
                "steps": attribution[codes[i]],
            }
            for i in order[:LISTED]
        ]
        out.append(
            {
                "method": method,
                "datasets_compared": len(codes),
                "datasets_moved": len(moved),
                "moved_by_step": dict(sorted(counts.items())),
                "datasets_that_could_move": {
                    step: len(datasets) for step, datasets in sorted(reach.items())
                },
                "differences_below_tolerance": int(
                    np.count_nonzero((relative > 0) & (relative <= MOVE_TOLERANCE))
                ),
                "largest_difference_below_tolerance": float(
                    np.max(relative[relative <= MOVE_TOLERANCE], initial=0.0)
                ),
                "moved": listed,
                "moved_not_listed": max(0, len(moved) - LISTED),
            }
        )
    return {"tolerance": MOVE_TOLERANCE, "methods": out, "unexplained_moves": unexplained_total}


# --- Putting it together ---------------------------------------------------------------


def compare(baseline: Path, candidate: Path) -> dict:
    from sentier_brightway.bridge import load_bridge
    from sentier_brightway.flows import load_ef_flows
    from sentier_brightway.methods import load_methods

    base, cand = read_inventory(baseline), read_inventory(candidate)
    steps = read_steps(candidate)
    summary = read_json(candidate / "release-summary.json")
    layer = read_json(candidate / "layer-receipt.json")
    fields = step_fields(summary, layer)
    rows = compare_rows(base, cand, steps, fields)
    root = candidate / "data-root"
    bridge, methods = load_bridge(root), load_methods(root)
    effective = effective_factors(bridge, methods)
    ef_flows = load_ef_flows(root)
    ef_names = dict(zip(ef_flows["code"], ef_flows["name"], strict=True))
    flows = compare_flows(rows["rows"], bridge, effective, ef_names)
    receipt = candidate / "adapter-receipt.json"
    observed = declared_flows(
        json.loads(receipt.read_text()) if receipt.is_file() else {},
        cand[1],
        steps,
        bridge,
        ef_names,
        fields,
    )

    base_scores, cand_scores = read_scores(baseline), read_scores(candidate)
    seeds = relevant_seeds(rows["rows"], effective, list(base_scores.columns))
    names = cand[0].set_index("process_id")[["name", "location"]].to_dict("index")
    scores = compare_scores(
        base_scores, cand_scores, seeds, consumer_graph(base[1], cand[1]), names
    )
    audits = {
        label: json.loads((build / "audit" / "audit.json").read_text())
        for label, build in (("baseline", baseline), ("candidate", candidate))
    }
    errors = []
    if rows["summary"]["unexplained_count"]:
        errors.append(f"{rows['summary']['unexplained_count']} changed row(s) no step explains")
    if scores["unexplained_moves"]:
        errors.append(f"{scores['unexplained_moves']} moved score(s) no changed dataset explains")
    if observed["unexplained"]:
        errors.append(f"{observed['unexplained']} corrected flow(s) no step explains")
    for key in ("exchange_rows_only_in_baseline", "exchange_rows_only_in_candidate"):
        if rows["summary"][key]:
            errors.append(f"{rows['summary'][key]} {key.replace('_', ' ')}")
    return {
        "status": "failed" if errors else "passed",
        "errors": errors,
        "what_a_step_can_explain": {
            "declared_in_the_comparison": sorted(STEP_FIELDS),
            "taken_from_the_run_summary": sorted(
                step
                for step in fields
                if step not in STEP_FIELDS and step != (layer or {}).get("step")
            ),
            "layer": (layer or {}).get("step"),
        },
        "builds": {
            label: {
                "label": audit["label"],
                "database": audit["databases"]["inventory"],
                "built_from": audit.get("built_from"),
                "audit_status": audit["status"],
                "datasets": audit["datasets"],
                "exchanges": audit["exchanges"],
                "biosphere_targets": audit["biosphere_targets"],
                "findings": audit["findings"],
            }
            for label, audit in audits.items()
        },
        "rows": rows["summary"],
        "technosphere_declared_against_linked": {
            "baseline": declared_against_linked(*base),
            "candidate": declared_against_linked(*cand),
        },
        "elementary_flows": flows,
        "linked_on_the_declared_flow": observed,
        "scores": scores,
        "published_results": published_results(baseline, candidate),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("baseline", type=Path, help="Build folder of the provider release")
    parser.add_argument("candidate", type=Path, help="Build folder of the patched release")
    parser.add_argument("--out", type=Path, required=True, help="JSON file to write")
    args = parser.parse_args(argv)
    try:
        result = compare(args.baseline, args.candidate)
    except CompareError as error:
        print(f"Comparison failed: {error}", file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    climate = next(
        m for m in result["scores"]["methods"] if m["method"].endswith(":climate-change")
    )
    print(
        f"{result['status']}: {result['rows']['exchange_rows_changed']} exchange row(s) changed, "
        f"{result['elementary_flows']['exchanges_that_lost_their_ef_3_1_flow']} elementary "
        f"exchange(s) lost their EF 3.1 flow, {climate['datasets_moved']} climate change "
        f"score(s) moved; {args.out}"
    )
    for line in result["errors"]:
        print(f"  {line}")
    return int(bool(result["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
