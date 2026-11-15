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
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType

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
        "factors_unit",
    }
)
# what the file says of a flow of Brightway Flows, the same on every row that links to it
PER_FLOW = ("flow_name", "flow_unit", "flow_list", "factors_from", "factors_unit")


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
    # flows of EF 3.1 by the links that the installer's flow terms and methods do not hold:
    # their node is made from the link, like the node of a flow outside EF 3.1
    in_ef_without_term: int = 0
    # left unlinked on request, because their flow has no factor in any method
    left_out_without_factor: int = 0

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
        if self.in_ef_without_term:
            lines.append(
                f"  {self.in_ef_without_term} of the flows of EF 3.1 are not in the flow terms "
                "the methods come with; their name is the link's"
            )
        if self.left_out_without_factor:
            lines.append(
                f"  {self.left_out_without_factor} not linked, as asked: their flow has no "
                "factor in any method"
            )
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
    ef_flows: pd.DataFrame  # the EF 3.1 flows, and one row for each other flow a link ends on
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
    said: dict[str, tuple] = {}  # what the first row of a flow says of it
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
        of_flow = tuple(row[field] for field in PER_FLOW)
        if said.setdefault(row["flow_id"], of_flow) != of_flow:
            raise ValueError(
                f"{path} line {number}: {row['flow_id']} is described in two ways "
                f"({', '.join(PER_FLOW)} are one flow's and must agree)"
            )
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


def _shared(categories: list[tuple[str, ...]]) -> tuple[str, ...]:
    """What the source flows that end on one flow agree on, from the front: all of it when
    they agree, the compartment alone when only the sub-compartments differ."""
    shared = list(categories[0])
    for other in categories[1:]:
        length = 0
        while length < min(len(shared), len(other)) and shared[length] == other[length]:
            length += 1
        shared = shared[:length]
    return tuple(shared)


def link(
    inventory: Inventory,
    source_flows: pd.DataFrame,
    ef_flows: pd.DataFrame,
    methods: tuple[MethodSpec, ...],
    targets: Mapping[tuple[str, str, str, str], dict],
    include_without_factor: bool = True,
    locations: Mapping[str, str] | None = None,
) -> FlowLinks:
    """The bridge, the flows and the methods for ``build()``, from the links.

    ``locations`` gives, per source flow code, the country the flow names. The links do not
    state it (``Water, CH`` and ``Water`` end on one flow), so it is taken from where it is
    stated, the mapping of sentier-mappings. ``build()`` then gives the flow that country's
    factor, as it does for the mapping's own links.

    ``source_flows`` are the source's own flow terms (``code, name, categories``); a flow's
    unit is the unit of its exchanges, which is one, because the unit is part of what makes
    a BAFU flow. ``include_without_factor=False`` leaves a flow whose target has no factor
    in any method in the residual database, as ``--skip-nomenclature`` does for the mapping.
    """
    exchanges = inventory.exchanges
    bio = exchanges[exchanges["flow_type"] == "biosphere"].drop_duplicates("flow")
    units = dict(zip(bio["flow"], bio["unit"], strict=True))
    exchange_names = dict(zip(bio["flow"], bio["flow_name"], strict=True))
    terms = source_flows.set_index("code")
    known = set(ef_flows["code"]) | {code for spec in methods for code in spec.flow_name}

    entries: dict[str, tuple[dict, float]] = {}
    unit_unknown: list[tuple[str, str, str]] = []
    not_in_crosswalk: list[str] = []
    ends_on: dict[str, list[tuple[str, ...]]] = {}  # flow: where its source flows go
    rows_of: dict[str, dict] = {}
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
        ends_on.setdefault(row["flow_id"], []).append(categories)
        rows_of[row["flow_id"]] = row

    # A flow outside EF 3.1 takes, in each method, the factor of the flow named for it,
    # where the two are counted in one unit: a factor is per unit of the flow.
    outside = {flow for flow, row in rows_of.items() if row["flow_list"] != EF_LIST}
    carried = {
        flow: rows_of[flow]["factors_from"]
        for flow in sorted(outside)
        if rows_of[flow]["factors_from"]
        and normalize_unit(rows_of[flow]["flow_unit"])
        == normalize_unit(rows_of[flow]["factors_unit"])
    }
    extended = []
    with_factors: set[str] = set()
    takers: dict[str, list[str]] = {}  # the flow named as the source: the flows that take from it
    for flow, source in carried.items():
        takers.setdefault(source, []).append(flow)
    for spec in methods:
        own = dict(spec.cfs)
        added = tuple((flow, own[source]) for flow, source in carried.items() if source in own)
        with_factors.update(flow for flow, _ in added)
        names = {flow: rows_of[flow]["flow_name"] for flow, _ in added}
        # the factors of single countries are carried the same way, country by country
        of_countries = {
            (flow, location): value
            for (source, location), value in spec.located.items()
            for flow in takers.get(source, ())
        }
        extended.append(
            replace(
                spec,
                cfs=spec.cfs + added,
                flow_name=MappingProxyType({**spec.flow_name, **names}),
                located=MappingProxyType({**spec.located, **of_countries}),
            )
        )
    characterised = {code for spec in extended for code, _ in spec.cfs}

    bridge: dict[str, BridgeEntry] = {}
    left_out = 0
    for code, (row, multiplier) in entries.items():
        without = row["flow_id"] not in characterised
        if without and not include_without_factor:
            left_out += 1
            continue
        bridge[code] = BridgeEntry(
            target_code=row["flow_id"],
            target_unit=row["flow_unit"],
            conversion_factor=multiplier,
            nomenclature=without,
            target_location=(locations or {}).get(code),
        )

    # A node needs a name and a place. The installer's flow terms give them for the flows of
    # EF 3.1 they hold; for every other flow a link ends on, the link's own name is taken,
    # and the source's words for where the flow goes, as far as its source flows agree.
    linked = {entry.target_code for entry in bridge.values()}
    made = sorted(flow for flow in linked if flow not in known)
    flows = pd.concat(
        [
            ef_flows,
            pd.DataFrame(
                [
                    {
                        "code": flow,
                        "name": rows_of[flow]["flow_name"],
                        "categories": _shared(ends_on[flow]),
                        "cas_number": None,
                    }
                    for flow in made
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
            1 for e in bridge.values() if e.target_code in outside and e.target_code in with_factors
        ),
        without_factor=sum(1 for e in bridge.values() if e.nomenclature),
        converted=sum(1 for code in bridge if entries[code][0]["conversion"]),
        unit_unknown=tuple(unit_unknown),
        not_in_crosswalk=tuple(not_in_crosswalk),
        in_ef_without_term=sum(
            1 for e in bridge.values() if e.target_code not in outside and e.target_code in made
        ),
        left_out_without_factor=left_out,
    )
    return FlowLinks(
        bridge=MappingProxyType(bridge), ef_flows=flows, methods=tuple(extended), report=report
    )
