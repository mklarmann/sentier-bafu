"""The comparison of two builds, as the site shows it: `before-after.json`.

`compare_builds.py` writes everything it found (`comparison.json`). This writes the part a
reader of the site asks for, in the format every Sentier dataset site reads
(`scripts/runrecord/before_after.py`): which datasets' results moved, in which impact
categories, from what to what, and which import fix or patch explains it.

It holds results of single datasets, so it lists only so many (`LISTED`), the ones that
moved furthest first, and says how many it left out. BAFU's inventory is not in it: no
exchange, no amount.
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runrecord import before_after  # noqa: E402

#: Datasets listed with their results. A page of the site shows them, so the list is short.
LISTED = 200
DIGITS = 6
#: How each EF 3.1 method is called in the head of a narrow column.
SHORT = {
    "ef-3.1:acidification": "Acidification",
    "ef-3.1:climate-change": "Climate",
    "ef-3.1:climate-change-biogenic": "Climate, biogenic",
    "ef-3.1:climate-change-fossil": "Climate, fossil",
    "ef-3.1:climate-change-land-use-and-land-use-change": "Climate, land use",
    "ef-3.1:ecotoxicity-freshwater": "Ecotox., freshwater",
    "ef-3.1:ecotoxicity-freshwater-inorganics": "Ecotox., inorganics",
    "ef-3.1:ecotoxicity-freshwater-organics": "Ecotox., organics",
    "ef-3.1:ef-particulate-matter": "Particulate matter",
    "ef-3.1:eutrophication-freshwater": "Eutroph., freshwater",
    "ef-3.1:eutrophication-marine": "Eutroph., marine",
    "ef-3.1:eutrophication-terrestrial": "Eutroph., terrestrial",
    "ef-3.1:human-toxicity-cancer": "Toxicity, cancer",
    "ef-3.1:human-toxicity-cancer-inorganics": "Tox., cancer, inorg.",
    "ef-3.1:human-toxicity-cancer-organics": "Tox., cancer, org.",
    "ef-3.1:human-toxicity-non-cancer": "Toxicity, non-cancer",
    "ef-3.1:human-toxicity-non-cancer-inorganics": "Tox., non-c., inorg.",
    "ef-3.1:human-toxicity-non-cancer-organics": "Tox., non-c., org.",
    "ef-3.1:ionising-radiation-human-health": "Ionising radiation",
    "ef-3.1:land-use": "Land use",
    "ef-3.1:ozone-depletion": "Ozone depletion",
    "ef-3.1:photochemical-ozone-formation-human-health": "Ozone formation",
    "ef-3.1:resource-use-fossils": "Fossil resources",
    "ef-3.1:resource-use-minerals-and-metals": "Minerals, metals",
    "ef-3.1:water-use": "Water use",
}
#: Names the id of a method does not give as a reader writes them.
NAMES = {
    "ef-3.1:climate-change-biogenic": "Climate change, biogenic",
    "ef-3.1:climate-change-fossil": "Climate change, fossil",
    "ef-3.1:climate-change-land-use-and-land-use-change": (
        "Climate change, land use and land use change"
    ),
    "ef-3.1:ecotoxicity-freshwater": "Ecotoxicity, freshwater",
    "ef-3.1:ecotoxicity-freshwater-inorganics": "Ecotoxicity, freshwater, inorganics",
    "ef-3.1:ecotoxicity-freshwater-organics": "Ecotoxicity, freshwater, organics",
    "ef-3.1:ef-particulate-matter": "Particulate matter",
    "ef-3.1:eutrophication-freshwater": "Eutrophication, freshwater",
    "ef-3.1:eutrophication-marine": "Eutrophication, marine",
    "ef-3.1:eutrophication-terrestrial": "Eutrophication, terrestrial",
    "ef-3.1:human-toxicity-cancer": "Human toxicity, cancer",
    "ef-3.1:human-toxicity-cancer-inorganics": "Human toxicity, cancer, inorganics",
    "ef-3.1:human-toxicity-cancer-organics": "Human toxicity, cancer, organics",
    "ef-3.1:human-toxicity-non-cancer": "Human toxicity, non-cancer",
    "ef-3.1:human-toxicity-non-cancer-inorganics": "Human toxicity, non-cancer, inorganics",
    "ef-3.1:human-toxicity-non-cancer-organics": "Human toxicity, non-cancer, organics",
    "ef-3.1:ionising-radiation-human-health": "Ionising radiation, human health",
    "ef-3.1:photochemical-ozone-formation-human-health": (
        "Photochemical ozone formation, human health"
    ),
    "ef-3.1:resource-use-fossils": "Resource use, fossils",
    "ef-3.1:resource-use-minerals-and-metals": "Resource use, minerals and metals",
}
NOT_A_FIELD = ("rows", "datasets")


def name_of(method: str) -> str:
    """A method's name: the one of `NAMES`, or its id in words (`x:water-use` is "Water use")."""
    if method in NAMES:
        return NAMES[method]
    words = method.rpartition(":")[2].replace("-", " ").strip()
    return words[:1].upper() + words[1:]


def rounded(value):
    """A result with `DIGITS` significant digits; None for one that is not a number."""
    if value is None or not math.isfinite(value):
        return None
    if value == 0:
        return 0.0
    return round(value, DIGITS - 1 - int(math.floor(math.log10(abs(value)))))


def distance(pair) -> float:
    """How far a pair of results lies from no change: the size of log10(after / before);
    a result of another sign, or of zero on one side, counts as a factor of 100."""
    found = before_after.ratio(*pair)
    if found is None:
        return 0.0 if pair[0] == pair[1] else 2.0
    return abs(math.log10(found))


def sides(baseline: dict, candidate: dict) -> tuple[str, tuple, tuple]:
    """The title of the comparison and its two sides, from the two builds' own records."""
    release = (candidate.get("release") or {}).get("name") or "the release"
    names = {key: (build.get("databases") or {}).get("inventory") for key, build in
             (("before", baseline), ("after", candidate))}  # fmt: skip
    patched = (
        "Patched copy",
        f"{release} with the import fixes and the community patches: database "
        f"`{names['after'] if not candidate.get('contribution') else names['before']}`.",
    )
    contribution = candidate.get("contribution")
    if contribution:
        after = (
            f"Contribution {contribution['id']}",
            f"The patched copy plus that one contribution ({contribution['standing']}): "
            f"database `{names['after']}`.",
        )
        return f"The patched copy and contribution {contribution['id']}", patched, after
    before = (release, f"As BAFU ships it, without a patch: database `{names['before']}`.")
    return f"{release} and the patched copy", before, patched


def causes_of(comparison: dict, steps: dict, moved_by: dict[str, int]) -> list[dict]:
    """Every step that changed a row or moved a result, with what it changed. A row that
    two steps explain together is listed under both names joined."""
    rows = comparison["rows"]["by_step"]
    found = []
    for name in sorted(set(rows) | set(moved_by)):
        entry, step = rows.get(name, {}), steps.get(name, {})
        found.append(
            before_after.cause(
                name,
                kind=step.get("kind") or ("two steps together" if " + " in name else None),
                title=(step.get("description") or "").strip()[:300] or None,
                rows=entry.get("rows"),
                changed={k: v for k, v in entry.items() if k not in NOT_A_FIELD},
                items=entry.get("datasets"),
                moved=moved_by.get(name, 0),
            )
        )
    return found


def account(
    comparison: dict,
    records: tuple[dict, dict],
    scores: tuple[dict, dict],
    moved: dict[str, dict[str, list[str]]],
    names: dict[str, dict],
    units: dict[str, str | None],
    steps: dict[str, dict],
    listed: int = LISTED,
) -> dict:
    """The comparison in the shared format.

    `scores` are the two builds' results `{method: {code: value}}`, `moved` what the
    comparison found `{method: {code: [steps that explain it]}}`, `names` each dataset's
    `{name, location}`, `steps` the patch run's steps by id.
    """
    before, after = scores
    methods = list(before)
    threshold = comparison["scores"]["tolerance"]
    counted = {m["method"]: m for m in comparison["scores"]["methods"]}
    indicators = []
    for method in methods:
        codes = sorted(set(before[method]) & set(after[method]))
        pairs = [(before[method][code], after[method][code]) for code in codes]
        counts = before_after.tally(pairs, threshold, floor=0.0, bands=True)
        said = counted[method]
        if (counts["compared"], counts["moved"]) != (
            said["datasets_compared"],
            said["datasets_moved"],
        ):
            raise ValueError(
                f"{method}: the comparison counted {said['datasets_moved']} moved of "
                f"{said['datasets_compared']}, this count gives {counts['moved']} of "
                f"{counts['compared']}"
            )
        indicators.append(
            before_after.indicator(
                method,
                name_of(method),
                counts,
                short=SHORT.get(method),
                unit=units.get(method),
                unexplained=said["moved_by_step"].get("unexplained", 0),
            )
        )

    explained: dict[str, set[str]] = {}
    for found in moved.values():
        for code, why in found.items():
            explained.setdefault(code, set()).update(why)
    moved_by: dict[str, int] = {}
    for why in explained.values():
        for name in why:
            moved_by[name] = moved_by.get(name, 0) + 1

    def values(code):
        return {m: (rounded(before[m].get(code)), rounded(after[m].get(code))) for m in methods}

    furthest = sorted(
        explained,
        key=lambda code: (-max(distance(pair) for pair in values(code).values()), code),
    )
    known = set(comparison["rows"]["by_step"]) | set(moved_by)
    items = [
        before_after.item(
            code,
            (names.get(code) or {}).get("name") or code,
            values(code),
            place=(names.get(code) or {}).get("location"),
            causes=sorted(explained[code] & known),
        )
        for code in furthest[:listed]
    ]
    rows, corrected = comparison["rows"], comparison["linked_on_the_declared_flow"]
    notes = []
    if corrected["exchanges"]:
        notes.append(
            f"{corrected['exchanges']} elementary exchanges whose name or compartment a patch "
            "corrects are linked on the flow as BAFU declared it, so the correction changes "
            "the label and moves no result."
        )
    lost = comparison["elementary_flows"]["exchanges_that_lost_their_ef_3_1_flow"]
    if lost:
        notes.append(f"{lost} elementary exchanges lost the flow that gives them a factor.")
    title, one, other = sides(*records)
    return before_after.account(
        title,
        one,
        other,
        ("dataset", "datasets", comparison["builds"]["candidate"]["datasets"], len(explained)),
        indicators,
        step="comparison",
        indicator={"one": "impact category", "many": "impact categories"},
        threshold=threshold,
        bands=before_after.BANDS,
        causes=causes_of(comparison, steps, moved_by),
        rows={
            "one": "exchange",
            "many": "exchanges",
            "compared": rows["exchange_rows_compared"],
            "differ": rows["exchange_rows_changed"],
            "unexplained": rows["unexplained_count"],
        },
        moved=items,
        moved_not_listed=max(0, len(explained) - listed),
        notes=notes,
    )
