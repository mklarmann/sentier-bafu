"""Measure what linking through Brightway Flows changes against the mapping of sentier-mappings.

The build can link BAFU's elementary flows two ways (`build_release.py build --linking`).
This script builds BAFU's release both ways with the installer, scores every dataset in
the 25 EF 3.1 categories, and writes what differs:

* per category, how many datasets move by more than 1 % and by more than 10 %, and in
  which direction;
* per flow, the factor each linking ends on: which flows lose their factor, which gain
  one, and why a flow has none under the links (no flow named as the source of factors,
  the named flow without a factor in the build's methods, more than one named).

Run it in the installer's environment, which has pandas, bw2calc and the installer:

    uv run --frozen --project brightway-installer --python 3.12 --extra testing \\
        python scripts/compare_flow_linkings.py --work output/linkings --out comparison.json

Without `--data-root` the installer downloads its pinned inventory, flow terms, methods and
mapping and checks them. `--work` receives two exports that hold BAFU's inventory: keep
that folder on your machine. The file written with `--out` holds counts, the names of
elementary flows and no amount of any dataset.
"""

import argparse
import collections
import json
import sys
from datetime import date
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
FLOW_LINKS = REPOSITORY / "src/bafu_community_fixes/data/brightway-flows-targets-bafu-2026-v1.csv"


def relative(x, y):
    import numpy as np

    scale = np.maximum(np.abs(x), np.abs(y))
    return np.where(scale > 0, np.abs(y - x) / np.where(scale > 0, scale, 1.0), 0.0)


def datasets(work: Path, data_root, flow_links: Path) -> dict:
    """Score every dataset both ways; per category, how many move and which way."""
    import numpy as np
    import sentier_brightway as sb
    from sentier_brightway.backtest import CATEGORIES
    from sentier_brightway.backtest.scorer import score_all

    frames = {}
    for name, links in (("sentier-mappings", None), ("brightway-flows", flow_links)):
        folder = work / name
        sb.import_files(folder, data_root=data_root, overwrite=True, flow_links=links)
        frames[name] = score_all(folder, CATEGORIES).frame.set_index("code")
    mapped = frames["sentier-mappings"]
    linked = frames["brightway-flows"].loc[mapped.index]
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


def flows(data_root, flow_links: Path) -> dict:
    """The factor each linking gives each flow, per method, and why one is lost."""
    from sentier_brightway import brightway_flows as bf
    from sentier_brightway.bridge import load_bridge
    from sentier_brightway.fetch import resolve_data_root
    from sentier_brightway.flows import load_ef_flows, load_source_flows
    from sentier_brightway.inventory import load_inventory
    from sentier_brightway.methods import load_methods
    from sentier_brightway.report import render

    root = resolve_data_root(data_root)
    inventory, methods = load_inventory(root), load_methods(root)
    source_flows = load_source_flows(root)
    targets = bf.load_targets(flow_links)
    mapping = load_bridge(root)
    ef_flows = load_ef_flows(root)
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
    per_method, lost_anywhere, gained_anywhere = [], {}, {}
    for method in before:
        lost, gained, changed = [], [], []
        for code in exchanges:
            old, new = mapping.get(code), links.bridge.get(code)
            a = before[method].get(old.target_code, 0.0) * old.conversion_factor if old else 0.0
            b = after[method].get(new.target_code, 0.0) * new.conversion_factor if new else 0.0
            if a != 0 and b == 0:
                lost.append(code)
            elif a == 0 and b != 0:
                gained.append(code)
            elif a != 0 and abs(a - b) > 1e-9 * max(abs(a), abs(b)):
                changed.append(code)
        for code in lost:
            lost_anywhere.setdefault(code, []).append(method)
        for code in gained:
            gained_anywhere.setdefault(code, []).append(method)
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
            return "its EF 3.1 flow has no factor in the build's methods"
        if row["factors_from"]:
            return (
                "the EF 3.1 flow named as the source of its factors has none in the build's "
                f"methods (Brightway Flows: {row['factors_derivation']})"
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
                    "why": why(code),
                }
                for code, methods_ in found.items()
            ),
            key=lambda entry: (-entry["exchanges"], entry["name"], entry["subCategory"]),
        )

    lost = listed(lost_anywhere)
    reasons = collections.Counter(entry["why"] for entry in lost)
    reason_exchanges = collections.Counter()
    for entry in lost:
        reason_exchanges[entry["why"]] += entry["exchanges"]
    coverage = render_lines(inventory, source_flows, ef_flows, methods, mapping, links, render)
    return {
        "flows_used": len(exchanges),
        "elementary_exchanges": int(sum(exchanges.values())),
        "report_of_each_linking": coverage,
        "per_method": per_method,
        "flows_that_lose_a_factor_in_some_method": len(lost),
        "their_exchanges": sum(entry["exchanges"] for entry in lost),
        "why_a_factor_is_lost": [
            {"why": reason, "flows": n, "exchanges": reason_exchanges[reason]}
            for reason, n in reasons.most_common()
        ],
        "flows_that_gain_a_factor_in_some_method": len(gained_anywhere),
        "lost": lost,
        "gained": [{k: entry[k] for k in entry if k != "why"} for entry in listed(gained_anywhere)],
    }


def render_lines(inventory, source_flows, ef_flows, methods, mapping, links, render) -> dict:
    """What the installer prints for each linking, without the last two lines (citation)."""
    from dataclasses import replace

    from sentier_brightway import brightway_flows as bf
    from sentier_brightway.build import build

    def lines(result):
        return [line for line in render(result).splitlines() if line.strip()][:-1]

    plain = build(inventory, ef_flows, source_flows, mapping, methods).coverage
    linked = build(inventory, links.ef_flows, source_flows, links.bridge, links.methods).coverage
    linked = replace(linked, linking=bf.LINKING, link_lines=links.report.lines())
    return {"sentier-mappings": lines(plain), "brightway-flows": lines(linked)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=Path, required=True, help="Folder for the two exports")
    parser.add_argument("--out", type=Path, required=True, help="The comparison (JSON)")
    parser.add_argument("--data-root", help="A folder with the four data folders (no download)")
    parser.add_argument("--flow-links", type=Path, default=FLOW_LINKS)
    args = parser.parse_args(argv)
    result = {
        "date": date.today().isoformat(),
        "flow_links": args.flow_links.name,
        "flows": flows(args.data_root, args.flow_links),
        "scores": datasets(args.work, args.data_root, args.flow_links),
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
