"""Link a source's elementary flows through Brightway Flows, as patch 0010 does.

The mapping folder of sentier-mappings is one way to say which flow of the impact methods
a BAFU flow is. Patch 0010 of the patch tool is another: it links every BAFU flow to a flow
of Brightway Flows, the list that EF 3.1 is one part of. This module builds the same three
things ``build()`` takes (the bridge, the flows a node is made for, the methods) from those
links, so the rest of the installer is the same for both.

Three separate statements are kept apart, each from where it is made:

* **Which flow it is** comes from the crosswalk patch 0010 uses, read here through the
  targets file (``scripts/build_brightway_flows_targets.py`` in sentier-bafu), which gives
  each link the identifier the flow has in the pinned release of Brightway Flows.
* **How an amount converts** is taken only where that release states a multiplier for the
  link. Two spellings of one unit need none. Where the units differ and nothing is stated,
  the conversion is unknown: the flow is not linked, it stays in the residual database, and
  the report counts it.
* **What a flow costs** stays with the methods the installer reads. A flow of EF 3.1 has
  the factors those methods give it. A flow outside EF 3.1 gets the factors of the one
  flow that Brightway Flows' own implementation names as their source, as the installer's
  methods have them; no factor is read from Brightway Flows. Where it names none or more
  than one, or names a flow the methods have no factor for (it can itself be outside
  EF 3.1), the flow has no factor, and the report counts it.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

import pandas as pd

from .bridge import BridgeEntry
from .inventory import Inventory
from .methods import MethodSpec
from .units import normalize_unit

#: ``flow_list`` of a target that EF 3.1 holds; every other target is outside EF 3.1.
EF_LIST = "EF 3.1"
LINKING = "brightway-flows"

KEY = ("name", "category", "subCategory", "unit")
COLUMNS = frozenset(
    {
        *KEY,
        "flow_id",
        "flow_name",
        "flow_unit",
        "flow_list",
        "conversion",
        "factors_from",
    }
)


@dataclass(frozen=True)
class LinkReport:
    """What the links did to the flows the inventory uses."""

    flows: int
    linked: int
    in_ef: int
    outside_ef: int
    outside_ef_with_factors: int
    without_factor: int
    converted: int
    unit_unknown: tuple[tuple[str, str, str], ...]  # (flow name, its unit, the target's unit)
    not_in_crosswalk: tuple[str, ...]  # flow names

    def lines(self) -> tuple[str, ...]:
        """The report, as the lines printed after an install."""
        lines = [
            f"Linked through Brightway Flows (the links of patch 0010): {self.linked}/"
            f"{self.flows} flows",
            f"  {self.in_ef} to a flow of EF 3.1; {self.outside_ef} to a flow outside EF 3.1, "
            f"of which {self.outside_ef_with_factors} take the factors of the EF 3.1 flow "
            "Brightway Flows names",
            f"  {self.converted} linked with a conversion the release states",
            f"  {self.without_factor} of the linked flows have no factor in any method "
            "(impact zero)",
        ]
        if self.unit_unknown:
            first = "; ".join(f"{name} ({a} to {b})" for name, a, b in self.unit_unknown[:3])
            lines.append(
                f"  {len(self.unit_unknown)} not linked: the units differ and the release "
                f"states no conversion (for example {first})"
            )
        if self.not_in_crosswalk:
            first = "; ".join(self.not_in_crosswalk[:3])
            lines.append(
                f"  {len(self.not_in_crosswalk)} not linked: not in the crosswalk "
                f"(for example {first})"
            )
        return tuple(lines)


@dataclass(frozen=True)
class FlowLinks:
    bridge: Mapping[str, BridgeEntry]
    ef_flows: pd.DataFrame  # the EF 3.1 flows, and one row for each linked flow outside EF 3.1
    methods: tuple[MethodSpec, ...]
    report: LinkReport


def load_targets(path: Path | str) -> dict[tuple[str, str, str, str], dict]:
    """The targets file, by BAFU's four fields of a flow: name, category, subCategory, unit."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"flow links: {path} is not a file")
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        missing = sorted(COLUMNS - set(reader.fieldnames or ()))
        if missing:
            raise ValueError(f"{path}: columns missing: {', '.join(missing)}")
        rows = list(reader)
    targets: dict[tuple[str, str, str, str], dict] = {}
    for number, row in enumerate(rows, start=2):
        key = tuple(row[field] for field in KEY)
        if key in targets:
            raise ValueError(f"{path} line {number}: {' | '.join(key)} is there twice")
        if not row["flow_id"]:
            raise ValueError(f"{path} line {number}: no flow_id")
        if row["conversion"]:
            try:
                multiplier = float(row["conversion"])
            except ValueError:
                raise ValueError(f"{path} line {number}: conversion is not a number") from None
            if not multiplier > 0:
                raise ValueError(f"{path} line {number}: conversion is not above zero")
        targets[key] = row
    if not targets:
        raise ValueError(f"{path}: no rows")
    return targets


def _conversion(row: dict, unit: str) -> float | None:
    """The multiplier from the source's unit to the target's; None when it is unknown."""
    if row["conversion"]:
        return float(row["conversion"])
    if normalize_unit(unit) == normalize_unit(row["flow_unit"]):
        return 1.0
    return None


def link(
    inventory: Inventory,
    source_flows: pd.DataFrame,
    ef_flows: pd.DataFrame,
    methods: tuple[MethodSpec, ...],
    targets: Mapping[tuple[str, str, str, str], dict],
    include_without_factor: bool = True,
) -> FlowLinks:
    """The bridge, the flows and the methods for ``build()``, from the links.

    ``source_flows`` are the source's own flow terms (``code, name, categories``); a flow's
    unit is the unit of its exchanges, which is one, because the unit is part of what makes
    a BAFU flow. ``include_without_factor=False`` leaves a flow whose target has no factor
    in any method in the residual database, as ``--skip-nomenclature`` does for the mapping.
    """
    exchanges = inventory.exchanges
    bio = exchanges[exchanges["flow_type"] == "biosphere"].drop_duplicates("flow")
    units = dict(zip(bio["flow"], bio["unit"]))
    exchange_names = dict(zip(bio["flow"], bio["flow_name"]))
    terms = source_flows.set_index("code")
    known_ef = set(ef_flows["code"])

    entries: dict[str, tuple[dict, float]] = {}
    unit_unknown: list[tuple[str, str, str]] = []
    not_in_crosswalk: list[str] = []
    outside: dict[str, dict] = {}  # flow outside EF 3.1: the row its node is made from
    for code in sorted(units):
        unit = "" if pd.isna(units[code]) else str(units[code])
        if code not in terms.index:
            not_in_crosswalk.append(str(exchange_names.get(code, code)))
            continue
        categories = tuple(terms.at[code, "categories"])
        compartment = categories[0] if categories else ""
        sub = categories[1] if len(categories) > 1 else ""
        name = str(terms.at[code, "name"])
        row = targets.get((name, compartment, sub, unit))
        if row is None:
            not_in_crosswalk.append(name)
            continue
        multiplier = _conversion(row, unit)
        if multiplier is None:
            unit_unknown.append((name, unit, row["flow_unit"]))
            continue
        entries[code] = (row, multiplier)
        if row["flow_list"] != EF_LIST and row["flow_id"] not in known_ef:
            outside.setdefault(
                row["flow_id"],
                {
                    "code": row["flow_id"],
                    "name": row["flow_name"],
                    "categories": categories,
                    "cas_number": None,
                    "factors_from": row["factors_from"],
                },
            )

    # a flow outside EF 3.1 takes, in each method, the factor of the EF 3.1 flow named for it
    carried = {
        code: node["factors_from"] for code, node in outside.items() if node["factors_from"]
    }
    extended = []
    with_factors: set[str] = set()
    for spec in methods:
        own = dict(spec.cfs)
        added = tuple((code, own[source]) for code, source in carried.items() if source in own)
        with_factors.update(code for code, _ in added)
        names = {code: outside[code]["name"] for code, _ in added}
        extended.append(
            replace(
                spec,
                cfs=spec.cfs + added,
                flow_name=MappingProxyType({**spec.flow_name, **names}),
            )
        )
    characterised = {code for spec in extended for code, _ in spec.cfs}

    bridge: dict[str, BridgeEntry] = {}
    for code, (row, multiplier) in entries.items():
        without = row["flow_id"] not in characterised
        if without and not include_without_factor:
            continue
        bridge[code] = BridgeEntry(
            target_code=row["flow_id"],
            target_unit=row["flow_unit"],
            conversion_factor=multiplier,
            nomenclature=without,
        )

    linked_outside = {e.target_code for e in bridge.values() if e.target_code in outside}
    flows = pd.concat(
        [
            ef_flows,
            pd.DataFrame(
                [
                    {k: outside[code][k] for k in ("code", "name", "categories", "cas_number")}
                    for code in sorted(linked_outside)
                ],
                columns=["code", "name", "categories", "cas_number"],
            ).astype(object),
        ],
        ignore_index=True,
    )
    report = LinkReport(
        flows=len(units),
        linked=len(bridge),
        in_ef=sum(1 for e in bridge.values() if e.target_code not in outside),
        outside_ef=sum(1 for e in bridge.values() if e.target_code in outside),
        outside_ef_with_factors=sum(
            1
            for e in bridge.values()
            if e.target_code in outside and e.target_code in with_factors
        ),
        without_factor=sum(1 for e in bridge.values() if e.nomenclature),
        converted=sum(1 for code in bridge if entries[code][0]["conversion"]),
        unit_unknown=tuple(unit_unknown),
        not_in_crosswalk=tuple(not_in_crosswalk),
    )
    return FlowLinks(
        bridge=MappingProxyType(bridge), ef_flows=flows, methods=tuple(extended), report=report
    )
