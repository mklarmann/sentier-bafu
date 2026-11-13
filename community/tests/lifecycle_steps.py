"""Do the unit tests pass whatever happens to the real records?

    uv run --no-project --with markdown==3.7 --with pyyaml==6.0.2 python community/tests/lifecycle_steps.py

A finding has a life: it is recorded, measured a second time, reported, answered, corrected or
withdrawn; a release is registered; a patch is added. Each such step is one review or one
command, and must stay that. A unit test that reads the repository's own records would fail at
one of these steps, and somebody would have to edit it.

This script takes each step on a scratch copy of the repository, with the commands people use
(`community.py repeat`, `send`, `answer`, `fixed`, `close`, `new_patch.py` and
`patches_snapshot.py`), checks the records of the copy,
and runs the unit tests on it. It exits 1 and names the tests that failed. The cure for such a
test is to read the frozen records (community/tests/frozen.py), not to update the test.
"""

import concurrent.futures
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import community  # noqa: E402

WHO = "lifecycle-check"
# Far in the future and in order: no real evidence is dated later.
DATES = {"repeated": "2099-01-01", "sent": "2099-01-02", "answer": "2099-01-03", "fixed": "2099-01-04",
         "closed": "2099-01-05", "reported": "2098-12-31"}


class Skip(Exception):
    pass


def run(copy, *args):
    return subprocess.run([sys.executable, str(copy / "scripts/community.py"), "--root", str(copy), *args],
                          capture_output=True, text=True)


def must(copy, *args):
    done = run(copy, *args)
    if done.returncode != 0:
        raise RuntimeError(f"community.py {' '.join(args[:2])} failed on the copy: {done.stdout}{done.stderr}")


def url(config, record):
    return community.issue_url(record, config["repository"]) or record["threads"][0]


def a_new_finding(copy):
    """A new finding is recorded."""
    config, findings = community.load_config(copy), community.load_findings(copy)
    number = max([config["older_numbering_until"]] + [community.finding_number(r) for r in findings]
                 + [r["issue"] or 0 for r in findings]) + 1
    codes = {dataset["code"] for record in findings for dataset in record["datasets"]}
    record = {
        "schema": 2, "id": f"F{number}", "issue": number, "title": "An example finding for the lifecycle check",
        "kind": "defect", "datasets": [{"code": max(codes | {0}) + 1, "name": "Example, at plant", "location": "CH"}],
        "scope": "", "releases": [config["releases"][-1]["id"]],
        "observation": "The dataset declares 1,000 kg where its siblings declare 1 kg.", "exposure": "",
        "method": "Measured on the release files.",
        "reported": {"by": "someone", "date": DATES["reported"], "url": f"{config['repository']}/issues/{number}"},
        "repeated": None, "sent": None, "answer": None, "fixed_in": None, "closed": None,
        "related": [], "threads": [], "next": None, "retained": [], "notes": "",
    }
    path = copy / community.record_path(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    community.write_record(path, record)


def next_step(copy):
    """Every finding takes the next step of its path."""
    config = community.load_config(copy)
    release = config["releases"][-1]["id"]
    batch = []
    for record in community.load_findings(copy):
        rid, stage, where = record["id"], community.stage(record), url(config, record)
        if stage == "filed" and record["reported"]["by"] and not record["repeated"]:
            must(copy, "repeat", rid, "--by", WHO, "--date", DATES["repeated"], "--url", where, "--result", "reproduced")
        elif stage == "confirmed":
            batch.append(rid)
        elif stage == "sent":
            must(copy, "answer", rid, "--outcome", "confirmed", "--date", DATES["answer"],
                 "--summary", f"{config['provider']} said it will look at it.", "--url", where)
        elif stage == "answered":
            must(copy, "fixed", rid, "--release", release, "--date", DATES["fixed"], "--url", where)
    if batch:
        must(copy, "send", "--batch", "2099-01", "--date", DATES["sent"],
             "--url", config["repository"] + "/issues/1", *batch)


def not_reproduced(copy):
    """Every finding that needs a second measurement gets one that does not reproduce it."""
    config = community.load_config(copy)
    for record in community.load_findings(copy):
        if community.stage(record) == "filed" and record["reported"]["by"] and not record["repeated"]:
            must(copy, "repeat", record["id"], "--by", WHO, "--date", DATES["repeated"], "--url", url(config, record),
                 "--result", "not-reproduced")


def withdrawn(copy):
    """Every finding that is still on its way is withdrawn."""
    for record in community.load_findings(copy):
        if community.stage(record) in community.OPEN_STAGES:
            must(copy, "close", record["id"], "--as", "withdrawn", "--date", DATES["closed"],
                 "--reason", "It did not hold when measured again.")


def a_new_release(copy):
    """A provider release is registered."""
    path = copy / "site/config.json"
    config = json.loads(path.read_text())
    config["releases"].append({"id": "9999-v1", "name": f"{config['provider']}:9999 v1"})
    path.write_text(json.dumps(config, indent=2) + "\n")
    form = copy / "scripts/intake.py"
    if form.exists():
        subprocess.run([sys.executable, str(form), "--root", str(copy), "form"], capture_output=True, check=True)


def a_new_patch(copy):
    """A community patch is added for a finding that has none."""
    registry = community.registry_module()
    if not registry.has_registry(copy):
        raise Skip("no patch tool in this tree")
    data = community.load_patches(copy) or {"patches": []}
    answered = {rid for patch in data["patches"] for rid in patch["findings"]}
    free = [record["id"] for record in community.load_findings(copy) if record["id"] not in answered]
    if not free:
        raise Skip("no finding without a patch")
    # As a person does it: the scaffold of the patch, then the list of patches from the registry.
    spec = importlib.util.spec_from_file_location("new_patch", copy / "scripts/new_patch.py")
    new_patch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(new_patch)
    new_patch.scaffold(copy, "lifecycle-check", free[-1], WHO)
    written = subprocess.run([sys.executable, str(copy / "scripts/patches_snapshot.py"), "--root", str(copy)],
                             capture_output=True, text=True)
    if written.returncode != 0:
        raise RuntimeError(f"patches_snapshot.py failed on the copy: {written.stdout}{written.stderr}")


STEPS = (a_new_finding, next_step, not_reproduced, withdrawn, a_new_release, a_new_patch)


def take(step, scratch):
    """One step on its own copy: (what the step is, failed tests or None when it was skipped)."""
    copy = Path(scratch) / step.__name__
    shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(".git", "_site", ".local", "__pycache__", ".venv"))
    what = step.__doc__.strip()
    try:
        step(copy)
    except Skip as skipped:
        return what, None, f"skipped ({skipped})"
    check = run(copy, "check")
    if check.returncode != 0:
        return what, ["the step itself left invalid records: " + check.stdout.strip()[:300]], ""
    done = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "community/tests"], cwd=copy,
                          capture_output=True, text=True)
    failed = sorted({line.split("(", 1)[1].rstrip(")") for line in done.stderr.splitlines()
                     if line.startswith(("FAIL:", "ERROR:")) and "(" in line})
    if done.returncode != 0 and not failed:
        failed = ["the tests did not run: " + done.stderr.strip()[-300:]]
    ran = next((line for line in done.stderr.splitlines() if line.startswith("Ran ")), "")
    return what, failed, ran


def main():
    with tempfile.TemporaryDirectory(prefix="lifecycle-steps-") as scratch:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda step: take(step, scratch), STEPS))
    broken = 0
    for what, failed, note in results:
        if failed is None:
            print(f"- {what} {note}")
        elif not failed:
            print(f"ok {what} {note}")
        else:
            broken += 1
            print(f"FAILED {what} {note}")
            for test in failed:
                print(f"       {test}")
    if broken:
        print("\nA test that fails here depends on what the repository's own records say. Let it read the "
              "frozen records instead (community/tests/frozen.py); do not update it to the new state.")
        return 1
    print("\nThe unit tests pass whatever happens to the records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
