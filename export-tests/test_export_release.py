"""The export step on a made-up database: written, read back, compared with the source.

Tests marked `xfail(strict=True)` state what an export should do and does not do yet;
each names the gap. They start failing the day the writer closes it, which is the
signal to turn them into ordinary tests.
"""

import copy
import json
import math
import uuid
import zipfile

import bw2data as bd
import olca_schema as o
import pytest
import recompute
import synthetic
from bw2io import BW2Package
from conftest import BRIGHTWAY_DIR, RELEASE, export, project, run_summary, step

CREDIT = "Life Cycle Inventory database of the Swiss Federal Administration, BAFU:2026"
CLIMATE = synthetic.methods()[("synthetic", "climate change")][1]
WATER = synthetic.methods()[("synthetic", "water use")][1]
INVENTORY, FLOWS = synthetic.INVENTORY, synthetic.FLOWS


def path(folder, manifest, kind):
    return folder / manifest["files"][kind]["name"]


def close(a, b):
    """Equal scores. Brightway keeps amounts as 32-bit floats, so not to the last digit."""
    return a.keys() == b.keys() and all(
        math.isclose(a[k], b[k], rel_tol=1e-6, abs_tol=1e-12) for k in a
    )


# --- Written, read back, the same ----------------------------------------------------


def test_every_export_reads_back_and_matches_the_database(base):
    manifest, out, _ = base
    assert {kind: check["problems"] for kind, check in manifest["checks"].items()} == {
        "brightway": [],
        "openlca": [],
        "ilcd": [],
        "simapro": [],
    }
    assert manifest["status"] == "completed"
    assert manifest["counts"] == {
        "activities": 9,
        "elementary_flows": 8,
        "exchanges": 40,
        "datasets_matched_to_the_record": 2,
    }
    assert manifest["simapro"]["links"] == {"resolved": 15, "ambiguous": 0, "missing": 0}


def test_manifest_holds_release_credit_label_tools_and_checksums(base):
    manifest, out, _ = base
    assert manifest["label"] == "Modified Data"
    assert manifest["release"] == RELEASE
    assert manifest["credit"] == CREDIT
    assert manifest["source"]["fingerprint_sha256"] == "ab" * 32
    assert "@db7af57cabd59b4256d00516027cc298bbcfc2ad" in manifest["tools"]["bw-interchange-export"]
    assert {"python", "bw-ilcd-bridge", "olca-schema", "bw-simapro-csv", "bw2io", "bw2data"} <= set(
        manifest["tools"]
    )
    for entry in manifest["files"].values():
        assert step.sha256(out / entry["name"]) == entry["sha256"]
        assert (out / entry["name"]).stat().st_size == entry["bytes"]
    listed = dict(line.split("  ")[::-1] for line in (out / "SHA256SUMS").read_text().splitlines())
    assert listed == {p.name: step.sha256(p) for p in out.iterdir() if p.name != "SHA256SUMS"}


def test_record_of_modifications_travels_with_the_files(base):
    manifest, out, _ = base
    record = json.loads((out / "MODIFICATIONS.json").read_text())
    assert record["label"] == "Modified Data" and record["credit"] == CREDIT
    # Steps that changed nothing in this run are not modifications of this release.
    assert [s["id"] for s in record["steps"]] == ["unit-names", "0001-flour-share", "0003-waiting"]
    assert record["steps"][1]["authored_by"] == "Ann Author"
    assert record["steps"][1]["rationale"] == "Why 0001-flour-share is needed."
    assert [(d["name"], d["location"]) for d in record["datasets"]] == [
        ("bread production", "CH"),
        ("wheat grains, at farm", "CH"),
    ]
    readable = (out / "MODIFICATIONS.md").read_text()
    assert "**Modified Data.**" in readable and CREDIT in readable
    assert (
        "| 0003-waiting | patch | Correct a location | 1 | 2 | Ann Author | not yet authorised |"
        in (readable)
    )


def test_brightway_package_restores_with_its_provenance_and_the_same_scores(base):
    manifest, out, databases = base
    source, _ = project()
    before = recompute.brightway(source, INVENTORY, CLIMATE)

    bd.projects.set_current("restored")
    BW2Package.import_file(str(path(out, manifest, "brightway")))
    for name, database in databases.items():
        restored = bd.Database(name).load()
        assert restored.keys() == database["data"].keys()
        for key, node in restored.items():
            assert step._canonical(node) == step._canonical(database["data"][key])
        provenance = bd.databases[name]["provenance"]
        assert provenance["label"] == "Modified Data" and provenance["credit"] == CREDIT
        assert provenance["modifications"]["sha256"] == manifest["files"]["modifications"]["sha256"]
        assert [s["id"] for s in provenance["modifications"]["steps"]] == [
            "unit-names",
            "0001-flour-share",
            "0003-waiting",
        ]
    assert close(recompute.brightway("restored", INVENTORY, CLIMATE), before)


def test_openlca_archive_names_credit_label_and_changes_in_every_process(base):
    manifest, out, databases = base
    _, process_id = step.olca_ids(step.NAMESPACE)
    processes = step.read_openlca(path(out, manifest, "openlca"))["processes"]
    assert len(processes) == 9
    for process in processes.values():
        restrictions = process.process_documentation.restrictions_description
        assert restrictions == manifest["statement"]
        assert CREDIT in restrictions and "Modified Data" in restrictions
        assert "unit-names" in restrictions and "0001-flour-share" in restrictions
        assert process.description.startswith("Modified Data: part of a patched release")
        assert process.last_change == run_summary()["finished"]
    bread = processes[process_id((INVENTORY, "bread-ch"))]
    assert bread.description.endswith("Changed by: 0001-flour-share.")
    wheat = processes[process_id((INVENTORY, "wheat"))]
    assert wheat.description.endswith("Changed by: unit-names, 0003-waiting.")
    assert "Changed by" not in processes[process_id((INVENTORY, "heat"))].description


def test_simapro_file_names_credit_label_and_changes(base):
    manifest, out, _ = base
    csv = step.read_simapro(path(out, manifest, "simapro"))
    assert f"{{Project: {RELEASE} patched release, Modified Data}}" in csv["header"]
    assert f"{{{manifest['statement']}}}" in csv["header"]
    (reference,) = csv["literature"]
    assert reference["Name"] == "Source database attribution"
    assert reference["Description"] == manifest["statement"]
    comments = {i: p["metadata"]["Comment"] for i, p in csv["processes"].items()}
    assert all(c.startswith("Modified Data: part of a patched release") for c in comments.values())
    assert comments[f"{INVENTORY}|bread-ch"].endswith("Changed by: 0001-flour-share.")


def test_ilcd_package_names_the_credit_in_every_process(base):
    manifest, out, _ = base
    with zipfile.ZipFile(path(out, manifest, "ilcd")) as archive:
        processes = [n for n in archive.namelist() if n.startswith("ILCD/processes/")]
        assert len(processes) == 9
        assert all(CREDIT in archive.read(n).decode() for n in processes)


# --- Provenance is not optional ------------------------------------------------------


def test_step_refuses_a_run_summary_that_is_missing_or_incomplete(tmp_path):
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({"steps": []}))
    with pytest.raises(step.ExportError, match="not a `bafu-fixes run --summary` file"):
        step.read_summary(summary)
    summary.write_text(json.dumps(run_summary() | {"status": "failed"}))
    with pytest.raises(step.ExportError, match="did not complete"):
        step.read_summary(summary)


def test_files_written_without_provenance_are_found_out(base, tmp_path):
    from bw_interchange_export import export_openlca_ilcd, export_simapro_csv

    manifest, out, databases = base
    nodes, marks = step.all_nodes(databases), (CREDIT, "Modified Data")
    package = path(out, manifest, "brightway")
    (tmp_path / "m.json").write_text("{}")
    bare = {k: tmp_path / k for k in ("olca.zip", "ilcd.zip", "simapro.csv", "bare.bw2package")}
    export_openlca_ilcd(
        package, tmp_path / "m.json", bare["olca.zip"], bare["ilcd.zip"],
        namespace=step.NAMESPACE, quiet=True,
    )  # fmt: skip
    export_simapro_csv(package, bare["simapro.csv"], quiet=True, product_naming="linked")
    step.write_bw2package(databases, None, bare["bare.bw2package"])

    openlca = step.check_openlca(bare["olca.zip"], nodes, step.NAMESPACE, marks)
    assert sum("restrictions lack" in p for p in openlca) == 2 * 9
    assert sum("description lacks 'Modified Data'" in p for p in openlca) == 9
    simapro, _ = step.check_simapro(bare["simapro.csv"], nodes, marks)
    assert "header lacks 'Modified Data'" in simapro
    assert f"literature reference lacks {CREDIT!r}" in simapro
    assert sum("comment lacks 'Modified Data'" in p for p in simapro) == 9
    assert step.check_ilcd(bare["ilcd.zip"], 9, marks) != []
    assert step.check_bw2package(bare["bare.bw2package"], databases, marks) == [
        f"{name}: metadata lacks {mark!r}" for name in (FLOWS, INVENTORY) for mark in marks
    ]


def test_step_fails_when_a_file_lacks_the_credit(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(step, "attribution", lambda record, terms_url=None: "Modified Data.")
    manifest, out, _ = export(tmp_path)
    assert manifest["status"] == "failed"
    assert json.loads((out / "manifest.json").read_text())["status"] == "failed"
    assert not manifest["checks"]["openlca"]["passed"]
    assert not manifest["checks"]["simapro"]["passed"]
    assert not manifest["checks"]["ilcd"]["passed"]


def test_checks_notice_data_that_differs_from_the_database(base):
    manifest, out, databases = base
    nodes, marks = copy.deepcopy(step.all_nodes(databases)), (CREDIT, "Modified Data")
    wheat = nodes[(INVENTORY, "wheat")]
    wheat["exchanges"][1]["amount"] *= 2  # transport
    wheat["exchanges"][3]["amount"] *= 2  # water
    nodes[(INVENTORY, "heat")]["exchanges"].pop()  # its emission

    openlca = step.check_openlca(path(out, manifest, "openlca"), nodes, step.NAMESPACE, marks)
    assert sorted(openlca) == [
        f"{(INVENTORY, code)}: exchanges differ from the database" for code in ("heat", "wheat")
    ]
    simapro, _ = step.check_simapro(path(out, manifest, "simapro"), nodes, marks)
    assert sorted(simapro) == [
        f"{(INVENTORY, 'heat')}: elementary flows differ from the database",
        f"{(INVENTORY, 'wheat')}: elementary flows differ from the database",
        f"{(INVENTORY, 'wheat')}: inputs differ from the database, or link elsewhere",
    ]
    changed = copy.deepcopy(databases)
    changed[INVENTORY]["data"][(INVENTORY, "wheat")]["exchanges"][1]["amount"] *= 2
    assert step.check_bw2package(path(out, manifest, "brightway"), changed, marks) == [
        f"{INVENTORY}: 1 nodes differ, first {(INVENTORY, 'wheat')}"
    ]


def test_step_refuses_exchanges_that_point_outside_the_selection():
    name, _ = project()
    with pytest.raises(step.ExportError, match=r"synthetic-flows \(15 exchanges\)"):
        step.export_release(
            step.load_databases(name, [INVENTORY]), run_summary(), "unused", release=RELEASE
        )


# --- Scores ----------------------------------------------------------------------------


def test_brightway_scores_of_the_synthetic_database_are_the_ones_worked_out_by_hand():
    name, _ = project()
    climate = recompute.brightway(name, INVENTORY, CLIMATE)
    flour = (1250 * (0.05 * 0.100596 + 0.02 * 0.03) + 80 * 0.03 + 30 * 0.50746) / 980
    by_hand = {
        "electricity-ch": 0.03,
        "electricity-de": 0.45 + 0.001 * 29.8,
        "heat": 0.06 + 0.01 * 0.4798,
        "transport": 0.1 + 2e-5 * 29.8,
        "waste": 0.05 * 0.03 + 0.5 + 2e-4 * 29.8,
        "wheat": 0.05 * 0.100596 + 0.02 * 0.03,
        "flour": flour,
        "bread-ch": 0.75 * flour + 2 * 0.064798 + 0.3 * 0.03 + 0.1 * 0.100596 + 0.02 * 0.50746,
        "bread-de": 0.75 * flour + 2.2 * 0.064798 + 0.3 * 0.4798,
    }
    assert close(climate, by_hand)
    water = recompute.brightway(name, INVENTORY, WATER)["wheat"]
    assert math.isclose(water, 0.3 + 0.02 * 0.002, rel_tol=1e-6)


@pytest.mark.parametrize("method", [CLIMATE, WATER], ids=["climate", "water"])
def test_scores_computed_from_the_exported_files_equal_brightways(base, method):
    manifest, out, databases = base
    nodes = step.all_nodes(databases)
    expected = recompute.brightway(project()[0], INVENTORY, method)
    assert any(expected.values())
    from_openlca = recompute.openlca(path(out, manifest, "openlca"), nodes, step.NAMESPACE, method)
    from_simapro = recompute.simapro(path(out, manifest, "simapro"), nodes, method)
    assert close(from_openlca, expected)
    assert close(from_simapro, expected)


# --- Shapes that need care ---------------------------------------------------------------


def test_reference_product_that_differs_from_the_name_keeps_its_links_in_simapro(base):
    manifest, out, _ = base
    csv = step.read_simapro(path(out, manifest, "simapro"))
    bread = csv["processes"][f"{INVENTORY}|bread-ch"]
    assert bread["metadata"]["Process name"] == "bread production"
    assert bread["products"][0]["name"] == "bread | bread production | CH"
    inputs = {row["name"]: (row["amount"], row["unit"]) for row in bread["inputs"]}
    assert inputs["electricity, low voltage | electricity, low voltage, at grid | CH"] == (
        pytest.approx(0.3),
        "kWh",
    )
    providers, _ = step.simapro_links(csv)
    assert set(providers.values()) == {f"{INVENTORY}|{code}" for code in (
        "electricity-ch", "electricity-de", "heat", "transport", "waste", "wheat", "flour",
    )}  # fmt: skip


def test_simapro_legacy_naming_breaks_the_links_of_this_database(tmp_path):
    manifest, out, databases = export(tmp_path, simapro_naming="legacy")
    # Two products are named "electricity, low voltage" and their users ask for
    # "electricity, low voltage, at grid": none of the six electricity inputs resolves.
    assert manifest["simapro"]["links"] == {"resolved": 9, "ambiguous": 0, "missing": 6}
    assert manifest["status"] == "failed"
    assert manifest["checks"]["simapro"]["problems"][0] == (
        "6 input rows name no product in the file and 0 name more than one"
    )
    nodes = step.all_nodes(databases)
    scores = recompute.simapro(path(out, manifest, "simapro"), nodes, CLIMATE)
    assert sorted(code for code, score in scores.items() if math.isnan(score)) == [
        "bread-ch", "bread-de", "flour", "heat", "waste", "wheat",
    ]  # fmt: skip


@pytest.mark.xfail(strict=True, reason="CSV writer: its default product naming breaks links")
def test_simapro_default_naming_keeps_links(tmp_path):
    from bw_interchange_export import export_simapro_csv

    manifest, out, _ = export(tmp_path)
    export_simapro_csv(path(out, manifest, "brightway"), tmp_path / "default.csv", quiet=True)
    _, links = step.simapro_links(step.read_simapro(tmp_path / "default.csv"))
    assert links["missing"] == links["ambiguous"] == 0


def test_units_and_amounts_are_written_as_they_are(base):
    manifest, out, _ = base
    flow_id, process_id = step.olca_ids(step.NAMESPACE)
    archive = step.read_openlca(path(out, manifest, "openlca"))
    bread = archive["processes"][process_id((INVENTORY, "bread-ch"))]
    written = {
        e.flow.id: (e.amount, archive["units"][e.unit.id].name, e.flow_property.name)
        for e in bread.exchanges
    }
    assert written[flow_id((INVENTORY, "electricity-ch"))] == (0.3, "kilowatt hour", "Energy")
    assert written[flow_id((INVENTORY, "heat"))] == (2.0, "megajoule", "Energy")
    assert written[flow_id((INVENTORY, "transport"))] == (0.1, "ton kilometer", "Goods transport")
    electricity = archive["processes"][process_id((INVENTORY, "electricity-ch"))]
    written = {
        e.flow.id: (e.amount, archive["units"][e.unit.id].name, e.flow_property.name)
        for e in electricity.exchanges
    }
    assert written[flow_id((FLOWS, "radon-air"))] == (0.5, "kilo Becquerel", "Radioactivity")
    assert written[flow_id((FLOWS, "water-river"))] == (0.002, "cubic meter", "Volume")
    # 1 kWh is 3.6 of the group's reference unit: the factor is declared, the amount untouched.
    kwh = next(u for u in archive["units"].values() if u.name == "kilowatt hour")
    assert kwh.conversion_factor == 3.6

    csv = step.read_simapro(path(out, manifest, "simapro"))
    rows = csv["processes"][f"{INVENTORY}|electricity-ch"]["elementary"]
    assert {(r["name"], r["unit"], r["amount"]) for r in rows} == {
        ("Carbon dioxide, fossil", "kg", 0.03),
        ("Radon-222", "kBq", 0.5),
        ("Water, river", "m3", 0.002),
    }


def test_activity_modelled_per_1000_kg_with_a_loss_exports_its_net_production(base):
    manifest, out, _ = base
    _, process_id = step.olca_ids(step.NAMESPACE)
    flour = step.read_openlca(path(out, manifest, "openlca"))["processes"][
        process_id((INVENTORY, "flour"))
    ]
    (reference,) = [e for e in flour.exchanges if e.is_quantitative_reference]
    assert reference.amount == 980.0
    assert len(flour.exchanges) == 4  # the 20 kg of its own product are not written again
    csv = step.read_simapro(path(out, manifest, "simapro"))
    assert csv["processes"][f"{INVENTORY}|flour"]["products"][0]["amount"] == 980.0


def test_waste_treatment_is_an_input_of_its_user_in_both_formats(base):
    manifest, out, _ = base
    flow_id, process_id = step.olca_ids(step.NAMESPACE)
    archive = step.read_openlca(path(out, manifest, "openlca"))
    bread = archive["processes"][process_id((INVENTORY, "bread-ch"))]
    (waste,) = [e for e in bread.exchanges if e.flow.id == flow_id((INVENTORY, "waste"))]
    assert (waste.is_input, waste.amount) == (True, 0.02)
    assert waste.default_provider.id == process_id((INVENTORY, "waste"))
    csv = step.read_simapro(path(out, manifest, "simapro"))
    rows = csv["processes"][f"{INVENTORY}|bread-ch"]["inputs"]
    (row,) = [r for r in rows if r["name"].startswith("disposal, municipal solid waste")]
    # Written under Materials/fuels, not under SimaPro's "Waste to treatment".
    assert (row["section"], row["amount"]) == ("Materials/fuels", 0.02)


def test_parameterised_amount_is_exported_as_its_value_without_the_formula(base):
    manifest, out, databases = base
    source = databases[INVENTORY]["data"][(INVENTORY, "bread-ch")]["exchanges"][1]
    assert source["formula"] == "flour_share * loaf_mass" and source["amount"] == 0.75
    with zipfile.ZipFile(path(out, manifest, "openlca")) as archive:
        assert not any("flour_share" in archive.read(n).decode() for n in archive.namelist())
    assert "flour_share" not in path(out, manifest, "simapro").read_text(encoding="cp1252")
    # The Brightway package keeps it.
    restored = BW2Package.load_file(str(path(out, manifest, "brightway")))
    data = {obj["name"]: obj["data"] for obj in restored}[INVENTORY]
    assert data[(INVENTORY, "bread-ch")]["exchanges"][1]["formula"] == "flour_share * loaf_mass"


def test_two_activities_with_one_name_and_location_get_distinct_simapro_products(tmp_path):
    manifest, out, _ = export(tmp_path, synthetic.with_a_namesake)
    assert manifest["status"] == "completed"
    assert manifest["simapro"]["links"] == {"resolved": 16, "ambiguous": 0, "missing": 0}
    csv = step.read_simapro(path(out, manifest, "simapro"))
    assert {
        csv["processes"][f"{INVENTORY}|{code}"]["products"][0]["name"]
        for code in ("transport", "transport-km")
    } == {"transport, lorry | RER | transport", "transport, lorry | RER | transport-km"}


# --- A unit the JSON-LD writer does not know -----------------------------------------------


def test_normal_cubic_metre_is_refused_before_anything_is_written(tmp_path):
    with pytest.raises(step.ExportError, match=r"'Nm3' \(2 nodes\).*--openlca-unit-label"):
        export(tmp_path, synthetic.with_normal_cubic_metre)
    assert not (tmp_path / "out").exists()


def test_normal_cubic_metre_exports_under_a_declared_label(tmp_path):
    manifest, out, _ = export(
        tmp_path, synthetic.with_normal_cubic_metre, openlca_unit_labels={"Nm3": "m3"}
    )
    assert manifest["status"] == "completed"
    assert manifest["openlca"]["unit_labels"] == {"Nm3": "m3"}
    flow_id, process_id = step.olca_ids(step.NAMESPACE)
    archive = step.read_openlca(path(out, manifest, "openlca"))
    boiler = archive["processes"][process_id((INVENTORY, "heat-gas"))]
    (gas,) = [e for e in boiler.exchanges if e.flow.id == flow_id((INVENTORY, "gas"))]
    assert (gas.amount, archive["units"][gas.unit.id].name) == (0.03, "m3")
    # SimaPro has the unit, and the Brightway package keeps the database's own label.
    csv = step.read_simapro(path(out, manifest, "simapro"))
    (row,) = csv["processes"][f"{INVENTORY}|heat-gas"]["inputs"]
    assert (row["amount"], row["unit"]) == (0.03, "Nm3")
    restored = BW2Package.load_file(str(path(out, manifest, "brightway")))
    data = {obj["name"]: obj["data"] for obj in restored}[INVENTORY]
    assert data[(INVENTORY, "gas")]["unit"] == "Nm3"


@pytest.mark.xfail(strict=True, raises=ValueError, reason="JSON-LD writer: no quantity for Nm3")
def test_openlca_writer_accepts_normal_cubic_metre(tmp_path):
    from bw_interchange_export import export_openlca_ilcd

    manifest, out, _ = export(
        tmp_path, synthetic.with_normal_cubic_metre, openlca_unit_labels={"Nm3": "m3"}
    )
    (tmp_path / "m.json").write_text("{}")
    export_openlca_ilcd(
        path(out, manifest, "brightway"), tmp_path / "m.json", tmp_path / "o.zip",
        tmp_path / "i.zip", namespace=step.NAMESPACE, quiet=True,
    )  # fmt: skip


# --- An activity with a second product -----------------------------------------------------


def test_co_product_is_refused_by_simapro_linked_naming_and_nothing_stays_behind(tmp_path):
    with pytest.raises(ValueError, match="co-product row names a product another block"):
        export(tmp_path, synthetic.with_co_product)
    assert list((tmp_path / "out").iterdir()) == []


def test_co_product_is_written_as_an_allocated_output_not_as_a_credit(tmp_path):
    manifest, out, databases = export(tmp_path, synthetic.with_co_product, simapro_naming="legacy")
    flow_id, process_id = step.olca_ids(step.NAMESPACE)
    unit = step.read_openlca(path(out, manifest, "openlca"))["processes"][
        process_id((INVENTORY, "cogeneration"))
    ]
    (heat,) = [e for e in unit.exchanges if e.flow.id == flow_id((INVENTORY, "heat"))]
    assert (heat.is_input, heat.amount, heat.is_avoided_product) == (False, 2.0, None)
    assert unit.allocation_factors is None

    csv = step.read_simapro(path(out, manifest, "simapro"))
    products = csv["processes"][f"{INVENTORY}|cogeneration"]["products"]
    # Shares follow the bare amounts, 1 kWh against 2 MJ.
    assert [(p["name"], p["amount"], p["unit"], round(p["allocation"], 2)) for p in products] == [
        ("electricity, at cogeneration unit", 1.0, "kWh", 33.33),
        ("heat, at boiler", 2.0, "MJ", 66.67),
    ]
    assert csv["processes"][f"{INVENTORY}|cogeneration"]["avoided"] == []
    # Two blocks now make "heat, at boiler": both bread activities link ambiguously.
    assert manifest["simapro"]["links"] == {"resolved": 7, "ambiguous": 2, "missing": 6}


@pytest.mark.xfail(strict=True, reason="writers: a co-product is not exported as a credit")
def test_co_product_scores_computed_from_the_files_equal_brightways(tmp_path):
    manifest, out, databases = export(tmp_path, synthetic.with_co_product, simapro_naming="legacy")
    nodes = step.all_nodes(databases)
    name, _ = project(synthetic.with_co_product)
    expected = recompute.brightway(name, INVENTORY, CLIMATE)["cogeneration"]
    # The heat displaces the boiler's: Brightway credits it.
    assert math.isclose(expected, 0.6 - 2.0 * 0.064798, rel_tol=1e-6)
    from_openlca = recompute.openlca(path(out, manifest, "openlca"), nodes, step.NAMESPACE, CLIMATE)
    from_simapro = recompute.simapro(path(out, manifest, "simapro"), nodes, CLIMATE)
    # Today: 0.6 from the openLCA file (no credit) and 0.2 from the SimaPro file (a third).
    assert math.isclose(from_openlca["cogeneration"], expected, rel_tol=1e-6)
    assert math.isclose(from_simapro["cogeneration"], expected, rel_tol=1e-6)


# --- Elementary flows -------------------------------------------------------------------


def test_elementary_flows_get_minted_ids_and_brightway_names_today(base):
    manifest, out, databases = base
    flow_id, _ = step.olca_ids(step.NAMESPACE)
    flows = step.read_openlca(path(out, manifest, "openlca"))["flows"]
    written = {
        code: (f.id, f.name, f.category, f.cas)
        for code in synthetic.databases()[FLOWS]
        for f in [flows[flow_id(code)]]
    }
    seed = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/sentier-dev/sentier-bafu")
    minted = str(uuid.uuid5(seed, "synthetic-flows|co2-air"))
    assert minted == "9148fa77-8cd0-5af7-8607-af1e6ff33ca9"
    assert written[(FLOWS, "co2-air")] == (minted, "Carbon dioxide, fossil", "air", "000124-38-9")
    assert written[(FLOWS, "co2-air-urban")][1:3] == (
        "Carbon dioxide, fossil",
        "air/high population density",
    )
    assert written[(FLOWS, "water-river")][1:3] == ("Water, river", "natural resource/in water")
    # The id is a function of the namespace, the database name and the code, nothing else.
    other, _ = step.olca_ids("https://example.org/another-project")
    assert other((FLOWS, "co2-air")) != written[(FLOWS, "co2-air")][0]

    csv = step.read_simapro(path(out, manifest, "simapro"))
    rows = {
        (row["name"], *row["context"])
        for process in csv["processes"].values()
        for row in process["elementary"]
    }
    assert rows == {
        ("Carbon dioxide, fossil", "Emissions to air", ""),
        ("Carbon dioxide, fossil", "Emissions to air", "high population density"),
        ("Methane, fossil", "Emissions to air", "low population density"),
        ("Radon-222", "Emissions to air", ""),
        ("Nitrate", "Emissions to water", "ground-"),
        ("Cadmium", "Emissions to soil", "agricultural"),
        ("Water, river", "Resources", "in water"),
        ("Occupation, arable", "Resources", "land"),
    }


@pytest.mark.xfail(strict=True, reason="JSON-LD writer: every elementary exchange is an input")
def test_openlca_emissions_are_outputs_and_resources_inputs(base):
    manifest, out, databases = base
    flow_id, _ = step.olca_ids(step.NAMESPACE)
    resources = {
        flow_id(key) for key, node in databases[FLOWS]["data"].items()
        if node["type"] == "natural resource"
    }  # fmt: skip
    archive = step.read_openlca(path(out, manifest, "openlca"))
    for process in archive["processes"].values():
        for exchange in process.exchanges:
            flow = archive["flows"][exchange.flow.id]
            if flow.flow_type == o.FlowType.ELEMENTARY_FLOW:
                assert exchange.is_input == (flow.id in resources)


@pytest.mark.xfail(strict=True, reason="JSON-LD writer: product flows take the activity's name")
def test_openlca_product_flow_is_named_after_the_reference_product(base):
    manifest, out, _ = base
    flow_id, _ = step.olca_ids(step.NAMESPACE)
    flows = step.read_openlca(path(out, manifest, "openlca"))["flows"]
    assert flows[flow_id((INVENTORY, "bread-ch"))].name == "bread"


# --- The command ---------------------------------------------------------------------------


def _arguments(tmp_path, *more):
    name, names = project()
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps(run_summary()))
    arguments = ["--brightway-dir", BRIGHTWAY_DIR, "--project", name]
    arguments += [x for database in names for x in ("--database", database)]
    arguments += ["--summary", str(summary), "--release", RELEASE, "--out", str(tmp_path / "out")]
    return [*arguments, *more]


def test_command_writes_the_exports_and_reports_the_read_back(tmp_path, capsys):
    step.main(_arguments(tmp_path, "--source-sha256", "cd" * 32, "--name", "demo"))
    output = capsys.readouterr().out
    assert "openlca: read back and matches" in output
    assert "simapro: read back and matches" in output
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == [
        "MODIFICATIONS.json",
        "MODIFICATIONS.md",
        "SHA256SUMS",
        "demo-ilcd.zip",
        "demo-openlca.zip",
        "demo-simapro.csv",
        "demo.bw2package",
        "manifest.json",
    ]
    manifest = json.loads((tmp_path / "out/manifest.json").read_text())
    assert manifest["source"]["sha256"] == "cd" * 32


def test_command_exits_1_when_a_read_back_differs(tmp_path, capsys):
    with pytest.raises(SystemExit) as exit:
        step.main(_arguments(tmp_path, "--simapro-product-naming", "legacy"))
    assert exit.value.code == 1
    assert "simapro: DIFFERS" in capsys.readouterr().out


def test_command_needs_the_summary_and_an_explicit_brightway_folder(tmp_path, capsys):
    arguments = _arguments(tmp_path)
    without_summary = [
        a for a in arguments if a not in ("--summary", str(tmp_path / "summary.json"))
    ]
    with pytest.raises(SystemExit) as exit:
        step.main(without_summary)
    assert exit.value.code == 2 and "--summary" in capsys.readouterr().err
    with pytest.raises(SystemExit) as exit:
        step.main(arguments[2:])
    assert exit.value.code == 2 and "--brightway-dir" in capsys.readouterr().err
    with pytest.raises(SystemExit, match="Not exported: No Brightway project 'nope'"):
        step.main([*arguments[:3], "nope", *arguments[4:]])
