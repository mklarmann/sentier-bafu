"""A contribution's layer: the changes it makes to the inventory, as a declared file.

A contribution that changes the inventory (a variant, a rebuilt supply mix) is never put
into the patched release. It declares a layer, and the build makes a database of its own
from the patched release plus that one layer, under the contribution's own name.

The layer is a JSON file:

    {
      "schema": "sentier-bafu/contribution-layer/1",
      "contribution": "C012",
      "name": "residual-electricity",
      "database": "bafu-2026-v1-c012-residual-electricity",
      "title": "One sentence: what the variant is",
      "authored_by": "A person",
      "authorised_by": null,
      "references": ["https://github.com/sentier-dev/sentier-bafu/issues/…"],
      "release": {"fingerprint": "<fingerprint of the provider release it was made for>"},
      "changes": [
        {
          "kind": "supplier-substitution",
          "dataset": {"code": "…", "name": "…", "location": "…"},
          "replaced_supplier": {"code": "…", "name": "…", "location": "…"},
          "new_supplier": {"code": "…", "name": "…", "location": "…"},
          "exchange": {"position": 4}
        }
      ]
    }

A dataset is named by its code (the part of its file name after `process_`) together with
its name and location, and the build stops if the release has another name or location under
that code: the layer was written for other data. `exchange.position` (the place of the input
among the dataset's exchanges, from 0) is only needed when the dataset takes the replaced
supplier more than once and not all of those inputs change.

One kind of change exists, `supplier-substitution`: the input keeps its amount and its unit
and is taken from another dataset. The new supplier must be in the release and have the unit
the input declares; nothing is converted.

A layer is refused if its result could depend on the order of its entries, or if an entry
changes nothing that a substitution can mean: a dataset made its own supplier; two entries
for the same input; within one dataset, a supplier that one entry replaces and another
entry brings in (a chain).

The database's name is the release's id, the contribution's id and the contribution's own
name, `bafu-2026-v1-c012-residual-electricity`. A name that is, starts with or ends with the
name of BAFU's release or of the patched release, or that holds the word `patched`, is
refused: nobody must take the database for one of those.

Reading and checking a layer needs the standard library only. Applying it to the importer's
tables needs pyarrow, so that part runs in the sentier-importers environment.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

SCHEMA = "sentier-bafu/contribution-layer/1"
KINDS = ("supplier-substitution",)
# Names that say "this is BAFU's release" or "this is the patched release"
RESERVED = ("bafu-2026", "bafu-2026-v1-patched")
_CONTRIBUTION = re.compile(r"C[0-9]{3,}")
_NAME = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
_DATABASE = re.compile(r"[a-z0-9]+([.-][a-z0-9]+)*")
RECEIPT = "layer-receipt.json"


class LayerError(Exception):
    """The layer can't be read or applied; the message says why."""


def step_id(layer: dict) -> str:
    """The id under which the layer appears among the steps of a build."""
    return f"{layer['contribution']}-{layer['name']}"


def _holds(words: list[str], name: str) -> bool:
    """Whether `words` hold the words of `name` side by side."""
    wanted = name.split("-")
    return any(words[i : i + len(wanted)] == wanted for i in range(len(words) - len(wanted) + 1))


def check_database_name(name: str, contribution: str | None = None) -> None:
    """A contribution's database carries the contribution's own name, and no other.

    With the contribution's id, the name must read `<release id>-<id>-<own name>`: what
    stands before the id is not the name of BAFU's release or of the patched release, what
    follows it is the contribution's own name and holds neither, and the word `patched` is
    nowhere in it.
    """
    if name in RESERVED or name in tuple(f"{r}-residual" for r in RESERVED):
        raise LayerError(
            f"{name} is the name of BAFU's release or of the patched release; a contribution "
            "is built under its own name and never into those"
        )
    if not _DATABASE.fullmatch(name) or name.endswith("-residual"):
        raise LayerError(f"{name!r} is not a database name (lower case, digits, `-` and `.`)")
    if contribution is None:
        return
    words = name.split("-")
    if contribution.lower() not in words:
        raise LayerError(f"The database name {name!r} must name its contribution, {contribution}")
    at = words.index(contribution.lower())
    before, own = words[:at], words[at + 1 :]
    mistakable = (
        "patched" in words
        or not own
        or "-".join(before) in RESERVED
        or any(_holds(own, reserved) for reserved in RESERVED)
    )
    if mistakable:
        raise LayerError(
            f"The database name {name!r} could be taken for BAFU's release or the patched "
            f"release, or has no name of its own after {contribution.lower()}; a "
            "contribution's database is named `<release id>-<id>-<own name>`, for example "
            f"bafu-2026-v1-{contribution.lower()}-residual-electricity"
        )


def _dataset(value, where: str) -> dict:
    if not isinstance(value, dict) or not isinstance(value.get("code"), str) or not value["code"]:
        raise LayerError(f"{where}: a dataset is named by its `code`, with `name` and `location`")
    for key in ("name", "location"):
        if not isinstance(value.get(key), str):
            raise LayerError(f"{where}: `{key}` of dataset {value['code']} is missing")
    return {key: value[key] for key in ("code", "name", "location")}


def validate(layer: dict) -> dict:
    """The layer with only the fields a layer has, or a LayerError that names what is wrong."""
    if not isinstance(layer, dict) or layer.get("schema") != SCHEMA:
        raise LayerError(f"not a contribution layer (schema must be {SCHEMA!r})")
    for key in ("contribution", "name", "database", "title", "authored_by"):
        if not isinstance(layer.get(key), str) or not layer[key].strip():
            raise LayerError(f"`{key}` is missing")
    if not _CONTRIBUTION.fullmatch(layer["contribution"]):
        raise LayerError(f"`contribution` must be an id like C012, not {layer['contribution']!r}")
    if not _NAME.fullmatch(layer["name"]):
        raise LayerError(f"`name` must be lower case words joined by `-`, not {layer['name']!r}")
    check_database_name(layer["database"], layer["contribution"])
    authorised = layer.get("authorised_by")
    if authorised is not None and (not isinstance(authorised, str) or not authorised.strip()):
        raise LayerError("`authorised_by` is a person's name, or null while nobody has authorised")
    references = layer.get("references", [])
    if not isinstance(references, list) or not all(isinstance(r, str) for r in references):
        raise LayerError("`references` is a list of links")
    release = layer.get("release") or {}
    fingerprint = release.get("fingerprint") if isinstance(release, dict) else None
    if fingerprint is not None and not re.fullmatch(r"[0-9a-f]{64}", str(fingerprint)):
        raise LayerError("`release.fingerprint` is the SHA-256 fingerprint of a provider release")
    changes = layer.get("changes")
    if not isinstance(changes, list) or not changes:
        raise LayerError("`changes` must list at least one change")
    checked = []
    for number, change in enumerate(changes, start=1):
        where = f"change {number}"
        if not isinstance(change, dict) or change.get("kind") not in KINDS:
            raise LayerError(f"{where}: `kind` must be one of {', '.join(KINDS)}")
        entry = {
            "kind": change["kind"],
            "dataset": _dataset(change.get("dataset"), where),
            "replaced_supplier": _dataset(change.get("replaced_supplier"), where),
            "new_supplier": _dataset(change.get("new_supplier"), where),
        }
        if entry["replaced_supplier"]["code"] == entry["new_supplier"]["code"]:
            raise LayerError(f"{where}: the new supplier is the replaced one")
        if entry["new_supplier"]["code"] == entry["dataset"]["code"]:
            raise LayerError(
                f"{where}: dataset {entry['dataset']['code']} would become its own supplier"
            )
        exchange = change.get("exchange")
        if exchange is not None:
            position = exchange.get("position") if isinstance(exchange, dict) else None
            if not isinstance(position, int) or isinstance(position, bool) or position < 0:
                raise LayerError(f"{where}: `exchange.position` counts the exchanges from 0")
            entry["exchange"] = {"position": position}
        checked.append(entry)
    _check_order(checked)
    return {
        "schema": SCHEMA,
        "contribution": layer["contribution"],
        "name": layer["name"],
        "database": layer["database"],
        "title": layer["title"].strip(),
        "authored_by": layer["authored_by"].strip(),
        "authorised_by": authorised.strip() if authorised else None,
        "references": references,
        "release": {"fingerprint": fingerprint},
        "changes": checked,
    }


def _check_order(changes: list[dict]) -> None:
    """Refuse entries whose result would depend on the order they are applied in."""
    entries: dict[tuple[str, str], list[tuple[int, int | None]]] = {}
    replaced: dict[str, dict[str, int]] = {}
    brought: dict[str, dict[str, int]] = {}
    for number, change in enumerate(changes, start=1):
        dataset, old, new = (
            change[role]["code"] for role in ("dataset", "replaced_supplier", "new_supplier")
        )
        position = change.get("exchange", {}).get("position")
        # Two entries for one supplier of one dataset are two inputs named by their
        # positions; anything else names an input twice
        for earlier, other in entries.get((dataset, old), ()):
            if position is None or other is None or other == position:
                raise LayerError(
                    f"change {number}: change {earlier} already substitutes the input of "
                    f"{old} in dataset {dataset}"
                )
        entries.setdefault((dataset, old), []).append((number, position))
        replaced.setdefault(dataset, {})[old] = number
        brought.setdefault(dataset, {})[new] = number
    for dataset, suppliers in replaced.items():
        for supplier, number in suppliers.items():
            if supplier in brought[dataset]:
                raise LayerError(
                    f"change {number}: in dataset {dataset}, {supplier} is replaced here and "
                    f"is the new supplier of change {brought[dataset][supplier]}; the result "
                    "would depend on the order of the entries"
                )


def load(path: Path | str) -> dict:
    """A layer file, checked, with the file's name and SHA-256."""
    path = Path(path)
    try:
        layer = validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as error:
        raise LayerError(f"{path.name}: {error}") from None
    except LayerError as error:
        raise LayerError(f"{path.name}: {error}") from None
    return layer | {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def find(folder: Path | str) -> list[Path]:
    """The layer files of a folder, in name order. A folder that isn't there has none."""
    folder = Path(folder)
    return sorted(folder.glob("*.json")) if folder.is_dir() else []


def substitute(processes: dict[str, dict], exchanges: list[dict], layer: dict) -> list[dict]:
    """Apply the layer's changes to `exchanges` in place; return what changed.

    `processes` is `{code: {"name", "location", "reference_unit"}}`. `exchanges` are the
    rows of the importer's exchange table, in its order, as dicts with `process_id`,
    `flow`, `flow_name`, `flow_type`, `unit`, `location` and `amount`.
    """
    rows_of: dict[str, list[int]] = {}
    for row, exchange in enumerate(exchanges):
        rows_of.setdefault(exchange["process_id"], []).append(row)
    changed = []
    for number, change in enumerate(layer["changes"], start=1):
        where = f"{step_id(layer)}, change {number}"
        for role in ("dataset", "replaced_supplier", "new_supplier"):
            wanted = change[role]
            found = processes.get(wanted["code"])
            if found is None:
                raise LayerError(f"{where}: the release has no dataset {wanted['code']}")
            if (found["name"], found["location"]) != (wanted["name"], wanted["location"]):
                raise LayerError(
                    f"{where}: dataset {wanted['code']} is {found['name']!r} "
                    f"({found['location']}) in the release, not {wanted['name']!r} "
                    f"({wanted['location']}); the layer was written for other data"
                )
        consumer, old, new = (
            change[role]["code"] for role in ("dataset", "replaced_supplier", "new_supplier")
        )
        rows = rows_of.get(consumer, [])
        taking = [
            row
            for row in rows
            if exchanges[row]["flow_type"] == "technosphere" and exchanges[row]["flow"] == old
        ]
        if "exchange" in change:
            position = change["exchange"]["position"]
            if position >= len(rows) or rows[position] not in taking:
                raise LayerError(
                    f"{where}: exchange {position} of {consumer} is not an input of {old}"
                )
            targets = [rows[position]]
        elif not taking:
            raise LayerError(f"{where}: {consumer} has no input of {old}; nothing to substitute")
        else:
            targets = taking
        for row in targets:
            exchange = exchanges[row]
            if exchange["unit"] != processes[new]["reference_unit"]:
                raise LayerError(
                    f"{where}: the input is in {exchange['unit']} and the new supplier's unit "
                    f"is {processes[new]['reference_unit']}; a substitution converts nothing"
                )
            before = {key: exchange[key] for key in ("flow", "flow_name", "location")}
            exchange["flow"] = new
            exchange["flow_name"] = processes[new]["name"]
            exchange["location"] = processes[new]["location"]
            changed.append(
                {
                    "change": number,
                    "kind": change["kind"],
                    "dataset": consumer,
                    "position": rows.index(row),
                    "unit": exchange["unit"],
                    "amount": exchange["amount"],
                    "before": before,
                    "after": {key: exchange[key] for key in ("flow", "flow_name", "location")},
                }
            )
    return changed


def apply_folder(folder: Path, layer: dict, database: str) -> dict:
    """Apply the layer to the importer's tables in `folder`; return the receipt."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    check_database_name(database, layer["contribution"])
    if database != layer["database"]:
        raise LayerError(f"The layer's database is {layer['database']}, not {database}")
    table = pq.read_table(folder / "processes.parquet")
    listed = table.select(["process_id", "name", "location", "reference_unit"]).to_pylist()
    processes = {row["process_id"]: row for row in listed}
    if len(processes) != len(listed):
        codes = [row["process_id"] for row in listed]
        twice = sorted({code for code in codes if codes.count(code) > 1})
        raise LayerError(
            f"The tables hold {len(twice)} dataset code(s) more than once, first {twice[0]}; "
            "a layer names a dataset by its code"
        )
    exchanges = pq.read_table(folder / "exchanges.parquet")
    columns = ["process_id", "flow", "flow_name", "flow_type", "unit", "location", "amount"]
    rows = exchanges.select(columns).to_pylist()
    changed = substitute(processes, rows, layer)
    for column in ("flow", "flow_name", "location"):
        index = exchanges.schema.get_field_index(column)
        field = exchanges.schema.field(index)
        values = pa.array([row[column] for row in rows], type=field.type)
        exchanges = exchanges.set_column(index, field, values)
    pq.write_table(exchanges, folder / "exchanges.parquet")
    remaining = {
        (row["process_id"], row["flow"]) for row in rows if row["flow_type"] == "technosphere"
    }
    return {
        "step": step_id(layer),
        "contribution": layer["contribution"],
        "name": layer["name"],
        "database": database,
        "layer_file": layer["file"],
        "layer_sha256": layer["sha256"],
        "changes_declared": len(layer["changes"]),
        "exchanges_changed": len(changed),
        "datasets_changed": sorted({entry["dataset"] for entry in changed}),
        "changes": [
            {
                "dataset": change["dataset"]["code"],
                "replaced_supplier": change["replaced_supplier"]["code"],
                "new_supplier": change["new_supplier"]["code"],
                "replaced_everywhere": (
                    change["dataset"]["code"],
                    change["replaced_supplier"]["code"],
                )
                not in remaining,
            }
            for change in layer["changes"]
        ],
        "exchanges": changed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path, help="Folder with the importer's two tables")
    parser.add_argument("--layer", type=Path, required=True, help="The layer file")
    parser.add_argument("--database", required=True, help="The database the build will write")
    parser.add_argument("--receipt", type=Path, required=True, help="Where to write what changed")
    args = parser.parse_args(argv)
    try:
        receipt = apply_folder(args.folder, load(args.layer), args.database)
    except LayerError as error:
        parser.exit(1, f"The layer was not applied: {error}\n")
    args.receipt.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n")
    print(
        f"{receipt['step']}: {receipt['exchanges_changed']} input(s) of "
        f"{len(receipt['datasets_changed'])} dataset(s) take another supplier"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
