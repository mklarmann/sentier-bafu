"""Write kWh as the reference unit of two power plant datasets that are modelled per kWh."""

from bafu_community_fixes.models import OutputGroup
from bafu_community_fixes.registry import patch
from bafu_community_fixes.xml import Database

ID = "0012-electricity-reference-unit"
LABELLED, MODELLED = "MJ", "kWh"
# dataset number: name in BAFU 2026 v1
DATASETS = {
    401085: "Electricity, natural gas, at power plant",  # FI
    316743: "Electricity, hard coal, at power plant, merged",  # IN
}


@patch(
    ID,
    findings=("F13",),
    authored_by="Claude Code",
    # authorised_by: added by whoever approves the patch for the community release
    reported_by="tngTUDOR (sentier-bafu #28)",
    references=(
        "https://github.com/sentier-dev/sentier-bafu/issues/28",
        "https://gitlab.com/eos-lci/lci-bafu-catalog/-/issues/34",
    ),
)
def electricity_reference_unit(db: Database) -> None:
    """Label two power plant datasets per kWh, the unit their inventories are modelled in.

    `Electricity, natural gas, at power plant` (FI) and `Electricity, hard coal, at power
    plant, merged` (IN) have the reference unit MJ. Their inventories are per kWh: the gas
    plant burns 14.07 MJ of gas per unit, which is its stated efficiency of 25.6 % per kWh
    (3.6 / 14.07), and the same datasets for 29 other regions are in kWh. The one dataset
    that takes the Finnish plant as an input, `Electricity, from natural gas` (FI), declares
    that input in kWh.

    The patch changes the unit label of the reference product from MJ to kWh, in the
    reference function and on the reference exchange. It changes no amount: the label was
    wrong, the inventory is right. A tool that converts units along that input multiplies
    it by 3.6 as long as the label says MJ; with the label corrected, the input and its
    supplier agree and nothing is converted.

    An already corrected dataset is left as it stands. A change of identity or a
    disagreement between the two unit labels needs review.
    """
    changes = []
    for dataset in db:
        if dataset.number not in DATASETS:
            continue
        if dataset.name != DATASETS[dataset.number]:
            raise ValueError(
                f"Dataset {dataset.number}: expected {DATASETS[dataset.number]!r}, "
                f"found {dataset.name!r}"
            )
        products = [e for e in dataset.exchanges if e.output_group == OutputGroup.REFERENCE_PRODUCT]
        if len(products) != 1:
            raise ValueError(
                f"Dataset {dataset.number}: expected one reference product, found {len(products)}"
            )
        function, product = dataset.reference_function, products[0]
        if (
            dataset.location != {401085: "FI", 316743: "IN"}[dataset.number]
            or product.number != dataset.number
            or product.name != dataset.name
        ):
            raise ValueError(f"Dataset {dataset.number}: unexpected reference product or geography")
        if function.unit != product.unit or function.unit not in (LABELLED, MODELLED):
            raise ValueError(
                f"Dataset {dataset.number}: unexpected units {function.unit!r} and {product.unit!r}"
            )
        if function.unit == LABELLED:
            changes.append((function, product))
    for function, product in changes:
        function.unit = product.unit = MODELLED
