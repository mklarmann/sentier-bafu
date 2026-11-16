"""The page of a comparison: two sets of results over the same items, before and after.

It shows one file, `before-after.json` (`scripts/runrecord/before_after.py`), as it is: every
number on the page is one the file states or the quotient of two it states, and every name is
the file's own. The page knows no dataset and no tool.

`body` is the page without a frame: a site whose frame is its own puts it into that frame,
with `assets/before-after.css` and `assets/before-after.js` beside it. It needs nothing but
this file, `text.py` and the format. `page` is the same in the frame of a site that the
shared build writes.

Without the script it is a page to read: the counts, what caused the changes, each indicator,
and the items that moved furthest with their ratios and their results. The script
(`assets/before-after.js`) sorts and filters the items and shows the results of any of them.

What the page shows of one pair of results is `after / before`: 1 is no change. Its colour
says how far from 1 it lies, and on which side.
"""

import json
import math

from runrecord import before_after

from .text import esc, plural, thousands

STYLE, SCRIPT = "assets/before-after.css", "assets/before-after.js"

#: Items the page holds as markup, for a reader without the script; the script shows the rest.
STATIC_ROWS = 100
STATIC_DETAILS = 20


def number(value):
    """A result as a reader takes it in: three significant digits."""
    if value is None:
        return "not stated"
    if value == 0:
        return "0"
    size = abs(value)
    if size < 0.001 or size >= 100000:
        mantissa, exponent = f"{value:.2e}".split("e")
        return f"{mantissa} × 10<sup>{int(exponent)}</sup>"
    return f"{value:.3g}" if size < 1000 else thousands(round(value))


def percent(before, after):
    """The change from `before` to `after` in percent, as text; None where there is none to say."""
    if before in (None, 0) or after is None:
        return None
    change = (after - before) / abs(before) * 100
    size = abs(change)
    digits = 0 if size >= 10 else 1 if size >= 1 else 2
    sign = "+" if change > 0 else "−" if change < 0 else ""
    return f"{sign}{size:.{digits}f} %"


def cell(pair, threshold):
    """One cell of the grid: the ratio of a pair of results, and how it is drawn."""
    before, after = pair if pair else (None, None)
    if before is None or after is None:
        return '<td class="num ba-cell is-none"></td>'
    found = before_after.ratio(before, after)
    if not before_after.moved(before, after, threshold or 0.0):
        # within the threshold: the ratio is shown as it is, and the cell is not coloured
        same = found is None or number(found) == "1"
        return f'<td class="num ba-cell is-same" title="{"No change" if same else "Within the threshold"}">{"1" if same else number(found)}</td>'
    if found is None:
        return '<td class="num ba-cell is-opposite" title="Zero, or of the other sign, on one side: no ratio">–</td>'
    depth = min(1.0, abs(max(-1.0, min(1.0, math.log10(found)))) * 2.2)
    side = "above" if found > 1 else "below"
    return f'<td class="num ba-cell is-{side}" style="--d:{depth:.2f}">{number(found)}</td>'


def plain(text):
    """A text of the file as it is, escaped: how `body` shows one where the site gives it no
    way of its own to read a text (links to its records, names shown as code)."""
    return esc(text)


def causes_table(data, said):
    causes = data.get("causes") or []
    if not causes:
        return ""
    rows_word = (data.get("rows") or {}).get("many", "rows")
    many = esc(data["items"]["many"])
    body = ""
    for cause in causes:
        changed = ", ".join(f"{thousands(n)} × {esc(what)}" for what, n in sorted(cause.get("changed", {}).items()))
        title = f'<span class="ba-about">{said(cause["title"])}</span>' if cause.get("title") else ""
        kind = f'<span class="tag">{esc(cause["kind"])}</span> ' if cause.get("kind") else ""
        body += (
            f'<tr id="cause-{esc(slug(cause["id"]))}"><th scope="row">{kind}<code>{esc(cause["id"])}</code>{title}</th>'
            f'<td class="num">{count(cause.get("rows"))}</td><td>{changed}</td>'
            f'<td class="num">{count(cause.get("items"))}</td><td class="num">{count(cause.get("moved"))}</td></tr>'
        )
    return (
        '<h2 id="causes">What caused the changes</h2>'
        f"<p>Every difference between the two sides must have a cause: a step that was taken on the way from one to the other. "
        f"A step that changes no result is listed too.</p>"
        '<div class="table-wrap"><table class="ba-table"><thead><tr><th scope="col">Cause</th>'
        f'<th scope="col" class="num">{esc(rows_word.capitalize())} changed</th><th scope="col">What was changed</th>'
        f'<th scope="col" class="num">{many.capitalize()} changed</th><th scope="col" class="num">{many.capitalize()} whose results moved</th>'
        f"</tr></thead><tbody>{body}</tbody></table></div>"
    )


def slug(text):
    return "".join(c if c.isalnum() else "-" for c in str(text)).strip("-").lower()


def count(value):
    return "" if value is None else thousands(value)


def strip(indicator, bands):
    """The items of one indicator by band, as one bar: far below 1 on the left, far above on
    the right, the band around 1 in the middle. Read by its title; the table has the counts."""
    counted = indicator.get("bands")
    if not counted or not sum(counted):
        return ""
    total = sum(counted)
    parts = ""
    for name, n in zip(bands, counted):
        if not n:
            continue
        kind = "mid" if name in (before_after.MIDDLE, before_after.NEAR_ZERO) else "odd" if name == before_after.OPPOSITE else "off"
        parts += f'<span class="is-{kind}" style="flex:{n} 0 0" title="{esc(name)}: {thousands(n)}"></span>'
    said = "; ".join(f"{name}: {thousands(n)}" for name, n in zip(bands, counted) if n)
    return f'<span class="ba-strip" role="img" aria-label="{esc(said)} (of {thousands(total)})">{parts}</span>'


def indicators_table(data, said, word):
    bands = data.get("bands") or []
    many = esc(data["items"]["many"])
    explained = any(i.get("unexplained") is not None for i in data["indicators"])
    banded = any(i.get("bands") for i in data["indicators"])
    body = ""
    for i in data["indicators"]:
        unit = f' <span class="quiet">{esc(i["unit"])}</span>' if i.get("unit") else ""
        reason = f'<span class="ba-about">{said(i["reason"])}</span>' if i.get("reason") else ""
        body += (
            f'<tr class="{"is-moved" if i["moved"] else "is-still"}"><th scope="row">{esc(i["name"])}{unit}{reason}</th>'
            f'<td class="num">{thousands(i["compared"])}</td><td class="num"><strong>{thousands(i["moved"])}</strong></td>'
            f'<td class="num">{thousands(i["lower"])}</td><td class="num">{thousands(i["higher"])}</td>'
            + (f'<td class="num">{count(i.get("unexplained"))}</td>' if explained else "")
            + (f"<td>{strip(i, bands)}</td>" if banded else "")
            + "</tr>"
        )
    still = sum(1 for i in data["indicators"] if not i["moved"])
    none = f" In {plural(still, word[0], word[1])} nothing moved." if still else ""
    return (
        f'<h2 id="indicators">Per {esc(word[0])}</h2>'
        f"<p>How many {many} moved in each {esc(word[0])}, and in which direction.{none}</p>"
        f'<div class="table-wrap"><table class="ba-table"><thead><tr><th scope="col">{esc(word[0].capitalize())}</th>'
        f'<th scope="col" class="num">Compared</th><th scope="col" class="num">Moved</th>'
        '<th scope="col" class="num">Lower after</th><th scope="col" class="num">Higher after</th>'
        + ('<th scope="col" class="num">Not explained</th>' if explained else "")
        + ('<th scope="col">After ÷ before, by band</th>' if banded else "")
        + f"</tr></thead><tbody>{body}</tbody></table></div>"
    )


def detail(data, item, word):
    """The results of one item: before, after and the change, per indicator."""
    threshold = data.get("threshold") or 0.0
    rows = ""
    for i in data["indicators"]:
        pair = item["values"].get(i["id"])
        if not pair:
            continue
        before, after = pair
        changed = before_after.moved(before, after, threshold)
        rows += (
            f'<tr class="{"is-moved" if changed else "is-still"}"><th scope="row">{esc(i["name"])}</th>'
            f'<td class="num">{number(before)}</td><td class="num">{number(after)}</td>'
            f'<td class="num">{(percent(before, after) or "") if changed else "no change"}</td>'
            f'<td class="quiet">{esc(i.get("unit") or "")}</td></tr>'
        )
    return (
        f'<div class="table-wrap"><table class="ba-table ba-values"><thead><tr><th scope="col">{esc(word[0].capitalize())}</th>'
        f'<th scope="col" class="num">{esc(data["before"]["label"])}</th><th scope="col" class="num">{esc(data["after"]["label"])}</th>'
        f'<th scope="col" class="num">Change</th><th scope="col">Unit</th></tr></thead><tbody>{rows}</tbody></table></div>'
    )


def name_of(item):
    return esc(item["name"]) + (f' <span class="quiet">{esc(item["place"])}</span>' if item.get("place") else "")


def grid(data, word):
    """The items that moved, one row each, one column per indicator: after ÷ before."""
    listed = data.get("moved") or []
    one, many = data["items"]["one"], data["items"]["many"]
    left = data.get("moved_not_listed", 0)
    if not listed:
        text = (
            f"{plural(left, one, many).capitalize()} moved; this file lists none of them."
            if left else f"No {esc(one)} moved."
        )
        return f'<h2 id="moved">The {esc(many)} that moved</h2><p class="list-none">{text}</p>'
    threshold = data.get("threshold")
    head = "".join(
        f'<th scope="col" class="num" data-indicator="{esc(i["id"])}"><abbr title="{esc(i["name"])}'
        + (f' ({esc(i["unit"])})' if i.get("unit") else "")
        + f'">{esc(i.get("short") or i["name"])}</abbr></th>'
        for i in data["indicators"]
    )
    rows = ""
    for position, item in enumerate(listed[:STATIC_ROWS]):
        cells = "".join(cell(item["values"].get(i["id"]), threshold) for i in data["indicators"])
        why = ", ".join(f"<code>{esc(c)}</code>" for c in item.get("causes") or ())
        rows += (
            f'<tr data-i="{position}"><th scope="row" class="ba-name" title="{esc(item["name"])}">{name_of(item)}'
            + (f'<span class="ba-why">{why}</span>' if why else "")
            + f"</th>{cells}</tr>"
        )
    details = "".join(
        f'<details class="ba-item"><summary>{name_of(item)}</summary>{detail(data, item, word)}</details>'
        for item in listed[:STATIC_DETAILS]
    )
    more = len(listed) - STATIC_ROWS
    shown = (
        f"The {thousands(len(listed))} that moved furthest are listed; {thousands(left)} more moved." if left
        else f"All {thousands(len(listed))} are listed." if len(listed) > 1 else ""
    )
    if more > 0:
        shown += f" Without the script the page shows the first {STATIC_ROWS}."
    payload = json.dumps(
        {key: data.get(key) for key in ("before", "after", "items", "threshold", "indicators", "groups", "causes", "moved")}
        | {"word": list(word)},
        ensure_ascii=False, separators=(",", ":"), allow_nan=False,
    ).replace("</", "<\\/")
    return (
        f'<h2 id="moved">The {esc(many)} that moved</h2>'
        f'<p>Each cell is the result after, divided by the result before, for that {esc(one)} and {esc(word[0])}: '
        f"1 is no change, 0.5 is half, 2 is double. {shown}</p>"
        '<div class="ba-board" data-before-after>'
        '<div class="ba-controls" hidden><div class="filter-row">'
        f'<label class="field grow"><span>Name</span><input type="search" data-ba-filter placeholder="Filter by name" autocomplete="off" spellcheck="false"></label>'
        '<label class="field" data-ba-cause-field hidden><span>Cause</span><select data-ba-cause><option value="">Any</option></select></label>'
        '<label class="field" data-ba-group-field hidden><span>Group</span><select data-ba-group><option value="">All</option></select></label>'
        '</div><p class="ba-count" data-ba-count role="status" aria-live="polite"></p></div>'
        '<p class="ba-legend" aria-hidden="true"><span><span class="ba-key is-below"></span>lower after</span> '
        '<span><span class="ba-key is-above"></span>higher after</span> '
        '<span><span class="ba-key is-opposite"></span>zero or other sign on one side</span> '
        '<span><span class="ba-key is-same"></span>no change</span></p>'
        f'<div class="table-wrap ba-grid-wrap" role="region" aria-label="After divided by before, per {esc(one)} and {esc(word[0])}" tabindex="0">'
        f'<table class="ba-grid" style="--n:{len(data["indicators"])}"><thead><tr><th scope="col" class="ba-name">{esc(one.capitalize())}</th>{head}</tr></thead>'
        f"<tbody>{rows}</tbody></table></div>"
        '<p class="ba-more"><button class="button" type="button" data-ba-more hidden>Show more</button></p>'
        '<div class="ba-detail" data-ba-detail hidden tabindex="-1"></div>'
        f'<div class="ba-static"><h3>Results of the {esc(many)} that moved furthest</h3>{details}</div>'
        f'<script type="application/json" data-ba-data>{payload}</script></div>'
    )


def reading(data, word):
    threshold = data.get("threshold")
    one, many = esc(data["items"]["one"]), esc(data["items"]["many"])
    moved = (
        f"<li>A {one} <strong>moved</strong> in {a(word[0])} {esc(word[0])} when its two results differ by more than "
        f"{threshold * 100:.10f}".rstrip("0").rstrip(".") + " % of the larger of the two. A smaller difference is the noise of two "
        "separate calculations.</li>"
        if threshold else f"<li>A {one} <strong>moved</strong> when its two results differ.</li>"
    )
    return (
        '<h2 id="reading">How to read this page</h2><ul class="plain">'
        f"<li>Both sides were calculated the same way, over the same {many} and with the same {esc(word[1])}. Only the data differs.</li>"
        f"{moved}"
        "<li>A cell shows <strong>after ÷ before</strong>. The further it lies from 1, the stronger its colour.</li>"
        "<li>A result of zero on one side, or of the other sign, has no ratio. Where both results are too small to say "
        "anything about their ratio, they count as not moved.</li>"
        "<li>The page judges nothing: whether a change is a correction is said where the change was decided, not here.</li>"
        "</ul>"
    )


def a(word):
    return "an" if word[:1].lower() in "aeiou" else "a"


def words(data):
    """What an indicator is called in this file: `(one, many)`."""
    named = data.get("indicator") or {}
    return named.get("one", "indicator"), named.get("many", "indicators")


def body(data, back=None, said=plain, file=None, up=""):
    """The page of one comparison, without a frame. `back` is `(address, label)` of where
    the reader came from, `said` how a text of the file is shown, `file` the address of the
    comparison as a file, `up` the way from the page to the folder that holds `assets/`."""
    word = words(data)
    items, rows = data["items"], data.get("rows")
    one, many = items["one"], items["many"]
    figures = [
        (thousands(items["compared"]), f"{many} compared"),
        (thousands(items["moved"]), f"{many if items['moved'] != 1 else one} moved"),
        (thousands(len(data["indicators"])), word[1] if len(data["indicators"]) != 1 else word[0]),
    ]
    if rows:
        figures += [
            (thousands(rows["compared"]), f"{rows['many']} compared"),
            (thousands(rows["differ"]), "differ"),
            (thousands(rows["unexplained"]), "not explained"),
        ]
    tally = '<dl class="ba-figures">' + "".join(f"<div><dt>{esc(label)}</dt><dd>{value}</dd></div>" for value, label in figures) + "</dl>"
    sides = '<div class="ba-sides">' + "".join(
        f'<div class="card"><p class="card-label">{label}</p><p class="ba-side">{esc(side["label"])}</p>'
        + (f'<p class="card-meta">{said(side["about"])}</p>' if side.get("about") else "")
        + "</div>"
        for label, side in (("Before", data["before"]), ("After", data["after"]))
    ) + "</div>"
    crumb = f'<p class="crumb"><a href="{esc(back[0])}">{esc(back[1])}</a></p>' if back else ""
    notes = "".join(f"<li>{said(note)}</li>" for note in data.get("notes") or ())
    as_file = (
        f'<p class="note">The same comparison as a file: <a href="{esc(file)}"><code>{esc(file)}</code></a>.</p>' if file else ""
    )
    return (
        f'{crumb}<p class="eyebrow">Before and after</p><h1>{esc(data["title"])}</h1>'
        f"{tally}{sides}"
        + causes_table(data, said)
        + indicators_table(data, said, word)
        + grid(data, word)
        + (f'<h2 id="notes">Notes</h2><ul class="plain">{notes}</ul>' if notes else "")
        + reading(data, word)
        + as_file
        + f'<script src="{up}{SCRIPT}" defer></script>'
    )


def page(site, data, name, back=None, current=None):
    """The whole page of one comparison, in the frame of a site the shared build writes: a
    text of the file links the findings it names, as everywhere on such a site."""
    from . import shell
    from .lastrun import inline

    inner = body(data, back, lambda text: inline(site, text, ""), f'api/v1/{name.removesuffix(".html")}.json')
    framed = f'<div class="wrap page ba-page"><article class="prose wide">{inner}</article></div>'
    many = data["items"]["many"]
    described = f'{data["title"]}: which {many} moved, in which {words(data)[1]}, and what caused it.'
    return shell.shell(site, data["title"], framed, current or name, page=name, description=described,
                       head=f'<link rel="stylesheet" href="{STYLE}">')
