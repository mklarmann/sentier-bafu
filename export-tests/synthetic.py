"""A small made-up Brightway database with the shapes that matter for an export.

Nothing here comes from a real inventory: every name and amount is invented. The
base database has only shapes that every writer accepts, so one export of it can
be compared in full. The variants add the shapes a writer refuses or changes:

* `with_normal_cubic_metre`: a unit (`Nm3`) outside the JSON-LD writer's unit table;
* `with_co_product`: an activity with a second product, which Brightway credits
  against that product's own producer;
* `with_a_namesake`: two activities with the same name and location;
* `with_a_declared_unit_of_another_quantity`: an input declared in kWh from a dataset
  whose unit is MJ;
* `with_an_unused_flow`: an elementary flow that no activity uses;
* `with_ef_compartments`: flows with the three-level compartments of the EF 3.1 flow
  list and with BAFU's own, and two flows with one name in one compartment;
* `with_an_undeclared_compartment`: a flow whose compartment no table names;
* `with_every_unit(units)`: one activity per unit of the declared table.
"""

import copy
import json

FLOWS = "synthetic-flows"
INVENTORY = "synthetic-inventory"

#: One made-up impact category per quantity that needs a factor: mass and volume.
METHODS = {
    ("synthetic", "climate change"): {
        "unit": "kg CO2-Eq",
        "cfs": {"co2-air": 1.0, "co2-air-urban": 1.0, "ch4-air": 29.8},
    },
    ("synthetic", "water use"): {"unit": "m3", "cfs": {"water-river": 1.0}},
}


def _flow(name, categories, unit, kind="emission", cas=None):
    node = {"name": name, "categories": categories, "unit": unit, "type": kind}
    if cas:
        node["CAS number"] = cas
    return node


def _flows():
    resource = "natural resource"
    return {
        "co2-air": _flow("Carbon dioxide, fossil", ("air",), "kilogram", cas="000124-38-9"),
        "co2-air-urban": _flow(
            "Carbon dioxide, fossil",
            ("air", "high population density"),
            "kilogram",
            cas="000124-38-9",
        ),
        "ch4-air": _flow("Methane, fossil", ("air", "low population density"), "kilogram"),
        "nitrate-water": _flow("Nitrate", ("water", "ground-"), "kilogram"),
        "cadmium-soil": _flow("Cadmium", ("soil", "agricultural"), "kilogram"),
        "radon-air": _flow("Radon-222", ("air",), "kilo Becquerel"),
        "water-river": _flow("Water, river", (resource, "in water"), "cubic meter", resource),
        "land-arable": _flow(
            "Occupation, arable", (resource, "land"), "square meter-year", resource
        ),
    }


def _process(name, location, unit, exchanges, reference_product=None, production=1.0):
    node = {"name": name, "location": location, "unit": unit, "type": "process"}
    if reference_product:
        node["reference product"] = reference_product
    node["_production"] = production
    node["_exchanges"] = exchanges
    return node


def _inventory():
    """Activities by code. `_exchanges` rows are `(kind, code, amount[, extra])`."""
    t, b = "technosphere", "biosphere"
    return {
        # Same name and reference product in two locations; the product is not the name.
        "electricity-ch": _process(
            "electricity, low voltage, at grid",
            "CH",
            "kilowatt hour",
            [(b, "co2-air", 0.03), (b, "radon-air", 0.5), (b, "water-river", 0.002)],
            reference_product="electricity, low voltage",
        ),
        "electricity-de": _process(
            "electricity, low voltage, at grid",
            "DE",
            "kilowatt hour",
            [(b, "co2-air", 0.45), (b, "ch4-air", 0.001)],
            reference_product="electricity, low voltage",
        ),
        "heat": _process(
            "heat, at boiler",
            "RER",
            "megajoule",
            [(t, "electricity-de", 0.01), (b, "co2-air-urban", 0.06)],
        ),
        "transport": _process(
            "transport, lorry", "RER", "ton kilometer", [(b, "co2-air", 0.1), (b, "ch4-air", 2e-5)]
        ),
        # A waste treatment is a service: its users take it as an input.
        "waste": _process(
            "disposal, municipal solid waste, to incineration",
            "CH",
            "kilogram",
            [
                (t, "electricity-ch", 0.05),
                (b, "co2-air", 0.5),
                (b, "ch4-air", 2e-4),
                (b, "cadmium-soil", 1e-7),
            ],
        ),
        "wheat": _process(
            "wheat grains, at farm",
            "CH",
            "kilogram",
            [
                (t, "transport", 0.05),
                (t, "electricity-ch", 0.02),
                (b, "water-river", 0.3),
                (b, "land-arable", 1.4),
                (b, "nitrate-water", 0.004),
                (b, "cadmium-soil", 2e-8),
            ],
        ),
        # Modelled per 1000 kg, with a loss of its own product: 980 kg net.
        "flour": _process(
            "wheat flour, at mill",
            "CH",
            "kilogram",
            [
                (t, "flour", 20.0),
                (t, "wheat", 1250.0),
                (t, "electricity-ch", 80.0),
                (t, "waste", 30.0),
            ],
            production=1000.0,
        ),
        "bread-ch": _process(
            "bread production",
            "CH",
            "kilogram",
            [
                # A parameterised amount: the formula travels beside its value.
                (t, "flour", 0.75, {"formula": "flour_share * loaf_mass"}),
                (t, "heat", 2.0),
                (t, "electricity-ch", 0.3),
                (t, "transport", 0.1),
                (t, "waste", 0.02),
            ],
            reference_product="bread",
        ),
        "bread-de": _process(
            "bread production",
            "DE",
            "kilogram",
            [(t, "flour", 0.75), (t, "heat", 2.2), (t, "electricity-de", 0.3)],
            reference_product="bread",
        ),
    }


def with_normal_cubic_metre(flows, inventory):
    """Add a gas supply in `Nm3` and a boiler that burns it."""
    flows["gas-ground"] = _flow(
        "Gas, natural, in ground", ("natural resource", "in ground"), "Nm3", "natural resource"
    )
    inventory["gas"] = _process(
        "natural gas, at consumer",
        "RER",
        "Nm3",
        [("biosphere", "gas-ground", 1.02), ("biosphere", "ch4-air", 0.004)],
    )
    inventory["heat-gas"] = _process(
        "heat, natural gas, at boiler",
        "RER",
        "megajoule",
        [("technosphere", "gas", 0.03), ("biosphere", "co2-air", 0.056)],
    )


def with_co_product(flows, inventory):
    """Add a cogeneration unit: electricity, plus heat that displaces the boiler's."""
    inventory["cogeneration"] = _process(
        "cogeneration unit, operation",
        "CH",
        "kilowatt hour",
        [("production", "heat", 2.0), ("biosphere", "co2-air", 0.6)],
        reference_product="electricity, at cogeneration unit",
    )


def with_a_namesake(flows, inventory):
    """Add a second "transport, lorry" in RER, per vehicle kilometre, and a user of it."""
    inventory["transport-km"] = _process(
        "transport, lorry", "RER", "kilometer", [("biosphere", "co2-air", 0.8)]
    )
    inventory["bread-de"]["_exchanges"].append(("technosphere", "transport-km", 0.05))


def with_a_declared_unit_of_another_quantity(flows, inventory):
    """Add a power plant whose unit is MJ and a consumer that takes it in kWh."""
    inventory["plant"] = _process(
        "electricity, gas, at power plant", "FI", "megajoule", [("biosphere", "co2-air", 0.15)]
    )
    inventory["supply"] = _process(
        "electricity, from gas",
        "FI",
        "kilowatt hour",
        [
            ("technosphere", "plant", 0.0157, {"unit": "kilowatt hour"}),
            ("technosphere", "electricity-de", 0.9843),
        ],
    )


def with_an_unused_flow(flows, inventory):
    """Add an elementary flow that nothing emits."""
    flows["krypton-air"] = _flow("Krypton-85", ("air",), "kilo Becquerel")


def with_ef_compartments(flows, inventory):
    """Add flows named as the Brightway build names them, and a farm that uses them all."""
    resource = "natural resource"
    emissions = "Emissions"
    added = {
        "so2-ef": _flow(
            "sulfur dioxide",
            (emissions, "Emissions to air", "Emissions to air, unspecified"),
            "kilogram",
        ),
        "nitrate-ef": _flow(
            "nitrate", (emissions, "Emissions to water", "Emissions to fresh water"), "kilogram"
        ),
        "zinc-ef": _flow(
            "zinc", (emissions, "Emissions to soil", "Emissions to agricultural soil"), "kilogram"
        ),
        "arable-ef": _flow(
            "from arable", ("Land use", "Land transformation"), "square meter", resource
        ),
        "gas-ef": _flow(
            "natural gas",
            ("Resources", "Resources from ground", "Non-renewable energy resources from ground"),
            "megajoule",
            resource,
        ),
        # The same name in the same compartment: two flows that must stay two.
        "heat-1": _flow("waste heat", ("air",), "megajoule"),
        "heat-2": _flow("waste heat", ("air",), "megajoule"),
        # BAFU's own compartments, on flows without an EF 3.1 flow.
        "uranium-river": _flow("Uranium alpha", ("emissions to water", "river"), "kilo Becquerel"),
        "noise": _flow("Noise, road", ("non material emissions", "unspecified"), "kilometer"),
    }
    flows.update(added)
    inventory["farm"] = _process(
        "field work",
        "CH",
        "hectare",
        [("biosphere", code, 0.5 + position) for position, code in enumerate(added)],
    )


def with_an_undeclared_compartment(flows, inventory):
    """Add an emission into a compartment that no table names."""
    flows["glow"] = _flow("Light, at night", ("sky",), "square meter")
    inventory["heat"]["_exchanges"].append(("biosphere", "glow", 0.25))


def with_every_unit(units):
    """A variant that adds one activity per unit, and one that takes an input of each."""

    def variant(flows, inventory):
        inputs = []
        for position, unit in enumerate(units):
            code = f"unit-{position}"
            inventory[code] = _process(
                f"service {position}", "GLO", unit, [("biosphere", "co2-air", 0.1)]
            )
            inputs.append(("technosphere", code, 1.5 + position))
        inventory["all-units"] = _process("assembly", "GLO", "kilogram", inputs)

    variant.__name__ = "with_every_unit"
    return variant


def databases(*variants):
    """`{database name: {(database, code): node}}`, ready for `Database.write`."""
    flows, inventory = _flows(), _inventory()
    for variant in variants:
        variant(flows, inventory)
    data = {}
    for code, node in inventory.items():
        node = copy.deepcopy(node)
        exchanges = [
            {
                "input": (INVENTORY, code),
                "amount": node.pop("_production"),
                "type": "production",
                "unit": node["unit"],
            }
        ]
        for kind, target, amount, *extra in node.pop("_exchanges"):
            database = FLOWS if kind == "biosphere" else INVENTORY
            unit = (flows if kind == "biosphere" else inventory)[target]["unit"]
            exchange = {"input": (database, target), "amount": amount, "type": kind, "unit": unit}
            exchanges.append(exchange | (extra[0] if extra else {}))
        data[(INVENTORY, code)] = node | {"exchanges": exchanges}
    return {
        FLOWS: {(FLOWS, code): node for code, node in flows.items()},
        INVENTORY: data,
    }


def methods():
    """`{method tuple: (unit, [((database, code), factor)])}` over the synthetic flows."""
    return {
        name: (spec["unit"], [((FLOWS, code), cf) for code, cf in spec["cfs"].items()])
        for name, spec in METHODS.items()
    }


def methods_json():
    """The methods in the sidecar format the JSON-LD writer reads."""
    return json.dumps(
        {
            " | ".join(name): {"unit": unit, "cfs": [[list(key), cf] for key, cf in cfs]}
            for name, (unit, cfs) in methods().items()
        }
    )
