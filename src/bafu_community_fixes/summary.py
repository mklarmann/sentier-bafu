"""A run's record of modifications as data, for anything built from the output.

The HTML report is for people. This is the same record for programs: which import
fixes and patches ran, why, who wrote and authorised each one, how much each changed,
and, for every changed dataset, which steps changed it. An export of the patched
release reads it to label the data as modified and to carry the list of changes.

It holds dataset numbers, names and locations, and no amounts.
"""

import json
from pathlib import Path

from bafu_community_fixes.changes import RunLog, StepLog
from bafu_community_fixes.xml import Database

SCHEMA = "bafu-community-fixes/run-summary/1"


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
        "references": list(provenance.references),
        "datasets": step.datasets,
        "changes": step.changes,
        "fields": {name: stats.changes for name, stats in sorted(step.fields.items())},
    }


def _datasets(db: Database) -> list[dict]:
    """Every dataset that a step changed, with the steps that changed it."""
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
                    "name": dataset.name,
                    "location": dataset.location,
                    "import_fixes": list(ext.import_fixes),
                    "patches": list(ext.patches),
                }
            )
    return changed


def summary(log: RunLog, db: Database | None = None) -> dict:
    """The run as plain data. Without `db` (a run that failed early), no dataset list."""
    return {
        "schema": SCHEMA,
        "status": log.status,
        "error": log.error,
        "started": log.started.isoformat(),
        "finished": log.finished.isoformat() if log.finished else None,
        "source": {
            "location": log.source,
            "fingerprint_sha256": log.input_fingerprint,
            "files": log.files,
            "datasets": log.datasets,
            "exchanges": log.exchanges,
        },
        "options": {key: str(value) for key, value in log.options.items()},
        "software": dict(log.software),
        "changed_datasets": len(log.changed_datasets),
        "steps": [_step(step) for step in log.steps],
        "datasets": _datasets(db) if db is not None else None,
    }


def write_summary(log: RunLog, path: Path | str, db: Database | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(summary(log, db), indent=2, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")
    return path
