"""What the build needs to follow patch 0010's links.

The script is `scripts/build_brightway_flows_targets.py`.
"""

import csv
import importlib.util
import re
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "build_brightway_flows_targets.py"
EF = "08a91e70-3ddc-11dd-9136-0050c2490048"
OTHER_EF = "fe0acd60-3ddc-11dd-a8a9-0050c2490048"
OUTSIDE = "a" * 40
TWO = "b" * 40
NONE = "c" * 40
OLD = "d" * 40


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("build_brightway_flows_targets", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def crosswalk_row(name, unit, source, target, key="as shipped"):
    return {
        "name": name,
        "category": "emissions to air",
        "subCategory": "unspecified",
        "unit": unit,
        "key": key,
        "exchanges": "1",
        "bafu_flow_uuid": source,
        "brightway_flow_id": target,
        "match": "closeMatch",
    }


def flow(identifier, source="EF 3.1", unit="kg"):
    return {
        "identifier": identifier,
        "source": source,
        "prefLabel": f"flow {identifier[:4]}",
        "context_iri": "https://vocab.brightway.one/flow-contexts/envi-air-unkn",
        "unit": unit,
    }


def association(source, target, multiplier=None):
    entry = {
        "xkos:sourceConcept": {"@id": f"https://vocab.brightway.one/bafu/2026-v1/flow/{source}"},
        "xkos:targetConcept": {"@id": f"https://vocab.brightway.dev/elementary-flows/{target}"},
    }
    if multiplier is not None:
        entry |= {
            "qudt:conversionMultiplier": multiplier,
            "brightway:conversionBasis": "unit-table",
        }
    return entry


def factor(identifier, category, source=None, derivation="sole", geography=None):
    return {
        "elementary_flow_uuid": identifier,
        "impact_category_id": category,
        "amount": 1.0,
        "geography": geography,
        "derivation": derivation,
        "source_flow_uuid": source,
    }


def release(associations):
    harmonised = {
        "flows": [
            flow(EF),
            flow(OTHER_EF),
            flow(OUTSIDE, "bafu algorithm addition", "kBq"),
            flow(TWO, "ecoinvent algorithm addition"),
            flow(NONE, "bafu algorithm addition"),
        ],
        "redirects": [
            {"identifier": OLD, "replaced_by_identifier": OTHER_EF},
            {"identifier": "e" * 40},  # withdrawn without a successor
        ],
        "correspondences": [
            {
                "@id": "https://vocab.brightway.dev/correspondences/agribalyse-3.2",
                "xkos:madeOf": [],
            },
            {
                "@id": "https://vocab.brightway.dev/correspondences/bafu-2026-v1",
                "xkos:madeOf": associations,
            },
        ],
    }
    method = {"name": "EF"}
    factors = {
        "impact_categories": [
            {"id": "own", "method": method, "version": "3.1", "implemented_by": "brightway-flows"},
            {"id": "jrc", "method": method, "version": "3.1", "implemented_by": "JRC"},
            {"id": "old", "method": method, "version": "3.0", "implemented_by": "brightway-flows"},
        ],
        "characterization_factors": [
            factor(EF, "own", source=OTHER_EF, derivation="carried"),  # a flow of EF 3.1: not asked
            factor(OUTSIDE, "own", source=EF, derivation="carried"),
            factor(OUTSIDE, "jrc", source=OTHER_EF),  # another implementation does not count
            factor(OUTSIDE, "old", source=OTHER_EF),  # nor another version
            factor(OUTSIDE, "own", source=OTHER_EF, geography="CH"),  # nor a factor of one place
            factor(TWO, "own", source=EF, derivation="carried"),
            factor(TWO, "own", source=OTHER_EF, derivation="restated"),
        ],
    }
    return harmonised, factors


def built(script, rows, associations):
    return script.targets(rows, *release(associations))


def test_each_row_of_the_crosswalk_gets_its_flow(script):
    rows = [
        crosswalk_row("Carbon dioxide", "kg", "s1", EF),
        crosswalk_row("Radon", "Bq", "s2", OUTSIDE),
    ]
    out = built(script, rows, [association("s1", EF), association("s2", OUTSIDE, 0.001)])
    assert [r["flow_id"] for r in out] == [EF, OUTSIDE]
    assert out[0]["flow_list"] == "EF 3.1" and out[0]["flow_unit"] == "kg"
    assert out[1]["flow_list"] == "bafu algorithm addition" and out[1]["flow_unit"] == "kBq"
    assert out[1]["flow_context"] == "envi-air-unkn"
    assert [r["name"] for r in out] == ["Carbon dioxide", "Radon"]
    assert tuple(out[0]) == script.FIELDS


def test_a_conversion_is_the_one_the_release_states_for_that_link(script):
    rows = [
        crosswalk_row("Radon", "Bq", "s2", OUTSIDE),
        crosswalk_row("Carbon dioxide", "kg", "s1", EF),
    ]
    out = built(script, rows, [association("s2", OUTSIDE, 0.001), association("s1", EF)])
    assert (out[0]["conversion"], out[0]["conversion_basis"]) == ("0.001", "unit-table")
    assert (out[1]["conversion"], out[1]["conversion_basis"]) == ("", "")
    # the release links this BAFU flow to another flow than the crosswalk does: what it says
    # about converting is about that other link, and is not taken
    out = built(script, rows[:1], [association("s2", NONE, 0.001)])
    assert out[0]["conversion"] == ""
    # nor is anything worked out where the release is silent
    out = built(script, rows[:1], [])
    assert out[0]["conversion"] == ""


def test_an_identifier_the_release_replaced_is_followed(script):
    out = built(
        script,
        [crosswalk_row("Fenpropimorph", "kg", "s3", OLD)],
        [association("s3", OTHER_EF, 2.0)],
    )
    assert out[0]["brightway_flow_id"] == OLD and out[0]["flow_id"] == OTHER_EF
    assert out[0]["conversion"] == "2.0"  # the release's statement is about the same flow
    assert script.current("x", {"x": "y", "y": "x"}) in {"x", "y"}  # a loop ends


def test_factors_come_from_one_named_flow_or_from_none(script):
    rows = [
        crosswalk_row("In EF", "kg", "s1", EF),
        crosswalk_row("One source", "Bq", "s2", OUTSIDE),
        crosswalk_row("Two sources", "kg", "s4", TWO),
        crosswalk_row("No source", "kg", "s5", NONE),
    ]
    out = {r["name"]: r for r in built(script, rows, [])}

    def named(name):
        row = out[name]
        return row["factors_from"], row["factors_unit"], row["factors_derivation"]

    # a flow of EF 3.1 has its own factors: nothing is named for it
    assert named("In EF") == ("", "", "")
    # only Brightway Flows' own implementation of EF 3.1 counts, and only without a geography;
    # the unit is the named flow's, so that a factor is taken over between equal units only
    assert named("One source") == (EF, "kg", "carried")
    assert named("Two sources") == ("", "", "carried+restated")
    assert named("No source") == ("", "", "")


def test_a_source_of_another_list_is_named_without_a_unit(script):
    """An adopted or restated factor names a flow of another implementation's own list. It
    is kept as named; its unit is not known here, and nothing is taken over from it."""
    harmonised, factors = release([])
    foreign = "9" * 8 + "-0000-4000-8000-000000000009"
    factors["characterization_factors"].append(
        factor(NONE, "own", source=foreign, derivation="adopted")
    )
    out = script.targets([crosswalk_row("Adopted", "kg", "s5", NONE)], harmonised, factors)
    assert out[0]["factors_from"] == foreign
    assert (out[0]["factors_unit"], out[0]["factors_derivation"]) == ("", "adopted")
    # a source the release replaced by another flow has that flow's unit
    factors["characterization_factors"][-1]["source_flow_uuid"] = OLD
    out = script.targets([crosswalk_row("Adopted", "kg", "s5", NONE)], harmonised, factors)
    assert (out[0]["factors_from"], out[0]["factors_unit"]) == (OLD, "kg")


def test_a_flow_the_release_does_not_hold_stops_the_build(script):
    with pytest.raises(script.SourceError, match="is not a flow of Brightway Flows"):
        built(script, [crosswalk_row("Gone", "kg", "s9", "f" * 40)], [])


def test_a_file_that_is_not_the_releases_is_refused(script, tmp_path):
    (tmp_path / "lcia-factors.json.gz").write_bytes(b"something else")
    with pytest.raises(script.SourceError, match="is not the file of Brightway Flows 1.1.0"):
        script.release_file("lcia-factors.json.gz", tmp_path)
    with pytest.raises(script.SourceError, match="is not there"):
        script.release_file("harmonised-flows-simple.json.gz", tmp_path)


def test_the_committed_file_follows_the_crosswalk_row_by_row(script):
    with open(script.CROSSWALK, newline="") as f:
        crosswalk = list(csv.DictReader(f))
    with open(script.TARGETS, newline="") as f:
        reader = csv.DictReader(f)
        assert tuple(reader.fieldnames) == script.FIELDS
        targets = list(reader)
    assert len(targets) == len(crosswalk)
    identifier = r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}|[0-9a-f]{40}"
    for mine, theirs in zip(targets, crosswalk, strict=True):
        for field in ("name", "category", "subCategory", "unit", "key", "brightway_flow_id"):
            assert mine[field] == theirs[field]
        assert re.fullmatch(identifier, mine["flow_id"])
        assert mine["flow_name"] and mine["flow_unit"] and mine["flow_list"]
        if mine["conversion"]:
            assert float(mine["conversion"]) > 0 and mine["conversion_basis"]
        if mine["flow_list"] == "EF 3.1":
            assert mine["factors_from"] == "" and mine["factors_derivation"] == ""
        if mine["factors_unit"]:
            # every flow that takes factors over is counted in the unit of its source
            assert mine["factors_from"] and mine["factors_unit"] == mine["flow_unit"]
        if mine["factors_from"]:
            # the flow named as the source is one flow; it need not be a flow of EF 3.1
            assert re.fullmatch(identifier, mine["factors_from"])
            assert mine["factors_derivation"]
    assert script.as_csv(targets) == script.TARGETS.read_text()
