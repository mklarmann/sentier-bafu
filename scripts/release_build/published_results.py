"""Summarise sentier-brightway's comparison with BAFU's published LCIA results.

`sentier-brightway backtest` scores every dataset in the 25 EF 3.1 categories and joins
BAFU's results workbook by dataset name and location. It writes `vs_bafu.csv` (one row per
dataset, the difference in percent per category) and `run_report.json`. This reads both and
writes a summary: how many datasets were joined, and per category how many were compared,
the share within 1 % and within 5 %, and the median difference.

Matching BAFU's published results is not a goal. The summary shows what a build changes.
Run it in the sentier-brightway environment (it needs pandas).
"""

import argparse
import json
from pathlib import Path

NOT_CATEGORIES = ("code", "name", "mapped_to", "type", "resolution", "name_ref", "mapped_to_ref")


def summarise(differences, counts: dict) -> dict:
    """`differences` is the `vs_bafu.csv` table; `counts` the run report's counts."""
    import pandas as pd

    categories = {}
    for column in differences.columns:
        if column in NOT_CATEGORIES:
            continue
        values = pd.to_numeric(differences[column], errors="coerce").dropna()
        if values.empty:
            categories[column] = {"compared": 0}
            continue
        categories[column] = {
            "compared": int(len(values)),
            "within_1_percent": round(float((values.abs() <= 1).mean()) * 100, 2),
            "within_5_percent": round(float((values.abs() <= 5).mean()) * 100, 2),
            "median_difference_percent": round(float(values.median()), 4),
        }
    return {
        "datasets": counts.get("processes"),
        "published_rows": counts.get("reference_rows"),
        "joined": counts.get("mapped"),
        "not_joined": counts.get("unmatched"),
        "unit_not_convertible": counts.get("unit_skipped"),
        "categories": categories,
    }


def main(argv: list[str] | None = None) -> int:
    import pandas as pd

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path, help="Output folder of `sentier-brightway backtest`")
    parser.add_argument("--out", type=Path, required=True, help="Summary JSON to write")
    args = parser.parse_args(argv)
    counts = json.loads((args.folder / "run_report.json").read_text()).get("counts", {})
    summary = summarise(pd.read_csv(args.folder / "vs_bafu.csv"), counts)
    args.out.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"{summary['joined']} of {summary['datasets']} datasets joined; {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
