"""Factors of one country, for the flows that name the country.

BAFU has elementary flows that name a country in their name: ``Water, CH``, or
``Occupation, traffic area, rail network, CH``. The mapping of sentier-mappings links such a
flow to its EF 3.1 flow and states the country beside it (``target.location``).
sentier-methods holds, beside each method's factors without a location, factors of single
countries: for water use mostly, and for land use.

``locate`` brings the two statements together. A linked flow that names a country for which
at least one method has that country's factor gets a target of its own: the EF 3.1 flow in
that country. In every method that has the country's factor the target takes it; in every
other method it takes the flow's factor without a location, so nothing is lost by the
country being named.

A flow that names no country keeps the factor without a location, whatever the location of
the dataset it is in. BAFU's exchanges carry no location of their own, and BAFU's published
results agree with that reading where it can be seen (acidification, terrestrial
eutrophication).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType

from .bridge import BridgeEntry
from .methods import MethodSpec

SEPARATOR = "@"


def located_code(code: str, location: str) -> str:
    """The code of the node for the flow ``code`` in ``location``."""
    return f"{code}{SEPARATOR}{location}"


@dataclass(frozen=True)
class Located:
    #: source flow code -> its link; the target is the located one where the flow names a
    #: country that has a factor of its own
    bridge: Mapping[str, BridgeEntry]
    #: the methods, with the factors of the located targets added
    methods: tuple[MethodSpec, ...]
    #: located target code -> (the flow's own code, the location)
    nodes: Mapping[str, tuple[str, str]]
    #: source flows that take a country's factor
    flows: int
    #: source flows that name a country for which no method has a factor of that country
    flows_without: int
    #: method id -> how many located targets have that method's own factor of the country
    per_method: Mapping[str, int]


def locate(bridge: Mapping[str, BridgeEntry], methods: tuple[MethodSpec, ...]) -> Located:
    """Give each linked flow that names a country the target and the factors of that country.

    Idempotent: a link that already ends on a located target is left as it is."""
    named = {
        (entry.target_code, entry.target_location)
        for entry in bridge.values()
        if entry.target_location and SEPARATOR not in entry.target_code
    }
    with_factor = sorted(pair for pair in named if any(pair in spec.located for spec in methods))
    nodes = {located_code(code, location): (code, location) for code, location in with_factor}

    links: dict[str, BridgeEntry] = {}
    flows = flows_without = 0
    for source, entry in bridge.items():
        pair = (entry.target_code, entry.target_location)
        if pair in named and located_code(*pair) in nodes:
            links[source] = replace(entry, target_code=located_code(*pair))
            flows += 1
        else:
            links[source] = entry
            flows_without += pair in named
    if not nodes:
        return Located(
            bridge, methods, MappingProxyType({}), 0, flows_without, MappingProxyType({})
        )

    specs, per_method = [], {}
    for spec in methods:
        table = dict(spec.cfs)
        added, own = [], 0
        for key, (code, location) in nodes.items():
            if key in table:
                continue
            if (code, location) in spec.located:
                added.append((key, spec.located[(code, location)]))
                own += 1
            elif code in table:
                # the method knows the flow and has no factor of this country
                added.append((key, table[code]))
        if own:
            per_method[spec.method_id] = own
        specs.append(replace(spec, cfs=(*spec.cfs, *added)) if added else spec)
    return Located(
        bridge=MappingProxyType(links),
        methods=tuple(specs),
        nodes=MappingProxyType(nodes),
        flows=flows,
        flows_without=flows_without,
        per_method=MappingProxyType(per_method),
    )
