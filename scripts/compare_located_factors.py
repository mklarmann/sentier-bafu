"""Measure what the factors of single countries change.

BAFU has elementary flows that name a country (`Water, CH`). The installer links such a flow
to the flow of that country and gives it that country's factor in every method that has one
(`src/sentier_brightway/located.py`). This script builds BAFU's release both ways, with and
without that, scores every dataset in the 25 EF 3.1 categories and writes what differs:

* how many flows name a country, how many of them take a factor of their country, and in
  which methods;
* per category, how many datasets move by more than 1 % and by more than 10 %, and in which
  direction;
* with `--published-results FILE`: how each way agrees with BAFU's published LCIA results,
  for the categories in which a dataset moves. Matching those results is not a goal; they
  are a second reading of what a flow that names a country means.

Run it in this repository's environment, with the `brightway` extra:

    uv run --frozen --extra brightway \\
        python scripts/compare_located_factors.py --work output/located --out comparison.json

The data is at the installer's pins (`src/sentier_brightway/sources.toml`), downloaded once
and checked by SHA-256; `--data-root` takes a folder that already holds the four data
folders instead. `--work` receives two exports that hold BAFU's inventory: keep that folder
on your machine. The file written with `--out` holds counts and names of methods, and no
amount of any dataset.
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from compare_flow_linkings import pinned_data, relative  # noqa: E402

WITH, WITHOUT = "with the factors of countries", "with the factors without a location only"


def flows(data_root: Path) -> dict:
    """The flows that name a country, and which of them take a factor of their country."""
    from sentier_brightway.bridge import load_bridge
    from sentier_brightway.inventory import load_inventory
    from sentier_brightway.located import locate
    from sentier_brightway.methods import load_methods

    bridge, methods = load_bridge(data_root), load_methods(data_root)
    found = locate(bridge, methods)
    exchanges = load_inventory(data_root).exchanges
    bio = exchanges[exchanges["flow_type"] == "biosphere"]
    used = set(bio["flow"])
    named = {code for code, entry in bridge.items() if entry.target_location}
    located = {code for code in named if found.bridge[code].target_code in found.nodes}
    return {
        "flows_the_inventory_uses": len(used),
        "flows_that_name_a_country": len(named & used),
        "of_which_take_a_factor_of_their_country": len(located & used),
        "their_exchanges": int(bio["flow"].isin(located).sum()),
        "countries": len({found.nodes[found.bridge[code].target_code][1] for code in located}),
        "targets_of_a_country": len(found.nodes),
        "targets_with_the_methods_own_factor_of_the_country": dict(
            sorted(found.per_method.items())
        ),
        "name_a_country_no_method_has_a_factor_for": len((named - located) & used),
    }


def scores(work: Path, data_root: Path) -> tuple[dict, dict[str, Path]]:
    """Score every dataset both ways; per category, how many move and which way."""
    import numpy as np

    import sentier_brightway as sb
    from sentier_brightway.backtest import CATEGORIES
    from sentier_brightway.backtest.scorer import score_all

    frames, folders = {}, {}
    for name, located in ((WITH, True), (WITHOUT, False)):
        folders[name] = work / ("located" if located else "not-located")
        sb.import_files(folders[name], data_root=data_root, overwrite=True, include_located=located)
        frames[name] = score_all(folders[name], CATEGORIES).frame.set_index("code")
    plain = frames[WITHOUT]
    with_countries = frames[WITH].loc[plain.index]
    per_category, any_moved = [], np.zeros(len(plain), bool)
    for category in CATEGORIES:
        x = plain[category.short].to_numpy(float)
        y = with_countries[category.short].to_numpy(float)
        moved = relative(x, y) > 0.01
        any_moved |= moved
        if moved.any():
            per_category.append(
                {
                    "category": category.short,
                    "method": category.method_id,
                    "moved_over_1_percent": int(moved.sum()),
                    "moved_over_10_percent": int((relative(x, y) > 0.10).sum()),
                    "lower": int((moved & (np.abs(y) < np.abs(x))).sum()),
                    "higher": int((moved & (np.abs(y) > np.abs(x))).sum()),
                }
            )
    result = {
        "datasets": int(len(plain)),
        "moved_in_any_category_over_1_percent": int(any_moved.sum()),
        "categories_in_which_a_dataset_moves": per_category,
    }
    return result, folders


def published(folders: dict[str, Path], workbook: Path, work: Path, shorts: list[str]) -> dict:
    """How each way agrees with BAFU's published results, in the categories named."""
    import pandas as pd

    from sentier_brightway import backtest

    result = {}
    for name, folder in folders.items():
        out = work / f"published-{folder.name}"
        done = backtest.run_backtest(folder, workbook, out)
        table = pd.read_csv(out / backtest.VS_BAFU_CSV)
        per_category = {}
        for short in shorts:
            values = pd.to_numeric(table[short], errors="coerce").dropna()
            per_category[short] = {
                "compared": int(len(values)),
                "within_1_percent": round(float((values.abs() <= 1).mean()) * 100, 2),
                "within_5_percent": round(float((values.abs() <= 5).mean()) * 100, 2),
                "median_difference_percent": round(float(values.median()), 4),
            }
        result[name] = {"datasets_joined": done.n_mapped, "categories": per_category}
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=Path, required=True, help="Folder for the two exports")
    parser.add_argument("--out", type=Path, required=True, help="The comparison (JSON)")
    parser.add_argument("--data-root", type=Path, help="A folder with the four data folders")
    parser.add_argument(
        "--published-results",
        type=Path,
        metavar="FILE",
        help="BAFU's published LCIA results workbook (.xlsx or .zip); it is not in this repository",
    )
    args = parser.parse_args(argv)
    if args.data_root:
        root, used = args.data_root.resolve(), "supplied with --data-root"
    else:
        root, used = pinned_data()
    work = args.work.resolve()
    moved, folders = scores(work, root)
    result = {"date": date.today().isoformat(), "data": used, "flows": flows(root), "scores": moved}
    if args.published_results:
        shorts = [entry["category"] for entry in moved["categories_in_which_a_dataset_moves"]]
        result["against_published_results"] = published(
            folders, args.published_results.resolve(), work, shorts
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    found = result["flows"]
    print(
        f"{found['of_which_take_a_factor_of_their_country']} of "
        f"{found['flows_that_name_a_country']} flows that name a country take a factor of "
        f"their country; {moved['moved_in_any_category_over_1_percent']} of "
        f"{moved['datasets']} datasets move by more than 1 % in some category. "
        f"Written to {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
