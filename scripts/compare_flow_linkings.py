"""Measure what linking through Brightway Flows changes against the mapping of sentier-mappings.

The build can link BAFU's elementary flows two ways (`build_release.py build --linking`).
This script builds BAFU's release both ways with the installer, on the data the build
uses, scores every dataset in the 25 EF 3.1 categories, and writes what differs:

* per category, how many datasets move by more than 1 % and by more than 10 %, and in
  which direction;
* per flow, the factor each linking ends on: which flows lose a factor, which gain one,
  and why a flow has none under the links.

Run it in this repository's environment, with the `brightway` extra:

    uv run --frozen --extra brightway \\
        python scripts/compare_flow_linkings.py --work output/linkings --out comparison.json

The data is the build's, because the build and the installer read one set of pins
(`src/sentier_brightway/sources.toml`): the flow terms, the methods, the mapping, and BAFU's
inventory as sentier-inventory holds it. The installer downloads them once into its cache
and checks each file's SHA-256. `--data-root` takes a folder that already holds the four
data folders instead; the file then says that the data was supplied.

`--work` receives two exports that hold BAFU's inventory: keep that folder on your machine.
The file written with `--out` holds counts, the names of elementary flows and no amount of
any dataset.
"""

import argparse
import collections
import json
import sys
from datetime import date
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
HELPERS = REPOSITORY / "scripts" / "release_build"
FLOW_LINKS = HELPERS / "brightway-flows-targets-bafu-2026-v1.csv"
MAPPING, LINKS = "sentier-mappings", "brightway-flows"


def pinned_data() -> tuple[Path, list[dict]]:
    """The data at the installer's pins, downloaded and checked, and the pins. The pinned
    files are taken whatever `$SENTIER_DATA_ROOT` says, so that the file names what was read."""
    from sentier_brightway.fetch import (
        default_cache_dir,
        load_packaged_manifest,
        manifest_key,
        materialize,
    )

    manifest = load_packaged_manifest()
    root = materialize(manifest, cache_dir=default_cache_dir() / manifest_key(manifest))
    used = [
        {"name": source.name, "commit": source.ref, "pinned_by": "this repository"}
        for source in manifest
    ]
    return root, used


def relative(x, y):
    import numpy as np

    scale = np.maximum(np.abs(x), np.abs(y))
    return np.where(scale > 0, np.abs(y - x) / np.where(scale > 0, scale, 1.0), 0.0)


def datasets(work: Path, data_root: Path, flow_links: Path) -> dict:
    """Score every dataset both ways; per category, how many move and which way."""
    import numpy as np

    import sentier_brightway as sb
    from sentier_brightway.backtest import CATEGORIES
    from sentier_brightway.backtest.scorer import score_all

    frames = {}
    for name, links in ((MAPPING, None), (LINKS, flow_links)):
        folder = work / name
        sb.import_files(folder, data_root=data_root, overwrite=True, flow_links=links)
        frames[name] = score_all(folder, CATEGORIES).frame.set_index("code")
    mapped = frames[MAPPING]
    linked = frames[LINKS].loc[mapped.index]
    per_category, any_moved = [], np.zeros(len(mapped), bool)
    for category in CATEGORIES:
        x = mapped[category.short].to_numpy(float)
        y = linked[category.short].to_numpy(float)
        moved = relative(x, y) > 0.01
        any_moved |= moved
        per_category.append(
            {
                "category": category.short,
                "moved_over_1_percent": int(moved.sum()),
                "moved_over_10_percent": int((relative(x, y) > 0.10).sum()),
                "lower": int((moved & (np.abs(y) < np.abs(x))).sum()),
                "higher": int((moved & (np.abs(y) > np.abs(x))).sum()),
            }
        )
    return {
        "datasets": int(len(mapped)),
        "moved_in_any_category_over_1_percent": int(any_moved.sum()),
        "per_category": per_category,
    }


def flows(data_root: Path, flow_links: Path) -> dict:
    """The factor each linking gives each flow, per method, and why one is lost.

    A flow "has a factor" in a method when the flow it is linked to has a factor there that
    is not zero. A factor table also lists flows with a factor of zero; those do not count.
    """
    from dataclasses import replace

    from sentier_brightway import brightway_flows as bf
    from sentier_brightway.bridge import load_bridge
    from sentier_brightway.build import build
    from sentier_brightway.flows import load_ef_flows, load_source_flows
    from sentier_brightway.inventory import load_inventory
    from sentier_brightway.methods import load_methods
    from sentier_brightway.report import render

    inventory, methods = load_inventory(data_root), load_methods(data_root)
    source_flows, ef_flows = load_source_flows(data_root), load_ef_flows(data_root)
    targets = bf.load_targets(flow_links)
    mapping = load_bridge(data_root)
    links = bf.link(inventory, source_flows, ef_flows, methods, targets)

    bio = inventory.exchanges[inventory.exchanges["flow_type"] == "biosphere"]
    exchanges = bio.groupby("flow").size().to_dict()
    unit = dict(zip(bio["flow"], bio["unit"], strict=True))
    terms = source_flows.set_index("code")

    def four(code):
        categories = tuple(terms.at[code, "categories"])
        return (
            str(terms.at[code, "name"]),
            categories[0] if categories else "",
            categories[1] if len(categories) > 1 else "",
            str(unit[code]),
        )

    def factors(specs):
        return {spec.method_id: dict(spec.cfs) for spec in specs}

    before, after = factors(methods), factors(links.methods)

    def factor(table, bridge, method, code):
        entry = bridge.get(code)
        return table[method].get(entry.target_code, 0.0) * entry.conversion_factor if entry else 0.0

    per_method = []
    lost_in, gained_in = collections.defaultdict(list), collections.defaultdict(list)
    has_before, has_after = set(), set()
    for method in before:
        lost, gained, changed = [], [], []
        for code in exchanges:
            a = factor(before, mapping, method, code)
            b = factor(after, links.bridge, method, code)
            if a != 0:
                has_before.add(code)
            if b != 0:
                has_after.add(code)
            if a != 0 and b == 0:
                lost.append(code)
            elif a == 0 and b != 0:
                gained.append(code)
            elif a != 0 and abs(a - b) > 1e-9 * max(abs(a), abs(b)):
                changed.append(code)
        for code in lost:
            lost_in[code].append(method)
        for code in gained:
            gained_in[code].append(method)
        per_method.append(
            {
                "method": method,
                "flows_that_lose_their_factor": len(lost),
                "their_exchanges": sum(exchanges[code] for code in lost),
                "flows_that_gain_a_factor": len(gained),
                "their_exchanges_gained": sum(exchanges[code] for code in gained),
                "flows_with_another_factor": len(changed),
            }
        )

    def why(code):
        row = targets[four(code)]
        if code not in links.bridge:
            return "not linked: the units differ and no conversion is stated"
        if row["flow_list"] == bf.EF_LIST:
            return "its EF 3.1 flow has no factor there in the build's methods"
        if row["factors_from"] and not row["factors_unit"]:
            return (
                "the source Brightway Flows names for its factors is a flow of another "
                f"implementation's list, which the build's methods do not hold "
                f"(Brightway Flows: {row['factors_derivation']})"
            )
        if row["factors_from"]:
            return (
                "the flow named as the source of its factors has none there in the build's methods"
            )
        if row["factors_derivation"]:
            return "Brightway Flows names more than one flow as the source of its factors"
        return "outside EF 3.1, and Brightway Flows names no flow as the source of factors"

    def listed(found):
        return sorted(
            (
                {
                    "name": four(code)[0],
                    "category": four(code)[1],
                    "subCategory": four(code)[2],
                    "unit": four(code)[3],
                    "exchanges": exchanges[code],
                    "flow_list": targets[four(code)]["flow_list"],
                    "methods": len(methods_),
                    "keeps_a_factor_in_another_method": code in has_after,
                    "why": why(code),
                }
                for code, methods_ in found.items()
            ),
            key=lambda entry: (-entry["exchanges"], entry["name"], entry["subCategory"]),
        )

    lost = listed(lost_in)
    reasons = collections.Counter(entry["why"] for entry in lost)
    reason_exchanges = collections.Counter()
    for entry in lost:
        reason_exchanges[entry["why"]] += entry["exchanges"]

    def lines(result):
        return [line for line in render(result).splitlines() if line.strip()][:-1]

    plain = build(inventory, ef_flows, source_flows, mapping, methods).coverage
    linked = build(inventory, links.ef_flows, source_flows, links.bridge, links.methods).coverage
    linked = replace(linked, linking=bf.LINKING, link_lines=links.report.lines())
    return {
        "flows_used": len(exchanges),
        "elementary_exchanges": int(sum(exchanges.values())),
        "report_of_each_linking": {MAPPING: lines(plain), LINKS: lines(linked)},
        "flows_with_a_factor_in_some_method": {
            MAPPING: len(has_before),
            LINKS: len(has_after),
        },
        "per_method": per_method,
        "flows_that_lose_a_factor_in_some_method": len(lost),
        "their_exchanges": sum(entry["exchanges"] for entry in lost),
        "of_which_lose_every_factor": sum(
            1 for entry in lost if not entry["keeps_a_factor_in_another_method"]
        ),
        "why_a_factor_is_lost": [
            {"why": reason, "flows": n, "exchanges": reason_exchanges[reason]}
            for reason, n in reasons.most_common()
        ],
        "flows_that_gain_a_factor_in_some_method": len(gained_in),
        "lost": lost,
        "gained": [{k: v for k, v in entry.items() if k != "why"} for entry in listed(gained_in)],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=Path, required=True, help="Folder for data and exports")
    parser.add_argument("--out", type=Path, required=True, help="The comparison (JSON)")
    parser.add_argument("--data-root", type=Path, help="A folder with the four data folders")
    parser.add_argument("--flow-links", type=Path, default=FLOW_LINKS)
    args = parser.parse_args(argv)
    if args.data_root:
        root, used = args.data_root.resolve(), "supplied with --data-root"
    else:
        root, used = pinned_data()
    result = {
        "date": date.today().isoformat(),
        "data": used,
        "flow_links": args.flow_links.name,
        "flows": flows(root, args.flow_links),
        "scores": datasets(args.work.resolve(), root, args.flow_links),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    scores, found = result["scores"], result["flows"]
    print(
        f"{found['flows_that_lose_a_factor_in_some_method']} of {found['flows_used']} flows "
        f"lose a factor in some method; {scores['moved_in_any_category_over_1_percent']} of "
        f"{scores['datasets']} datasets move by more than 1 % in some category. "
        f"Written to {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
