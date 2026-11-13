# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "bw-interchange-export @ git+https://gitlab.com/eos-lci/bw-interchange-export.git@db7af57cabd59b4256d00516027cc298bbcfc2ad",
#     "bw-simapro-csv==0.5",
#     "bw2data==4.8",
#     "bw2io==0.9.17",
#     "olca-schema==2.6.2",
# ]
# ///
"""Export a Brightway build of the patched release for openLCA, SimaPro and Brightway.

Reads one or more databases from a Brightway project and writes, into one folder:

* `<name>.bw2package`: the databases for Brightway (`bw2io.BW2Package.import_file`);
* `<name>-openlca.zip`: openLCA JSON-LD, and `<name>-ilcd.zip`: the same as ILCD;
* `<name>-simapro.csv`: SimaPro CSV;
* `MODIFICATIONS.json` and `MODIFICATIONS.md`: the record of modifications;
* `manifest.json` and `SHA256SUMS`: provider, release, credit, label, tool versions,
  checksums and the result of reading every file back.

The patched release is Modified Data under BAFU's Terms of Use: each file carries the
credit, the label and the ids of the modifications inside it, and the full record
travels beside it. The list of modifications comes from `bafu-fixes run --summary`.

Every file is read back after writing (`olca_schema`, `bw_simapro_csv`, `bw2io`) and
compared with the database: same datasets, exchanges, amounts and units, links intact,
provenance present. A failed check is recorded in the manifest and the step exits 1.

Usage:

    uv run scripts/export_release.py --brightway-dir DIR --project NAME \\
        --database NAME [--database NAME ...] --release "BAFU:2026 v1" \\
        --summary run-summary.json --out DIR

`--brightway-dir` is required on purpose: the step never opens the Brightway
projects in the default location. See docs/exports.md.
"""

import argparse
import hashlib
import json
import math
import os
import platform
import re
import sys
import tempfile
import uuid
import zipfile
from collections import Counter
from importlib import metadata
from pathlib import Path

SCHEMA = "sentier-bafu/export-manifest/1"
LABEL = "Modified Data"
CREDIT = "Life Cycle Inventory database of the Swiss Federal Administration, BAFU:{year}"
NAMESPACE = "https://github.com/sentier-dev/sentier-bafu"
#: Database metadata that changes with every write and says nothing about the data.
VOLATILE_METADATA = ("modified", "processed", "dirty")
#: The name the CSV writer gives the literature reference that holds the attribution.
SIMAPRO_ATTRIBUTION = "Source database attribution"
TOOLS = (
    "bw-interchange-export",
    "bw-ilcd-bridge",
    "olca-schema",
    "bw-simapro-csv",
    "bw2io",
    "bw2data",
)
TECHNOSPHERE_SECTIONS = ("Materials/fuels", "Electricity/heat", "Waste to treatment")
ELEMENTARY_SECTIONS = (
    "Resources",
    "Emissions to air",
    "Emissions to water",
    "Emissions to soil",
    "Final waste flows",
    "Non material emissions",
    "Social issues",
    "Economic issues",
)


class ExportError(Exception):
    """The database or its inputs can't be exported as they are."""


# --- The database ------------------------------------------------------------------


def is_elementary(node):
    """Whether the writers treat a node as an elementary flow (their rule, restated)."""
    kind = (node.get("type") or "").lower()
    return kind in ("emission", "biosphere", "natural resource") or bool(node.get("categories"))


def load_databases(project, names):
    """`{name: {"metadata", "class", "data"}}` for the named databases of a project."""
    import bw2data as bd

    if project not in bd.projects:
        raise ExportError(f"No Brightway project {project!r} in the given Brightway folder")
    bd.projects.set_current(project)
    if missing := [name for name in names if name not in bd.databases]:
        raise ExportError(f"Not in project {project!r}: {', '.join(missing)}")
    if dirty := [name for name in names if bd.databases[name].get("dirty")]:
        raise ExportError(f"Interrupted write, process these databases first: {', '.join(dirty)}")
    loaded = {}
    for name in names:
        database = bd.Database(name)
        kind = type(database)
        loaded[name] = {
            "metadata": dict(bd.databases[name]),
            "class": {"module": kind.__module__, "name": kind.__name__},
            "data": database.load(),
        }
    return loaded


def all_nodes(databases):
    return {key: node for db in databases.values() for key, node in db["data"].items()}


def check_closure(nodes):
    """Refuse a selection whose exchanges point outside it: the writers drop such rows."""
    outside = Counter()
    for node in nodes.values():
        for exchange in node.get("exchanges", ()):
            key = tuple(exchange.get("input") or ())
            if key not in nodes:
                outside[key[0] if key else "(no input)"] += 1
    if outside:
        listed = ", ".join(f"{name} ({count} exchanges)" for name, count in sorted(outside.items()))
        raise ExportError(f"Exchanges point at nodes outside the selected databases: {listed}")


def check_units(nodes, labels):
    """Refuse units the JSON-LD writer has no quantity for, before anything is written."""
    from bw_ilcd.units import resolve_unit

    unknown = Counter()
    for node in nodes.values():
        unit = labels.get(node.get("unit"), node.get("unit"))
        try:
            resolve_unit(unit)
        except ValueError:
            unknown[node.get("unit")] += 1
    if unknown:
        listed = ", ".join(f"{unit!r} ({count} nodes)" for unit, count in sorted(unknown.items()))
        raise ExportError(
            f"The JSON-LD writer has no quantity for these units: {listed}. "
            "Name a label it knows with --openlca-unit-label FROM=TO (amounts stay as they are)."
        )


def net_production(key, node):
    """Production of the node's own product minus its inputs of that product."""
    production, has_production, self_input = 0.0, False, 0.0
    for exchange in node.get("exchanges", ()):
        if tuple(exchange.get("input") or ()) != key:
            continue
        if exchange.get("type") == "production":
            production, has_production = production + exchange["amount"], True
        elif exchange.get("type") == "technosphere":
            self_input += exchange["amount"]
    return (production if has_production else 1.0) - self_input


# --- Provenance --------------------------------------------------------------------


def read_summary(path):
    summary = json.loads(Path(path).read_text(encoding="utf-8"))
    schema = summary.get("schema", "")
    if not schema.startswith("bafu-community-fixes/run-summary/"):
        raise ExportError(f"{path} is not a `bafu-fixes run --summary` file (schema {schema!r})")
    if summary.get("status") != "completed":
        raise ExportError(f"{path} records a run that did not complete: {summary.get('status')}")
    return summary


def modifications_record(summary, release, credit, extra_steps=()):
    """The record of modifications: every step that changed data, and each changed dataset.

    `extra_steps` are changes made after the patch run, for example by the build of the
    Brightway database, in the same shape as the summary's steps.
    """
    for step in extra_steps:
        if missing := {"id", "kind", "description"} - set(step):
            raise ExportError(f"An extra step lacks {', '.join(sorted(missing))}: {step}")
    steps = [step for step in summary["steps"] if step["datasets"]] + list(extra_steps)
    return {
        "schema": "sentier-bafu/modifications/1",
        "label": LABEL,
        "release": release,
        "credit": credit,
        "source_fingerprint_sha256": summary["source"]["fingerprint_sha256"],
        "datasets_in_release": summary["source"]["datasets"],
        "datasets_changed": summary["changed_datasets"],
        "patch_tool": summary["software"],
        "steps": steps,
        "datasets": summary["datasets"] or [],
    }


def modifications_markdown(record):
    """The record for readers: every step in full, the dataset list by reference."""
    lines = [
        f"# Record of modifications: {record['release']}, patched release",
        "",
        f"**{LABEL}.** This is not BAFU's original data. Source: {record['credit']}.",
        "",
        f"{record['datasets_changed']} of {record['datasets_in_release']} datasets were "
        "changed. `MODIFICATIONS.json` lists each changed dataset (number, name, location) "
        "with the steps that changed it.",
        "",
        "| Step | Kind | What it does | Datasets | Values | Written by | Authorised by |",
        "|---|---|---|---|---|---|---|",
    ]
    for step in record["steps"]:
        cells = [
            step["id"],
            step["kind"],
            step["description"],
            step.get("datasets", ""),
            step.get("changes", ""),
            step.get("authored_by") or "",
            step.get("authorised_by") or "not yet authorised",
        ]
        lines.append("| " + " | ".join(str(c).replace("|", "\\|") for c in cells) + " |")
    for step in record["steps"]:
        lines += ["", f"## {step['id']}", "", step["description"]]
        if step.get("rationale"):
            lines += ["", step["rationale"]]
        for label, key in (("Reported by", "reported_by"), ("Confirmed by", "confirmed_by")):
            if step.get(key):
                lines += ["", f"{label}: {step[key]}"]
        lines += ["", *(f"- {reference}" for reference in step.get("references", ()))]
    return "\n".join(lines).rstrip() + "\n"


def attribution(record, terms_url=None):
    """One line with the credit, the label and the modification ids, for inside the files.

    No semicolons, double quotes or question marks: the CSV writer replaces them.
    """
    by_kind = {}
    for step in record["steps"]:
        by_kind.setdefault(step["kind"], []).append(step["id"])
    changes = ". ".join(f"{kind}: {', '.join(ids)}" for kind, ids in by_kind.items())
    terms = f" ({terms_url})" if terms_url else ""
    return (
        f"{LABEL}. Source: {record['credit']}. This is a patched release of "
        f"{record['release']}, not BAFU's original data. Modifications ({changes or 'none'}) "
        "are described in MODIFICATIONS.md and MODIFICATIONS.json, which travel with this "
        f"file. Passed on under terms substantially equivalent to BAFU's Terms of Use{terms}."
    )


def dataset_notes(nodes, record):
    """`{key: note}` for every activity: the label, and the steps that changed it if known.

    The record names datasets by name and location. A node is matched only when exactly
    one record entry has its name and location.
    """
    by_identity = {}
    for dataset in record["datasets"]:
        by_identity.setdefault((dataset["name"], dataset["location"]), []).append(dataset)
    notes, matched = {}, 0
    for key, node in nodes.items():
        if is_elementary(node):
            continue
        note = f"{LABEL}: part of a patched release of {record['release']}, not BAFU's original."
        entries = by_identity.get((node.get("name"), node.get("location")), ())
        if len(entries) == 1:
            matched += 1
            steps = entries[0]["import_fixes"] + entries[0]["patches"]
            note += f" Changed by: {', '.join(steps)}."
        notes[key] = note
    return notes, matched


def tool_versions():
    tools = {"python": platform.python_version()}
    for name in TOOLS:
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        tools[name] = dist.version
        url = json.loads(dist.read_text("direct_url.json") or "{}")
        if commit := url.get("vcs_info", {}).get("commit_id"):
            tools[name] += f" ({url['url']}@{commit})"
    tools["export_release.py sha256"] = sha256(Path(__file__))
    return tools


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


# --- Writing -----------------------------------------------------------------------


def write_bw2package(databases, provenance, path):
    """The databases as one `.bw2package`, each with the provenance in its metadata.

    Databases that others depend on come first, so the package imports in order. Nodes
    are sorted and the volatile metadata is left out, so the same database gives the
    same file.
    """
    from bw2data.serialization import JsonSanitizer, JsonWrapper

    def depth(name, seen=()):
        depends = databases[name]["metadata"].get("depends", ())
        inside = [d for d in depends if d in databases and d != name and d not in seen]
        return 1 + max((depth(d, (*seen, name)) for d in inside), default=0)

    objects = []
    for name in sorted(databases, key=lambda name: (depth(name), name)):
        database = databases[name]
        meta = {k: v for k, v in database["metadata"].items() if k not in VOLATILE_METADATA}
        objects.append(
            {
                "metadata": meta | {"provenance": provenance},
                "name": name,
                "class": database["class"],
                "data": dict(sorted(database["data"].items())),
            }
        )
    JsonWrapper.dump_bz2(JsonSanitizer.sanitize(objects), str(path))
    path.chmod(0o644)  # written owner-only; this file is for handing on


def interchange_view(notes, unit_labels=None, disambiguate=False):
    """A pass over the nodes as the interchange writers load them, in memory only.

    Adds the dataset note to each activity's comment (it becomes the openLCA description
    and the SimaPro comment), applies the unit labels, and, for SimaPro's linked naming,
    gives a product name with the node's code to activities whose default name collides.
    """
    from bw_interchange_export import product_name

    unit_labels = unit_labels or {}

    def transform(nodes):
        names = Counter(
            _clean(product_name(node, key))
            for key, node in nodes.items()
            if not is_elementary(node)
        )
        for key, node in nodes.items():
            if node.get("unit") in unit_labels:
                node["unit"] = unit_labels[node["unit"]]
            for exchange in node.get("exchanges", ()):
                if exchange.get("unit") in unit_labels:
                    exchange["unit"] = unit_labels[exchange["unit"]]
            if key in notes:
                node["comment"] = "\n\n".join(filter(None, [node.get("comment"), notes[key]]))
            if not (disambiguate and not is_elementary(node)):
                continue
            if names[_clean(product_name(node, key))] > 1:
                node["simapro_product_name"] = f"{product_name(node, key)} | {key[1]}"

    return transform


def write_openlca(package, methods, out_openlca, out_ilcd, *, namespace, text, view, stamp):
    from bw_interchange_export import export_openlca_ilcd, load_transform

    with load_transform(view):
        return export_openlca_ilcd(
            package,
            methods,
            out_openlca,
            out_ilcd,
            namespace=namespace,
            quiet=True,
            source_attribution=text,
            source_category="Provenance",
            last_change=stamp,
        )


def write_simapro(package, out_csv, *, project, text, view, naming):
    from bw_interchange_export import export_simapro_csv, load_transform

    with load_transform(view):
        return export_simapro_csv(
            package,
            out_csv,
            project=project,
            quiet=True,
            source_attribution=text,
            source_category="Provenance",
            product_naming=naming,
        )


# --- Reading back ------------------------------------------------------------------


def _same(a, b):
    return math.isclose(a, b, rel_tol=1e-12, abs_tol=0.0)


def _amounts(counter):
    """A multiset of rows with amounts rounded just enough to survive unit conversion."""
    return Counter({(*key[:-1], float(f"{key[-1]:.12g}")): n for key, n in counter.items()})


def _canonical(value):
    return json.dumps(value, sort_keys=True, default=list)


def check_bw2package(path, databases, marks):
    """Problems found when the package is loaded again and compared with the database."""
    from bw2io import BW2Package

    problems = []
    loaded = {obj["name"]: obj for obj in BW2Package.load_file(str(path))}
    if set(loaded) != set(databases):
        problems.append(f"databases {sorted(loaded)} instead of {sorted(databases)}")
    for name, obj in loaded.items():
        source = databases.get(name, {"data": {}})["data"]
        if set(obj["data"]) != set(source):
            problems.append(f"{name}: {len(obj['data'])} nodes instead of {len(source)}")
        differing = [
            k for k, v in obj["data"].items() if _canonical(v) != _canonical(source.get(k))
        ]
        if differing:
            problems.append(f"{name}: {len(differing)} nodes differ, first {differing[0]}")
        text = _canonical(obj["metadata"].get("provenance"))
        problems += [f"{name}: metadata lacks {mark!r}" for mark in marks if mark not in text]
    return problems


def olca_ids(namespace):
    """The ids the JSON-LD writer mints: `uuid5` of the database and code."""
    seed = uuid.uuid5(uuid.NAMESPACE_URL, namespace)

    def flow(key):
        return str(uuid.uuid5(seed, f"{key[0]}|{key[1]}"))

    def process(key):
        return str(uuid.uuid5(seed, f"proc|{key[0]}|{key[1]}"))

    return flow, process


def read_openlca(path):
    import olca_schema as o
    from olca_schema import zipio

    with zipio.ZipReader(str(path)) as reader:
        return {
            "flows": {f.id: f for f in reader.read_each(o.Flow)},
            "processes": {p.id: p for p in reader.read_each(o.Process)},
            "units": {u.id: u for g in reader.read_each(o.UnitGroup) for u in g.units},
            "properties": {p.id: p for p in reader.read_each(o.FlowProperty)},
            "locations": {loc.id: loc for loc in reader.read_each(o.Location)},
            "categories": {c.id: c for c in reader.read_each(o.ImpactCategory)},
        }


def check_openlca(path, nodes, namespace, marks, unit_labels=None):
    """Problems found when the JSON-LD archive is read back and compared with the database."""
    import olca_schema as o

    unit_labels = unit_labels or {}
    flow_id, process_id = olca_ids(namespace)
    archive = read_openlca(path)
    flows, processes = archive["flows"], archive["processes"]
    problems = []

    def unit(node):
        return unit_labels.get(node.get("unit"), node.get("unit"))

    activities = {key: node for key, node in nodes.items() if not is_elementary(node)}
    if len(processes) != len(activities):
        problems.append(f"{len(processes)} processes instead of {len(activities)}")
    if len(flows) != len(nodes):
        problems.append(f"{len(flows)} flows instead of {len(nodes)}")
    for key, node in nodes.items():
        flow = flows.get(flow_id(key))
        if flow is None:
            problems.append(f"{key}: no flow")
        elif flow.name != node.get("name"):
            problems.append(f"{key}: flow is named {flow.name!r}")
        elif is_elementary(node) != (flow.flow_type == o.FlowType.ELEMENTARY_FLOW):
            problems.append(f"{key}: flow type {flow.flow_type}")
        elif is_elementary(node) and flow.category != "/".join(node.get("categories") or ()):
            problems.append(f"{key}: compartment {flow.category!r}")

    for key, node in activities.items():
        process = processes.get(process_id(key))
        if process is None:
            problems.append(f"{key}: no process")
            continue
        documentation = process.process_documentation
        restrictions = (documentation.restrictions_description or "") if documentation else ""
        for mark in marks:
            if mark not in restrictions:
                problems.append(f"{key}: restrictions lack {mark!r}")
        if LABEL not in (process.description or ""):
            problems.append(f"{key}: description lacks {LABEL!r}")
        if process.name != node.get("name"):
            problems.append(f"{key}: process is named {process.name!r}")
        location = archive["locations"].get(process.location.id) if process.location else None
        if (location.code if location else None) != node.get("location"):
            problems.append(f"{key}: location {location.code if location else None!r}")

        expected = Counter()
        for exchange in node.get("exchanges", ()):
            target = tuple(exchange["input"])
            if target == key:
                continue  # folded into the reference amount
            provider = None
            if exchange["type"] == "technosphere" and not is_elementary(nodes[target]):
                provider = process_id(target)
            expected[(flow_id(target), unit(nodes[target]), provider, exchange["amount"])] += 1
        written = Counter()
        for exchange in process.exchanges:
            refs = (
                exchange.flow.id in flows,
                exchange.unit.id in archive["units"],
                exchange.flow_property.id in archive["properties"],
                exchange.default_provider is None or exchange.default_provider.id in processes,
            )
            if not all(refs):
                problems.append(f"{key}: an exchange refers to something not in the archive")
            row = (exchange.flow.id, archive["units"][exchange.unit.id].name)
            if exchange.is_quantitative_reference:
                if row != (flow_id(key), unit(node)):
                    problems.append(f"{key}: reference exchange is {row}")
                if not _same(exchange.amount, net_production(key, node)):
                    problems.append(f"{key}: reference amount {exchange.amount}")
                continue
            provider = exchange.default_provider.id if exchange.default_provider else None
            written[(*row, provider, exchange.amount)] += 1
        if _amounts(written) != _amounts(expected):
            problems.append(f"{key}: exchanges differ from the database")
    return problems


def _clean(text):
    """The CSV writer's field cleaning, so names can be compared."""
    text = str(text or "").replace(";", ",").replace('"', "”")
    return text.replace("\n", " ").replace("\r", " ").strip()


def read_simapro(path):
    """`{process identifier: {"metadata", "products", "inputs", "elementary"}}` and the rest."""
    from bw_simapro_csv import SimaProCSV
    from bw_simapro_csv.blocks import LiteratureReference, Process

    def rows(block, sections):
        found = []
        for section in sections:
            for row in block.blocks[section].parsed if section in block.blocks else ():
                # The parser converts to reference units; undo it to compare amounts.
                factor = row.get("unit conversion factor", 1.0)
                unit = row.get("original unit before conversion", row["unit"])
                found.append(
                    row | {"section": section, "amount": row["amount"] / factor, "unit": unit}
                )
        return found

    parsed = SimaProCSV(Path(path), stderr_logs=False, write_logs=False)
    processes = {}
    for block in parsed.blocks:
        if isinstance(block, Process):
            processes[block.parsed["metadata"]["Process identifier"]] = {
                "metadata": block.parsed["metadata"],
                "products": rows(block, ("Products",)),
                "avoided": rows(block, ("Avoided products",)),
                "inputs": rows(block, TECHNOSPHERE_SECTIONS),
                "elementary": rows(block, ELEMENTARY_SECTIONS),
            }
    literature = [b.parsed for b in parsed.blocks if isinstance(b, LiteratureReference)]
    text = Path(path).read_bytes().decode("cp1252")
    header = [line for line in text.split("\n\n", 1)[0].splitlines() if line.startswith("{")]
    return {"processes": processes, "literature": literature, "header": header}


def simapro_links(csv):
    """How each input row resolves to a product row by name, as SimaPro links them.

    Returns `(providers, counts)`: `providers[(process, row index)]` is the one process
    that makes a product of that name, or None; `counts` tallies resolved, ambiguous and
    missing rows.
    """
    makers = {}
    for identifier, process in csv["processes"].items():
        for product in process["products"]:
            makers.setdefault(product["name"], []).append(identifier)
    providers, counts = {}, Counter(resolved=0, ambiguous=0, missing=0)
    for identifier, process in csv["processes"].items():
        for index, row in enumerate(process["inputs"]):
            found = makers.get(row["name"], [])
            state = "resolved" if len(found) == 1 else "ambiguous" if found else "missing"
            counts[state] += 1
            providers[(identifier, index)] = found[0] if state == "resolved" else None
    return providers, dict(counts)


def check_simapro(path, nodes, marks):
    """Problems found when the CSV is parsed again and compared with the database."""
    csv = read_simapro(path)
    providers, counts = simapro_links(csv)
    problems = []
    activities = {key: node for key, node in nodes.items() if not is_elementary(node)}
    identifiers = {f"{key[0]}|{key[1]}": key for key in activities}
    if set(csv["processes"]) != set(identifiers):
        problems.append(f"{len(csv['processes'])} processes instead of {len(identifiers)}")
    if counts["ambiguous"] or counts["missing"]:
        problems.append(
            f"{counts['missing']} input rows name no product in the file and "
            f"{counts['ambiguous']} name more than one"
        )
    header = "\n".join(csv["header"])
    sources = [r for r in csv["literature"] if r.get("Name") == SIMAPRO_ATTRIBUTION]
    described = sources[0].get("Description") or "" if sources else ""
    for mark in marks:
        if _clean(mark) not in header:
            problems.append(f"header lacks {mark!r}")
        if _clean(mark) not in described:
            problems.append(f"literature reference lacks {mark!r}")

    for identifier, process in csv["processes"].items():
        key = identifiers.get(identifier)
        if key is None:
            continue
        node = nodes[key]
        if LABEL not in (process["metadata"].get("Comment") or ""):
            problems.append(f"{key}: comment lacks {LABEL!r}")
        product = process["products"][0]
        if not _same(product["amount"], net_production(key, node)):
            problems.append(f"{key}: product amount {product['amount']}")
        technosphere, elementary = Counter(), Counter()
        for exchange in node.get("exchanges", ()):
            target = tuple(exchange["input"])
            if target == key or exchange["type"] == "production":
                continue
            if is_elementary(nodes[target]):
                flow = nodes[target]
                sub = (flow.get("categories") or ("", ""))[1:2]
                elementary[
                    (_clean(flow["name"]), _clean(sub[0] if sub else ""), exchange["amount"])
                ] += 1
            else:
                technosphere[(f"{target[0]}|{target[1]}", exchange["amount"])] += 1
        linked = Counter(
            (providers[(identifier, index)], row["amount"])
            for index, row in enumerate(process["inputs"])
        )
        if _amounts(linked) != _amounts(technosphere):
            problems.append(f"{key}: inputs differ from the database, or link elsewhere")
        emitted = Counter(
            (row["name"], row["context"][1], row["amount"]) for row in process["elementary"]
        )
        if _amounts(emitted) != _amounts(elementary):
            problems.append(f"{key}: elementary flows differ from the database")
    return problems, counts


def check_ilcd(path, activities, marks):
    """The ILCD package is only counted and searched for the credit, not compared."""
    problems = []
    with zipfile.ZipFile(path) as archive:
        members = [n for n in archive.namelist() if n.startswith("ILCD/processes/")]
        if len(members) != activities:
            problems.append(f"{len(members)} process datasets instead of {activities}")
        for member in members:
            text = archive.read(member).decode("utf-8")
            if any(mark not in text for mark in marks):
                problems.append(f"{member}: lacks the credit or the label")
                break
    return problems


# --- The step ----------------------------------------------------------------------


def provenance_record(record, text, files, tools, *, provider, source_url, source_sha256):
    """What every export says about itself: who, which release, what changed, with what."""
    return {
        "label": LABEL,
        "provider": provider,
        "release": record["release"],
        "credit": record["credit"],
        "statement": text,
        "source": {
            "url": source_url,
            "sha256": source_sha256,
            "fingerprint_sha256": record["source_fingerprint_sha256"],
        },
        "modifications": {
            "record": files["modifications"].name,
            "sha256": sha256(files["modifications"]),
            "steps": [
                {k: step.get(k) for k in ("id", "kind", "description", "datasets", "authorised_by")}
                for step in record["steps"]
            ],
        },
        "tools": tools,
    }


def export_release(
    databases,
    summary,
    out,
    *,
    release,
    name=None,
    year=None,
    provider="BAFU, Swiss Federal Office for the Environment",
    source_url=None,
    source_sha256=None,
    terms_url=None,
    methods=None,
    namespace=NAMESPACE,
    simapro_naming="linked",
    openlca_unit_labels=None,
    extra_steps=(),
):
    """Write the exports with their provenance into `out`, read them back, and return
    the manifest. Raises before anything stays written when the database can't be
    exported; a read-back that differs is in the manifest (`status: failed`).
    """
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise ExportError(f"{out} is not empty")
    nodes = all_nodes(databases)
    labels = dict(openlca_unit_labels or {})
    check_closure(nodes)
    check_units(nodes, labels)
    year = year or (re.search(r"\b(\d{4})\b", release) or [None, None])[1]
    if not year:
        raise ExportError(f"No release year in {release!r}; pass it")
    credit = CREDIT.format(year=year)
    record = modifications_record(summary, release, credit, extra_steps)
    text = attribution(record, terms_url)
    notes, matched = dataset_notes(nodes, record)
    name = name or re.sub(r"[^a-z0-9]+", "-", release.lower()).strip("-") + "-patched"
    files = {
        "brightway": out / f"{name}.bw2package",
        "openlca": out / f"{name}-openlca.zip",
        "ilcd": out / f"{name}-ilcd.zip",
        "simapro": out / f"{name}-simapro.csv",
        "modifications": out / "MODIFICATIONS.json",
        "modifications_readable": out / "MODIFICATIONS.md",
    }
    tools = tool_versions()

    out.mkdir(parents=True, exist_ok=True)
    try:
        files["modifications"].write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        files["modifications_readable"].write_text(modifications_markdown(record), encoding="utf-8")
        provenance = provenance_record(
            record, text, files, tools,
            provider=provider, source_url=source_url, source_sha256=source_sha256,
        )  # fmt: skip
        write_bw2package(databases, provenance, files["brightway"])
        with tempfile.TemporaryDirectory() as scratch:
            no_methods = Path(scratch) / "methods.json"
            no_methods.write_text("{}")
            openlca_stats = write_openlca(
                files["brightway"],
                methods or no_methods,
                files["openlca"],
                files["ilcd"],
                namespace=namespace,
                text=text,
                view=interchange_view(notes, labels),
                stamp=summary.get("finished"),
            )
        simapro_stats = write_simapro(
            files["brightway"],
            files["simapro"],
            project=f"{release} patched release, {LABEL}",
            text=text,
            view=interchange_view(notes, disambiguate=simapro_naming == "linked"),
            naming=simapro_naming,
        )
    except Exception:
        # Nothing half-written stays behind: the folder was empty when the step began.
        for path in files.values():
            path.unlink(missing_ok=True)
        raise

    marks = (credit, LABEL)
    activities = sum(1 for node in nodes.values() if not is_elementary(node))
    simapro_problems, links = check_simapro(files["simapro"], nodes, marks)
    checks = {
        "brightway": check_bw2package(files["brightway"], databases, marks),
        "openlca": check_openlca(files["openlca"], nodes, namespace, marks, labels),
        "ilcd": check_ilcd(files["ilcd"], activities, marks),
        "simapro": simapro_problems,
    }
    manifest = {
        "schema": SCHEMA,
        "status": "failed" if any(checks.values()) else "completed",
        **{k: provenance[k] for k in ("label", "provider", "release", "credit", "statement")},
        "source": provenance["source"],
        "modifications": provenance["modifications"],
        "databases": {n: len(db["data"]) for n, db in databases.items()},
        "counts": {
            "activities": activities,
            "elementary_flows": len(nodes) - activities,
            "exchanges": sum(len(node.get("exchanges", ())) for node in nodes.values()),
            "datasets_matched_to_the_record": matched,
        },
        "openlca": {
            "ids": "minted: uuid5 of the namespace, the database name and the node code",
            "namespace": namespace,
            "unit_labels": labels,
            "last_change": summary.get("finished"),
            "written": openlca_stats,
        },
        "simapro": {
            "flow_names": "elementary flows keep the Brightway names and subcompartments",
            "product_naming": simapro_naming,
            "links": links,
            "written": simapro_stats,
        },
        "tools": tools,
        "files": {
            kind: {"name": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
            for kind, path in files.items()
        },
        "checks": {
            kind: {"passed": not problems, "problems": problems[:50], "total": len(problems)}
            for kind, problems in checks.items()
        },
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    sums = [f"{sha256(p)}  {p.name}" for p in sorted(out.iterdir()) if p.name != "SHA256SUMS"]
    (out / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    return manifest


def _pairs(values, option):
    pairs = {}
    for value in values or ():
        old, sep, new = value.partition("=")
        if not sep or not old or not new:
            raise ExportError(f"{option} takes FROM=TO, not {value!r}")
        pairs[old] = new
    return pairs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--brightway-dir", type=Path, required=True, help="BRIGHTWAY2_DIR to read")
    parser.add_argument("--project", required=True)
    parser.add_argument(
        "--database",
        action="append",
        required=True,
        help="Repeat for every database the inventory links to (elementary flows too)",
    )
    parser.add_argument(
        "--summary", type=Path, required=True, help="From `bafu-fixes run --summary`"
    )
    parser.add_argument("--release", required=True, help='For example "BAFU:2026 v1"')
    parser.add_argument("--out", type=Path, required=True, help="An empty or new folder")
    parser.add_argument("--name", help="File name stem (default: from the release)")
    parser.add_argument("--source-url", help="Where the provider release was downloaded")
    parser.add_argument("--source-sha256", help="Checksum of that download")
    parser.add_argument("--terms-url", help="Where BAFU's Terms of Use can be read")
    parser.add_argument("--methods-cf", type=Path, help="Impact factors for the openLCA export")
    parser.add_argument("--namespace", default=NAMESPACE, help="Seed of the openLCA ids")
    parser.add_argument("--simapro-product-naming", choices=("linked", "legacy"), default="linked")
    parser.add_argument(
        "--openlca-unit-label",
        action="append",
        metavar="FROM=TO",
        help="Write a unit the JSON-LD writer does not know under another label",
    )
    parser.add_argument(
        "--extra-steps", type=Path, help="JSON list of further modification steps to record"
    )
    args = parser.parse_args(argv)

    os.environ["BRIGHTWAY2_DIR"] = str(args.brightway_dir.resolve())
    try:
        if not args.brightway_dir.is_dir():
            raise ExportError(f"{args.brightway_dir} is not a folder")
        extra = json.loads(args.extra_steps.read_text()) if args.extra_steps else ()
        manifest = export_release(
            load_databases(args.project, args.database),
            read_summary(args.summary),
            args.out,
            release=args.release,
            name=args.name,
            source_url=args.source_url,
            source_sha256=args.source_sha256,
            terms_url=args.terms_url,
            methods=args.methods_cf,
            namespace=args.namespace,
            simapro_naming=args.simapro_product_naming,
            openlca_unit_labels=_pairs(args.openlca_unit_label, "--openlca-unit-label"),
            extra_steps=extra,
        )
    except (ExportError, ValueError) as error:
        sys.exit(f"Not exported: {error}")
    for kind, check in manifest["checks"].items():
        print(f"{kind}: {'read back and matches' if check['passed'] else 'DIFFERS'}")
        for problem in check["problems"][:10]:
            print(f"  {problem}")
    print(f"Wrote {len(manifest['files'])} files and manifest.json to {args.out}")
    if manifest["status"] != "completed":
        sys.exit(1)


if __name__ == "__main__":
    main()
