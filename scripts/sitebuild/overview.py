"""The overview: what the site is, how a finding reaches the provider, where help is wanted."""

from . import findings, pages, shell, status
from .text import esc, ext, number_word, plural


def second_measurement_list(site, up="", limit=5):
    """The findings that need a second measurement, the longest waiting first."""
    waiting = sorted(
        (f for f in site.triage["findings"] if f["stage"] == "filed"),
        key=lambda f: (f["waiting_since"] or "9999", f["id"]),
    )
    return findings.rows(
        site, waiting, up, limit=limit, more=f"{up}findings.html?sort=waiting#stage-filed",
        empty="No finding is waiting for a second measurement.",
    )


def overview(site):
    p, d = esc(site.provider), esc(site.dataset)
    counts = site.triage["counts"]
    total, waiting = len(site.findings), counts.get("filed", 0)
    accepted = sum(c["status"] == "accepted" for c in site.contributions)
    patches = len((site.patches or {}).get("patches", []))
    report = f"{site.repo}/issues/new?template=bafu-data-finding.yml"
    hero = (
        f'<section class="wrap hero"><p class="eyebrow">{d} life-cycle inventory database</p>'
        f"<h1>Measured feedback on {p}'s inventory database</h1>"
        f'<p class="lead">People who work with the {d} life-cycle inventory database record here what they find in the '
        "data: an amount that looks wrong, a link that leads nowhere, a unit that does not fit. Each finding is measured "
        f"on {p}'s own release files, and a second person is asked to repeat the measurement.</p>"
        f'<p class="lead">The findings are reported to {p}, the Swiss Federal Office for the Environment. '
        f"{p} decides what it changes.</p>"
        f'<div class="actions"><a class="button primary" href="findings.html">See the findings</a>'
        f'<a class="button" href="take-part.html">Take part</a></div>{shell.lookup(site)}</section>'
    )
    reach = (
        f'<section class="wrap section" aria-labelledby="path"><div class="section-head"><h2 id="path">How a finding reaches {p}</h2>'
        f"<p>Five steps, and where the {plural(total, 'finding')} stand today. {p} decides at step four. "
        f"Nothing here promises that {p} adopts a finding.</p></div>{status.path_with_counts(site)}"
        f'<p class="aside">Need a correction before {p}\'s next release? A community patch can apply it to your copy. '
        'See the <a href="patched-release.html">patched release</a> (in preparation).</p></section>'
    )
    helped = (
        '<section class="wrap section" aria-labelledby="help"><div class="section-head"><h2 id="help">Help wanted: a second measurement</h2>'
        f"<p>For {plural(waiting, 'finding')} no second measurement is on record. Anyone with {p}'s release files can repeat "
        "one and write in its issue what they got. A different result is as useful as the same one.</p></div>"
        + second_measurement_list(site)
        + '<div class="actions"><a class="button" href="take-part.html">How to take part</a></div></section>'
    ) if waiting else ""
    recent = (
        '<section class="wrap section" aria-labelledby="recent"><div class="section-head"><h2 id="recent">Recently</h2></div>'
        + pages.change_lines(site, site.changes[:5])
        + '<div class="actions"><a class="arrow" href="changes.html">All changes</a></div></section>'
    ) if site.changes else ""
    beside = (
        '<section class="wrap section" aria-labelledby="also"><div class="section-head"><h2 id="also">Beside the findings</h2></div>'
        '<div class="also"><a class="card also-card" href="contributions.html"><span class="card-label">Contributions</span>'
        "<h3>Proposals, models and variants</h3><p>Work that goes beyond a single finding: mappings, rebuilt inventories, "
        "and method variants such as residual electricity mixes. Each contribution lists the checks it must pass. Named "
        f"reviewers approve it before it is accepted. A variant keeps its own name and never replaces {p}'s numbers.</p>"
        f'<span class="also-foot"><strong>{plural(len(site.contributions), "contribution")}</strong> · '
        f'{number_word(accepted, "none")} accepted{"" if accepted else " yet"}</span></a>'
        '<a class="card also-card" href="patched-release.html"><span class="card-label">Patched release · a convenience</span>'
        f"<h3>{p}'s release with community patches applied</h3><p>For those who need a correction before {p}'s next release. "
        "Each patch names its author and the person who authorised it. Ready-made exports are not available yet.</p>"
        f'<span class="also-foot"><strong>{plural(patches, "community patch", "community patches")}</strong> · in preparation</span></a></div>'
        '<div class="band"><p><strong>Found something in the data?</strong> Report it with the dataset code, the release and '
        f'what you measured. It gets a number and is listed as "{esc(site.label("filed"))}" until a second person has '
        f'repeated it. Reporting needs a free GitHub account.</p>{ext(report, "Report a finding", "button ext")}</div></section>'
    )
    return shell.shell(site, "Overview", hero + reach + helped + recent + beside, "index.html", page="index.html")
