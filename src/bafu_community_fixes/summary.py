"""A machine-readable summary of a run: one record for everything built from it.

The HTML report is written for people and quotes the data: example datasets, XML
snippets, old and new values. The summary doesn't. It has the identity of the input
and of the output, the software, for each step who is behind it, why, and how much
it changed, and for every changed dataset the steps that changed it. So an automated
run can publish it without publishing the inventory, a later run can be compared
with it, and anything built from the output can say which modifications it carries.

It holds file names and dataset numbers, and no names, amounts or other values of
the release. The only text taken from a run is the first line of an error message,
which can name a dataset number, an exchange name and one value.
"""

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path

from bafu_community_fixes.changes import RunLog, StepLog
from bafu_community_fixes.download import CHECKSUMS, FINGERPRINTS
from bafu_community_fixes.xml import Database

SCHEMA = "bafu-community-fixes/run-summary/1"
MAX_ERROR_LENGTH = 300


def _first_line(text: str | None) -> str | None:
    if not text:
        return None
    line = text.strip().splitlines()[0]
    return line if len(line) <= MAX_ERROR_LENGTH else line[:MAX_ERROR_LENGTH] + "…"


def fingerprint(root: Path, files: Iterable[Path]) -> tuple[str, int]:
    """SHA-256 of a set of files, and their size in bytes.

    Built like the input fingerprint in `import_database`, from each file's path
    relative to `root` and its bytes, in sorted order. So the fingerprint of one
    run's output is the input fingerprint of a run that reads that output.
    """
    digest, size = hashlib.sha256(), 0
    for path in sorted(files):
        data = path.read_bytes()
        digest.update(str(path.relative_to(root)).encode() + b"\0" + data)
        size += len(data)
    return digest.hexdigest(), size


def _release(log: RunLog) -> dict:
    """The input, and which known release it is (`url` is None if it isn't one)."""
    url = next((u for u, f in FINGERPRINTS.items() if f == log.input_fingerprint), None)
    return {
        "url": url,
        "archive_sha256": CHECKSUMS.get(url),
        "fingerprint": log.input_fingerprint,
        "files": log.files,
        "datasets": log.datasets,
        "exchanges": log.exchanges,
    }


def _step(step: StepLog) -> dict:
    provenance = step.provenance
    return {
        "id": step.id,
        "kind": step.kind,
        "description": step.description,
        "rationale": step.rationale,
        "authored_by": provenance.authored_by,
        "authorised_by": provenance.authorised_by,
        "reported_by": provenance.reported_by,
        "confirmed_by": provenance.confirmed_by,
        "findings": list(provenance.findings),
        "references": list(provenance.references),
        "datasets": step.datasets,
        "exchanges": step.exchanges,
        "changes": step.changes,
        "fields": {name: stats.changes for name, stats in sorted(step.fields.items())},
        "xsd_checked": step.xsd_checked,
        "error": _first_line(step.error),
    }


def _datasets(db: Database) -> list[dict]:
    """Every dataset that a step changed: its file, its number, and those steps."""
    changed = []
    for path, doc in db.documents.items():
        for dataset in doc.datasets:
            ext = dataset.ext
            if ext is None or not (ext.import_fixes or ext.patches):
                continue
            changed.append(
                {
                    "file": path.as_posix(),
                    "number": dataset.number,
                    "import_fixes": list(ext.import_fixes),
                    "patches": list(ext.patches),
                }
            )
    return changed


def summarise(log: RunLog, written: Iterable[Path] = (), db: Database | None = None) -> dict:
    """The summary of a run, as JSON-ready data.

    `written` are the files it wrote. `db` is what it read and changed; without it
    (a run that failed before reading anything), there is no list of datasets.
    """
    output = None
    if log.status == "completed" and log.destination is not None:
        digest, size = fingerprint(Path(log.destination), written)
        output = {"files": log.written, "bytes": size, "fingerprint": digest}
    return {
        "schema": SCHEMA,
        "status": log.status,
        "error": _first_line(log.error),
        "started": log.started.isoformat(timespec="seconds"),
        "finished": log.finished.isoformat(timespec="seconds") if log.finished else None,
        "duration_seconds": log.duration,
        "release": _release(log),
        "software": dict(log.software),
        "options": dict(log.options),
        "steps": [_step(step) for step in log.steps],
        "totals": {
            "steps": len(log.steps),
            "datasets_changed": len(log.changed_datasets),
            "values_changed": sum(step.changes for step in log.steps),
        },
        "output": output,
        "datasets": _datasets(db) if db is not None else None,
    }


def write_summary(
    log: RunLog, path: Path | str, written: Iterable[Path] = (), db: Database | None = None
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(summarise(log, written, db), indent=2, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")
    return path
