"""A made-up release in BAFU's EcoSpold 1 form, for testing the whole path.

Seven invented datasets with invented amounts. No dataset content of BAFU's release is
used. The elementary flows carry names and compartments that BAFU's release also uses
(carbon dioxide, methane, natural gas), because the pinned mapping to EF 3.1 is keyed by
them; and two datasets carry the number and the exchange name that patches 0001 and 0002
look for, so that those patches apply.

What it exercises:

- two inputs with one exchange number (the import fix gives the second a dummy number, the
  adapter restores it);
- `Gas, natural/m3` in Nm3 (patch 0007 renames it) and `Carbon dioxide, in air` under
  `resources / biotic` (patch 0008 moves it): both must stay linked on the declared flow;
- an input that declares `ENTSO` for a supplier in `ENTSO-E` (patch 0002);
- a dataset in `Europe without Switzerland` (the import fix writes `EURwoCH`);
- a dataset with the number and input that patch 0001 corrects;
- a dataset whose name starts with `xx` (patch 0003 flags it).

`EXPECTED` holds scores worked by hand from the amounts below and the EF 3.1 factors
(carbon dioxide 1, fossil methane 29.8, dinitrogen monoxide 273 kg CO2 eq per kg; natural
gas 35.98 MJ per Nm3).
"""

from pathlib import Path
from xml.sax.saxutils import quoteattr

AIR = ("emissions to air", "unspecified")
CO2 = ("Carbon dioxide, fossil", *AIR, "kg")
CH4 = ("Methane, fossil", *AIR, "kg")
N2O = ("Dinitrogen monoxide", *AIR, "kg")
GAS = ("Gas, natural/m3", "resources", "in ground", "Nm3")
UPTAKE = ("Carbon dioxide, in air", "resources", "biotic", "kg")
DISPOSAL = "Disposal, polyethylene, 0.4% water, to municipal incineration"

# code (file name), number, name, category, location, unit, exchanges
# an exchange is ("input", supplier number, name, declared location, unit, amount)
# or ("to nature" | "from nature", flow, amount)
DATASETS = (
    (
        "syn-gas",
        101,
        "Synthetic gas, at well",
        "natural gas",
        "NO",
        "m3",
        (("from nature", GAS, 1.0), ("to nature", CH4, 0.001)),
    ),
    (
        "syn-power",
        102,
        "Synthetic electricity, at plant",
        "electricity",
        "ENTSO-E",
        "kWh",
        (("input", 101, "Synthetic gas, at well", "NO", "m3", 0.2), ("to nature", CO2, 0.4)),
    ),
    (
        "syn-mix",
        103,
        "Synthetic electricity mix",
        "electricity",
        "Europe without Switzerland",
        "kWh",
        (
            ("input", 102, "Synthetic electricity, at plant", "ENTSO", "kWh", 0.6),
            ("input", 102, "Synthetic electricity, at plant", "ENTSO-E", "kWh", 0.4),
            ("to nature", N2O, 0.0001),
        ),
    ),
    (
        "syn-crop",
        104,
        "Synthetic crop, at farm",
        "agricultural",
        "CH",
        "kg",
        (
            ("input", 103, "Synthetic electricity mix", "Europe without Switzerland", "kWh", 0.05),
            ("from nature", UPTAKE, 1.5),
            ("to nature", N2O, 0.001),
        ),
    ),
    (
        "syn-old",
        105,
        "xx Synthetic heat, obsolete",
        "heat",
        "CH",
        "MJ",
        (("to nature", CO2, 0.07),),
    ),
    ("syn-disposal", 106, DISPOSAL, "waste management", "CH", "kg", (("to nature", CO2, 3.0),)),
    (
        "syn-berries",
        188725,  # the dataset number patch 0001 corrects
        "Synthetic berries, tunnel",
        "agricultural",
        "ES",
        "kg",
        (("input", 106, DISPOSAL, "CH", "kg", 126.22),),
    ),
)

_GAS_SCORE = 0.001 * 29.8
_POWER_SCORE = 0.4 + 0.2 * _GAS_SCORE
_MIX_SCORE = _POWER_SCORE + 0.0001 * 273
EXPECTED = {
    "climate": {
        "syn-gas": _GAS_SCORE,
        "syn-power": _POWER_SCORE,
        "syn-mix": _MIX_SCORE,
        "syn-crop": 0.05 * _MIX_SCORE + 0.001 * 273,
        "syn-old": 0.07,
        "syn-disposal": 3.0,
        "syn-berries": 126.22 * 3.0,
    },
    "climate, patched": {"syn-berries": 0.00957 * 3.0},
    "fossils": {
        "syn-gas": 35.98,
        "syn-power": 0.2 * 35.98,
        "syn-mix": 0.2 * 35.98,
        "syn-crop": 0.05 * 0.2 * 35.98,
        "syn-old": 0.0,
        "syn-disposal": 0.0,
        "syn-berries": 0.0,
    },
}
SAMPLE = {
    "datasets": [
        {"code": code, "name": name, "location": location}
        for code, _, name, _, location, _, _ in DATASETS
    ]
}

_META = """    <metaInformation>
      <processInformation>
        <timePeriod dataValidForEntirePeriod="True">
          <startDate>2021-02</startDate>
          <endDate>2022</endDate>
        </timePeriod>
        <referenceFunction amount="1.0" category={category} datasetRelatesToProduct="True"
            generalComment="A made-up dataset for tests." infrastructureProcess="False"
            localCategory={category} localName={name} localSubCategory="unspecified"
            name={name} subCategory="unspecified" unit={unit}/>
        <geography location={location} text=""/>
        <technology text="Made up"/>
        <dataSetInformation energyValues="0" impactAssessmentResult="False"
            internalVersion="1.0" languageCode="en" localLanguageCode="de"
            timestamp="2024-06-21T22:32:02.538+02:00" type="1" version="2023"/>
      </processInformation>
      <modellingAndValidation>
        <representativeness percent="100"/>
        <validation proofReadingDetails="" proofReadingValidator="2"/>
        <source additionalAuthors="" firstAuthor="Doe J." number="10"
            placeOfPublications="Bern" publisher="A publisher" sourceType="0" title="Report"
            volumeNo="nan" year=""/>
      </modellingAndValidation>
      <administrativeInformation>
        <dataGeneratorAndPublication accessRestrictedTo="0" copyright="" dataPublishedIn="0"
            person="1" referenceToPublishedSource="10"/>
        <person address="Somewhere" companyCode="TESTCO" countryCode="CH" name="Jane Doe"
            number="1"/>
        <dataEntryBy person="1"/>
        <person companyCode="" countryCode="" name="John Doe" number="2"/>
      </administrativeInformation>
    </metaInformation>
"""


def _exchange(number: int, attributes: dict, group: str, code: int) -> str:
    text = " ".join(f"{key}={quoteattr(str(value))}" for key, value in attributes.items())
    return (
        f'      <exchange number="{number}" {text} generalComment="" uncertaintyType="0">\n'
        f"        <{group}>{code}</{group}>\n      </exchange>\n"
    )


def document(number: int, name: str, category: str, location: str, unit: str, rows) -> str:
    """One dataset as BAFU's files are written: no namespace, repeated exchange numbers."""
    product = {"name": name, "category": category, "subCategory": "unspecified"}
    product |= {"location": location, "unit": unit, "meanValue": 1.0}
    product["infrastructureProcess"] = "False"
    exchanges = _exchange(number, product, "outputGroup", 0)
    for row in rows:
        if row[0] == "input":
            _, supplier, supplier_name, declared, supplier_unit, amount = row
            attributes = {"name": supplier_name, "location": declared, "unit": supplier_unit}
            attributes |= {"meanValue": amount, "infrastructureProcess": "False"}
            exchanges += _exchange(supplier, attributes, "inputGroup", 5)
        else:
            direction, (flow, compartment, subcompartment, flow_unit), amount = row
            attributes = {"name": flow, "category": compartment, "subCategory": subcompartment}
            attributes |= {"unit": flow_unit, "meanValue": amount}
            group = "inputGroup" if direction == "from nature" else "outputGroup"
            # every elementary exchange of a substance shares one number in BAFU's files
            exchanges += _exchange(7000 + len(flow), attributes, group, 4)
    meta = _META.format(
        name=quoteattr(name),
        category=quoteattr(category),
        location=quoteattr(location),
        unit=quoteattr(unit),
    )
    return (
        "<?xml version='1.0' encoding='UTF-8'?>\n<ecoSpold>\n"
        f'  <dataset generator="test" number="{number}" timestamp="2025-09-04 18:38:44.741718">\n'
        f"{meta}    <flowData>\n{exchanges}    </flowData>\n  </dataset>\n</ecoSpold>\n"
    )


def write_release(folder: Path) -> Path:
    """Write the made-up release as `process_<code>.xml` files; return the folder."""
    folder.mkdir(parents=True, exist_ok=True)
    for code, number, name, category, location, unit, rows in DATASETS:
        text = document(number, name, category, location, unit, rows)
        (folder / f"process_{code}.xml").write_text(text, encoding="utf-8")
    return folder


if __name__ == "__main__":
    import sys

    print(write_release(Path(sys.argv[1])))
