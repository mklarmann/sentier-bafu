"""Write a CI job summary of a release run (`build_release.py release`).

Reads the run folder and writes Markdown: every step with its result, time and peak
memory; the provider build, the patched build and their comparison; the inputs whose
declared unit is not their supplier's; the export files with their checksums and whether
each read back; every contribution built beside the patched release; and the table of the
patch run. Everything it prints is counts, checksums, dataset codes, names and single
scores. The run folder holds BAFU's inventory and stays on the runner; the files a job may
keep are the ones the run set aside in its `results` folder.

Standard library only. A step that did not run is reported as such.
"""

import argparse
import json
from pathlib import Path

CLIMATE = "ef-3.1:climate-change"
NOT_PUBLISHED = (
    "The export files are produced and read back in CI but are not published until a download "
    "exists that asks for acceptance of BAFU's terms."
)


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


def comparison_lines(
    comparison: dict | None, title: str = "Patched against provider release"
) -> list[str]:
    if comparison is None:
        return [f"### {title}", "", "No comparison was written.", ""]
    rows, flows = comparison["rows"], comparison["elementary_flows"]
    observed = comparison.get("linked_on_the_declared_flow") or {"exchanges": 0}
    before = comparison["builds"]["baseline"]["database"]
    after = comparison["builds"]["candidate"]["database"]
    lines = [
        f"### {title}",
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
        lines += [f"| dataset | `{before}` | `{after}` |", "|---|---:|---:|"]
        for entry in climate["moved"][:10]:
            lines.append(
                f"| {entry['name']} ({entry['location']}) | {entry['before']:.4g} | "
                f"{entry['after']:.4g} |"
            )
    return [*lines, ""]


def step_lines(manifest: dict | None) -> list[str]:
    if manifest is None:
        return ["The run wrote no manifest.", ""]
    lines = [
        f"Run **{manifest['status']}**"
        + (f", tag `{manifest['tag']}`." if manifest["tag"] else ".")
    ]
    lines += ["", *(f"- {problem}" for problem in manifest["problems"])]
    if manifest["tag"] and manifest["not_releasable"]:
        lines += ["", "> [!CAUTION]", "> This run can't be published as a release:"]
        lines += [f"> - {reason}" for reason in manifest["not_releasable"]]
    lines += ["", "| step | result | seconds | peak memory, MB | |", "|---|---|---:|---:|---|"]
    for step in manifest["steps"]:
        seconds, memory = step["seconds"], step["peak_memory_mb"]
        lines.append(
            f"| {step['name']} | {step['status']} | "
            f"{'' if seconds is None else format(seconds, ',.0f')} | "
            f"{'' if memory is None else format(memory, ',.0f')} | "
            f"{(step['reason'] or '').replace('|', '/')} |"
        )
    return [*lines, ""]


def declared_unit_lines(manifest: dict | None) -> list[str]:
    declared = (manifest or {}).get("declared_units")
    if not declared:
        return []
    total = declared["exchanges_whose_declared_unit_is_not_the_suppliers"]
    lines = [
        "### Inputs whose declared unit is not their supplier's",
        "",
        f"{total:,} in the patched database. The build uses each amount as written; no unit "
        "is converted.",
        "",
    ]
    lines += [
        f"- {count:,}: {pair} (the same quantity under another label)"
        for pair, count in declared["same_quantity_other_label"].items()
    ]
    for row in declared["another_quantity"]:
        lines.append(
            f"- `{row['dataset_name']}` ({row['dataset_location']}) takes `{row['supplier_name']}` "
            f"({row['supplier_location']}): declared in {row['declared_unit']}, the supplier's "
            f"unit is {row['supplier_unit']}; amount used {row['amount_brightway_uses']:.6g}; "
            f"finding {row['finding'] or '**none recorded**'}"
        )
    return [*lines, ""]


def export_lines(title: str, folder: Path) -> list[str]:
    export = load(folder / "manifest.json")
    if export is None:
        return [f"### {title}", "", "No export was written.", ""]
    lines = [f"### {title}", "", f"Exports **{export['status']}**, labelled {export['label']}.", ""]
    lines += ["| format | written | read back | |", "|---|---|---|---|"]
    for kind, entry in export["formats"].items():
        check = export["checks"][kind]
        back = "matches" if check["passed"] else f"{check['total']:,} difference(s)"
        failed_to_write = entry.get("stage") == "write"
        lines.append(
            f"| {kind} | {'no' if failed_to_write else 'yes'} | "
            f"{'' if failed_to_write else back} | {(entry.get('error') or '').replace('|', '/')} |"
        )
    lines += ["", "| file | bytes | SHA-256 |", "|---|---:|---|"]
    lines += [
        f"| {entry['name']} | {entry['bytes']:,} | `{entry['sha256']}` |"
        for entry in export["files"].values()
    ]
    return [*lines, ""]


def summarise(run: Path) -> str:
    manifest = load(run / "manifest.json")
    lines = ["## Release build", "", *step_lines(manifest)]
    lines += build_lines("Provider release", run / "provider")
    lines += build_lines("Patched release", run / "patched")
    lines += comparison_lines(load(run / "comparison.json"))
    lines += declared_unit_lines(manifest)
    lines += export_lines("Exports of the patched release", run / "exports" / "patched")
    for folder in sorted((run / "contributions").glob("*/")):
        name = folder.name.upper()
        lines += build_lines(f"Contribution {name}, beside the patched release", folder / "build")
        lines += comparison_lines(
            load(folder / "comparison.json"), f"{name} against the patched release"
        )
        lines += export_lines(f"Exports of {name}", folder / "exports")
    kept = sorted(path.name for path in (run / "results").glob("*")) if run.is_dir() else []
    lines += [
        f"Kept from this run: {', '.join(kept) or 'nothing'} (counts, checksums, dataset "
        "codes, names and single scores). The build folders and the export files hold BAFU's "
        f"inventory and are not uploaded. {NOT_PUBLISHED}",
        "",
    ]
    table = run / "results" / "patch-run.md"
    if table.is_file():
        lines += [table.read_text(encoding="utf-8")]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run", type=Path, help="Folder of a release run")
    parser.add_argument("--out", type=Path, required=True, help="Markdown file to append to")
    args = parser.parse_args(argv)
    with args.out.open("a", encoding="utf-8") as stream:
        stream.write(summarise(args.run))
    print(f"Summary appended to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
