"""The comparison of two builds, as the site shows it: `before-after.json`.

`compare_builds.py` writes everything it found (`comparison.json`). This writes the part a
reader of the site asks for, in the format every Sentier dataset site reads
(`scripts/runrecord/before_after.py`): which datasets' results moved, in which impact
categories, from what to what, and which import fix or patch explains it.

It holds results of single datasets, so it lists only so many (`LISTED`), the ones that
moved furthest first, and says how many it left out. BAFU's inventory is not in it: no
exchange, no amount.

Each step gets a claim that is worked out, not stated: every dataset whose supply chain
reaches what the step changed, in the methods the change can affect (the comparison's own
attribution). A score that moved outside every such reach is "not claimed", which is what the
comparison calls unexplained and fails on. The list of datasets a step reaches stays here;
the file says how many there are.

`index` writes the review of a run that also built contributions: the builds, what each
contains, and the pairs that were compared (`scripts/runrecord/review.py`).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runrecord import before_after, review  # noqa: E402

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


def text(value, limit) -> str:
    """A text as the format takes it: one line, no control character, not longer than `limit`."""
    cleaned = " ".join(
        "".join(c if ord(c) >= 32 and ord(c) != 127 else " " for c in str(value)).split()
    )
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip() + "…"


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


def derived_claim(name: str, reach: dict[str, dict[str, set]]) -> dict:
    """What a step can move, worked out by the comparison: per method, every dataset
    downstream of what the step changed. For a step that can move no score, that."""
    entries = [
        before_after.scope([method], set(by_step[name]))
        for method, by_step in reach.items()
        if by_step.get(name)
    ]
    if not entries:
        return before_after.claim(
            "Nothing this step changed can move a result: no amount, no supplier, and no "
            "flow that takes another factor.",
            derived=True,
            reach=0,
        )
    reached = set().union(*(entry["items"] for entry in entries))
    return before_after.claim(
        "Every dataset whose supply chain reaches what this step changed may move, in the "
        "impact categories the change can affect. Nothing else moves.",
        entries,
        derived=True,
        reach=len(reached),
    )


def causes_of(comparison: dict, steps: dict, moved_by: dict, reach: dict) -> tuple[list, dict]:
    """Every step that changed a row or moved a result, with what it changed and what it can
    move; and the id each is written under. A row that two steps explain together is listed
    under both names joined: such a pair has no reach and no count of its own."""
    rows = comparison["rows"]["by_step"]
    found, ids = [], {}
    for name in sorted(set(rows) | set(moved_by)):
        entry, step = rows.get(name, {}), steps.get(name, {})
        joined = " + " in name
        ids[name] = text(name, before_after.MAX_ID)
        found.append(
            before_after.cause(
                ids[name],
                kind=step.get("kind") or ("two steps together" if joined else None),
                title=text(step["description"], before_after.MAX_NAME)
                if step.get("description")
                else None,
                rows=entry.get("rows"),
                changed={k: v for k, v in entry.items() if k not in NOT_A_FIELD},
                items=entry.get("datasets"),
                moved=None if joined else moved_by.get(name, 0),
                claim=None if joined else derived_claim(name, reach),
            )
        )
    return found, ids


def account(
    comparison: dict,
    records: tuple[dict, dict],
    scores: tuple[dict, dict],
    moved: dict[str, dict[str, list[str]]],
    names: dict[str, dict],
    units: dict[str, str | None],
    steps: dict[str, dict],
    reach: dict[str, dict[str, set]] | None = None,
    listed: int = LISTED,
) -> dict:
    """The comparison in the shared format.

    `scores` are the two builds' results `{method: {code: value}}`, `moved` what the
    comparison found `{method: {code: [steps that explain it]}}`, `reach` what each step can
    move `{method: {step: datasets}}`, `names` each dataset's `{name, location}`, `steps` the
    patch run's steps by id.
    """
    before, after = scores
    methods = list(before)
    counted = {m["method"]: m for m in comparison["scores"]["methods"]}
    values = {
        m: {code: (before[m][code], after[m][code]) for code in before[m] if code in after[m]}
        for m in methods
    }
    explained: dict[str, set[str]] = {}
    for found in moved.values():
        for code, why in found.items():
            explained.setdefault(code, set()).update(why)
    moved_by: dict[str, int] = {}
    for why in explained.values():
        for name in why:
            moved_by[name] = moved_by.get(name, 0) + 1
    causes, ids = causes_of(comparison, steps, moved_by, reach or {})
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
    data = before_after.compare(
        title,
        one,
        other,
        ("dataset", "datasets"),
        [(m, name_of(m), SHORT.get(m), units.get(m)) for m in methods],
        values,
        names={
            code: {
                "name": text(about.get("name") or code, before_after.MAX_NAME),
                "place": text(about["location"], 60) if about.get("location") else None,
            }
            for code, about in names.items()
        },  # fmt: skip
        threshold=comparison["scores"]["tolerance"],
        floors=0.0,  # two builds of the same data: every difference above the threshold counts
        # no state is built twice, so nothing is said about how far two builds of one lie apart
        noise={"note": "Both builds were made in one run, on one machine."},
        causes=causes,
        item_causes={
            code: [ids[name] for name in why if name in ids] for code, why in explained.items()
        },
        unexplained={m: counted[m]["moved_by_step"].get("unexplained", 0) for m in methods},
        listed=listed,
        keep_items=False,  # which datasets a step reaches stays here; the file says how many
        step="comparison",
        indicator={"one": "impact category", "many": "impact categories"},
        rows={
            "one": "exchange",
            "many": "exchanges",
            "compared": rows["exchange_rows_compared"],
            "differ": rows["exchange_rows_changed"],
            "unexplained": rows["unexplained_count"],
        },
        notes=notes,
    )
    # this file and the comparison must say the same, or neither is to be believed
    for written in data["indicators"]:
        said = counted[written["id"]]
        if (written["compared"], written["moved"]) != (
            said["datasets_compared"],
            said["datasets_moved"],
        ):
            raise ValueError(
                f"{written['id']}: the comparison counted {said['datasets_moved']} moved of "
                f"{said['datasets_compared']}, this count gives {written['moved']} of "
                f"{written['compared']}"
            )
        outside = (written["classes"] or {}).get(before_after.NOT_CLAIMED, 0)
        if reach is not None and outside != written["unexplained"]:
            raise ValueError(
                f"{written['id']}: {outside} moved outside every step's reach, and the "
                f"comparison calls {written['unexplained']} unexplained"
            )
    return data


def index(
    out: Path, provider: dict, patched: dict, contributions: list[tuple[str, dict]], steps: dict
) -> dict:
    """The review of a run that built contributions beside the patched copy: the builds, what
    each contains, and the pairs that were compared. `provider` and `patched` are the two
    builds' records, `contributions` `(name, record)` of each contribution's build, `steps`
    the patch run's steps by id. The comparisons are read from where the run wrote them."""

    def compared(path):
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def identity(record):
        tools, release = record.get("tools") or {}, record.get("release") or {}
        return {
            "database": (record.get("databases") or {}).get("inventory"),
            "commit": str(tools.get("this repository") or "")[:12],
            "built": record.get("started"),
            "files built from": str(release.get("built_tree_sha256") or "")[:12],
            "flows linked through": record.get("linking"),
        }

    release = patched.get("release") or {}
    applied = [*release.get("import_fixes", {}), *release.get("patches", {})]
    main = compared(out / before_after.FILE)
    claims = {c["id"]: c.get("claim") for c in (main or {}).get("causes", [])}
    causes = [
        review.cause(
            text(name, before_after.MAX_ID),
            kind=(steps.get(name) or {}).get("kind"),
            title=text(steps[name]["description"], before_after.MAX_NAME)
            if (steps.get(name) or {}).get("description")
            else None,
            claim=claims.get(name),
        )
        for name in applied
    ]
    runs = [
        review.run(
            "provider", provider.get("label") or "provider release", identity=identity(provider)
        ),
        review.run(
            "patched", patched.get("label") or "patched copy", applied, identity=identity(patched)
        ),
    ]
    pairs = [review.pair("provider", "patched", page=before_after.FILE.replace(".json", ".html"),
                         classes=review.totals(main) if main else None)]  # fmt: skip
    for name, record in contributions:
        about = record.get("contribution") or {}
        step = about.get("step") or name
        found = compared(out / "contributions" / name / before_after.FILE)
        claim = next(
            (c.get("claim") for c in (found or {}).get("causes", []) if c["id"] == step), None
        )
        causes.append(
            review.cause(
                step,
                kind="contribution",
                title=text(about.get("title") or name, before_after.MAX_NAME),
                claim=claim,
            )
        )
        runs.append(
            review.run(
                name, record.get("label") or name, [*applied, step], identity=identity(record)
            )
        )
        page = f"{name}-before-after.html" if found else None
        classes = review.totals(found) if found else None
        pairs.append(review.pair("patched", name, page=page, classes=classes))
    return review.index("The patched copy and each contribution", runs, causes, pairs)
