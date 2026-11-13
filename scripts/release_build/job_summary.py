"""Write a CI job summary of two builds and their comparison, and collect what may be kept.

Reads the provider build, the patched build and the comparison, writes a Markdown summary
(counts, findings, the steps' times, what the patches change), and copies the two audits and
the comparison into one folder: the only files a CI job keeps. They hold counts, dataset
codes, names and single scores. The build folders hold BAFU's inventory and stay on the
runner.

Standard library only. A build that did not get as far as its audit is reported as such.
"""

import argparse
import json
import shutil
from pathlib import Path

CLIMATE = "ef-3.1:climate-change"


def load(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.is_file() else None


def build_lines(name: str, folder: Path) -> list[str]:
    record, audit = load(folder / "build.json"), load(folder / "audit" / "audit.json")
    if record is None:
        return [f"### {name}", "", "The build did not start.", ""]
    lines = [f"### {name}", ""]
    lines.append(f"Build **{record['status']}**; database `{record['databases']['inventory']}`.")
    if record.get("error"):
        lines += ["", "```", record["error"][-1500:], "```"]
    if audit is not None:
        built_from = audit.get("built_from") or {}
        exchanges, targets = audit["exchanges"], audit["biosphere_targets"]
        unlinked = sum(audit["unlinked"].values())
        lines += [
            "",
            f"Audit **{audit['status']}**. Label: {built_from.get('label', 'none')}; "
            f"{len(built_from.get('patches') or [])} patches.",
            "",
            "| | |",
            "|---|---|",
            f"| datasets | {audit['datasets']:,} |",
            f"| production, technosphere, elementary exchanges | {exchanges['production']:,}, "
            f"{exchanges['technosphere']:,}, {exchanges['biosphere']:,} |",
            f"| unlinked exchanges | {unlinked:,} |",
            f"| elementary exchanges on an EF 3.1 flow | {targets['ef_3_1']:,} |",
            f"| elementary exchanges without one | {targets['no_ef_3_1_flow']:,} |",
        ]
        for kind in ("errors", "findings"):
            if audit[kind]:
                lines += ["", f"**{kind.capitalize()}**", ""]
                lines += [f"- {text}" for text in audit[kind]]
    if record.get("steps"):
        lines += ["", "| step | seconds | peak memory, MB |", "|---|---:|---:|"]
        for step, result in record["steps"].items():
            memory = result["peak_memory_mb"]
            lines.append(
                f"| {step} | {result['seconds']:.0f} | "
                f"{'' if memory is None else format(memory, ',.0f')} |"
            )
    published = record.get("published_results")
    if published:
        text = published.get("reason") or f"{published.get('joined'):,} datasets joined"
        lines += ["", f"Comparison with BAFU's published results: {published['status']} ({text})."]
    return [*lines, ""]


def comparison_lines(comparison: dict | None) -> list[str]:
    if comparison is None:
        return ["### Patched against provider release", "", "No comparison was written.", ""]
    rows, flows = comparison["rows"], comparison["elementary_flows"]
    observed = comparison.get("linked_on_the_declared_flow") or {"exchanges": 0}
    lines = [
        "### Patched against provider release",
        "",
        f"Comparison **{comparison['status']}**.",
        "",
        f"- {rows['exchange_rows_changed']:,} of {rows['exchange_rows_compared']:,} exchange "
        f"rows differ; {rows['unexplained_count']} have no explanation.",
        f"- {observed['exchanges']:,} elementary exchanges that a patch corrects are linked "
        "on the flow BAFU declared.",
        f"- {flows['exchanges_that_lost_their_ef_3_1_flow']:,} elementary exchanges lost "
        "their EF 3.1 flow.",
    ]
    lines += [f"- {text}" for text in comparison["errors"]]
    lines += ["", "| step | rows | datasets |", "|---|---:|---:|"]
    for step, counts in rows["by_step"].items():
        lines.append(f"| {step} | {counts['rows']:,} | {counts['datasets']:,} |")
    lines += ["", "| method | datasets whose score moves | attributed to |", "|---|---:|---|"]
    for method in comparison["scores"]["methods"]:
        steps = ", ".join(f"{step}: {n:,}" for step, n in method["moved_by_step"].items())
        lines.append(f"| {method['method']} | {method['datasets_moved']:,} | {steps} |")
    climate = next((m for m in comparison["scores"]["methods"] if m["method"] == CLIMATE), None)
    if climate and climate["moved"]:
        lines += ["", "Climate change, kg CO2 eq per unit:", ""]
        lines += ["| dataset | provider | patched |", "|---|---:|---:|"]
        for entry in climate["moved"][:10]:
            lines.append(
                f"| {entry['name']} ({entry['location']}) | {entry['before']:.4g} | "
                f"{entry['after']:.4g} |"
            )
    return [*lines, ""]


def summarise(provider: Path, patched: Path, comparison: Path) -> str:
    lines = ["## Release build", ""]
    lines += build_lines("Provider release", provider)
    lines += build_lines("Patched release", patched)
    lines += comparison_lines(load(comparison))
    lines += [
        "Kept from this run: the two audits and the comparison (counts, dataset codes, names "
        "and single scores). The build folders hold BAFU's inventory and are not uploaded.",
        "",
    ]
    return "\n".join(lines)


def collect(provider: Path, patched: Path, comparison: Path, results: Path) -> list[str]:
    """Copy the audits and the comparison into `results`; return the names written."""
    results.mkdir(parents=True, exist_ok=True)
    wanted = {
        "provider-audit.json": provider / "audit" / "audit.json",
        "patched-audit.json": patched / "audit" / "audit.json",
        "comparison.json": comparison,
    }
    written = []
    for name, source in wanted.items():
        if source.is_file():
            shutil.copyfile(source, results / name)
            written.append(name)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--provider", type=Path, required=True, help="Provider build folder")
    parser.add_argument("--patched", type=Path, required=True, help="Patched build folder")
    parser.add_argument("--comparison", type=Path, required=True, help="comparison.json")
    parser.add_argument("--out", type=Path, required=True, help="Markdown file to append to")
    parser.add_argument("--results", type=Path, required=True, help="Folder for the kept files")
    args = parser.parse_args(argv)
    with args.out.open("a", encoding="utf-8") as stream:
        stream.write(summarise(args.provider, args.patched, args.comparison))
    written = collect(args.provider, args.patched, args.comparison, args.results)
    print(f"Summary appended to {args.out}; kept: {', '.join(written) or 'nothing'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
