"""Audit a Brightway database installed by sentier-brightway and write one JSON file.

It reads the Brightway project itself, not the files it was built from:

- datasets and exchanges, by kind;
- exchanges whose input does not exist (unlinked), and elementary exchanges that stayed on a
  BAFU flow because the mapping has no EF 3.1 flow for it;
- per method, how many of the elementary flows the inventory uses carry a characterisation
  factor, and how many exchanges that covers;
- scores of a fixed sample of datasets for EF 3.1 climate change, and of every dataset for
  every method (written beside the audit as `scores.csv`).

Errors fail the audit: an unlinked exchange, a score that is not a number. Findings are
things a person has to look at: a sample score outside its plausible range, or elementary
flows that the pinned flow terms don't hold (a patch renamed or moved them, so they lost
their EF 3.1 flow). `--fail-on-findings` turns findings into a failure.

Scores are computed from one factorisation of the technosphere matrix: one solve per sample
dataset, and one transposed solve per method for all datasets. The two must agree, the
residual of every solve is checked, and three sample scores are recomputed with bw2calc's
own `LCA`. `LeastSquaresLCA` is never used.

Run it in the environment that holds sentier-brightway, with `BRIGHTWAY2_DIR` set to the
folder the build wrote. It refuses to run without `BRIGHTWAY2_DIR`, so that it can't open
the Brightway projects a person keeps in their default folder.
"""

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import sys
import time
from collections import Counter
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

AUDIT_VERSION = 1
BIOSPHERE_DB = "ef-3.1-biosphere"
PROVIDER_DB = "bafu-2026"  # BAFU's name: only a database of the provider release carries it
MARKER = "release_build"  # written into the database metadata by `mark_database.py`
CLIMATE_METHOD = "ef-3.1:climate-change"
RESIDUAL_TOLERANCE = 1e-8  # relative residual of a linear solve
AGREEMENT_TOLERANCE = 1e-6  # between the per-dataset solve, the transposed solve and bw2calc
BW2CALC_CHECKS = 3
MAX_REFINEMENTS = 3
DOCUMENTED_TOLERANCE = 1e-5  # a documented score is given to six significant digits


class AuditError(Exception):
    """The project can't be audited as asked; the message says why."""


# --- Pure helpers (no Brightway needed) -----------------------------------------------


def load_sample(path: Path) -> list[dict]:
    """The fixed sample: dataset code, name, location, and an optional plausible range."""
    sample = json.loads(path.read_text())["datasets"]
    codes = [item["code"] for item in sample]
    if len(set(codes)) != len(codes):
        raise AuditError(f"{path}: dataset codes repeat")
    for item in sample:
        low, high = item.get("plausible_range", (None, None))
        if (low is None) != (high is None) or (low is not None and not low < high):
            raise AuditError(f"{path}: {item['code']}: plausible_range must be [low, high]")
    return sample


def range_flag(score: float, plausible_range: list[float] | None) -> str | None:
    """`None` if the score is inside the range (or there is none), else what is wrong."""
    if not math.isfinite(score):
        return "not a finite number"
    if plausible_range is None:
        return None
    low, high = plausible_range
    if score < low:
        return f"below the plausible range {low:g} to {high:g}"
    if score > high:
        return f"above the plausible range {low:g} to {high:g}"
    return None


def exchange_accounting(
    rows: list[tuple[str, str, str]],
    nodes: set[tuple[str, str]],
    inventory_db: str,
    residual_db: str,
) -> dict:
    """Counts by kind and link target. `rows` are `(input database, input code, type)`."""
    kinds = Counter(kind for _, _, kind in rows)
    unlinked = Counter(kind for database, code, kind in rows if (database, code) not in nodes)
    biosphere = Counter(database for database, _, kind in rows if kind == "biosphere")
    other_targets = {
        database: count
        for database, count in sorted(biosphere.items())
        if database not in (BIOSPHERE_DB, residual_db)
    }
    wrong_database = sum(
        1
        for database, _, kind in rows
        if kind in ("production", "technosphere") and database != inventory_db
    )
    known = {"production", "technosphere", "biosphere"}
    return {
        "exchanges": {kind: kinds.get(kind, 0) for kind in sorted(known)}
        | {"total": len(rows), "other_kinds": sum(n for k, n in kinds.items() if k not in known)},
        "unlinked": {
            "technosphere": unlinked.get("technosphere", 0),
            "production": unlinked.get("production", 0),
            "biosphere": unlinked.get("biosphere", 0),
            "technosphere_or_production_outside_inventory_database": wrong_database,
        },
        "biosphere_targets": {
            "ef_3_1": biosphere.get(BIOSPHERE_DB, 0),
            "no_ef_3_1_flow": biosphere.get(residual_db, 0),
            "other_databases": other_targets,
        },
    }


def method_coverage(
    emitted: Counter, factors: dict[tuple[str, str], float], residual_db: str
) -> dict:
    """Coverage of one method. `emitted` counts elementary exchanges per flow key."""
    with_factor = [key for key in emitted if key in factors]
    without = [key for key in emitted if key not in factors]
    return {
        "factors": len(factors),
        "flows_used": len(emitted),
        "flows_with_factor": len(with_factor),
        "flows_with_zero_factor": sum(1 for key in with_factor if factors[key] == 0),
        "flows_without_factor": len(without),
        "flows_without_factor_no_ef_3_1_flow": sum(1 for key in without if key[0] == residual_db),
        "exchanges_with_factor": sum(emitted[key] for key in with_factor),
        "exchanges_without_factor": sum(emitted[key] for key in without),
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


# --- Linear algebra --------------------------------------------------------------------


class Factorised:
    """One factorisation of the technosphere matrix, used for every solve.

    Every solution is checked by its residual. The inventory spans many orders of magnitude,
    and a plain triangular solve of the transposed system has been seen to leave a relative
    residual near 1e-5, so a solution above the tolerance is refined (the residual is solved
    for and added) before it is accepted or refused.
    """

    def __init__(self, matrix):
        import scipy.sparse as sp

        self.matrix = sp.csc_matrix(matrix)
        try:  # UMFPACK where it is installed; SciPy's SuperLU otherwise
            from scikits.umfpack import splu

            self.solver = "umfpack"
            self._lu = splu(self.matrix)
            self._lu_transposed = splu(self.matrix.T.tocsc())
        except ImportError:
            from scipy.sparse.linalg import splu

            self.solver = "superlu"
            try:
                self._lu = splu(self.matrix)
            except RuntimeError as error:  # "Factor is exactly singular"
                raise AuditError(f"The technosphere matrix can't be factorised: {error}") from None
            self._lu_transposed = None
        self.worst_residual = 0.0
        self.refinements = 0

    def _refined(self, matrix, rhs, solve, what: str):
        import numpy as np

        scale = np.maximum(np.linalg.norm(rhs, axis=0), np.finfo(float).tiny)
        solution = solve(rhs)
        for step in range(MAX_REFINEMENTS + 1):
            remainder = rhs - matrix @ solution
            worst = float(np.max(np.linalg.norm(remainder, axis=0) / scale))
            if worst <= RESIDUAL_TOLERANCE:
                self.worst_residual = max(self.worst_residual, worst)
                return solution
            if step < MAX_REFINEMENTS:
                solution = solution + solve(remainder)
                self.refinements += 1
        raise AuditError(f"{what}: relative residual {worst:.3g} > {RESIDUAL_TOLERANCE:g}")

    def solve(self, rhs):
        return self._refined(self.matrix, rhs, self._lu.solve, "solve")

    def solve_transposed(self, rhs):
        if self._lu_transposed is not None:
            solve = self._lu_transposed.solve
        else:

            def solve(values):
                return self._lu.solve(values, trans="T")

        return self._refined(self.matrix.T, rhs, solve, "transposed solve")


# --- Reading the project -----------------------------------------------------------------


def open_project(project: str):
    if not os.environ.get("BRIGHTWAY2_DIR"):
        raise AuditError(
            "BRIGHTWAY2_DIR is not set. Point it at the folder this build wrote; the audit "
            "does not open projects in the default Brightway folder."
        )
    import bw2data as bd

    if project not in bd.projects:
        raise AuditError(f"No Brightway project {project!r} in {os.environ['BRIGHTWAY2_DIR']}")
    bd.projects.set_current(project)
    dirty = sorted(name for name, meta in bd.databases.items() if meta.get("dirty"))
    if dirty:
        raise AuditError(
            f"Databases {dirty} are marked dirty: a write was interrupted. Rebuild the project; "
            "waiting longer will not help."
        )
    return bd


def read_project(bd, inventory_db: str, residual_db: str) -> dict:
    from bw2data.backends import ActivityDataset, ExchangeDataset

    for name in (inventory_db, BIOSPHERE_DB, residual_db):
        if name not in bd.databases:
            raise AuditError(f"Database {name!r} is not in the project: {sorted(bd.databases)}")
    node_rows = list(
        ActivityDataset.select(
            ActivityDataset.id, ActivityDataset.database, ActivityDataset.code
        ).tuples()
    )
    exchange_rows = list(
        ExchangeDataset.select(
            ExchangeDataset.input_database,
            ExchangeDataset.input_code,
            ExchangeDataset.type,
            ExchangeDataset.output_code,
        )
        .where(ExchangeDataset.output_database == inventory_db)
        .tuples()
    )
    return {
        "key_of_id": {node_id: (database, code) for node_id, database, code in node_rows},
        "nodes": {(database, code) for _, database, code in node_rows},
        "nodes_per_database": dict(sorted(Counter(db for _, db, _ in node_rows).items())),
        "exchanges": exchange_rows,
    }


def read_methods(bd, key_of_id: dict) -> list[dict]:
    methods = []
    for key in sorted(bd.methods):
        meta = bd.methods[key]
        factors = {}
        for flow, value in bd.Method(key).load():
            flow_key = key_of_id.get(flow) if isinstance(flow, int) else tuple(flow)
            if flow_key is None:
                raise AuditError(f"Method {key}: factor for a flow that is not in the project")
            if flow_key in factors:
                raise AuditError(f"Method {key}: two factors for flow {flow_key}")
            factors[flow_key] = float(value)
        methods.append(
            {
                "key": key,
                "id": meta.get("sentier_method_id") or " | ".join(key),
                "unit": meta.get("unit"),
                "factors": factors,
            }
        )
    return methods


# --- Scores -----------------------------------------------------------------------------


def compute_scores(
    bd, inventory_db: str, methods: list[dict], sample: list[dict], id_of_key: dict
) -> dict:
    import bw2calc as bc
    import numpy as np

    climate = next((m for m in methods if m["id"] == CLIMATE_METHOD), None)
    if climate is None:
        raise AuditError(f"Method {CLIMATE_METHOD} is not installed")
    nodes = {
        node["code"]: node
        for node in bd.Database(inventory_db)
        if node.get("type") in ("process", "processwithreferenceproduct")
    }
    missing = [item["code"] for item in sample if item["code"] not in nodes]
    if missing:
        raise AuditError(f"Sample datasets not in {inventory_db}: {missing}")
    first = nodes[sample[0]["code"]] if sample else next(iter(nodes.values()))
    demand, data_objs, _ = bd.prepare_lca_inputs({first: 1.0}, method=climate["key"])
    lca = bc.LCA(demand, data_objs=data_objs)
    lca.load_lci_data()
    technosphere, biosphere = lca.technosphere_matrix, lca.biosphere_matrix
    if technosphere.shape[0] != technosphere.shape[1]:
        raise AuditError(f"Technosphere matrix is not square: {technosphere.shape}")

    started = time.perf_counter()
    lu = Factorised(technosphere)
    factorise_seconds = time.perf_counter() - started

    characterisation = np.zeros((biosphere.shape[0], len(methods)))
    for column, method in enumerate(methods):
        for flow_key, value in method["factors"].items():
            flow_id = id_of_key.get(flow_key)
            if flow_id in lca.dicts.biosphere:  # flows no dataset uses are not in the matrix
                characterisation[lca.dicts.biosphere[flow_id], column] = value
    # score(j, m) = c_m' B inv(A) e_j = (inv(A') B' c_m)_j: one transposed solve per method
    started = time.perf_counter()
    all_scores = lu.solve_transposed(np.asarray(biosphere.T @ characterisation))
    adjoint_seconds = time.perf_counter() - started

    codes = sorted(nodes)
    rows = np.array([lca.dicts.product[nodes[code].id] for code in codes])
    table = all_scores[rows, :]
    climate_column = methods.index(climate)
    position = {code: i for i, code in enumerate(codes)}

    started = time.perf_counter()
    entries, flags, worst_disagreement = [], [], 0.0
    floor = 1e-9 * float(np.max(np.abs(table[:, climate_column])))
    for item in sample:
        node = nodes[item["code"]]
        unit_demand = np.zeros(technosphere.shape[0])
        unit_demand[lca.dicts.product[node.id]] = 1.0
        supply = lu.solve(unit_demand)
        score = float(characterisation[:, climate_column] @ (biosphere @ supply))
        adjoint = float(table[position[item["code"]], climate_column])
        if not math.isclose(score, adjoint, rel_tol=AGREEMENT_TOLERANCE, abs_tol=floor):
            raise AuditError(
                f"{item['code']}: per-dataset solve {score!r} != transposed solve {adjoint!r}"
            )
        if score:
            worst_disagreement = max(worst_disagreement, abs(score - adjoint) / abs(score))
        flag = range_flag(score, item.get("plausible_range"))
        entry = {
            "code": item["code"],
            "name": node["name"],
            "location": node["location"],
            "unit": node["unit"],
            "score": score,
            "plausible_range": item.get("plausible_range"),
            "flag": flag,
        }
        for field in ("name", "location"):
            if item.get(field) is not None and item[field] != node[field]:
                entry[f"sample_{field}"] = item[field]
        if (documented := item.get("documented_score")) is not None:
            entry["documented_score"] = documented | {
                "agrees": math.isclose(score, documented["value"], rel_tol=DOCUMENTED_TOLERANCE)
            }
        entries.append(entry)
        if flag:
            flags.append(f"{node['name']} ({node['location']}): {score:.6g}, {flag}")
    sample_seconds = time.perf_counter() - started

    checked = []
    for item in sample[:BW2CALC_CHECKS]:
        node = nodes[item["code"]]
        demand, data_objs, _ = bd.prepare_lca_inputs({node: 1.0}, method=climate["key"])
        stock = bc.LCA(demand, data_objs=data_objs)
        stock.lci()
        stock.lcia()
        ours = table[position[item["code"]], climate_column]
        if not math.isclose(stock.score, ours, rel_tol=AGREEMENT_TOLERANCE, abs_tol=floor):
            raise AuditError(f"{item['code']}: bw2calc {stock.score!r} != this audit {ours!r}")
        checked.append(item["code"])

    return {
        "codes": codes,
        "nodes": nodes,
        "table": table,
        "climate_column": climate_column,
        "summary": {
            "method": CLIMATE_METHOD,
            "method_key": list(climate["key"]),
            "unit": climate["unit"],
            "solver": lu.solver,
            "matrix": {
                "technosphere_shape": list(technosphere.shape),
                "technosphere_stored_values": int(technosphere.nnz),
                "biosphere_shape": list(biosphere.shape),
                "biosphere_stored_values": int(biosphere.nnz),
            },
            "checks": {
                "worst_relative_residual": lu.worst_residual,
                "refinement_steps": lu.refinements,
                "worst_sample_disagreement_between_solves": worst_disagreement,
                "recomputed_with_bw2calc": checked,
                "residual_tolerance": RESIDUAL_TOLERANCE,
                "agreement_tolerance": AGREEMENT_TOLERANCE,
            },
            "seconds": {
                "factorise": round(factorise_seconds, 3),
                "all_datasets_all_methods": round(adjoint_seconds, 3),
                "sample": round(sample_seconds, 3),
            },
            "sample": entries,
            "range_flags": flags,
        },
    }


def write_scores(path: Path, scores: dict, methods: list[dict]) -> None:
    """Every dataset's score for every method. Derived results; keep them with the build."""
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["code", *[method["id"] for method in methods]])
        for code, row in zip(scores["codes"], scores["table"], strict=True):
            writer.writerow([code, *[repr(float(value)) for value in row]])


# --- The audit ---------------------------------------------------------------------------


def audit(project: str, inventory_db: str, sample_path: Path, out_dir: Path, label: str) -> dict:
    import numpy as np

    residual_db = f"{inventory_db}-residual"
    bd = open_project(project)
    data = read_project(bd, inventory_db, residual_db)
    accounting = exchange_accounting(
        [(database, code, kind) for database, code, kind, _ in data["exchanges"]],
        data["nodes"],
        inventory_db,
        residual_db,
    )
    emitted = Counter(
        (database, code) for database, code, kind, _ in data["exchanges"] if kind == "biosphere"
    )
    methods = read_methods(bd, data["key_of_id"])
    coverage = [
        {"id": m["id"], "unit": m["unit"]} | method_coverage(emitted, m["factors"], residual_db)
        for m in methods
    ]
    any_factor = set().union(*(m["factors"] for m in methods)) if methods else set()
    residual_nodes = {
        key: bd.get_node(database=key[0], code=key[1]) for key in emitted if key[0] == residual_db
    }
    residual_names = sorted({node["name"] for node in residual_nodes.values()})
    # sentier-brightway gives a flow without an EF 3.1 flow its compartment from the pinned
    # flow terms. A flow with no compartment is one those terms don't hold: its name,
    # compartment or unit differs from BAFU's release, so the mapping can't know it either.
    unknown = {key: node for key, node in residual_nodes.items() if not node.get("categories")}
    unknown_names = sorted({node["name"] for node in unknown.values()})
    unknown_exchanges = sum(emitted[key] for key in unknown)
    id_of_key = {key: node_id for node_id, key in data["key_of_id"].items()}
    scores = compute_scores(bd, inventory_db, methods, load_sample(sample_path), id_of_key)
    out_dir.mkdir(parents=True, exist_ok=True)
    scores_path = out_dir / "scores.csv"
    write_scores(scores_path, scores, methods)

    table = scores["table"]
    datasets = data["nodes_per_database"].get(inventory_db, 0)
    errors = []
    if accounting["exchanges"]["production"] != datasets:
        errors.append("The number of production exchanges differs from the number of datasets")
    if accounting["exchanges"]["other_kinds"]:
        errors.append("Exchanges of a kind other than production, technosphere or biosphere")
    for kind, count in accounting["unlinked"].items():
        if count:
            errors.append(f"{count} unlinked exchange(s): {kind}")
    if accounting["biosphere_targets"]["other_databases"]:
        errors.append("Elementary exchanges point at an unexpected database")
    if not np.isfinite(table).all():
        errors.append("Scores that are not finite numbers")
    with_exchanges = {code for _, _, _, code in data["exchanges"]}
    marker = dict(bd.databases[inventory_db]).get(MARKER)
    if marker and marker.get("modified_data") and inventory_db == PROVIDER_DB:
        errors.append(f"A database of modified data carries BAFU's name, {PROVIDER_DB}")
    findings = [] if marker else ["The database's metadata does not say what it was built from"]
    findings += [
        f"Sample score outside its plausible range: {flag}"
        for flag in scores["summary"]["range_flags"]
    ]
    findings += [
        f"Sample score differs from the documented one: {entry['name']} ({entry['location']}): "
        f"{entry['score']:.6g}, documented {entry['documented_score']['value']:.6g}"
        for entry in scores["summary"]["sample"]
        if not entry.get("documented_score", {"agrees": True})["agrees"]
    ]
    if unknown:
        findings.append(
            f"{len(unknown)} elementary flow(s) are not in the pinned flow terms, so the mapping "
            f"can't know them, and their {unknown_exchanges} exchange(s) have no EF 3.1 flow: "
            + "; ".join(unknown_names)
        )
    return {
        "audit_version": AUDIT_VERSION,
        "label": label,
        "status": "failed" if errors else "passed",
        "errors": errors,
        "findings": findings,
        "project": project,
        "databases": {
            "inventory": inventory_db,
            "biosphere": BIOSPHERE_DB,
            "no_ef_3_1_flow": residual_db,
            "nodes": data["nodes_per_database"],
        },
        "built_from": None
        if marker is None
        else {
            key: marker.get(key)
            for key in ("label", "modified_data", "provider_release", "patches", "import_fixes")
        },
        "datasets": datasets,
        "datasets_without_exchanges": datasets - len(with_exchanges),
        **accounting,
        "elementary_flows": {
            "used": len(emitted),
            "on_ef_3_1": sum(1 for database, _ in emitted if database == BIOSPHERE_DB),
            "no_ef_3_1_flow": sum(1 for database, _ in emitted if database == residual_db),
            "with_a_factor_in_any_method": sum(1 for key in emitted if key in any_factor),
            "without_a_factor_in_any_method": sum(1 for key in emitted if key not in any_factor),
            "no_ef_3_1_flow_names": residual_names,
            "not_in_the_pinned_flow_terms": {
                "flows": len(unknown),
                "exchanges": unknown_exchanges,
                "names": unknown_names,
            },
        },
        "methods": coverage,
        "scores": scores["summary"]
        | {
            "all_datasets": {
                "file": scores_path.name,
                "sha256": sha256_file(scores_path),
                "datasets": len(scores["codes"]),
                "methods": len(methods),
                "climate_change_non_zero": int(
                    np.count_nonzero(table[:, scores["climate_column"]])
                ),
            }
        },
        "software": {
            "python": platform.python_version(),
            "platform": platform.platform(terse=True),
            **{
                name: _version(name)
                for name in (
                    "sentier-brightway",
                    "bw2data",
                    "bw2calc",
                    "bw-processing",
                    "scipy",
                    "numpy",
                )
            },
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", required=True, help="Brightway project to read")
    parser.add_argument("--database", default="bafu-2026", help="Inventory database name")
    parser.add_argument(
        "--sample",
        type=Path,
        default=Path(__file__).with_name("score_sample.json"),
        help="Datasets to score, with plausible ranges",
    )
    parser.add_argument("--out", type=Path, required=True, help="Folder for audit.json")
    parser.add_argument("--label", default="", help="What this build is, e.g. 'patched release'")
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Exit with an error if the audit has findings: a sample score outside its "
        "plausible range, or elementary flows the pinned flow terms don't hold",
    )
    args = parser.parse_args(argv)
    try:
        result = audit(args.project, args.database, args.sample, args.out, args.label)
    except AuditError as error:
        print(f"Audit failed: {error}", file=sys.stderr)
        return 2
    target = args.out / "audit.json"
    target.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    findings = result["findings"]
    print(
        f"{result['status']}: {result['datasets']} datasets, "
        f"{result['exchanges']['total']} exchanges, {len(findings)} finding(s); {target}"
    )
    for line in [*result["errors"], *findings]:
        print(f"  {line}")
    return int(bool(result["errors"]) or (args.fail_on_findings and bool(findings)))


if __name__ == "__main__":
    raise SystemExit(main())
