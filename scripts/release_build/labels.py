"""Read the declared table of unit and compartment labels (`export_labels.toml`).

The table says what BAFU's files write for a unit, what the Brightway build writes, and
what each export format is given; which SimaPro section a compartment belongs to; and which
technosphere inputs are known to declare a unit of another quantity than their supplier's.
The audit and the export step both read it through this module, so they can't disagree.

A label is a name. Nothing here converts an amount: `per_reference` only says whether two
labels name the same amount.

Standard library only.
"""

import hashlib
import tomllib
from pathlib import Path

TABLE = Path(__file__).with_name("export_labels.toml")
#: The sections of a SimaPro CSV that hold elementary flows.
SIMAPRO_SECTIONS = (
    "Resources",
    "Emissions to air",
    "Emissions to water",
    "Emissions to soil",
    "Final waste flows",
    "Non material emissions",
    "Social issues",
    "Economic issues",
)


class LabelError(Exception):
    """The table can't be used as it is; the message says why."""


def load(path: Path | str = TABLE) -> dict:
    """The table as `{"units", "compartments", "differences", "file", "sha256"}`.

    `units` is keyed by the Brightway spelling, `compartments` by the lowercased first
    levels of a flow's categories.
    """
    path = Path(path)
    table = tomllib.loads(path.read_text(encoding="utf-8"))
    units = {}
    for row in table.get("unit", ()):
        missing = {"bafu", "brightway", "openlca", "simapro", "quantity", "per_reference"} - set(
            row
        )
        if missing:
            raise LabelError(f"{path.name}: a unit row lacks {', '.join(sorted(missing))}: {row}")
        if row["brightway"] in units:
            raise LabelError(f"{path.name}: two rows for the unit {row['brightway']!r}")
        units[row["brightway"]] = row
    compartments = {
        tuple(part.strip().lower() for part in row["categories"]): row["simapro"]
        for row in table.get("compartment", ())
    }
    if unknown := sorted(set(compartments.values()) - set(SIMAPRO_SECTIONS)):
        raise LabelError(f"{path.name}: not a section of the SimaPro CSV: {', '.join(unknown)}")
    differences = list(table.get("declared_unit_difference", ()))
    for row in differences:
        if missing := {"finding", "supplier", "declared", "supplier_unit"} - set(row):
            raise LabelError(
                f"{path.name}: a declared_unit_difference lacks {', '.join(sorted(missing))}"
            )
    return {
        "file": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "units": units,
        "compartments": compartments,
        "differences": differences,
    }


#: No table: every label stays as it is, and no two different labels are the same quantity.
EMPTY = {"file": None, "sha256": None, "units": {}, "compartments": {}, "differences": []}


def same_quantity(table: dict, declared: str, supplier_unit: str) -> bool:
    """Whether two unit labels name the same amount, by the table. Unknown labels don't."""

    def size(unit):
        row = table["units"].get(unit)
        return (row["quantity"], row["per_reference"]) if row else None

    return size(declared) is not None and size(declared) == size(supplier_unit)


def finding_of(table: dict, supplier: str, declared: str, supplier_unit: str) -> str | None:
    """The finding a declared unit of another quantity belongs to, if one is recorded."""
    for row in table["differences"]:
        if (row["supplier"], row["declared"], row["supplier_unit"]) == (
            supplier,
            declared,
            supplier_unit,
        ):
            return row["finding"]
    return None


def classify(table: dict, rows: list[dict]) -> dict:
    """Sort exchanges whose declared unit is not their supplier's unit.

    `rows` have `supplier` (its code), `declared_unit`, `supplier_unit` and `kind`. Each
    gets `same_quantity` and `finding`. Returns the counts by pair of labels for those of
    the same quantity, the rows of another quantity, and the recorded differences that no
    exchange shows any more (after a correction, their row in the table can go).
    """
    pairs: dict[str, int] = {}
    other = []
    for row in rows:
        row["same_quantity"] = same_quantity(table, row["declared_unit"], row["supplier_unit"])
        row["finding"] = None
        if row["same_quantity"]:
            what = "flow" if row.get("kind") == "biosphere" else "dataset"
            pair = f"{row['declared_unit']} for a {what} in {row['supplier_unit']}"
            pairs[pair] = pairs.get(pair, 0) + 1
        else:
            row["finding"] = finding_of(
                table, row["supplier"], row["declared_unit"], row["supplier_unit"]
            )
            other.append(row)
    seen = {(row["supplier"], row["declared_unit"], row["supplier_unit"]) for row in other}
    stale = [
        {key: row.get(key) for key in ("finding", "supplier", "declared", "supplier_unit")}
        for row in table["differences"]
        if (row["supplier"], row["declared"], row["supplier_unit"]) not in seen
    ]
    return {
        "exchanges_whose_declared_unit_is_not_the_suppliers": len(rows),
        "same_quantity_other_label": dict(sorted(pairs.items())),
        "another_quantity": other,
        "recorded_differences_not_found": stale,
    }
