"""The comparison of the builds, as a chain of states in the format of sentier-diagnostics.

`compare_builds.py` finds what changed between two builds and explains it (`comparison.json`).
This writes what it found as `diagnostics.json`, in the format every Sentier dataset repository
writes (sentier-dev/sentier-diagnostics, `sentier-diagnostics/1`): the results of every dataset
in every impact category in each state, one class per value by one counting rule, and each
step held against its claim.

The chain of a run's own comparison has three states and two steps:

1. BAFU's release with the world's factors (`build --skip-located`), then with the countries'
   factors: a flow that names a country takes that country's factor. The claim of that step
   is read from the build, not written by hand: the categories in which a country's own
   factor is used (`located_by_method` of the install report). On BAFU:2026 v1 those are
   water use and land use.
2. BAFU's release, then the patched copy: the import fixes and the community patches,
   applied together. Its claim is the comparison's own reach: every dataset whose supply
   chain reaches what a step changed may move, in the categories the change can affect.
   The list of those datasets stays here (`claim_lists=False`); the file says how many.

Without a build of the world's factors the chain has the last two states only. A
contribution's comparison is the patched copy, then the patched copy with that contribution.

Noise is not measured: no state is built twice in a run. The file says so.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from release_build import before_after_account  # noqa: E402

LISTED = before_after_account.LISTED
#: What the comparison counts as moved. The steps of the chain use it too, so that a value
#: the comparison calls unexplained is never one the chain calls "agrees".
TOLERANCE_NOTE = "the threshold of the comparison of two builds (compare_builds.py)"


class ChainError(ValueError):
    """A chain this module refuses to write."""


def read_json(path: Path):
    # Two clauses, not one of two errors: the formatter writes such a clause without its
    # parentheses, which Python 3.12 can't read, and the build starts on 3.12.
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def scores_of(build: Path, methods: list[str], codes: list[str]) -> dict:
    """`{method: {code: score}}` of one build's audit, for the datasets compared."""
    import pandas as pd

    frame = pd.read_csv(Path(build) / "audit" / "scores.csv").set_index("code")
    missing = [m for m in methods if m not in frame.columns]
    if missing:
        raise ChainError(f"{build}: the audit has no scores in {', '.join(missing)}")
    return {
        m: {c: (float(frame.at[c, m]) if c in frame.index else None) for c in codes}
        for m in methods
    }


def located_by_method(build: Path) -> list[str] | None:
    """The categories in which a flow that names a country takes that country's own factor,
    from the install report of a build; None where the report does not say."""
    report = read_json(Path(build) / "logs" / "install-report.json") or {}
    found = (report.get("coverage") or {}).get("located_by_method")
    if found is None:
        return None
    return sorted(method for method, n in found if n)


def reach_claim(reach: dict[str, dict[str, set]], text: str) -> dict:
    """The claim of a step whose scope is the comparison's reach, per category."""
    from sentier_diagnostics import claims

    entries = [
        claims.scope([method], set().union(*by_step.values()), "any", None, claims.MAY)
        for method, by_step in sorted(reach.items())
        if by_step and set().union(*by_step.values())
    ]
    union = set().union(*(e["items"] for e in entries)) if entries else set()
    return claims.claim(
        text, entries, by=claims.origin("code", "compare_builds.py, reach"), reach=len(union)
    )


def chain(
    comparison: dict,
    records: tuple[dict, dict],
    scores: tuple[dict, dict],
    names: dict[str, dict],
    units: dict[str, str | None],
    steps: dict[str, dict],
    reach: dict[str, dict[str, set]],
    item_units: dict[str, str | None],
    world: Path | None = None,
    candidate: Path | None = None,
    listed: int = LISTED,
) -> dict:
    """The chain of one comparison, checked by sentier-diagnostics. `world` is the build of
    BAFU's release with the world's factors, `candidate` the build whose install report names
    the categories of the countries' factors (the build of BAFU's release)."""
    from sentier_diagnostics import chain as build_chain
    from sentier_diagnostics import claims

    before, after = scores
    methods = list(before)
    codes = sorted(set().union(*(set(v) for v in before.values())))
    title, one, other = before_after_account.sides(*records)
    contribution = (records[1] or {}).get("contribution")
    tolerance = build_chain.tolerance(comparison["scores"]["tolerance"], "declared", TOLERANCE_NOTE)
    not_measured = build_chain.noise(note="No state is built twice in a run.")

    def state(id_, side, record):
        tools = (record or {}).get("tools") or {}
        identity = {
            "commit": str(tools.get("this repository") or "")[:12] or None,
            "database": ((record or {}).get("databases") or {}).get("inventory"),
            "machine": tools.get("platform"),
        }
        return build_chain.state(
            id_, side[0], about=side[1], identity={k: str(v) for k, v in identity.items() if v}
        )

    fixes = [s for s in steps.values() if s.get("kind") in ("import fix", "patch")]
    if contribution:
        step_text = (
            f"Contribution {contribution['id']}, applied to the patched copy. Every dataset "
            "whose supply chain reaches an input it changed may move, in every category. "
            "Nothing else moves."
        )
        last = build_chain.step(
            "contribution", f"Contribution {contribution['id']}", kind="contribution",
            about=(contribution.get("title") or None), claim=reach_claim(reach, step_text),
            tolerance=tolerance, noise=not_measured,
        )  # fmt: skip
    else:
        n_fix = sum(1 for s in fixes if s["kind"] == "import fix")
        n_patch = sum(1 for s in fixes if s["kind"] == "patch")
        last = build_chain.step(
            "fixes", "Import fixes and patches", kind="fix",
            about=f"{n_fix} import fixes and {n_patch} community patches, applied together; "
            "they are not built one at a time.",
            claim=reach_claim(
                reach,
                "Every dataset whose supply chain reaches what an import fix or patch changed may "
                "move, in the categories the change can affect. Nothing else moves.",
            ),
            tolerance=tolerance, noise=not_measured,
        )  # fmt: skip
    states = [state("before", one, records[0]), state("after", other, records[1])]
    values = {"before": before, "after": after}
    steps_out = [last]
    if world is not None and not contribution:
        categories = located_by_method(candidate) if candidate else None
        if categories is None:
            raise ChainError(
                "the install report of BAFU's release does not say in which categories a "
                "country's own factor is used (coverage.located_by_method)"
            )
        unknown = sorted(set(categories) - set(methods))
        if unknown:
            raise ChainError(
                f"the countries' factors are used in categories not compared: {unknown}"
            )
        # in words, the category a reader looks for first ("water use and land use")
        words = sorted(
            (before_after_account.name_of(m).lower() for m in categories),
            key=lambda word: (word != "water use", word),
        )
        names_of = " and ".join([", ".join(words[:-1]), words[-1]] if len(words) > 1 else words)
        located = build_chain.step(
            "located-factors", "The countries' factors", kind="method",
            about="A flow that names a country takes that country's factor instead of the world's.",
            claim=claims.claim(
                f"{names_of[:1].upper() + names_of[1:]} may move; nothing else moves."
                if categories else "Nothing moves.",
                [claims.scope(categories, "*", "any", None, claims.MAY)] if categories else [],
                by=claims.origin("code", "install report, located_by_method"),
            ),
            tolerance=tolerance, noise=not_measured,
        )  # fmt: skip
        world_record = read_json(Path(world) / "build.json") or {}
        world_side = (
            "BAFU's release, the world's factors",
            "Every elementary flow on the world's factor, also one that names a country.",
        )
        states.insert(0, state("world", world_side, world_record))
        values = {"world": scores_of(world, methods, codes), **values}
        steps_out = [located, last]
    corrected = comparison["linked_on_the_declared_flow"]["exchanges"]
    notes = []
    if corrected:
        notes.append(
            f"{corrected} elementary exchanges whose name or compartment a patch corrects are "
            "linked on the flow as BAFU declared it, so the correction changes the label and "
            "moves no result."
        )
    data = build_chain.build(
        title,
        about="The builds of one run, compared score by score in every impact category.",
        indicators=[
            (m, before_after_account.name_of(m), before_after_account.SHORT.get(m), units.get(m))
            for m in methods
        ],  # fmt: skip
        states=states,
        steps=steps_out,
        values=values,
        units=item_units,
        names={
            c: {
                "name": (names.get(c) or {}).get("name") or c,
                "place": (names.get(c) or {}).get("location"),
                "group": None,
            }
            for c in codes
        },  # fmt: skip
        item_word=("dataset", "datasets"),
        listed=listed,
        audience="public",
        claim_lists=False,
        notes=notes,
    )
    # the chain and the comparison must agree on what nothing explains, or neither is believed
    unexplained = sum(
        m["moved_by_step"].get("unexplained", 0) for m in comparison["scores"]["methods"]
    )
    outside = sum(
        (block.get("verdicts") or {}).get("not claimed", 0)
        for block in data["counts"]["steps"][last["id"]].values()
    )
    if outside > unexplained:
        raise ChainError(
            f"{outside} values moved outside the reach of every step, and the comparison calls "
            f"{unexplained} unexplained"
        )
    return data


def write(data: dict, path: Path) -> Path:
    from sentier_diagnostics import chain as build_chain

    return build_chain.write(data, Path(path))
