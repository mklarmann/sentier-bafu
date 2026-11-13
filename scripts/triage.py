"""Assemble the triage view: where each finding stands, where it is discussed, who acts next.

The stage of a finding comes from its record (community/findings/), which is reviewed. GitHub
adds only what the tracker knows: comment counts, last activity, labels, and issues filed as
findings that have no record yet. Without the tracker everything still builds from the records.
"""

import json
import os
import re
import urllib.request
from pathlib import Path

# (key, title, what it means). "the provider" is replaced by the provider's name on the site.
STAGES = [
    (
        "needs-triage",
        "Awaiting a second measurement",
        "Reported with a measurement. A second person has not yet repeated it on the release files.",
    ),
    (
        "open",
        "Measured, not yet sent to the provider",
        "Measured on the release files. It goes to the provider with the next batch.",
    ),
    (
        "upstream-reported",
        "Reported to the provider",
        "The provider decides what it changes. A community patch may apply the correction for those who need it now.",
    ),
    (
        "upstream-fixed",
        "Fixed by the provider",
        "The provider shipped the correction in a named release.",
    ),
    (
        "handled-in-layer",
        "Handled in a layer, question open",
        "A patch or layer applies it in a candidate build. The question to the provider is still open.",
    ),
    (
        "informational",
        "For information",
        "A method or scope difference, not a defect. Recorded so nobody derives it again.",
    ),
    (
        "withdrawn",
        "Withdrawn",
        "Did not survive re-measurement. Kept so nobody finds it again.",
    ),
]
STAGE_ORDER = {key: n for n, (key, _, _) in enumerate(STAGES)}
ISSUE = re.compile(r"https://github\.com/([^/]+/[^/]+)/issues/(\d+)")
FINDING_LABEL = "bafu-finding"


def slug(repository):
    return repository.rstrip("/").split("github.com/")[-1]


def fetch_issues(repository, token=None):
    """The repository's finding issues as {number: issue}: one request per hundred."""
    issues, page = {}, 1
    while True:
        request = urllib.request.Request(
            f"https://api.github.com/repos/{slug(repository)}/issues"
            f"?state=all&labels={FINDING_LABEL}&per_page=100&page={page}",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "sentier-site-build"},
        )
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        batch = json.load(urllib.request.urlopen(request, timeout=20))
        for item in batch:
            if "pull_request" in item:
                continue
            issues[item["number"]] = {
                "number": item["number"],
                "title": item["title"],
                "state": item["state"],
                "labels": sorted(label["name"] for label in item["labels"]),
                "comments": item["comments"],
                "updated": item["updated_at"][:10],
                "url": item["html_url"],
            }
        if len(batch) < 100:
            return issues
        page += 1


def load_issues(repository, snapshot=None, offline=False, require=False):
    """Issues from a snapshot file, else the API. ({}, None) when neither is available,
    unless `require` is set: a published site must not lose its discussion data silently."""
    if snapshot and Path(snapshot).exists():
        data = json.loads(Path(snapshot).read_text())
        return {int(k): v for k, v in data["issues"].items()}, data.get("fetched", "snapshot")
    if offline:
        return {}, None
    try:
        return fetch_issues(repository, os.environ.get("GITHUB_TOKEN")), "live"
    except Exception as error:
        if require:
            raise SystemExit(f"Could not read the issues of {repository}: {error}") from error
        print(f"Issues not read ({type(error).__name__}); building from the records alone.")
        return {}, None


def assemble(findings, repository, issues):
    """Findings with their stage and discussion, plus finding issues that have no record yet."""
    repo = slug(repository)
    placed, cited, counts = [], set(), {}
    for record in findings:
        own = [int(n) for name, n in ISSUE.findall(" ".join(record["links"])) if name == repo]
        cited.update(own)
        issue = issues.get(own[0]) if own else None
        awaiting = record["awaiting_second_measurement"]
        stage = "needs-triage" if awaiting else record["status"]
        # The issue's labels should mirror the record; say so when they do not.
        label_differs = bool(issue) and (
            (record["status"] != "open" and record["status"] not in issue["labels"])
            or awaiting != ("needs-triage" in issue["labels"])
        )
        counts[stage] = counts.get(stage, 0) + 1
        placed.append(
            dict(
                record,
                stage=stage,
                issue=issue,
                issue_number=own[0] if own else None,
                other_issues=own[1:],
                external=[u for u in record["links"] if f"github.com/{repo}/" not in u],
                label_differs=label_differs,
            )
        )
    placed.sort(key=lambda f: (STAGE_ORDER[f["stage"]], -int(f["id"][1:])))
    unlisted = [
        i for n, i in sorted(issues.items()) if n not in cited and i["state"] == "open"
    ]
    return dict(findings=placed, unlisted=unlisted, counts=counts)
