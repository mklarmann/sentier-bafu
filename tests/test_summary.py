import json

import pytest

from bafu_community_fixes import registry
from bafu_community_fixes.changes import Provenance
from bafu_community_fixes.cli import main
from bafu_community_fixes.models import UncertaintyType
from bafu_community_fixes.pipeline import PatchError, run
from bafu_community_fixes.registry import Patch
from bafu_community_fixes.summary import SCHEMA


def _set_uncertainty(db):
    for dataset in db:
        dataset.exchanges[0].uncertainty_type = UncertaintyType.LOGNORMAL


def _break_keys(db):
    for dataset in db:
        dataset.exchanges[1].number = dataset.exchanges[0].number


def test_summary_records_steps_and_changed_datasets(raw_bafu, tmp_path, monkeypatch):
    provenance = Provenance("Ann Author", authorised_by="Rita Reviewer", references=("ref",))
    patch = Patch("0001-test", "Set the type", _set_uncertainty, provenance, "Because.")
    monkeypatch.setitem(registry._REGISTRY, patch.id, patch)
    log = run(raw_bafu, tmp_path / "out", summary=tmp_path / "summary.json")
    data = json.loads((tmp_path / "summary.json").read_text())

    assert data["schema"] == SCHEMA
    assert data["status"] == "completed"
    assert data["source"]["fingerprint_sha256"] == log.input_fingerprint
    assert data["source"]["datasets"] == 1
    assert [s["id"] for s in data["steps"]] == [s.id for s in log.steps]
    (step,) = [s for s in data["steps"] if s["id"] == "0001-test"]
    assert step == {
        "id": "0001-test",
        "kind": "patch",
        "description": "Set the type",
        "rationale": "Because.",
        "authored_by": "Ann Author",
        "authorised_by": "Rita Reviewer",
        "reported_by": None,
        "confirmed_by": None,
        "references": ["ref"],
        "datasets": 1,
        "changes": 1,
        "fields": {"flowData/exchange/@uncertaintyType": 1},
    }
    (dataset,) = data["datasets"]
    assert dataset["file"] == "raw_bafu.xml"
    assert "0001-test" in dataset["patches"]
    assert dataset["import_fixes"] == [
        s.id for s in log.steps if s.kind == "import fix" and s.datasets
    ]
    assert set(dataset) == {"file", "number", "name", "location", "import_fixes", "patches"}


def test_summary_holds_counts_not_values(raw_bafu, tmp_path):
    run(raw_bafu, tmp_path / "out", summary=tmp_path / "summary.json")
    data = json.loads((tmp_path / "summary.json").read_text())
    assert set(data) == {
        "schema",
        "status",
        "error",
        "started",
        "finished",
        "source",
        "options",
        "software",
        "changed_datasets",
        "steps",
        "datasets",
    }
    for step in data["steps"]:
        assert all(isinstance(count, int) for count in step["fields"].values())


def test_summary_written_when_run_fails(raw_bafu, tmp_path, monkeypatch):
    patch = Patch("0002-broken", "Break things", _break_keys, Provenance("Ann Author"))
    monkeypatch.setitem(registry._REGISTRY, patch.id, patch)
    with pytest.raises(PatchError):
        run(raw_bafu, tmp_path / "out", summary=tmp_path / "summary.json")
    data = json.loads((tmp_path / "summary.json").read_text())
    assert data["status"] == "failed"
    assert "0002-broken" in data["error"]


def test_cli_writes_summary(raw_bafu, tmp_path, capsys):
    main(["run", str(raw_bafu), str(tmp_path / "out"), "--summary", str(tmp_path / "s.json")])
    assert "Summary written to" in capsys.readouterr().out
    assert json.loads((tmp_path / "s.json").read_text())["status"] == "completed"
