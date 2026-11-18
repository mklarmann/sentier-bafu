"""Look up reviewed technosphere inputs using the supplier numbers in BAFU's files."""

from collections.abc import Iterator

from bafu_community_fixes.models import Exchange, InputGroup
from bafu_community_fixes.xml import Database


def reviewed_inputs(
    db: Database,
    consumers: dict[int, tuple[int, ...]],
    suppliers: dict[int, tuple[str, str, str]],
) -> Iterator[tuple[Exchange, str]]:
    """Check the supplier identity and return each reviewed input with the supplier location.

    The registered exchange numbers are the original supplier numbers on these rows.
    For a partial database, the reviewed supplier identity also allows a consumer to
    be checked when its supplier document is absent.
    """
    for dataset in db:
        if dataset.number in suppliers:
            identity = dataset.name, dataset.reference_function.unit, dataset.location
            if identity != suppliers[dataset.number]:
                raise ValueError(f"Supplier {dataset.number}: unexpected identity {identity!r}")
    for dataset in db:
        if dataset.number not in consumers:
            continue
        by_number = {e.number: e for e in dataset.exchanges}
        for number in consumers[dataset.number]:
            exchange = by_number.get(number)
            name, _, location = suppliers[number]
            if (
                exchange is None
                or exchange.input_group != InputGroup.FROM_TECHNOSPHERE
                or exchange.name != name
                or (exchange.ext and exchange.ext.original_number)
            ):
                raise ValueError(f"Dataset {dataset.number}: expected input from {number} ({name})")
            yield exchange, location
