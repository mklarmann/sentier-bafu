"""Linking through Brightway Flows: which flow, which conversion, which factors."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

import sentier_brightway as sb
from sentier_brightway import brightway_flows as bf
from sentier_brightway.cli import main
from sentier_brightway.constants import BIOSPHERE_DB, DEFAULT_SOURCE, inventory_db, residual_db
from sentier_brightway.flows import load_ef_flows, load_source_flows
from sentier_brightway.inventory import load_inventory
from sentier_brightway.methods import load_methods
from tests.conftest import B1, B2, B3, CLIMATE, E1, E2, IONISING, P1, P2

OUTSIDE = "a" * 40  # a flow of Brightway Flows that EF 3.1 does not hold
OTHER = "b" * 40
FIELDS = (
    *("name", "category", "subCategory", "unit", "key", "brightway_flow_id", "flow_id"),
    *("flow_name", "flow_context", "flow_unit", "flow_list", "conversion", "conversion_basis"),
    *("factors_from", "factors_derivation"),
)


def row(name, category, sub, unit, flow_id, **more):
    fields = {
        "name": name,
        "category": category,
        "subCategory": sub,
        "unit": unit,
        "key": "as shipped",
        "brightway_flow_id": flow_id,
        "flow_id": flow_id,
        "flow_name": name.lower(),
        "flow_context": "envi-unkn",
        "flow_unit": unit,
        "flow_list": bf.EF_LIST,
        "conversion": "",
        "conversion_basis": "",
        "factors_from": "",
        "factors_derivation": "",
    }
    return fields | more


def rows(heat_unit="kWh"):
    """CO2 onto a flow of EF 3.1; uranium onto a flow outside EF 3.1, in another unit with a
    stated conversion, taking its factors from the EF 3.1 uranium flow; heat onto a flow
    outside EF 3.1 with no source of factors, in ``heat_unit``."""
    return [
        row("Carbon dioxide, fossil", "emissions to air", "unspecified", "kg", E1),
        row(
            "Uranium-238",
            "emissions to water",
            "lake",
            "Bq",
            OUTSIDE,
            flow_name="uranium-238, to a lake",
            flow_unit="kBq",
            flow_list="bafu algorithm addition",
            conversion="0.001",
            conversion_basis="unit-table",
            factors_from=E2,
            factors_derivation="carried",
        ),
        row(
            "Heat, waste",
            "emissions to air",
            "unspecified",
            "MJ",
            OTHER,
            flow_unit=heat_unit,
            flow_list="bafu algorithm addition",
        ),
    ]


def write(path: Path, content: list[dict]) -> Path:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(content)
    return path


@pytest.fixture
def links_file(tmp_path: Path) -> Path:
    return write(tmp_path / "targets.csv", rows())


def linked(data_root: Path, content: list[dict], **options) -> bf.FlowLinks:
    targets = {tuple(r[k] for k in bf.KEY): r for r in content}
    return bf.link(
        load_inventory(data_root),
        load_source_flows(data_root),
        load_ef_flows(data_root),
        load_methods(data_root),
        targets,
        **options,
    )


def test_a_flow_is_linked_to_the_flow_the_crosswalk_names(data_root):
    links = linked(data_root, rows())
    assert links.bridge[B1].target_code == E1
    assert links.bridge[B1].conversion_factor == 1.0
    assert links.bridge[B2].target_code == OUTSIDE
    assert links.bridge[B2].target_unit == "kBq"


def test_a_conversion_is_taken_only_where_it_is_stated(data_root):
    links = linked(data_root, rows())
    assert links.bridge[B2].conversion_factor == 0.001
    # heat is in MJ and its target in kWh; nothing states the conversion, so it is unknown:
    # the flow is not linked, and the report names it
    assert B3 not in links.bridge
    assert links.report.unit_unknown == (("Heat, waste", "MJ", "kWh"),)
    assert links.report.converted == 1


def test_two_spellings_of_one_unit_need_no_conversion(data_root):
    # the installer's unit table knows both spellings of a megajoule
    links = linked(data_root, rows(heat_unit="megajoule"))
    assert links.bridge[B3].conversion_factor == 1.0
    assert links.report.unit_unknown == ()


def test_a_flow_outside_ef_takes_the_installers_factor_of_the_flow_named_for_it(data_root):
    methods = load_methods(data_root)
    links = linked(data_root, rows())
    by_id = {spec.method_id: dict(spec.cfs) for spec in links.methods}
    before = {spec.method_id: dict(spec.cfs) for spec in methods}
    # the factor of the EF 3.1 uranium flow, in the method that has one, and nowhere else
    assert by_id[IONISING][OUTSIDE] == before[IONISING][E2] == 3.0
    assert OUTSIDE not in by_id[CLIMATE]
    # nothing else changes, and the methods that were read are left as they were
    assert {k: v for k, v in by_id[IONISING].items() if k != OUTSIDE} == before[IONISING]
    assert by_id[CLIMATE] == before[CLIMATE]
    assert {spec.method_id: dict(spec.cfs) for spec in methods} == before
    assert links.report.outside_ef == 1 and links.report.outside_ef_with_factors == 1


def test_a_flow_outside_ef_without_a_named_source_has_no_factor(data_root):
    links = linked(data_root, rows(heat_unit="MJ"))
    assert links.bridge[B3].target_code == OTHER
    assert links.bridge[B3].nomenclature is True
    assert all(OTHER not in dict(spec.cfs) for spec in links.methods)
    assert links.report.without_factor == 1
    # and with the option that leaves such flows unlinked, it stays in the residual database
    skipped = linked(data_root, rows(heat_unit="MJ"), include_without_factor=False)
    assert B3 not in skipped.bridge


def test_a_named_source_without_a_factor_gives_none(data_root):
    content = rows()
    content[1]["factors_from"] = "f" * 8 + "-0000-4000-8000-00000000000f"  # no method knows it
    links = linked(data_root, content)
    assert links.bridge[B2].nomenclature is True
    assert links.report.outside_ef_with_factors == 0


def test_a_node_is_made_for_a_linked_flow_outside_ef(data_root):
    links = linked(data_root, rows(heat_unit="megajoule"))
    added = links.ef_flows.set_index("code")
    assert added.at[OUTSIDE, "name"] == "uranium-238, to a lake"
    # the source's own words for where the flow goes
    assert tuple(added.at[OUTSIDE, "categories"]) == ("emissions to water", "lake")
    assert OTHER in added.index
    assert len(links.ef_flows) == len(load_ef_flows(data_root)) + 2
    # a flow that is not linked gets no node
    assert OTHER not in linked(data_root, rows()).ef_flows["code"].tolist()


def test_a_flow_the_crosswalk_does_not_hold_stays_unlinked(data_root):
    links = linked(data_root, rows()[:1])
    assert set(links.bridge) == {B1}
    assert sorted(links.report.not_in_crosswalk) == ["Heat, waste", "Uranium-238"]


def test_assemble_links_the_exchanges_and_converts_the_amounts(data_root, links_file):
    result = sb.assemble(data_root, flow_links=links_file)
    inventory, residual = inventory_db(DEFAULT_SOURCE), residual_db(DEFAULT_SOURCE)
    bio = {
        (p[1], e["input"]): e["amount"]
        for p, node in result.inventory.items()
        for e in node["exchanges"]
        if e["type"] == "biosphere"
    }
    assert bio[(P2, (BIOSPHERE_DB, OUTSIDE))] == pytest.approx(1000.0 * 0.001)
    assert bio[(P1, (BIOSPHERE_DB, E1))] == pytest.approx(1.0)
    assert (P1, (residual, B3)) in bio  # heat: the conversion is unknown
    assert result.biosphere[(BIOSPHERE_DB, OUTSIDE)]["unit"] == "kilo Becquerel"
    assert (inventory, P1) in result.inventory
    coverage = result.coverage
    assert coverage.linking == "brightway-flows"
    assert coverage.flows_mapped == 2 and coverage.flows_used == 3
    assert coverage.link_lines[0].startswith("Linked through Brightway Flows")
    # without the file nothing of this happens
    plain = sb.assemble(data_root).coverage
    assert plain.linking == "sentier-mappings" and plain.link_lines == ()


def test_the_scores_are_the_ones_the_mapping_gives_where_both_say_the_same(data_root, links_file):
    """CO2 and uranium end on flows with the same factors both ways, so the files score the
    same: 6.0 for ionising radiation of the first process, through the conversion."""
    dpk = pytest.importorskip("sentier_brightway.datapackage")
    pytest.importorskip("bw2calc")
    out = data_root.parent / "linked"
    sb.import_files(out, data_root=data_root, flow_links=links_file)
    assert dpk.score(out, P1, IONISING) == pytest.approx(6.0)
    assert dpk.score(out, P1, CLIMATE) == pytest.approx(2.0)


def test_the_files_say_how_they_were_linked_and_keep_the_file(data_root, links_file):
    pytest.importorskip("bw_processing")
    out = data_root.parent / "linked"
    sb.import_files(out, data_root=data_root, flow_links=links_file, datapackages=False)
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["linking"] == "brightway-flows"
    assert manifest["bridge_packages"] == []
    kept = out / "mappings" / "brightway-flows" / links_file.name
    assert kept.read_bytes() == links_file.read_bytes()
    assert not (out / "mappings" / "bafu-2026-v1__ef-3.1").exists()
    plain = data_root.parent / "plain"
    sb.import_files(plain, data_root=data_root, datapackages=False)
    assert json.loads((plain / "manifest.json").read_text())["linking"] == "sentier-mappings"


def test_the_command_line_takes_the_file(data_root, links_file, capsys):
    assert main(["coverage", "--data-root", str(data_root), "--flow-links", str(links_file)]) == 0
    printed = capsys.readouterr().out
    assert "Linked through Brightway Flows (the links of patch 0010): 2/3 flows" in printed
    assert "1 not linked: the units differ and the release states no conversion" in printed
    assert "Installed bafu-2026: 2 processes" in printed
    assert main(["coverage", "--data-root", str(data_root)]) == 0
    assert "Linked through Brightway Flows" not in capsys.readouterr().out


def test_a_file_that_is_not_a_targets_file_is_refused(tmp_path, data_root, capsys):
    with pytest.raises(FileNotFoundError):
        bf.load_targets(tmp_path / "none.csv")
    short = tmp_path / "short.csv"
    short.write_text("name,category\nx,y\n")
    with pytest.raises(ValueError, match="columns missing"):
        bf.load_targets(short)
    twice = write(tmp_path / "twice.csv", [rows()[0], rows()[0]])
    with pytest.raises(ValueError, match="is there twice"):
        bf.load_targets(twice)
    content = rows()
    content[1]["conversion"] = "-1"
    with pytest.raises(ValueError, match="not above zero"):
        bf.load_targets(write(tmp_path / "negative.csv", content))
    content[1]["conversion"] = "about a thousandth"
    with pytest.raises(ValueError, match="not a number"):
        bf.load_targets(write(tmp_path / "words.csv", content))
    # and the command says so, and ends with an error
    assert main(["coverage", "--data-root", str(data_root), "--flow-links", str(short)]) == 2
    assert "columns missing" in capsys.readouterr().err
