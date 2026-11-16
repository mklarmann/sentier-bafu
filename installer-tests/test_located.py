"""A flow that names a country takes that country's factor (``located.py``)."""

import json
from types import MappingProxyType

import pytest
from conftest import B1, B2, CLIMATE, E1, E2, FLOWS, IONISING, P1, P1_CLIMATE_SCORE

import sentier_brightway
from sentier_brightway import cli
from sentier_brightway.bridge import BridgeEntry, load_bridge
from sentier_brightway.constants import BIOSPHERE_DB
from sentier_brightway.located import locate, located_code
from sentier_brightway.methods import MethodSpec, load_methods

E1_DE = located_code(E1, "DE")


def spec(method_id, cfs, located=None):
    return MethodSpec(
        key=("sentier", "EF v3.1", method_id),
        method_id=method_id,
        unit="x",
        description="",
        cfs=tuple(cfs.items()),
        flow_context=MappingProxyType({}),
        flow_name=MappingProxyType({}),
        located=MappingProxyType(located or {}),
    )


def entry(code, location=None):
    return BridgeEntry(target_code=code, target_unit="kilogram", target_location=location)


def test_the_methods_reader_keeps_the_factors_of_single_countries(data_root):
    climate, ionising = load_methods(data_root)
    # the made-up climate method has a factor of 2.0 for E1 in DE beside the 1.0 without one
    assert dict(climate.cfs) == {E1: 1.0}
    assert dict(climate.located) == {(E1, "DE"): 2.0}
    assert dict(ionising.located) == {}


def test_a_flow_that_names_a_country_takes_that_countrys_factor():
    bridge = {"water-de": entry("w", "DE"), "water": entry("w"), "other": entry("o", "DE")}
    methods = (
        spec("water-use", {"w": 40.0}, {("w", "DE"): 1.5, ("w", "FR"): 9.0}),
        spec("land-use", {"w": 7.0, "o": 3.0}),  # knows the flow, has no factor of DE
        spec("climate", {"c": 1.0}),  # does not know the flow
    )
    found = locate(bridge, methods)
    key = located_code("w", "DE")
    assert found.nodes == {key: ("w", "DE")}
    # the flow that names DE moves to the target of its own; the others stay
    assert found.bridge["water-de"].target_code == key
    assert found.bridge["water-de"].target_location == "DE"
    assert found.bridge["water"].target_code == "w"
    # "o" names DE too, and no method has a factor of DE for it: it keeps its target
    assert found.bridge["other"].target_code == "o"
    assert (found.flows, found.flows_without) == (1, 1)
    water, land, climate = (dict(m.cfs) for m in found.methods)
    assert water == {"w": 40.0, key: 1.5}  # the country's own factor
    assert land == {"w": 7.0, "o": 3.0, key: 7.0}  # the factor without a location
    assert climate == {"c": 1.0}  # still none
    assert found.per_method == {"water-use": 1}
    # no factor of a country nobody names is installed
    assert all("FR" not in code for m in found.methods for code, _ in m.cfs)


def test_two_flows_of_one_country_share_one_target_and_a_second_pass_changes_nothing():
    bridge = {"a": entry("w", "DE"), "b": entry("w", "DE")}
    methods = (spec("water-use", {"w": 40.0}, {("w", "DE"): 1.5}),)
    once = locate(bridge, methods)
    assert len(once.nodes) == 1 and once.flows == 2
    twice = locate(once.bridge, once.methods)
    assert twice.bridge == once.bridge
    assert (dict(twice.nodes), twice.flows, twice.flows_without) == (dict(once.nodes), 2, 0)
    assert [dict(m.cfs) for m in twice.methods] == [dict(m.cfs) for m in once.methods]


def test_without_a_named_country_nothing_changes():
    bridge = {"a": entry("w")}
    methods = (spec("water-use", {"w": 40.0}, {("w", "DE"): 1.5}),)
    found = locate(bridge, methods)
    assert found.bridge is bridge and found.methods is methods
    assert (dict(found.nodes), found.flows, found.flows_without) == ({}, 0, 0)


def name_the_country(data_root, source_code=B1, location="DE"):
    """Make the made-up mapping state a country for one flow, as sentier-mappings does."""
    path = data_root / "sentier-mappings/data/bafu-2026-v1__ef-3.1/biosphere-1-curated.json"
    package = json.loads(path.read_text())
    for item in package["replace"]:
        if item["source"]["code"] == source_code:
            item["target"]["location"] = location
    path.write_text(json.dumps(package))


def test_the_build_gives_the_flow_a_node_of_its_country_and_scores_with_its_factor(data_root):
    name_the_country(data_root)
    assert load_bridge(data_root)[B1].target_location == "DE"
    result = sentier_brightway.assemble(data_root)
    node = result.biosphere[(BIOSPHERE_DB, E1_DE)]
    base = result.biosphere[(BIOSPHERE_DB, E1)]
    assert node["name"] == f"{base['name']}, DE" and node["location"] == "DE"
    assert (node["categories"], node["type"]) == (base["categories"], base["type"])
    assert node["unit"] == "kilogram"  # the unit of the links that end on it
    assert "location" not in base
    # every exchange of the flow is on the country's node
    inputs = [
        exchange["input"]
        for process in result.inventory.values()
        for exchange in process["exchanges"]
        if exchange["type"] == "biosphere"
    ]
    assert (BIOSPHERE_DB, E1_DE) in inputs and (BIOSPHERE_DB, E1) not in inputs
    climate = next(m for m in result.methods if m.method_id == CLIMATE)
    ionising = next(m for m in result.methods if m.method_id == IONISING)
    assert dict(climate.cfs)[(BIOSPHERE_DB, E1_DE)] == 2.0
    assert dict(climate.cfs)[(BIOSPHERE_DB, E1)] == 1.0
    assert (BIOSPHERE_DB, E1_DE) not in dict(ionising.cfs)  # that method does not know E1
    assert result.coverage.flows_located == 1
    assert result.links[B1].target_code == E1_DE and result.links[B2].target_code == E2
    # the methods in which naming a country can move a score: climate has DE's factor,
    # ionising radiation does not know the flow
    assert result.coverage.located_by_method == ((CLIMATE, 1),)
    assert f"a country's own factor in: {CLIMATE} (1)" in sentier_brightway.render(result.coverage)


def test_the_score_follows_the_countrys_factor(data_root, tmp_path):
    """P1 emits 1 kg of the flow itself and 0.5 kg per kWh through 2 kWh of P2: with the
    factor of DE (2.0) in place of 1.0 its climate score doubles."""
    from sentier_brightway.backtest import by_short
    from sentier_brightway.backtest.scorer import score_all

    name_the_country(data_root)
    scores = {}
    for name, located in (("with", True), ("without", False)):
        out = tmp_path / name
        sentier_brightway.import_files(out, data_root=data_root, include_located=located)
        frame = score_all(out, (by_short("climate"),)).frame.set_index("code")
        scores[name] = float(frame.loc[P1, "climate"])
    assert scores["without"] == pytest.approx(P1_CLIMATE_SCORE)
    assert scores["with"] == pytest.approx(2 * P1_CLIMATE_SCORE)


def test_the_report_says_how_many_flows_take_a_countrys_factor(data_root, capsys):
    name_the_country(data_root)
    assert cli.main(["coverage", "--data-root", str(data_root)]) == 0
    assert "1 of the linked flows name a country and take that country's factor" in (
        capsys.readouterr().out
    )
    assert cli.main(["coverage", "--data-root", str(data_root), "--skip-located"]) == 0
    assert "name a country" not in capsys.readouterr().out


def test_a_data_root_that_names_no_country_builds_as_before(data_root):
    result = sentier_brightway.assemble(data_root)
    assert result.coverage.flows_located == 0
    assert not any("@" in code for _, code in result.biosphere)


def add_factor_of_a_country(data_root, method_id, code, location, value):
    """Give a made-up method one more factor of a single country."""
    import pandas as pd

    path = data_root / "sentier-methods/data/01-ef-3.1/characterization-factors.parquet"
    table = pd.read_parquet(path)
    row = table[(table["method_id"] == method_id) & table["location"].isna()].iloc[[0]].copy()
    row["flow"] = FLOWS + code
    row["factor_value"] = value
    row["location"] = location
    pd.concat([table, row], ignore_index=True).to_parquet(path, index=False)


def test_the_same_factor_of_a_country_twice_is_refused(data_root):
    add_factor_of_a_country(data_root, CLIMATE, E1, "DE", 5.0)  # the made-up data has one
    with pytest.raises(ValueError, match="duplicate .method_id, flow, location."):
        load_methods(data_root)


def test_the_links_of_brightway_flows_take_the_country_from_the_mapping(data_root, tmp_path):
    """The links end ``Water, CH`` and ``Water`` on one flow and state no country. The
    mapping does, and the build follows it in the second linking too."""
    from test_brightway_flows import rows, write

    name_the_country(data_root)
    links = write(tmp_path / "targets.csv", rows())
    result = sentier_brightway.assemble(data_root, flow_links=links)
    assert result.links[B1].target_code == E1_DE
    assert result.biosphere[(BIOSPHERE_DB, E1_DE)]["location"] == "DE"
    climate = next(m for m in result.methods if m.method_id == CLIMATE)
    assert dict(climate.cfs)[(BIOSPHERE_DB, E1_DE)] == 2.0
    assert result.coverage.flows_located == 1 and result.coverage.linking == "brightway-flows"
    # and not where it is switched off
    plain = sentier_brightway.assemble(data_root, flow_links=links, include_located=False)
    assert plain.links[B1].target_code == E1 and plain.coverage.flows_located == 0


def test_a_flow_outside_ef_takes_the_countrys_factor_of_the_flow_named_for_it(data_root, tmp_path):
    """Uranium is linked to a flow outside EF 3.1 that takes its factors from E2. Where the
    BAFU flow names a country and E2 has that country's factor, the flow takes it too."""
    from test_brightway_flows import OUTSIDE, rows, write

    add_factor_of_a_country(data_root, IONISING, E2, "FR", 9.0)
    name_the_country(data_root, B2, "FR")
    links = write(tmp_path / "targets.csv", rows())
    result = sentier_brightway.assemble(data_root, flow_links=links)
    key = located_code(OUTSIDE, "FR")
    assert result.links[B2].target_code == key
    ionising = next(m for m in result.methods if m.method_id == IONISING)
    factors = dict(ionising.cfs)
    assert factors[(BIOSPHERE_DB, key)] == 9.0
    assert factors[(BIOSPHERE_DB, OUTSIDE)] == 3.0  # the factor without a location, carried
    node = result.biosphere[(BIOSPHERE_DB, key)]
    assert node["name"] == "uranium-238, to a lake, FR" and node["unit"] == "kilo Becquerel"


def test_the_measurement_says_what_the_countrys_factor_changes(data_root, tmp_path):
    """`scripts/compare_located_factors.py`, on the made-up data with one flow that names a
    country: both datasets emit it, and both double in climate change and move nowhere else."""
    import importlib.util
    from pathlib import Path

    script = Path(__file__).parents[1] / "scripts" / "compare_located_factors.py"
    spec = importlib.util.spec_from_file_location("compare_located_factors", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    name_the_country(data_root)
    out = tmp_path / "comparison.json"
    arguments = ["--data-root", str(data_root), "--work", str(tmp_path / "work")]
    assert module.main([*arguments, "--out", str(out)]) == 0
    found = json.loads(out.read_text())
    assert found["data"] == "supplied with --data-root"
    flows = found["flows"]
    assert flows["flows_that_name_a_country"] == 1
    assert flows["of_which_take_a_factor_of_their_country"] == 1
    assert flows["targets_with_the_methods_own_factor_of_the_country"] == {CLIMATE: 1}
    assert flows["name_a_country_no_method_has_a_factor_for"] == 0
    assert found["scores"]["datasets"] == 2
    assert found["scores"]["categories_in_which_a_dataset_moves"] == [
        {
            "category": "climate",
            "method": CLIMATE,
            "moved_over_1_percent": 2,
            "moved_over_10_percent": 2,
            "lower": 0,
            "higher": 2,
        }
    ]
    assert "against_published_results" not in found
