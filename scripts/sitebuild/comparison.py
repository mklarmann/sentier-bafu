"""Case selection and the recorded scope of the current build comparison."""

import hashlib
import json

from . import findings
from .cases import patch_key
from .text import esc, plural, thousands


def measured_sets(site, record, data, diagnostics):
    """A case-set snapshot can only accompany the exact reviewed build and step chain."""
    from .lastrun import verified_build

    config = (verified_build(site, record) or {}).get("step_diagnostics", {})
    source = config.get("case_sets")
    if not (source and data and diagnostics):
        return None
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    if hashlib.sha256(canonical).hexdigest() != config["comparison_sha256"]:
        return None
    step_bytes = (site.root / config["snapshot"]).read_bytes()
    if json.loads(step_bytes) != diagnostics:
        return None
    content = (site.root / source["snapshot"]).read_bytes()
    if hashlib.sha256(content).hexdigest() != source["sha256"]:
        raise ValueError("Case measurements differ from the reviewed snapshot")
    sets = json.loads(content)
    if (sets["step_snapshot_sha256"] != hashlib.sha256(step_bytes).hexdigest()
            or sets["datasets"] != data["items"]["compared"]
            or sets["indicators"] != [i["id"] for i in data["indicators"]]
            or any(set(outcome["rows"]) - {r["id"] for r in data["moved"]} for outcome in sets["outcomes"].values())):
        raise ValueError("Case measurements do not cover the published comparison")
    return sets


def whole_result(data, diagnostics, config):
    if data:
        items = data["items"]
        indicator = data.get("indicator") or {"one": "indicator", "many": "indicators"}
        return (f'<p><strong>Whole build</strong> · {esc(plural(items["compared"], items["one"], items["many"]))} compared '
                f'across {esc(plural(len(data["indicators"]), indicator["one"], indicator["many"]))}. '
                f'{thousands(items["moved"])} changed.</p>')
    items = diagnostics["item"]
    total = diagnostics["items_count"]["all"]
    summary = (f'<p><strong>Whole build</strong> · {esc(plural(total, items["one"], items["many"]))}, '
               f'{plural(len(diagnostics["indicators"]), "indicator")} and {plural(len(diagnostics["steps"]), "build step")}.</p>')
    key = config.get("headline_indicator")
    result = diagnostics["counts"]["total"].get(key, {})
    if result.get("classes"):
        name = next(i["name"] for i in diagnostics["indicators"] if i["id"] == key)
        counts = " · ".join(f"{esc(label.capitalize())} {thousands(n)}" for label, n in result["classes"].items() if n)
        summary += f'<p>{esc(name)} · {counts}</p>'
    return summary


def case_result(site, case, data, measured=False):
    rid = esc(case["id"])
    registered = {patch_key(p) for p in case["patches"]}
    causes = [c for c in (data or {}).get("causes", []) if c["id"] in registered]
    parts = [f'<p><strong>{rid}</strong> · {esc(site.label(case["stage"]))}</p>']
    for cause in causes:
        rows = (data.get("rows") or {"one": "row", "many": "rows"})
        changes = []
        if cause.get("rows") is not None:
            changes.append(f'{esc(plural(cause["rows"], rows["one"], rows["many"]))} changed')
        if cause.get("moved") is not None:
            items = data["items"]
            changes.append(f'{esc(plural(cause["moved"], items["one"], items["many"]))} with changed impact results')
        parts.append(f'<p>{esc(cause["title"])} {" · ".join(changes)}</p>')
    if not causes and not measured:
        parts.append('<p>This build records no separate impact measurement for this case.</p>')
    record = f'cases/{rid}.html'
    evidence = (case.get("closed") or {}).get("reason") or case.get("observation")
    if evidence and not causes:
        from .lastrun import inline
        parts.append(f'<p>{inline(site, evidence, "")}</p>')
    parts.append(f'<p><a href="{record}">Open case {rid}</a> · <a href="{record}#case-sources">Sources for {rid}</a></p>')
    return "".join(parts)


def step_selector(sets):
    options = "".join(
        f'<label><input type="checkbox" value="{esc(s["id"])}"> <span>{n}. {esc(s["label"])}</span></label>'
        for n, s in enumerate(sets["step_sets"]["steps"], 1)
    )
    return ('<div data-step-sets hidden><button type="button" class="button" data-step-chain>Back to build order</button>'
            '<fieldset><legend>Combine build steps</legend><div class="comparison-options">'
            + options + '</div></fieldset><div data-step-set-result aria-live="polite"></div>'
            '<label data-step-dataset-label hidden>Dataset <select data-step-dataset></select></label>'
            '<details data-step-categories><summary>Results by impact category</summary>'
            '<div class="table-wrap"><table class="ba-table ba-values" data-step-table></table></div></details></div>')


def opening(site, data, diagnostics, back, config, said, sets=None):
    cases = findings.recent(site)
    options = "".join(
        f'<label><input type="checkbox" name="case" value="{esc(f["id"])}"> '
        f'<span><strong>{esc(f["id"])}</strong> · {esc(f["title"])}</span></label>' for f in cases
    )
    sides = (data["before"], data["after"]) if data else (diagnostics["states"][0], diagnostics["states"][-1])
    pair = "".join(
        f'<div class="comparison-state"><p class="comparison-state-label">{label}</p>'
        f'<strong class="comparison-state-name">{esc(side["label"])}</strong>'
        + (f'<p class="comparison-state-detail">{said(side["about"])}</p>' if side.get("about") else "") + '</div>'
        for label, side in zip(("Before", "After"), sides, strict=True)
    )
    build = site.walk_page or site.patched_page or "index.html"
    run = config.get("run_url") or (back[0] if back else build)
    sources = config.get("sources_url", "sources.html")
    whole = (whole_result(data, diagnostics, config)
             + f'<p><a href="{esc(run)}">Build record</a> · <a href="{esc(sources)}">Sources</a></p>')
    templates = "".join(f'<template data-result-case="{esc(f["id"])}">{case_result(site, f, data, sets and f["id"] in sets["cases"])}</template>' for f in cases)
    from .beforeafter import as_data
    payload = ('<script type="application/json" data-case-measurements>'
               + as_data(json.dumps(sets, ensure_ascii=False, separators=(",", ":"))) + "</script>") if sets else ""
    intro = config.get("intro") or (data or diagnostics)["title"]
    return (f'<div class="comparison-opening"><p class="comparison-crumb"><a href="{esc(build)}">Build</a></p>'
            f'<h1 class="comparison-title">Comparison</h1><p class="comparison-intro">{esc(intro)}</p>'
            '<details class="comparison-filter" data-review-filter id="review-cases" hidden>'
            '<summary>Review cases <span data-case-count>All cases</span></summary>'
            '<fieldset id="review-case"><legend class="visually-hidden">Select review cases</legend>'
            '<button type="button" data-clear-cases>Clear selection</button>'
            f'<div class="comparison-options">{options}</div></fieldset></details>'
            '<noscript><p><a href="cases.html">Browse the case register</a></p></noscript>'
            f'<div class="comparison-pair">{pair}</div><h2 class="comparison-results-title" id="case-results">Results</h2>'
            f'<div data-review-result aria-live="polite">{whole}</div>{payload}'
            f'<template data-result-case="">{whole}</template>{templates}</div>')
