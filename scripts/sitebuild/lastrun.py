"""The last release build on a page: whether it worked, what is blocking, what was in it,
and every line it printed.

Everything is read from the record of scripts/last_run.py: GitHub's record of the run, and
the manifest and the transcript the run kept. No sentence here states a result the record
does not hold. The lines of the transcript are the run's own: each is escaped for HTML and
is otherwise unchanged, and a test compares the page with the transcript line by line."""

import datetime

from .text import day, esc, ext, plural, thousands

NOT_SHOWN = {
    "no run": "No release build has run yet.",
    "not read": "This copy of the site was built without reading GitHub, so the last run is not shown here.",
    "unreadable": "The last run could not be read from GitHub when this page was built.",
}
EVENTS = {
    "push": "after a change was accepted",
    "workflow_dispatch": "started by hand",
    "schedule": "the monthly run",
}
ENDED = {
    "success": "succeeded", "failure": "failed", "cancelled": "was cancelled",
    "timed_out": "ran out of time", "skipped": "was skipped", "startup_failure": "could not start",
}
KEPT = {
    "none": "The run kept no record of its own, so only what GitHub recorded is shown.",
    "expired": "The record the run kept is no longer on GitHub: it is kept for 90 days.",
    "needs a token": "The record the run kept was not read: this copy of the site was built without access to it.",
    "unreadable": "The record the run kept could not be read.",
}
EXPORT_NAMES = {"brightway": "Brightway", "openlca": "openLCA", "ilcd": "ILCD", "simapro": "SimaPro"}
STOPPED = ("failure", "cancelled", "timed_out", "startup_failure")
SHOWN_STEPS = ("Set up job", "Complete job")  # GitHub's own two; the rest are the workflow's


def moment(iso):
    try:
        return datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None


def when(iso):
    """13 November 2026, 20:11 UTC"""
    at = moment(iso)
    if at is None:
        return ""
    at = at.astimezone(datetime.timezone.utc)
    return f'{day(at.date().isoformat(), long=True)}, {at:%H:%M} UTC'


def duration(seconds):
    """97 -> 1 min 37 s; 3700 -> 1 h 1 min"""
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        return f"{seconds // 60} min {seconds % 60} s"
    return f"{seconds // 3600} h {seconds % 3600 // 60} min"


def clock(seconds):
    """The time of a line since the run began: 02:49, or 1:02:49."""
    seconds = int(seconds)
    if seconds < 3600:
        return f"{seconds // 60:02d}:{seconds % 60:02d}"
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def took(run):
    start, end = moment(run.get("started")), moment(run.get("ended"))
    return duration((end - start).total_seconds()) if start and end and end >= start else None


def visible(text):
    """A line as HTML. A control character has no place in HTML: it is shown by its picture
    (U+2400 and following), so that it is neither lost nor acted on."""
    return esc("".join(chr(0x2400 + ord(c)) if ord(c) < 32 and c != "\t" else c for c in text))


def stopped_at(record):
    """The first step GitHub records as failed, cancelled or out of time: (job, step)."""
    for job in record.get("jobs") or ():
        for step in job.get("steps") or ():
            if step.get("conclusion") in STOPPED:
                return job, step
    return None, None


def sentence(text):
    """A text of the run as a sentence of the page: escaped, first letter capital, one full stop."""
    text = str(text).strip()
    return esc(text[:1].upper() + text[1:] + ("" if text.endswith((".", "!", "?")) else "."))


# ------------------------------------------------------------------------ the four facts


def run_line(site, record):
    run = record["run"]
    number = f' {int(run["number"])}' if isinstance(run.get("number"), int) else ""
    how = EVENTS.get(run.get("event"), "")
    tag = (record.get("manifest") or {}).get("tag")
    if tag:
        how = f"for the tag <code>{esc(tag)}</code>"
    commit = f'commit <code>{esc(str(run.get("commit") or "")[:7])}</code>' if run.get("commit") else ""
    branch = f' of <code>{esc(run["branch"])}</code>' if run.get("branch") and not tag else ""
    parts = [f"Release build{number} of {when(run.get('started'))}"]
    if commit:
        parts.append(f"on {commit}{branch}")
    if how:
        parts.append(how)
    line = ", ".join(parts) + ". " + ext(run["url"], "The run on GitHub")
    newer = record.get("newer")
    if newer and str(newer.get("url") or "").startswith("https://github.com/"):
        line += f' <span class="quiet">A newer run has not ended yet: {ext(newer["url"], "see it on GitHub")}.</span>'
    return line


def worked(record):
    """(yes | no | unknown, the sentence)."""
    run, manifest = record["run"], record.get("manifest")
    conclusion, time = run.get("conclusion"), took(run)
    job, step = stopped_at(record)
    at = f' at the step “{esc(step["name"])}”' if step and step.get("name") else ""
    ended = ENDED.get(conclusion, "ended without a result")
    if manifest is None:
        if conclusion == "success":
            return "unknown", "GitHub records that the run succeeded." + (f" It took {time}." if time else "")
        return "no", f"<strong>No.</strong> GitHub records that the run {ended}{at}."
    steps = manifest["steps"]
    done = [s for s in steps if s["status"] == "completed"]
    wrong = [s for s in steps if s["status"] not in ("completed", "skipped")]
    if manifest["status"] == "completed" and conclusion == "success":
        counted = f"All {len(done)} steps completed" if len(done) == len(steps) else f"{len(done)} of {len(steps)} steps completed, and none failed"
        return "yes", f"<strong>Yes.</strong> {counted}" + (f", in {time}." if time else ".")
    if manifest["status"] == "completed":
        return "no", (f"<strong>No.</strong> The {plural(len(done), 'step')} of the build completed, "
                      f"but GitHub records that the run {ended}{at}.")
    failed = [s for s in wrong if s["status"] == "failed"]
    names = ", ".join(f"<strong>{esc(s['name'])}</strong>" for s in failed) or "none"
    return "no", (f"<strong>No.</strong> {len(done)} of {len(steps)} steps completed. "
                  f"Failed: {names}." + (f" {len(wrong) - len(failed)} did not run." if len(wrong) > len(failed) else ""))


def blocking(site, record):
    """What stands between this run and a published release, in the run's own words."""
    run, manifest = record["run"], record.get("manifest")
    items = []
    if manifest is None:
        job, step = stopped_at(record)
        if run.get("conclusion") != "success" and step and step.get("name"):
            items.append(f"GitHub records that the step “{esc(step['name'])}” {ENDED.get(step.get('conclusion'), 'did not end well')}.")
        items.append(KEPT.get(record.get("kept"), KEPT["none"]))
        return items
    said = []
    for text in [*manifest["problems"], *manifest["not_releasable"]]:
        if text not in said:
            said.append(text)
    items += [sentence(text) for text in said]
    if not said and manifest["status"] == "completed":
        items.append("Nothing in this run keeps it from being published as a release.")
    tag = manifest.get("tag")
    published = next((job for job in record.get("jobs") or () if str(job.get("name") or "").startswith("Publish")), None)
    if tag and published and published.get("conclusion") == "success":
        items.append(f"It is published as the release <code>{esc(tag)}</code>: its manifest, and no file of the data.")
    elif tag:
        items.append(f"It was built for the tag <code>{esc(tag)}</code>, and that release was not published.")
    else:
        items.append("It is not a release. A release is built when a maintainer pushes a tag.")
    exports = manifest.get("exports") or {}
    if exports.get("published") is False and exports.get("note"):
        items.append(sentence(exports["note"]))
    return items


def contents(site, record, up):
    manifest = record.get("manifest")
    if manifest is None or manifest.get("provider_release") is None:
        return ["The run did not record what it read."] if manifest is not None else []
    items = []
    release = manifest["provider_release"]
    name = site.release_name(release["id"]) if release.get("id") else "A release this site does not name"
    checksum = f', checksum <code title="{esc(release["archive_sha256"])}">{esc(str(release["archive_sha256"])[:12])}</code>' if release.get("archive_sha256") else ""
    counts = (f': {thousands(release["datasets"])} datasets and {thousands(release["exchanges"])} exchanges'
              if isinstance(release.get("datasets"), int) and isinstance(release.get("exchanges"), int) else "")
    items.append(f"{esc(name)}{counts}{checksum}.")
    fixes, patches = manifest["import_fixes"], manifest["patches"]
    answered = sorted({f for patch in patches for f in patch["findings"]}, key=lambda f: (len(f), f))
    links = ", ".join(
        f'<a href="{up}findings/{esc(f)}.html">{esc(f)}</a>' if f in site.by_id else esc(f) for f in answered
    )
    line = f"{plural(len(fixes), 'import fix', 'import fixes')} and {plural(len(patches), 'community patch', 'community patches')}"
    if links:
        line += f"; the patches answer {links}"
    totals = manifest.get("totals") or {}
    if isinstance(totals.get("datasets_changed"), int):
        line += f". Together they changed {thousands(totals['datasets_changed'])} datasets"
    items.append(line + ".")
    comparison = manifest.get("comparison")
    if comparison:
        left = comparison["rows_no_step_explains"]
        items.append(
            f"In the Brightway database, {thousands(comparison['exchange_rows_changed'])} of "
            f"{thousands(comparison['exchange_rows_compared'])} exchange rows differ from {esc(site.provider)}'s release; "
            + ("an import fix or a patch explains each." if left == 0 else f"{thousands(left)} of them no import fix or patch explains.")
        )
    exports = (manifest.get("exports") or {}).get("patched")
    if exports:
        back = exports["read_back_matches"]
        good = [EXPORT_NAMES.get(kind, kind) for kind, ok in back.items() if ok]
        bad = [EXPORT_NAMES.get(kind, kind) for kind, ok in back.items() if not ok]
        if good:
            items.append("Files for " + ", ".join(esc(n) for n in good) + " were written, and each was read back.")
        if bad:
            items.append("The file for " + ", ".join(esc(n) for n in bad) + " did not read back the same.")
    if manifest.get("contributions"):
        items.append(f"{plural(len(manifest['contributions']), 'contribution')} built beside the patched release.")
    return items


def listed(items):
    if not items:
        return '<span class="quiet">Not recorded.</span>'
    if len(items) == 1:
        return items[0]
    return '<ul class="plain">' + "".join(f"<li>{item}</li>" for item in items) + "</ul>"


# ------------------------------------------------------------------- steps and transcript


def steps_table(record):
    """Each step with its result and its time: the run's own steps when it kept them,
    else the steps GitHub recorded."""
    manifest = record.get("manifest")
    rows = []
    if manifest is not None:
        for step in manifest["steps"]:
            time = duration(step["seconds"]) if isinstance(step.get("seconds"), (int, float)) else ""
            rows.append((step["name"], step["status"], time, step.get("reason") or "", True))
    else:
        for job in record.get("jobs") or ():
            for step in job.get("steps") or ():
                name = str(step.get("name") or "")
                if name in SHOWN_STEPS or name.startswith("Post "):
                    continue
                start, end = moment(step.get("started")), moment(step.get("ended"))
                time = duration((end - start).total_seconds()) if start and end and end >= start else ""
                rows.append((name, step.get("conclusion") or "not run", time, "", False))
    if not rows:
        return ""
    head = ("Step", "Result", "Time")
    lines = ""
    for name, result, time, reason, own in rows:
        said = esc(result) + (f': <span class="quiet">{esc(reason)}</span>' if reason else "")
        # A step of the run is named as the run names it; a step of the job is GitHub's sentence.
        cells = (f"<code>{esc(name)}</code>" if own else esc(name), said, esc(time))
        mark = "" if result in ("completed", "success", "skipped") else ' class="run-failed"'
        lines += f'<tr role="row"{mark}>' + "".join(
            f'<td role="cell" data-label="{label}">{cell}</td>' for label, cell in zip(head, cells)
        ) + "</tr>"
    return (
        '<div class="table-wrap"><table role="table" class="cols-3 key-short"><thead role="rowgroup"><tr role="row">'
        + "".join(f'<th role="columnheader" scope="col">{label}</th>' for label in head)
        + f'</tr></thead><tbody role="rowgroup">{lines}</tbody></table></div>'
    )


def transcript_block(record, up):
    """What the run printed, line for line. Each line is one element; the time of the line
    is an attribute, drawn by the stylesheet, so the text of the block is the transcript."""
    data = record.get("transcript")
    if data is None:
        return ""
    lines = data["lines"]
    body = "".join(
        f'<span class="tl{" tl-step" if text.startswith("[") else ""}" data-t="{float(t):.1f}" data-clock="{clock(t)}">{visible(text)}\n</span>'
        for t, text in lines
    )
    ended = "It ended with status 0." if data["exit_code"] == 0 else f"It ended with status {int(data['exit_code'])}."
    if data.get("stopped_by"):
        ended = f"It was stopped ({esc(data['stopped_by'])})."
    cut = " The run printed more than is kept here." if data.get("cut") else ""
    return (
        '<h3 id="what-the-run-printed">What the run printed</h3>'
        f"<p>{plural(len(lines), 'line')}, exactly as the run printed them, each with its time since the start. {ended}{cut} "
        "Most of the time a run prints nothing while a step works; the replay shortens those waits and changes nothing else.</p>"
        '<div class="replay" data-replay>'
        '<p class="replay-bar" hidden><button type="button" class="button" data-replay-play>Replay</button>'
        '<button type="button" class="button" data-replay-all hidden>Show all lines</button>'
        '<span class="replay-clock" data-replay-clock></span></p>'
        f'<pre class="transcript" tabindex="0" role="region" aria-label="What the run printed">{body}</pre>'
        f'<p class="note">SHA-256 of these lines: <code>{esc(data["sha256"])}</code>. '
        f'The same record as a file: <a href="{up}api/v1/last-run.json"><code>api/v1/last-run.json</code></a>.</p>'
        f'</div><script src="{up}assets/replay.js" defer></script>'
    )


def last_run(site, up=""):
    """The block a prose page asks for with <!-- generated: last-run -->."""
    record = site.last_run
    if record["state"] != "read":
        return f'<p class="list-none">{esc(NOT_SHOWN[record["state"]])}</p>'
    kind, sentence_ = worked(record)
    facts = (
        ("Run", run_line(site, record)),
        ("Did it work", f'<span class="run-{kind}">{sentence_}</span>'),
        ("What is blocking", listed(blocking(site, record))),
        ("What was in it", listed(contents(site, record, up))),
    )
    panel = '<dl class="panel run-facts">' + "".join(f"<div><dt>{label}</dt><dd>{value}</dd></div>" for label, value in facts) + "</dl>"
    table = steps_table(record)
    return (
        panel
        + (f'<h3 id="steps-of-the-run">Step by step</h3>{table}' if table else "")
        + transcript_block(record, up)
    )


def public_record(record):
    """The record as a file of the site: as it was read, without the lists of dataset
    numbers of each patch (the manifest of a release holds them)."""
    if record.get("manifest") is None:
        return record
    manifest = dict(record["manifest"])
    manifest["patches"] = [{k: v for k, v in patch.items() if k != "datasets"} for patch in manifest.get("patches") or ()]
    return record | {"manifest": manifest}
