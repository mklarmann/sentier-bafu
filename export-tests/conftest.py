"""Fixtures for the export tests.

They run outside the package project, on their own requirements:

    uv run --no-project --python 3.12 --with-requirements export-tests/requirements.txt \\
        pytest export-tests

Brightway is pointed at a fresh temporary folder before it is imported, so the tests
never open the projects of the person running them.
"""

import atexit
import importlib.util
import os
import shutil
import tempfile
from pathlib import Path

BRIGHTWAY_DIR = tempfile.mkdtemp(prefix="sentier-bafu-export-tests-")
os.environ["BRIGHTWAY2_DIR"] = BRIGHTWAY_DIR
atexit.register(shutil.rmtree, BRIGHTWAY_DIR, ignore_errors=True)

import bw2data as bd  # noqa: E402
import pytest  # noqa: E402
import synthetic  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RELEASE = "SYNTHETIC:2026 v1"


def _script():
    spec = importlib.util.spec_from_file_location(
        "export_release", ROOT / "scripts/export_release.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


step = _script()


PATCHED_FILES = "cd" * 32


def run_summary():
    """What `bafu-fixes run --summary` would write for a run over the synthetic data."""

    def entry(id, kind, description, datasets, authorised_by="Rita Reviewer"):
        return {
            "id": id,
            "kind": kind,
            "description": description,
            "rationale": f"Why {id} is needed.",
            "authored_by": "Ann Author",
            "authorised_by": authorised_by,
            "reported_by": None,
            "confirmed_by": None,
            "findings": [],
            "references": [f"https://example.org/{id}"],
            "datasets": datasets,
            "exchanges": datasets,
            "changes": datasets * 2,
            "fields": {"flowData/exchange/@unit": datasets * 2},
            "xsd_checked": None,
            "error": None,
        }

    def dataset(number, code, import_fixes=(), patches=()):
        return {
            "file": f"process_{code}.xml",
            "number": number,
            "import_fixes": list(import_fixes),
            "patches": list(patches),
        }

    return {
        "schema": "bafu-community-fixes/run-summary/1",
        "status": "completed",
        "error": None,
        "started": "2026-11-13T10:00:00+01:00",
        "finished": "2026-11-13T10:01:00+01:00",
        "duration_seconds": 60.0,
        "release": {
            "url": None,
            "archive_sha256": None,
            "fingerprint": "ab" * 32,
            "files": 9,
            "datasets": 9,
            "exchanges": 39,
        },
        "software": {"bafu-community-fixes": "0.1.0"},
        "options": {},
        "steps": [
            entry("unit-names", "import fix", "Write unit names the schema allows", 1),
            entry("0001-flour-share", "patch", "Correct the flour input of bread", 1),
            entry("0002-no-effect", "patch", "A patch that changed nothing here", 0),
            entry("0003-waiting", "patch", "Correct a location", 1, authorised_by=None),
        ],
        "totals": {"steps": 4, "datasets_changed": 2, "values_changed": 6},
        "output": {"files": 9, "bytes": 9000, "fingerprint": PATCHED_FILES},
        "datasets": [
            dataset(101, "bread-ch", patches=["0001-flour-share"]),
            dataset(102, "wheat", ["unit-names"], ["0003-waiting"]),
        ],
    }


def marker(**changes):
    """What the build writes into the metadata of a database of a patched copy."""
    record = {
        "label": "Modified Data",
        "modified_data": True,
        "provider_release": RELEASE,
        "built_release_tree_sha256": PATCHED_FILES,
        "patches": ["0001-flour-share", "0003-waiting"],
        "import_fixes": ["unit-names"],
    }
    return record | changes


_projects = {}


def project(*variants):
    """The synthetic databases in a Brightway project of their own, written once."""
    name = "synthetic" + "".join(f"+{variant.__name__}" for variant in variants)
    if name not in _projects:
        bd.projects.set_current(name)
        data = synthetic.databases(*variants)
        for database, nodes in data.items():
            bd.Database(database).write(nodes)
        bd.databases[synthetic.INVENTORY][step.MARKER] = marker()
        bd.databases.flush()
        _projects[name] = list(data)
    return name, _projects[name]


def export(tmp_path, *variants, **options):
    """Run the step on the synthetic databases; returns `(manifest, folder, databases)`."""
    name, names = project(*variants)
    databases = step.load_databases(name, names)
    out = tmp_path / "out"
    manifest = step.export_release(databases, run_summary(), out, release=RELEASE, **options)
    return manifest, out, databases


@pytest.fixture(scope="session")
def base(tmp_path_factory):
    """One export of the base database with a method, shared by the tests that only read."""
    methods = tmp_path_factory.mktemp("methods") / "methods.json"
    methods.write_text(synthetic.methods_json())
    return export(tmp_path_factory.mktemp("base"), methods=methods)
