"""Track contributed layers and compare isolated builds; no importer dependencies."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

STATES = {"proposed", "testing", "reviewing", "accepted", "rejected", "superseded"}


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate(record):
    errors = []
    required = {
        "id",
        "title",
        "status",
        "baseline",
        "layer",
        "evidence",
        "required_checks",
        "runs",
        "required_reviewers",
        "approvals",
        "objections",
        "upstream_project",
    }
    if required - record.keys():
        return ["missing fields: " + ", ".join(sorted(required - record.keys()))]
    if record["status"] not in STATES:
        errors.append("invalid status")
    for key in (
        "evidence",
        "required_checks",
        "runs",
        "required_reviewers",
        "approvals",
        "objections",
    ):
        if not isinstance(record[key], list):
            errors.append(f"{key} must be a list")
    for key, fields in [
        (
            "baseline",
            {
                "dataset",
                "release",
                "import_repository",
                "import_revision",
                "input_hashes",
            },
        ),
        (
            "layer",
            {"kind", "implementation_url", "implementation_revision", "payloads"},
        ),
    ]:
        if not isinstance(record[key], dict) or fields - record[key].keys():
            errors.append(f"{key} needs {sorted(fields)}")
    if errors:
        return errors
    if record["status"] == "accepted":
        baseline = record["baseline"]
        if not all(
            record["layer"].get(k)
            for k in ("kind", "implementation_url", "implementation_revision")
        ):
            errors.append("accepted contributions need a named, pinned implementation")
        if any(not isinstance(r, str) or not r.strip() for r in record["required_reviewers"]):
            errors.append("required reviewers must have nonempty identities")
        if not all(
            baseline.get(k)
            for k in (
                "dataset",
                "release",
                "import_repository",
                "import_revision",
                "input_hashes",
            )
        ):
            errors.append("accepted contributions need a pinned baseline and input hashes")
        if not record["required_checks"] or not record["evidence"]:
            errors.append("acceptance needs required checks and source evidence")
        # A failed or skipped required check cannot be hidden by another passed run.
        checks = {}
        for run in record["runs"]:
            if (
                not isinstance(run, dict)
                or run.get("baseline") != baseline
                or run.get("layer_revision") != record["layer"]["implementation_revision"]
            ):
                errors.append(
                    "accepted run must identify the exact baseline and candidate revision"
                )
                continue
            if not run.get("evidence_url"):
                errors.append("accepted run needs public validation evidence")
            for check in run.get("checks", []):
                checks.setdefault(check.get("id"), []).append(check)
        for name in record["required_checks"]:
            results = checks.get(name, [])
            if not results or any(
                c.get("status") != "passed" or not c.get("evidence_url") for c in results
            ):
                errors.append(f"required check {name} has missing, failed or skipped evidence")
        approved = {
            a.get("reviewer")
            for a in record["approvals"]
            if isinstance(a, dict)
            and a.get("evidence_url")
            and a.get("baseline") == baseline
            and a.get("layer_revision") == record["layer"]["implementation_revision"]
        }
        if not record["required_reviewers"] or not set(record["required_reviewers"]) <= approved:
            errors.append(
                "acceptance needs named reviewers and every approval tied to the exact baseline and layer revision"
            )
        if any(
            not isinstance(o, dict) or not o.get("disposition") or not o.get("evidence_url")
            for o in record["objections"]
        ):
            errors.append("objections need documented disposition and evidence")
    return errors


FINDING_STATES = {
    "open": "observed and measured; not yet sent to BAFU",
    "upstream-reported": "sent to BAFU (date on the issue)",
    "upstream-fixed": "BAFU corrected it in a named release",
    "informational": "a method or scope difference, not a defect; recorded so nobody derives it again",
    "handled-in-layer": "a layer applies it in a candidate build; the question to BAFU stays open",
    "withdrawn": "did not survive re-measurement on BAFU's own files; kept so nobody finds it again",
}
ROLES = {"data user", "partner", "reviewer", "maintainer", "flow curator", "importer maintainer"}
RETAINED_KINDS = {"ask", "objection", "earlier-interpretation"}
FINDING_FIELDS = {
    "id",
    "title",
    "datasets",
    "release",
    "status",
    "awaiting_second_measurement",
    "observation",
    "links",
    "community_patch",
    "provider_response",
    "provider_correction_shipped",
    "reviewer_consensus",
    "pipeline_run_evidence",
    "validation_scope",
    "next_action",
    "review_role",
    "evidence_url",
    "retained",
}
# A table cell holds one line; a record holds Markdown, never raw HTML.
BREAKS_A_ROW = re.compile(r"[|\r\n\x0b\x0c\x1c-\x1e\x85\u2028\u2029]")
RAW_HTML = re.compile(r"<[A-Za-z/!]")
INDEX_HEAD = """# Findings about the BAFU/UVEK data

<!-- Generated from community/findings/ by `python3 scripts/community.py index`. Do not edit. -->

One line per finding. The full record of a finding is its file in [findings/](findings/), for
example [findings/F3.json](findings/F3.json); the [site](https://sentier-dev.github.io/sentier-bafu/findings.html)
shows every record with its discussion. Dataset values and names are quoted; text from the
LCI reports is never pasted (Terms of Use clause 4).

Numbers are shared with the [lci-bafu-catalog ledger](https://gitlab.com/eos-lci/lci-bafu-catalog/-/blob/main/docs/bafu_findings.md),
so a finding has one number in both places. A number missing here is a finding recorded
there that has no record in this repository yet.

## Status vocabulary

| Status | Meaning |
|---|---|
"""
INDEX_TABLE = """
## Ledger

| # | Dataset(s) | Observation | Release | Status | Thread here · derivation |
|---|---|---|---|---|---|
"""


def finding_number(record):
    match = re.fullmatch(r"F([1-9][0-9]*)", str(record.get("id", "")))
    return int(match.group(1)) if match else 0


def load_findings(root):
    """Every finding record, in number order. One file per finding scales; one table does not."""
    records = [read(p) for p in (Path(root) / "community/findings").rglob("F*.json")]
    return sorted(records, key=finding_number)


def retained_errors(rid, items):
    if not isinstance(items, list) or any(
        not isinstance(x, dict)
        or x.get("kind") not in RETAINED_KINDS
        or not x.get("text")
        or not x.get("evidence_url")
        for x in items
    ):
        return [f"{rid}: retained items need a kind, text and evidence"]
    return []


def validate_finding(record, filename=None):
    if not isinstance(record, dict):
        return [f"{filename or '?'}: a finding record is a JSON object"]
    rid = record.get("id", "?")
    if FINDING_FIELDS - record.keys():
        return [f"{rid}: missing fields: " + ", ".join(sorted(FINDING_FIELDS - record.keys()))]
    errors = []
    if not finding_number(record):
        errors.append(f"{rid}: the id is F followed by a number")
    if filename and filename != f"{rid}.json":
        errors.append(f"{rid}: the file is named {filename}")
    status = record["status"]
    if not isinstance(status, str) or status not in FINDING_STATES:
        return errors + [f"{rid}: invalid status {status}"]
    for key in ("title", "datasets", "release", "observation"):
        if not isinstance(record[key], str) or not record[key].strip():
            errors.append(f"{rid}: {key} is empty")
        elif key != "observation" and BREAKS_A_ROW.search(record[key]):
            errors.append(f"{rid}: {key} must be one line without a table bar")
    for key in ("title", "datasets", "release", "observation", "notes"):
        if isinstance(record.get(key), str) and RAW_HTML.search(record[key]):
            errors.append(f"{rid}: {key} holds raw HTML; write Markdown")
    if not isinstance(record.get("notes", ""), str):
        errors.append(f"{rid}: notes is text")
    links = record["links"]
    if (
        not isinstance(links, list)
        or not links
        or any(not re.fullmatch(r"https://[^\s()<>\"|]+", str(u)) for u in links)
    ):
        errors.append(f"{rid}: needs at least one plain https link to its thread")
    awaiting = record["awaiting_second_measurement"]
    if not isinstance(awaiting, bool):
        errors.append(f"{rid}: awaiting_second_measurement is true or false")
    elif awaiting and status != "open":
        errors.append(f"{rid}: only an open finding can await its second measurement")
    for key in ("community_patch", "provider_response", "provider_correction_shipped"):
        if record[key] is not None and not isinstance(record[key], dict):
            errors.append(f"{rid}: {key} is an object or null")
            return errors
    # A patch or a provider confirmation never closes a finding; only a shipped release does.
    shipped = record["provider_correction_shipped"]
    if status == "upstream-fixed" and not shipped:
        errors.append(f"{rid}: upstream-fixed needs a shipped provider correction")
    if shipped and not (shipped.get("release") and shipped.get("evidence_url")):
        errors.append(f"{rid}: shipped correction needs a release and evidence")
    if shipped and status != "upstream-fixed":
        errors.append(f"{rid}: a shipped correction makes the finding upstream-fixed")
    patch = record["community_patch"]
    if patch and not (
        patch.get("id")
        and patch.get("url")
        and isinstance(patch.get("authorisation"), dict)
        and patch["authorisation"].get("evidence_url")
    ):
        errors.append(f"{rid}: patch needs an id, a pinned url and authorisation evidence")
    provider = record["provider_response"]
    if provider and not all(
        provider.get(k) for k in ("by", "date", "public_summary", "evidence_url")
    ):
        errors.append(
            f"{rid}: provider response needs who, when, a public summary and evidence"
        )
    if status not in {"withdrawn", "upstream-fixed"} and not (
        record["next_action"] and record["review_role"] in ROLES and record["evidence_url"]
    ):
        errors.append(f"{rid}: open record needs a next action, review role and evidence")
    return errors + retained_errors(rid, record["retained"])


def validate_contribution_triage(record):
    """What the triage view needs from a contribution that is still in progress."""
    rid = record.get("id", "?")
    errors = retained_errors(rid, record.get("retained", []))
    if not isinstance(record.get("validation_scope", ""), str):
        errors.append(f"{rid}: validation_scope is text")
    if record.get("status") not in {"accepted", "rejected", "superseded"} and not (
        record.get("next_action") and record.get("review_role") in ROLES and record.get("evidence_url")
    ):
        errors.append(f"{rid}: open contribution needs a next action, review role and evidence")
    return errors


def link_label(url):
    """#12 for an issue here, "lci-bafu-catalog #3" for one elsewhere, the host for the rest."""
    issue = re.search(r"/([^/]+)/(?:-/)?issues/(\d+)$", url)
    if not issue:
        return url.split("/")[2]
    here = "github.com/sentier-dev/sentier-bafu/" in url
    return f"#{issue.group(2)}" if here else f"{issue.group(1)} #{issue.group(2)}"


def link_cell(record):
    return " · ".join(f"[{link_label(url)}]({url})" for url in record["links"])


def index_text(findings):
    """The one-line-per-finding ledger, generated from the records."""
    vocabulary = "".join(f"| **{k}** | {v} |\n" for k, v in FINDING_STATES.items())
    rows = "".join(
        f"| {r['id']} | {r['datasets']} | {r['title']} | {r['release']} | {r['status']} | {link_cell(r)} |\n"
        for r in findings
    )
    return INDEX_HEAD + vocabulary + INDEX_TABLE + rows


def ledger_rows(text):
    """Rows of the generated ledger: {id: {status, links}}. Other projects read the same table."""
    rows, inside = {}, False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = line.startswith("## Ledger")
        if inside and line.startswith("| F"):
            cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
            rows[cells[0]] = {
                "status": cells[4],
                "links": set(re.findall(r"\((https://[^)]+)\)", cells[5])),
            }
    return rows


def check(root):
    root = Path(root)
    errors, records = [], {}
    for path in sorted((root / "community/contributions").glob("*.json")):
        record = read(path)
        errors += [f"{path.name}: {e}" for e in validate(record)]
        errors += [f"{path.name}: {e}" for e in validate_contribution_triage(record)]
        if record.get("id") in records:
            errors.append(f"duplicate contribution {record.get('id')}")
        records[record.get("id")] = record
    for packet in read(root / "community/recommendations/tracker.json"):
        record = records.get(packet.get("contribution_id"))
        state = packet.get("status")
        if state not in {"draft", "ready", "sent", "acknowledged", "resolved"}:
            errors.append("invalid recommendation state")
        if not record:
            errors.append("recommendation references unknown contribution")
        if state != "draft" and (
            not record or record["status"] != "accepted" or not packet.get("recipient")
        ):
            errors.append(
                "ready recommendation needs accepted contribution and confirmed recipient"
            )
        if state in {"sent", "acknowledged", "resolved"} and not packet.get("delivery_url"):
            errors.append("sent recommendation needs delivery evidence")
        if state in {"acknowledged", "resolved"} and not packet.get("response_url"):
            errors.append("provider response needs evidence")
    findings, seen = [], set()
    for path in sorted((root / "community/findings").rglob("*.json")):
        try:
            record = read(path)
            problems = validate_finding(record, path.name)
        except Exception as error:  # name the file; never stop at the first broken record
            errors.append(f"{path.name}: unreadable record ({type(error).__name__}: {error})")
            continue
        errors += problems
        if not isinstance(record, dict):
            continue
        if record.get("id") in seen:
            errors.append(f"duplicate finding {record.get('id')}")
        seen.add(record.get("id"))
        if not problems:
            findings.append(record)
    findings.sort(key=finding_number)
    index = root / "community/findings.md"
    if not errors and (not index.exists() or index.read_text() != index_text(findings)):
        errors.append("community/findings.md is out of date: run `python3 scripts/community.py index`")
    print(
        "\n".join(errors)
        if errors
        else f"Validated {len(findings)} findings, {len(records)} contribution records "
        "and the recommendation references."
    )
    return int(bool(errors))


def compare(baseline_path, candidate_path):
    baseline, candidate = read(baseline_path), read(candidate_path)
    if not baseline.get("baseline_id") or baseline.get("baseline_id") != candidate.get(
        "baseline_id"
    ):
        raise ValueError("baseline identities differ or are missing")
    scope = {
        "background",
        "method",
        "functional_unit",
        "allocation",
        "boundary",
        "geography",
    }
    if not isinstance(baseline.get("scope"), dict) or scope - baseline["scope"].keys():
        raise ValueError("comparison scope is incomplete")
    if baseline["scope"] != candidate.get("scope"):
        raise ValueError("comparison scopes differ")
    if (
        not baseline.get("metrics")
        or baseline["metrics"].keys() != candidate.get("metrics", {}).keys()
    ):
        raise ValueError("metric sets differ or are empty; omitted metrics cannot hide regressions")
    metrics = {}
    for key, before in baseline["metrics"].items():
        after = candidate["metrics"][key]
        if not before.get("unit") or before["unit"] != after.get("unit"):
            raise ValueError(f"metric {key}: incompatible units")
        values = [before.get("value"), after.get("value")]
        if any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
            for v in values
        ):
            raise ValueError(f"metric {key}: values must be finite numbers")
        delta = values[1] - values[0]
        if not math.isfinite(delta):
            raise ValueError(f"metric {key}: delta overflow")
        metrics[key] = {
            "baseline": values[0],
            "candidate": values[1],
            "delta": delta,
            "relative_delta": delta / abs(values[0]) if values[0] else None,
            "unit": before["unit"],
        }
    return {
        "baseline_id": baseline["baseline_id"],
        "scope": baseline["scope"],
        "input_sha256": {
            "baseline": digest(baseline_path),
            "candidate": digest(candidate_path),
        },
        "metrics": metrics,
        "checks": {
            "baseline": baseline.get("checks", []),
            "candidate": candidate.get("checks", []),
        },
        "interpretation": "Comparison only; scientific validation and partner review are separate.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    sub.add_parser("index")
    command = sub.add_parser("compare")
    command.add_argument("baseline", type=Path)
    command.add_argument("candidate", type=Path)
    command.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.command == "check":
        return check(root)
    if args.command == "index":
        (root / "community/findings.md").write_text(index_text(load_findings(root)))
        print("community/findings.md")
        return 0
    # Refuse overwrite: old evidence must remain available for review.
    report = compare(args.baseline, args.candidate)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
