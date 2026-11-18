import pytest

from bafu_community_fixes.models import OutputGroup
from bafu_community_fixes.patches.p0012_electricity_reference_unit import DATASETS, ID
from bafu_community_fixes.pipeline import apply_patch
from bafu_community_fixes.registry import available_patches

NUMBER = 401085


def _patch():
    return next(p for p in available_patches() if p.id == ID)


def _product(dataset):
    (product,) = [e for e in dataset.exchanges if e.output_group == OutputGroup.REFERENCE_PRODUCT]
    return product


def _as_in_the_release(dataset, unit="MJ"):
    """The fixture dataset with the number, name and unit label of the Finnish gas plant."""
    dataset.number = _product(dataset).number = NUMBER
    dataset.meta_information.process_information.geography.location = "FI"
    dataset.reference_function.name = _product(dataset).name = DATASETS[NUMBER]
    dataset.reference_function.unit = _product(dataset).unit = unit
    return [(e.name, e.mean_value, e.unit) for e in dataset.exchanges if e is not _product(dataset)]


def test_electricity_reference_unit(db, dataset):
    others = _as_in_the_release(dataset)
    amount = _product(dataset).mean_value
    (changed,) = apply_patch(db, _patch())
    assert changed is dataset
    assert dataset.reference_function.unit == "kWh"
    assert _product(dataset).unit == "kWh"
    # a label, not a conversion: no amount moved, and no other exchange's unit
    assert _product(dataset).mean_value == amount
    assert dataset.reference_function.amount == 1.0
    assert [(e.name, e.mean_value, e.unit) for e in dataset.exchanges[1:]] == others


def test_electricity_reference_unit_names_both_datasets():
    assert DATASETS == {
        401085: "Electricity, natural gas, at power plant",
        316743: "Electricity, hard coal, at power plant, merged",
    }
    assert _patch().provenance.findings == ("F13",)
    assert _patch().provenance.authorised_by is None  # a proposal: nobody has authorised it


def test_electricity_reference_unit_leaves_other_datasets_alone(db, dataset):
    dataset.reference_function.unit = _product(dataset).unit = "MJ"
    assert apply_patch(db, _patch()) == []
    assert dataset.reference_function.unit == "MJ"


def test_electricity_reference_unit_leaves_an_already_corrected_pair_alone(db, dataset):
    _as_in_the_release(dataset, unit="kWh")  # as if BAFU had corrected the label
    assert apply_patch(db, _patch()) == []


def test_electricity_reference_unit_stops_when_only_the_product_differs(db, dataset):
    _as_in_the_release(dataset)
    _product(dataset).unit = "kWh"
    with pytest.raises(ValueError, match="unexpected units"):
        apply_patch(db, _patch())


def test_electricity_reference_unit_stops_on_unexpected_name(db, dataset):
    _as_in_the_release(dataset)
    dataset.reference_function.name = "Electricity, at plant"
    with pytest.raises(ValueError, match="expected 'Electricity, natural gas, at power plant'"):
        apply_patch(db, _patch())
