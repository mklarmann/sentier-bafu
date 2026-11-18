"""Correct the units of the natural-gas inputs reviewed in F15."""

from bafu_community_fixes.registry import patch
from bafu_community_fixes.reviewed_inputs import reviewed_inputs
from bafu_community_fixes.xml import Database

ID = "0013-natural-gas-input-units"
SUPPLIERS = {
    163364: ("Natural gas, at production onshore", "Nm3", "NL"),
    175171: ("Natural gas, at production", "Nm3", "NG"),
    176712: ("Natural gas, liquefied, production DZ, at freight ship", "Nm3", "FR"),
    204577: ("Natural gas, at production offshore", "Nm3", "GB"),
    221991: ("Natural gas, at production offshore", "Nm3", "NO"),
    236843: ("Natural gas, production RU, at long-distance pipeline", "Nm3", "RER"),
    265252: ("Natural gas, at production onshore", "Nm3", "DE"),
    278811: ("Natural gas, production NG, at long-distance pipeline", "Nm3", "RER"),
    308087: ("Natural gas, production DZ, at long-distance pipeline", "Nm3", "RER"),
    313588: ("Natural gas, at production offshore", "Nm3", "NL"),
    401327: ("Natural gas, at production onshore", "Nm3", "RU"),
    435418: ("Natural gas, at production", "Nm3", "US"),
    473414: ("Natural gas, at production", "Nm3", "QA"),
    555597: ("Natural gas, at production", "Nm3", "DZ"),
}
# Consumer number and the supplier number on each of its affected inputs.
CONSUMERS = {
    164035: (221991,),
    189735: (473414,),
    197975: (236843, 278811, 308087),
    220168: (265252,),
    224586: (555597,),
    258668: (221991,),
    282309: (401327,),
    308323: (265252,),
    315993: (236843,),
    316651: (176712,),
    342313: (175171,),
    376970: (265252,),
    405801: (401327,),
    409382: (313588,),
    418338: (176712,),
    426763: (221991,),
    464146: (401327,),
    485501: (236843,),
    498191: (555597,),
    504863: (435418,),
    520330: (163364, 313588),
    539371: (163364, 175171, 204577, 221991, 265252, 313588, 401327, 473414, 555597),
    542730: (555597,),
    545909: (176712,),
    561435: (265252,),
    566993: (313588,),
    584414: (555597,),
    587796: (435418,),
    603193: (313588,),
}


@patch(
    ID,
    findings=("F15",),
    authored_by="OpenAI Codex",
    reported_by="tngTUDOR",
    references=("https://github.com/sentier-dev/sentier-bafu/issues/30",),
)
def natural_gas_input_units(db: Database) -> None:
    """Relabel 40 natural-gas inputs in 29 datasets with the supplier unit Nm3.

    The supplier numbers and the quantities on comparable gas inputs support Nm3.
    The quantities already describe normal cubic metres. Only their labels change.
    """
    rows = list(reviewed_inputs(db, CONSUMERS, SUPPLIERS))
    for exchange, location in rows:
        if exchange.location != location or exchange.unit not in ("m3", "Nm3"):
            raise ValueError(f"Unexpected location or unit on gas input from {exchange.number}")
    for exchange, _ in rows:
        exchange.unit = "Nm3"
