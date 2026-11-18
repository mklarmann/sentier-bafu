"""Make the numbered supplier's location explicit on the inputs reviewed in F16."""

from bafu_community_fixes.registry import patch
from bafu_community_fixes.reviewed_inputs import reviewed_inputs
from bafu_community_fixes.xml import Database

ID = "0014-production-mix-input-locations"
SUPPLIER = 744613
SUPPLIERS = {SUPPLIER: ("Electricity, production mix", "kWh", "ENTSO-E")}
CONSUMERS = dict.fromkeys(
    (249768, 279362, 317726, 325339, 332249, 341749, 421735, 423933, 563303, 619541), (SUPPLIER,)
)


@patch(
    ID,
    findings=("F16",),
    authored_by="OpenAI Codex",
    reported_by="tngTUDOR",
    references=("https://github.com/sentier-dev/sentier-bafu/issues/31",),
)
def production_mix_input_locations(db: Database) -> None:
    """State the ENTSO-E supplier location on ten electricity production-mix inputs.

    All ten inputs already point to production mix 744613. Writing the location of
    that supplier preserves the electricity mix, amount and unit used by the model.
    """
    rows = list(reviewed_inputs(db, CONSUMERS, SUPPLIERS))
    for exchange, location in rows:
        if exchange.unit != "kWh" or exchange.location not in (None, location):
            raise ValueError(
                f"Unexpected location or unit on production mix input {exchange.number}"
            )
    for exchange, location in rows:
        exchange.location = location
