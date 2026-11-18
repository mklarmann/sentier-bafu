import pytest

from bafu_community_fixes.patches import p0013_natural_gas_input_units as gas
from bafu_community_fixes.patches import p0014_production_mix_input_locations as mix
from bafu_community_fixes.pipeline import apply_patch
from bafu_community_fixes.registry import available_patches


@pytest.mark.parametrize(
    "module,before,after",
    [
        (gas, "m3", "Nm3"),
        (mix, None, "ENTSO-E"),
    ],
)
def test_only_reviewed_input_label_changes(db, dataset, module, before, after):
    consumer, (supplier,) = next((c, s) for c, s in module.CONSUMERS.items() if len(s) == 1)
    name, unit, geography = module.SUPPLIERS[supplier]
    dataset.number = consumer
    row = dataset.exchanges[2]
    row.ext = None
    row.number, row.name = supplier, name
    attr = "unit" if module is gas else "location"
    row.unit, row.location = unit, geography
    setattr(row, attr, before)
    similar = row.model_copy(update={"number": supplier + 10000000})
    dataset.exchanges.append(similar)
    original = row.model_dump()
    draft = next(p for p in available_patches() if p.id == module.ID)
    assert draft.provenance.authorised_by is None
    assert apply_patch(db, draft) == [dataset]
    assert row.model_dump() == {**original, attr: after}
    assert getattr(similar, attr) == before
    assert apply_patch(db, draft) == []


def test_gas_patch_checks_number_and_location_before_touching_any_row(db, dataset):
    dataset.number, suppliers = next((c, s) for c, s in gas.CONSUMERS.items() if len(s) > 1)
    rows = []
    for number in suppliers:
        name, _, location = gas.SUPPLIERS[number]
        rows.append(
            dataset.exchanges[-1].model_copy(
                update={
                    "number": number,
                    "name": name,
                    "location": location,
                    "unit": "m3",
                    "ext": None,
                }
            )
        )
    dataset.exchanges.extend(rows)
    rows[-1].location = "GLO"
    with pytest.raises(ValueError, match="Unexpected location or unit"):
        gas.natural_gas_input_units(db)
    assert all(r.unit == "m3" for r in rows)


def test_mix_patch_preserves_an_unreviewed_consumers_missing_location(db, dataset):
    row = dataset.exchanges[2]
    row.number = mix.SUPPLIER
    row.name, row.unit, _ = mix.SUPPLIERS[mix.SUPPLIER]
    row.location = None
    mix.production_mix_input_locations(db)
    assert row.location is None
