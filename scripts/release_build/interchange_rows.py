"""Preserve source exchange rows in the archives produced by the pinned interchange writers."""

import json
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

from lxml import etree as ET


def direction(exchange):
    side = exchange.get("source_direction")
    if side not in ("input", "output"):
        raise ValueError(
            "An exchange has no source direction. Rebuild the inventory from its source tables."
        )
    return side


def ilcd_key(document):
    note = document.findtext(".//{*}dataSetInformation/{*}generalComment", "")
    key = next(
        (line.removeprefix("bw:key=") for line in note.splitlines() if line.startswith("bw:key=")),
        "",
    )
    db, sep, code = key.partition("||")
    if not sep or not db or not code:
        raise ValueError("ILCD process lacks its database and source identity")
    return db, code


def rewrite(path, renderers):
    # A new ZIP avoids duplicate member names and keeps the original intact on failure.
    path = Path(path)
    with tempfile.TemporaryDirectory(dir=path.parent) as tmp:
        output = Path(tmp) / path.name
        with zipfile.ZipFile(path) as old, zipfile.ZipFile(output, "w") as new:
            new.comment = old.comment
            for info in old.infolist():
                data = old.read(info)
                render = renderers.get(info.filename.rpartition("/")[0])
                if render is not None and not info.is_dir():
                    data = render(data)
                new.writestr(info, data)
        output.replace(path)


def magnitude(unit, target):
    """Convert a declared quantity to the native ILCD flow unit."""
    from bw_ilcd.units import resolve_unit

    source, native = resolve_unit(unit), resolve_unit(target)
    if source.property_name != native.property_name:
        raise ValueError(f"Cannot represent {unit} on an ILCD flow measured in {target}")
    return source.factor / native.factor


def restore_rows(jsonld, ilcd, activities, nodes, flow_id, process_id, differences, unit_labels):
    """The shared writers supply the format metadata. Restore the source row semantics.

    JSON-LD folds self-inputs into net production and gives elementary exchanges one
    direction. ILCD keeps the rows but derives their direction from their sign. Join
    each serialized exchange to its source before making either change.
    """
    from bw_interchange_export.openlca_export import _uncertainty

    by_process = {process_id(key): key for key in activities}
    used_keys = {tuple(e["input"]) for proc in activities.values() for e in proc["exchanges"]}
    flow_names = {flow_id(key): nodes[key]["name"] for key in used_keys}

    overrides = {(r["key"], r["position"]): r for r in differences}
    units = {}
    with zipfile.ZipFile(jsonld) as archive:
        for name in archive.namelist():
            if name.startswith("unit_groups/") and name.endswith(".json"):
                for unit in json.loads(archive.read(name))["units"]:
                    units[unit["name"]] = {
                        "@type": "Unit",
                        "@id": unit["@id"],
                        "name": unit["name"],
                    }

    def unit_detail(change):
        return (
            f"Declared unit in the provider release: {change['amount_as_built']} "
            f"{change['declared_unit']}. "
            f"Supplier reference unit: {change['supplier_unit']}."
            + (f" Finding {change['finding']}." if change.get("finding") else "")
        )

    def process_json(data):
        process = json.loads(data)
        key = by_process[process["@id"]]
        reference, *other = process["exchanges"]
        if not reference.get("isQuantitativeReference") or reference["flow"]["@id"] != flow_id(key):
            raise ValueError(f"{key}: expected a reference product")
        pending = iter(other)
        rows = []
        references = 0
        for pos, exchange in enumerate(activities[key]["exchanges"]):
            target = tuple(exchange["input"])
            amount = exchange["amount"]
            if target == key:
                row = dict(reference)
                row.pop("isQuantitativeReference", None)
                row["amount"] = amount
                if exchange["type"] == "production":
                    references += 1
                    row["isQuantitativeReference"] = True
                else:
                    row["defaultProvider"] = {
                        "@type": "Process",
                        "@id": process["@id"],
                        "name": process["name"],
                    }
                if exchange.get("comment"):
                    row["description"] = exchange["comment"]
                uncertainty = _uncertainty(exchange)
                if uncertainty is not None:
                    row["uncertainty"] = uncertainty.to_dict()
            else:
                row = next(pending)
                if row["flow"]["@id"] != flow_id(target) or row["amount"] != amount:
                    raise ValueError(
                        f"{key}: cannot associate the written exchange with its source"
                    )
            if change := overrides.get((key, pos)):
                declared = unit_labels.get(change["declared_unit"], change["declared_unit"])
                row["unit"] = units[declared]
                row["description"] = unit_detail(change)
            row["isInput"] = direction(exchange) == "input"
            row["internalId"] = len(rows) + 1
            rows.append(row)
        if references != 1 or next(pending, None) is not None:
            raise ValueError(f"{key}: reference product or exchange count differs")
        process["exchanges"] = rows
        process["lastInternalId"] = len(rows)
        return json.dumps(
            process, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode()

    def flow_xml(data):
        doc = ET.fromstring(data)
        mapped = flow_names.get(doc.findtext(".//{*}UUID"))
        name = doc.find(".//{*}dataSetInformation/{*}name/{*}baseName")
        if mapped is None or name.text == mapped:
            return data
        name.text = mapped
        return ET.tostring(doc, encoding="UTF-8", xml_declaration=True)

    def process_xml(data):
        doc = ET.fromstring(data)
        key = ilcd_key(doc)
        rows = doc.findall(".//{*}exchanges/{*}exchange")
        for pos, (row, exchange) in enumerate(zip(rows, activities[key]["exchanges"], strict=True)):
            if (
                row.find("{*}referenceToFlowDataSet").get("refObjectId")
                != flow_id(tuple(exchange["input"]))
                or float(row.findtext("{*}meanAmount")) != exchange["amount"]
            ):
                raise ValueError(f"{key}: cannot associate the ILCD exchange with its source")
            row.find("{*}exchangeDirection").text = direction(exchange).title()
            ref = row.find("{*}referenceToFlowDataSet")
            label = ref.find("{*}shortDescription")
            if label is not None and label.text != flow_names[ref.get("refObjectId")]:
                comment = row.find("{*}generalComment")
                comment.text = (
                    (comment.text or "") + "\nSource exchange name: " + (label.text or "")
                )
                label.text = flow_names[ref.get("refObjectId")]
            if change := overrides.get((key, pos)):
                declared = unit_labels.get(change["declared_unit"], change["declared_unit"])
                native = unit_labels.get(change["supplier_unit"], change["supplier_unit"])
                factor = magnitude(declared, native)
                for field in ("meanAmount", "resultingAmount", "minimumAmount", "maximumAmount"):
                    value = row.find("{*}" + field)
                    if value is not None:
                        value.text = repr(float(value.text) * factor)
                comment = row.find("{*}generalComment")
                comment.text = (comment.text or "") + "\n" + unit_detail(change)
        return ET.tostring(doc, encoding="UTF-8", xml_declaration=True)

    rewrite(jsonld, {"processes": process_json})
    rewrite(ilcd, {"ILCD/processes": process_xml, "ILCD/flows": flow_xml})


def check_ilcd(path, activities, flow_id, marks, nodes, unit_labels, differences):
    """Read native flow units through flow → property → unit group; compare every process row."""
    from bw_ilcd.units import resolve_unit

    problems = []
    seen = set()
    expected_flows = {
        flow_id(tuple(e["input"])): tuple(e["input"])
        for process in activities.values()
        for e in process["exchanges"]
    }
    unit_notes = {(row["key"], flow_id((row["key"][0], row["supplier"]))) for row in differences}
    native_amount_factor = {}
    for change in differences:
        declared = unit_labels.get(change["declared_unit"], change["declared_unit"])
        native = unit_labels.get(change["supplier_unit"], change["supplier_unit"])
        native_amount_factor[change["key"], change["position"]] = magnitude(declared, native)

    def units_match(native, expected):
        a, b = resolve_unit(native), resolve_unit(unit_labels.get(expected, expected))
        return (a.property_name, a.factor) == (b.property_name, b.factor)

    with zipfile.ZipFile(path) as archive:

        def documents(folder):
            for name in archive.namelist():
                if name.startswith(f"ILCD/{folder}/") and name.endswith(".xml"):
                    yield ET.fromstring(archive.read(name))

        groups = {}
        for doc in documents("unitgroups"):
            index = doc.findtext(".//{*}referenceToReferenceUnit")
            unit = doc.find(f'.//{{*}}unit[@dataSetInternalID="{index}"]')
            if unit is None or float(unit.findtext("{*}meanValue")) != 1:
                raise ValueError("Invalid ILCD reference unit")
            groups[doc.findtext(".//{*}UUID")] = unit.findtext("{*}name")
        props = {
            doc.findtext(".//{*}UUID"): groups[
                doc.find(".//{*}referenceToReferenceUnitGroup").get("refObjectId")
            ]
            for doc in documents("flowproperties")
        }
        units = {}
        for doc in documents("flows"):
            fid = doc.findtext(".//{*}UUID")
            if fid in expected_flows:
                source = expected_flows[fid]
                name = doc.findtext(".//{*}dataSetInformation/{*}name/{*}baseName")
                kind = "Product flow" if source in activities else "Elementary flow"
                if name != nodes[source]["name"] or doc.findtext(".//{*}typeOfDataSet") != kind:
                    problems.append(f"{fid}: ILCD mapped flow name or type differs")
            index = doc.findtext(".//{*}referenceToReferenceFlowProperty")
            prop = doc.find(f'.//{{*}}flowProperty[@dataSetInternalID="{index}"]')
            if prop is None or float(prop.findtext("{*}meanValue")) != 1:
                raise ValueError(f"{fid}: invalid ILCD reference property")
            units[fid] = props[prop.find("{*}referenceToFlowPropertyDataSet").get("refObjectId")]
            if fid in expected_flows and not units_match(
                units[fid], nodes[expected_flows[fid]]["unit"]
            ):
                problems.append(f"{fid}: ILCD native unit differs from the source")
        for doc in documents("processes"):
            key = ilcd_key(doc)
            if key in seen or key not in activities:
                problems.append(f"{key}: duplicate or unexpected process")
                continue
            seen.add(key)
            restrictions = doc.findtext(".//{*}accessRestrictions", "")
            if any(mark not in restrictions for mark in marks):
                problems.append(f"{key}: missing credit or label")
            ref = doc.findtext(".//{*}referenceToReferenceFlow")
            written = Counter()
            for row in doc.findall(".//{*}exchanges/{*}exchange"):
                target = row.find("{*}referenceToFlowDataSet").get("refObjectId")
                amount = float(row.findtext("{*}meanAmount"))
                if target not in units or float(row.findtext("{*}resultingAmount")) != amount:
                    problems.append(f"{key}: unresolved flow or inconsistent exchange amount")
                if (key, target) in unit_notes and "Declared unit" not in row.findtext(
                    "{*}generalComment", ""
                ):
                    problems.append(f"{key}: exchange lacks its declared-unit note")
                written[
                    target,
                    row.findtext("{*}exchangeDirection"),
                    amount,
                    row.get("dataSetInternalID") == ref,
                ] += 1
            expected = Counter(
                (
                    flow_id(tuple(e["input"])),
                    direction(e).title(),
                    e["amount"] * native_amount_factor.get((key, pos), 1),
                    tuple(e["input"]) == key and e["type"] == "production",
                )
                for pos, e in enumerate(activities[key]["exchanges"])
            )
            if expected != written:
                problems.append(
                    f"{key}: ILCD exchange identity, direction, reference or amount differs"
                )
    if seen != set(activities):
        problems.append("ILCD process set differs from the source")
    return problems
