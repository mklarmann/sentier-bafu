"""Two sets of results over the same items, compared: `before-after.json`.

A run that changes data can say what the change did to the results: it scores the same
items before and after, in the same indicators, and writes this file beside its own account
(`summary.py`). A page shows it as it is (`scripts/sitebuild/beforeafter.py`). The same file
serves any pair of results over the same items: a provider's data and a patched copy of it,
published results and a rebuild of them, two ways of building one database.

    {
      "format": "sentier/before-after/1",
      "step": "comparison",                 the step of the run this belongs to, if any
      "title": "The release and the patched copy",
      "before": {"label": "The release", "about": "As the provider ships it."},
      "after": {"label": "The patched copy", "about": null},
      "items": {"one": "dataset", "many": "datasets", "compared": 11947, "moved": 3},
      "indicator": {"one": "impact category", "many": "impact categories"},
                                            what an indicator is called here; may be left out
      "threshold": 1e-06,                   the relative difference from which a result
                                            counts as moved; null where the run sets none
      "bands": ["below 0.1", ...],          the bands `indicators[].bands` counts, or []
      "indicators": [
        {
          "id": "ef-3.1:climate-change",
          "name": "Climate change", "short": "Climate", "unit": "kg CO2 eq",
          "compared": 11947, "moved": 3, "higher": 0, "lower": 3,
          "unexplained": 0,                 moved results that no cause explains, or null
          "bands": null,                    items per band of after / before, or null
          "reason": null                    why this indicator differs as a whole, if known
        }
      ],
      "groups": {"farm": "at the farm gate"},     what an item's `group` stands for, or {}
      "causes": [
        {
          "id": "0001-a-patch", "kind": "community patch", "title": "What it corrects.",
          "rows": 3,                        rows of the data it changed, or null
          "changed": {"amount": 3},         of which, by what was changed
          "items": 3,                       items it changed
          "moved": 3                        items whose result it moved in some indicator
        }
      ],
      "rows": {"one": "exchange", "many": "exchanges",
               "compared": 420063, "differ": 188, "unexplained": 0},        or null
      "moved": [
        {
          "id": "c2d0c99c", "name": "Strawberries", "place": "ES", "group": null,
          "causes": ["0001-a-patch"],
          "values": {"ef-3.1:climate-change": [383.2, 0.659]},     [before, after]
          "note": null
        }
      ],
      "moved_not_listed": 0,                items that moved and are not in `moved`
      "notes": ["Said below the comparison."]
    }

**What a number means.** `after / before` is the ratio a page shows; 1 is no change. An item
*moved* in an indicator when its two results differ by more than `threshold`, relative to
the larger of the two. Near zero a ratio says nothing: where both results are below the
indicator's floor (`floor_of`), the item counts as not moved and its band is `near zero`.
A result of the opposite sign, or a result of zero on one side, has no ratio either: its
band is `opposite sign or zero`.

`tally` counts one indicator this way from pairs of results, so that every run that writes
this file counts alike. `BANDS` are the bands it counts.

A file read from a run is data. `shape_errors` refuses a key it does not know, a text that
is too long or holds a control character, a number that is not finite and a list that is too
long. `moved` holds results of single items: a run lists as many as it may show, and says
how many it left out.

Nothing here knows a dataset, a provider or a tool. Standard library only.
"""

import json
import math
from pathlib import Path

from .summary import is_number, is_text

FORMAT = "sentier/before-after/1"
FILE = "before-after.json"
KEYS = {
    "format", "step", "title", "before", "after", "items", "indicator", "threshold", "bands",
    "indicators", "groups", "causes", "rows", "moved", "moved_not_listed", "notes",
}  # fmt: skip
SIDE_KEYS = {"label", "about"}
ITEMS_KEYS = {"one", "many", "compared", "moved"}
INDICATOR_KEYS = {
    "id", "name", "short", "unit", "compared", "moved", "higher", "lower", "unexplained",
    "bands", "reason",
}  # fmt: skip
CAUSE_KEYS = {"id", "kind", "title", "rows", "changed", "items", "moved"}
ROWS_KEYS = {"one", "many", "compared", "differ", "unexplained"}
MOVED_KEYS = {"id", "name", "place", "group", "causes", "values", "note"}
MAX_INDICATORS, MAX_CAUSES, MAX_GROUPS, MAX_BANDS, MAX_NOTES = 60, 200, 20, 20, 12
MAX_MOVED = 5000
MAX_ID, MAX_NAME, MAX_WORD, MAX_TEXT = 100, 300, 40, 600

#: The bands of `after / before`, from far below 1 to far above it: the same distance from
#: 1 on both sides. Then what has no ratio.
EDGES = (0.1, 0.5, 0.8, 1 / 1.1, 1.1, 1.25, 2.0, 10.0)
BANDS = (
    "below 0.1",
    "0.1 to 0.5",
    "0.5 to 0.8",
    "0.8 to 0.91",
    "0.91 to 1.1",
    "1.1 to 1.25",
    "1.25 to 2",
    "2 to 10",
    "above 10",
    "near zero",
    "opposite sign or zero",
)
MIDDLE, NEAR_ZERO, OPPOSITE = "0.91 to 1.1", "near zero", "opposite sign or zero"
#: A result below this share of the median size of the results before is near zero.
FLOOR_FACTOR = 0.01


# ------------------------------------------------------------------------ counting alike


def ratio(before, after):
    """`after / before`, or None where that says nothing: a zero or another sign on one side.

    >>> ratio(2.0, 3.0), ratio(0.0, 3.0), ratio(2.0, -1.0), ratio(-2.0, -1.0), ratio(None, 1)
    (1.5, None, None, 0.5, None)
    """
    if before is None or after is None or before == 0 or after == 0:
        return None
    if (before > 0) != (after > 0):
        return None
    return after / before


def floor_of(values, factor=FLOOR_FACTOR) -> float:
    """The size below which a result of an indicator is near zero: `factor` times the median
    size of the results that are not zero. Without such a result there is no floor.

    >>> floor_of([0.0, 1.0, -3.0, 2.0]), floor_of([0.0, None])
    (0.02, 0.0)
    """
    sizes = sorted(abs(v) for v in values if v is not None and math.isfinite(v) and v != 0)
    if not sizes:
        return 0.0
    middle = len(sizes) // 2
    median = sizes[middle] if len(sizes) % 2 else (sizes[middle - 1] + sizes[middle]) / 2
    return factor * median


def band(before, after, floor=0.0) -> str | None:
    """The band of one pair of results; None where a side is missing.

    >>> band(1.0, 1.05), band(1.0, 0.05), band(1.0, 12.0), band(1.0, -1.0), band(0.0, 0.0)
    ('0.91 to 1.1', 'below 0.1', 'above 10', 'opposite sign or zero', 'near zero')
    >>> band(1e-9, 5e-9, floor=1e-6), band(None, 1.0)
    ('near zero', None)
    """
    if before is None or after is None:
        return None
    if abs(before) <= floor and abs(after) <= floor:
        return NEAR_ZERO
    found = ratio(before, after)
    if found is None:
        return OPPOSITE
    for edge, name in zip(EDGES, BANDS, strict=False):
        if found < edge:
            return name
    return BANDS[len(EDGES)]


def moved(before, after, threshold, floor=0.0) -> bool:
    """Whether two results differ by more than `threshold`, relative to the larger of the
    two; never where both are near zero.

    >>> moved(1.0, 1.0000001, 1e-6), moved(1.0, 1.1, 1e-6), moved(0.0, 0.0, 1e-6)
    (False, True, False)
    >>> moved(1e-9, 5e-9, 1e-6, floor=1e-6)
    False
    """
    if before is None or after is None:
        return False
    if abs(before) <= floor and abs(after) <= floor:
        return False
    size = max(abs(before), abs(after))
    return size > 0 and abs(after - before) / size > threshold


def tally(pairs, threshold, floor=None, bands=False) -> dict:
    """One indicator counted from its pairs `(before, after)`: how many were compared, moved,
    went up and went down, and with `bands` how many lie in each band. A pair with a side
    missing is not compared. `floor` None takes the floor from the results before.

    >>> tally([(1.0, 1.0), (1.0, 2.0), (2.0, 1.0), (None, 1.0)], 1e-6)
    {'compared': 3, 'moved': 2, 'higher': 1, 'lower': 1, 'bands': None}
    """
    pairs = [(b, a) for b, a in pairs if b is not None and a is not None]
    if floor is None:
        floor = floor_of(b for b, _ in pairs)
    counts = dict.fromkeys(BANDS, 0)
    found = {"compared": len(pairs), "moved": 0, "higher": 0, "lower": 0}
    for before, after in pairs:
        counts[band(before, after, floor)] += 1
        if moved(before, after, threshold, floor):
            found["moved"] += 1
            found["higher" if after > before else "lower"] += 1
    return found | {"bands": [counts[name] for name in BANDS] if bands else None}


# ------------------------------------------------------------------------ the shape


def is_count(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def is_result(value) -> bool:
    return value is None or (is_number(value) and math.isfinite(value))


def _optional(value, limit) -> bool:
    return value is None or is_text(value, limit)


def side_errors(side, where) -> list[str]:
    if not isinstance(side, dict) or set(side) - SIDE_KEYS:
        return [f"`{where}` is not {{label, about}}"]
    if not is_text(side.get("label"), 60) or not _optional(side.get("about"), MAX_NAME):
        return [f"`{where}` has no short label, or its `about` is not a text"]
    return []


def indicator_errors(indicator, bands) -> list[str]:
    if not isinstance(indicator, dict) or set(indicator) - INDICATOR_KEYS:
        return ["an indicator has a key this format does not know"]
    where = f"indicator {indicator.get('id')!r}"
    found = []
    if not is_text(indicator.get("id"), MAX_ID) or not is_text(indicator.get("name"), MAX_ID):
        found.append(f"{where}: `id` and `name` are short texts")
    for key in ("short", "unit"):
        if not _optional(indicator.get(key), MAX_WORD):
            found.append(f"{where}: `{key}` is not a short text")
    for key in ("compared", "moved", "higher", "lower"):
        if not is_count(indicator.get(key)):
            found.append(f"{where}: `{key}` is not a count")
    if indicator.get("unexplained") is not None and not is_count(indicator["unexplained"]):
        found.append(f"{where}: `unexplained` is not a count")
    counted = indicator.get("bands")
    if counted is not None and not (
        isinstance(counted, list) and len(counted) == len(bands) and all(map(is_count, counted))
    ):
        found.append(f"{where}: `bands` is not one count for each band")
    if not _optional(indicator.get("reason"), MAX_TEXT):
        found.append(f"{where}: `reason` is not a text")
    return found


def cause_errors(cause) -> list[str]:
    if not isinstance(cause, dict) or set(cause) - CAUSE_KEYS:
        return ["a cause has a key this format does not know"]
    where = f"cause {cause.get('id')!r}"
    found = []
    if not is_text(cause.get("id"), MAX_ID):
        found.append("a cause has no `id`")
    if not _optional(cause.get("kind"), MAX_WORD) or not _optional(cause.get("title"), MAX_NAME):
        found.append(f"{where}: `kind` or `title` is not a text")
    for key in ("rows", "items", "moved"):
        if cause.get(key) is not None and not is_count(cause[key]):
            found.append(f"{where}: `{key}` is not a count")
    changed = cause.get("changed", {})
    if (
        not isinstance(changed, dict)
        or len(changed) > 12
        or not all(is_text(k, MAX_WORD) and is_count(v) for k, v in changed.items())
    ):
        found.append(f"{where}: `changed` is not a short table of counts")
    return found


def moved_errors(item, indicators, causes, groups) -> list[str]:
    if not isinstance(item, dict) or set(item) - MOVED_KEYS:
        return ["an item has a key this format does not know"]
    where = f"item {item.get('id')!r}"
    if not is_text(item.get("id"), MAX_ID) or not is_text(item.get("name"), MAX_NAME):
        return [f"{where}: `id` and `name` are texts"]
    found = []
    if not _optional(item.get("place"), 60) or not _optional(item.get("note"), MAX_TEXT):
        found.append(f"{where}: `place` or `note` is not a text")
    if item.get("group") is not None and item["group"] not in groups:
        found.append(f"{where}: `group` is not one of `groups`")
    named = item.get("causes", [])
    if not isinstance(named, list) or not all(isinstance(c, str) and c in causes for c in named):
        found.append(f"{where}: `causes` names a cause the file does not hold")
    values = item.get("values")
    if not isinstance(values, dict) or not values:
        return [*found, f"{where}: `values` holds no result"]
    for key, pair in values.items():
        if key not in indicators:
            found.append(f"{where}: a result of an indicator the file does not hold")
            break
        if not (isinstance(pair, list) and len(pair) == 2 and all(map(is_result, pair))):
            found.append(f"{where}: a result is not [before, after]")
            break
    return found


def shape_errors(data) -> list[str]:
    """What is wrong with a comparison; nothing when a page can show it."""
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        return [f"not a comparison of format {FORMAT}"]
    found = [f"a key this format does not know: {key}" for key in sorted(set(data) - KEYS)]
    if not is_text(data.get("title"), 120):
        found.append("`title` is not a short text")
    if not _optional(data.get("step"), MAX_ID):
        found.append("`step` is not the name of a step")
    for where in ("before", "after"):
        found += side_errors(data.get(where), where)
    items = data.get("items")
    if (
        not isinstance(items, dict)
        or set(items) != ITEMS_KEYS
        or not all(is_text(items[key], 30) for key in ("one", "many"))
        or not all(is_count(items[key]) for key in ("compared", "moved"))
    ):
        found.append("`items` is not {one, many, compared, moved}")
    word = data.get("indicator")
    if word is not None and not (
        isinstance(word, dict)
        and set(word) == {"one", "many"}
        and all(is_text(w, 30) for w in word.values())
    ):
        found.append("`indicator` is not {one, many}")
    threshold = data.get("threshold")
    if threshold is not None and not (is_result(threshold) and threshold >= 0):
        found.append("`threshold` is not a share")
    bands = data.get("bands", [])
    if (
        not isinstance(bands, list)
        or len(bands) > MAX_BANDS
        or not all(is_text(name, MAX_WORD) for name in bands)
    ):
        return [*found, f"`bands` is not a list of at most {MAX_BANDS} names"]
    indicators = data.get("indicators")
    if not isinstance(indicators, list) or not indicators or len(indicators) > MAX_INDICATORS:
        return [*found, f"`indicators` is not a list of 1 to {MAX_INDICATORS}"]
    for indicator in indicators:
        found += indicator_errors(indicator, bands)
    ids = [i.get("id") for i in indicators if isinstance(i, dict)]
    if len(set(ids)) != len(ids):
        found.append("two indicators have the same id")
    groups = data.get("groups", {})
    if (
        not isinstance(groups, dict)
        or len(groups) > MAX_GROUPS
        or not all(is_text(k, MAX_WORD) and is_text(v, MAX_ID) for k, v in groups.items())
    ):
        found.append("`groups` is not a short table of names")
        groups = {}
    causes = data.get("causes", [])
    if not isinstance(causes, list) or len(causes) > MAX_CAUSES:
        return [*found, f"`causes` is not a list of at most {MAX_CAUSES}"]
    for cause in causes:
        found += cause_errors(cause)
    cause_ids = [c.get("id") for c in causes if isinstance(c, dict)]
    if len(set(cause_ids)) != len(cause_ids):
        found.append("two causes have the same id")
    rows = data.get("rows")
    if rows is not None and (
        not isinstance(rows, dict)
        or set(rows) != ROWS_KEYS
        or not all(is_text(rows[key], 30) for key in ("one", "many"))
        or not all(is_count(rows[key]) for key in ("compared", "differ", "unexplained"))
    ):
        found.append("`rows` is not {one, many, compared, differ, unexplained}")
    listed = data.get("moved", [])
    if not isinstance(listed, list) or len(listed) > MAX_MOVED:
        return [*found, f"`moved` is not a list of at most {MAX_MOVED} items"]
    for item in listed:
        errors = moved_errors(item, set(ids), set(cause_ids), groups)
        if errors:
            found.append(errors[0])
            break
    if not is_count(data.get("moved_not_listed", 0)):
        found.append("`moved_not_listed` is not a count")
    notes = data.get("notes", [])
    if not isinstance(notes, list) or len(notes) > MAX_NOTES or not all(map(is_text, notes)):
        found.append(f"`notes` is not a list of at most {MAX_NOTES} texts")
    return found


# ------------------------------------------------------------------------ writing one


def indicator(id, name, counts, *, short=None, unit=None, unexplained=None, reason=None):
    """One indicator, as this format writes it; `counts` is what `tally` returned."""
    return {
        "id": id,
        "name": name,
        "short": short,
        "unit": unit,
        **{key: counts[key] for key in ("compared", "moved", "higher", "lower")},
        "unexplained": unexplained,
        "bands": counts.get("bands"),
        "reason": reason,
    }


def cause(id, *, kind=None, title=None, rows=None, changed=None, items=None, moved=None):
    """One cause of a difference: a step, a patch, a decision."""
    return {
        "id": id,
        "kind": kind,
        "title": title,
        "rows": rows,
        "changed": dict(changed or {}),
        "items": items,
        "moved": moved,
    }


def item(id, name, values, *, place=None, group=None, causes=(), note=None):
    """One item that moved, with its results `{indicator id: (before, after)}`."""
    return {
        "id": id,
        "name": name,
        "place": place,
        "group": group,
        "causes": list(causes),
        "values": {key: [pair[0], pair[1]] for key, pair in values.items()},
        "note": note,
    }


def account(title, before, after, items, indicators, **more):
    """A comparison, checked: raises ValueError for one a page could not show. `before` and
    `after` are `(label, about)`, `items` is `(one, many, compared, moved)`."""
    data = {
        "format": FORMAT,
        "step": more.pop("step", None),
        "title": title,
        "before": {"label": before[0], "about": before[1]},
        "after": {"label": after[0], "about": after[1]},
        "items": dict(zip(("one", "many", "compared", "moved"), items, strict=True)),
        "indicator": more.pop("indicator", None),
        "threshold": more.pop("threshold", None),
        "bands": list(more.pop("bands", ())),
        "indicators": list(indicators),
        "groups": dict(more.pop("groups", {})),
        "causes": list(more.pop("causes", ())),
        "rows": more.pop("rows", None),
        "moved": list(more.pop("moved", ())),
        "moved_not_listed": more.pop("moved_not_listed", 0),
        "notes": list(more.pop("notes", ())),
    }
    if more:
        raise ValueError(f"a comparison has no {sorted(more)}")
    errors = shape_errors(data)
    if errors:
        raise ValueError("not a comparison: " + "; ".join(errors))
    return data


def write(data, path: Path) -> Path:
    """Write a comparison to `path`, checked first."""
    errors = shape_errors(data)
    if errors:
        raise ValueError("not a comparison: " + "; ".join(errors))
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=1, ensure_ascii=False, allow_nan=False) + "\n"
    path.write_text(text, encoding="utf-8")
    return path
