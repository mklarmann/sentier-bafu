"""The last release build, as GitHub and the run itself recorded it.

    python3 scripts/last_run.py --repository owner/name --out FILE

For the workflow `release-build.yml` of one repository this reads

- GitHub's own record of the last run that has ended: its number, its commit, what
  started it, how it ended, and every step with its result. Anyone can read this.
- what that run kept: `manifest.json` and `transcript.json` of its artifact
  `release-build-results`. Reading an artifact needs a token (`actions: read`).

and returns one record. The site shows it as it is (`scripts/sitebuild/lastrun.py`): the
last run, not the last run that worked. A run that failed is shown as failed, with the step
and the reason; a run that kept nothing is shown with what GitHub recorded about it.

Nothing here is trusted because it came from a run: the two files are read with limits,
checked for their shape and for the names a public page must not carry, and the site
escapes every text of them.

    state       read | no run | not read | unreadable
    kept        read | none | expired | needs a token | unreadable     (when state is read)

Standard library only. `transport` and `fetch` are how requests leave the process; the tests
pass recorded answers, and nothing in the tests reaches the network.
"""

import argparse
import datetime
import io
import json
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import github_api  # noqa: E402
from release_build import public_summary, release_manifest, transcript  # noqa: E402

FORMAT = "sentier-bafu/last-run/1"
WORKFLOW = "release-build.yml"
ARTIFACT = "release-build-results"
MAX_ARCHIVE = 30 * 1024 * 1024
MAX_FILE = 12 * 1024 * 1024
STATES = ("read", "no run", "not read", "unreadable")
KEPT = ("read", "none", "expired", "needs a token", "unreadable")


def now():
    return datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat()


def empty(state, repository=None, note=None, read=None):
    """A record that holds no run, and says why. `read` is when GitHub was read; a record
    made without reading it has no time, so that two builds of one revision are the same."""
    return {
        "format": FORMAT,
        "state": state,
        "note": note,
        "repository": repository,
        "workflow": WORKFLOW,
        "read": read,
    }


def fetch_address(url):
    """The bytes at an address that needs no token. At most MAX_ARCHIVE of them."""
    if not url.startswith("https://"):
        raise ValueError("an artifact is read over https")
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 - https only
        data = response.read(MAX_ARCHIVE + 1)
    if len(data) > MAX_ARCHIVE:
        raise ValueError("the artifact is larger than a run's record can be")
    return data


def text(value, limit=300):
    return value[:limit] if isinstance(value, str) else None


def run_facts(run):
    """What the page says about a run, from GitHub's record. No person is named."""
    return {
        "id": int(run["id"]),
        "number": run.get("run_number"),
        "attempt": run.get("run_attempt"),
        "url": text(run.get("html_url")),
        "event": text(run.get("event"), 40),
        "branch": text(run.get("head_branch"), 200),
        "commit": text(run.get("head_sha"), 40),
        "conclusion": text(run.get("conclusion"), 40),
        "started": text(run.get("run_started_at") or run.get("created_at"), 30),
        "ended": text(run.get("updated_at"), 30),
    }


def job_facts(job):
    return {
        "name": text(job.get("name")),
        "conclusion": text(job.get("conclusion"), 40),
        "started": text(job.get("started_at"), 30),
        "ended": text(job.get("completed_at"), 30),
        "steps": [
            {
                "number": step.get("number"),
                "name": text(step.get("name")),
                "conclusion": text(step.get("conclusion"), 40),
                "started": text(step.get("started_at"), 30),
                "ended": text(step.get("completed_at"), 30),
            }
            for step in job.get("steps") or ()
        ],
    }


def unpack(archive):
    """manifest.json and transcript.json of an artifact's archive, each parsed or None,
    and what was wrong. A file that is too large, unreadable or of another shape is left out."""
    found, problems = {"manifest": None, "transcript": None}, []
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            for key in found:
                try:
                    info = bundle.getinfo(f"{key}.json")
                except KeyError:
                    continue
                if info.file_size > MAX_FILE:
                    problems.append(f"{key}.json is larger than a run's record can be")
                    continue
                try:
                    found[key] = json.loads(bundle.read(info).decode("utf-8"))
                except ValueError:  # a text that is not UTF-8 is a ValueError too
                    problems.append(f"{key}.json is not JSON")
    except zipfile.BadZipFile:
        return found, ["the artifact is not an archive"]
    checks = (
        ("manifest", release_manifest.shape_errors),
        ("transcript", transcript.shape_errors),
    )
    for key, check in checks:
        if found[key] is None:
            continue
        errors = check(found[key])
        errors += public_summary.named(found[key])
        if errors:
            problems.append(f"{key}.json: {errors[0]}")
            found[key] = None
    return found, problems


def kept_by(github, run_id, fetch=fetch_address):
    """What a run kept: (kept, note, manifest, transcript)."""
    listing = github.get(f"/actions/runs/{int(run_id)}/artifacts?per_page=100") or {}
    wanted = [a for a in listing.get("artifacts") or () if a.get("name") == ARTIFACT]
    if not wanted:
        return "none", None, None, None
    artifact = wanted[0]
    if artifact.get("expired"):
        return "expired", text(artifact.get("expires_at"), 30), None, None
    if int(artifact.get("size_in_bytes") or 0) > MAX_ARCHIVE:
        return "unreadable", "the artifact is larger than a run's record can be", None, None
    address = github.location(f"/actions/artifacts/{int(artifact['id'])}/zip")
    if address is None:
        return "needs a token", None, None, None
    found, problems = unpack(fetch(address))
    if found["manifest"] is None and found["transcript"] is None:
        return "unreadable", "; ".join(problems) or "it holds no record", None, None
    return "read", "; ".join(problems) or None, found["manifest"], found["transcript"]


def fetch(repository, token=None, transport=None, fetch=fetch_address):
    """The record of the last ended run of the release build of `repository`."""
    github = github_api.GitHub(repository, token, transport=transport)
    try:
        listing = github.get(f"/actions/workflows/{WORKFLOW}/runs?per_page=20") or {}
    except github_api.NotFound:
        return empty("no run", repository, "the repository has no release build", now())
    runs = listing.get("workflow_runs") or []
    ended = [run for run in runs if run.get("status") == "completed"]
    if not ended:
        return empty("no run", repository, None, now())
    run = ended[0]
    newer = runs[0] if runs[0] is not run else None
    jobs = github.get(f"/actions/runs/{int(run['id'])}/jobs?per_page=100") or {}
    kept, note, manifest, lines = kept_by(github, run["id"], fetch)
    return empty("read", repository, read=now()) | {
        "run": run_facts(run),
        "newer": None
        if newer is None
        else {
            "url": text(newer.get("html_url")),
            "status": text(newer.get("status"), 40),
        },
        "jobs": [job_facts(job) for job in jobs.get("jobs") or ()],
        "kept": kept,
        "kept_note": note,
        "manifest": manifest,
        "transcript": lines,
    }


def shape_errors(record):
    """What is wrong with a record read from a file; nothing when a page can show it."""
    if not isinstance(record, dict) or record.get("format") != FORMAT:
        return [f"not a record of format {FORMAT}"]
    if record.get("state") not in STATES:
        return ["`state` is not one of " + ", ".join(STATES)]
    if record["state"] != "read":
        return []
    found = []
    run = record.get("run")
    if not isinstance(run, dict) or not isinstance(run.get("id"), int):
        return ["`run` is not GitHub's record of a run"]
    if not str(run.get("url") or "").startswith("https://github.com/"):
        found.append("`run.url` is not an address on GitHub")
    if record.get("kept") not in KEPT:
        found.append("`kept` is not one of " + ", ".join(KEPT))
    if not isinstance(record.get("jobs"), list):
        found.append("`jobs` is not a list")
    if record.get("manifest") is not None:
        found += [f"manifest: {e}" for e in release_manifest.shape_errors(record["manifest"])]
    if record.get("transcript") is not None:
        found += [f"transcript: {e}" for e in transcript.shape_errors(record["transcript"])]
    found += [f"names who confirmed for the provider: {p}" for p in public_summary.named(record)]
    return found


def load(repository, snapshot=None, offline=False):
    """The record for a build of the site: from a file, else from GitHub, else one that says
    it was not read. A site is built without it rather than not built."""
    if snapshot:
        record = json.loads(Path(snapshot).read_text(encoding="utf-8"))
        errors = shape_errors(record)
        if errors:
            raise SystemExit(f"{snapshot} is not a record of a run: {errors[0]}")
        return record
    if offline:
        return empty("not read", repository, "this copy of the site was built without GitHub")
    try:
        record = fetch(repository, os.environ.get("GITHUB_TOKEN"))
    except Exception as error:  # noqa: BLE001 - the site is built without the run
        name = type(error).__name__
        print(f"The last release build was not read ({name}); the page says so.")
        return empty("unreadable", repository, "GitHub could not be read when the site was built")
    errors = shape_errors(record)
    if errors:
        print(f"The last release build is not shown: {github_api.plain(errors[0])}")
        return empty("unreadable", repository, "the record of the run could not be read")
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repository", required=True, help="owner/name")
    parser.add_argument("--out", type=Path, required=True, help="Where to write the record")
    args = parser.parse_args(argv)
    record = fetch(args.repository, os.environ.get("GITHUB_TOKEN"))
    errors = shape_errors(record)
    if errors:
        print(f"not written: {errors[0]}")
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    kept = record.get("kept", "nothing")
    print(f"Last release build of {args.repository}: {record['state']}, kept: {kept}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
