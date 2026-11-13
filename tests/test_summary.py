import json

import pytest
from lxml import etree

from bafu_community_fixes import download, registry
from bafu_community_fixes.changes import Change, DatasetRef, Provenance, RunLog, StepLog
from bafu_community_fixes.cli import main
from bafu_community_fixes.models import UncertaintyType
from bafu_community_fixes.pipeline import PatchError, import_database, run
from bafu_community_fixes.registry import Patch
from bafu_community_fixes.summary import SUMMARY_VERSION, fingerprint

PROVENANCE = Provenance(
    "Ann Author", "Olga Owner", ("https://example.org/issue/1",), "Rita Reporter", "BAFU", ("F14",)
)


def _change_two_exchanges(db):
    for dataset in db:
        dataset.exchanges[0].uncertainty_type = UncertaintyType.LOGNORMAL
        dataset.exchanges[2].mean_value = 2.5


def _break_keys(db):
    for dataset in db:
        dataset.exchanges[1].number = dataset.exchanges[0].number


def _unexpected_target(db):
    raise ValueError("Dataset 100: expected 1.5 kg, found 2.5\nmore detail on a second line")


def _register(monkeypatch, id, func, provenance=PROVENANCE):
    monkeypatch.setitem(registry._REGISTRY, id, Patch(id, "Change something", func, provenance))


def _run(raw_bafu, tmp_path, **options):
    summary = tmp_path / "summary.json"
    run(raw_bafu, tmp_path / "out", summary=summary, **options)
    return json.loads(summary.read_text())


def test_summary(raw_bafu, tmp_path, monkeypatch):
    _register(monkeypatch, "0000-test", _change_two_exchanges)
    summary = _run(raw_bafu, tmp_path, xsd_check="every-step")

    assert summary["summary_version"] == SUMMARY_VERSION
    assert summary["status"] == "completed" and summary["error"] is None
    assert summary["release"] | {"fingerprint": None} == {
        "url": None,  # the fixture isn't a known release
        "archive_sha256": None,
        "fingerprint": None,
        "files": 1,
        "datasets": 1,
        "exchanges": 3,
    }
    assert len(summary["release"]["fingerprint"]) == 64
    assert summary["software"]["bafu-community-fixes"]
    assert summary["options"]["XSD schema check"] == "after import and after every patch"

    step = next(s for s in summary["steps"] if s["id"] == "0000-test")
    assert step == {
        "id": "0000-test",
        "kind": "patch",
        "description": "Change something",
        "authored_by": "Ann Author",
        "authorised_by": "Olga Owner",
        "reported_by": "Rita Reporter",
        "confirmed_by": "BAFU",
        "findings": ["F14"],
        "references": ["https://example.org/issue/1"],
        "datasets": 1,
        "exchanges": 2,
        "changes": 2,
        "fields": {"flowData/exchange/@meanValue": 1, "flowData/exchange/@uncertaintyType": 1},
        "xsd_checked": 1,
        "error": None,
    }
    kinds = [s["kind"] for s in summary["steps"]]
    assert kinds == sorted(kinds)  # import fixes first, in order, then patches
    assert summary["totals"]["steps"] == len(summary["steps"])
    assert summary["totals"]["datasets_changed"] == 1
    assert summary["totals"]["values_changed"] == sum(s["changes"] for s in summary["steps"])


def test_output_fingerprint_is_the_input_fingerprint_of_the_next_run(raw_bafu, tmp_path):
    summary = _run(raw_bafu, tmp_path)
    out = tmp_path / "out"
    files = list(out.iterdir())
    assert summary["output"] == {
        "files": 1,
        "bytes": sum(p.stat().st_size for p in files),
        "fingerprint": fingerprint(out, files)[0],
    }
    log = RunLog(str(out), {})
    import_database(out, log=log)
    assert log.input_fingerprint == summary["output"]["fingerprint"]


def test_summary_has_no_data_from_the_release(raw_bafu, tmp_path, monkeypatch):
    _register(monkeypatch, "0000-test", _change_two_exchanges)
    run(raw_bafu, tmp_path / "out", summary=tmp_path / "summary.json")
    text = (tmp_path / "summary.json").read_text()
    values = {
        value
        for el in etree.parse(str(raw_bafu)).iter()
        if isinstance(el.tag, str)
        for value in el.attrib.values()
        if len(value) > 8  # short ones, like "Report", are also words in a description
    }
    assert len(values) > 10
    assert [value for value in values if value in text] == []
    assert str(tmp_path) not in text  # nor paths of the machine it ran on


def test_summary_written_when_run_fails(raw_bafu, tmp_path, monkeypatch):
    _register(monkeypatch, "0000-broken", _break_keys)
    _register(monkeypatch, "0000-never-reached", _change_two_exchanges)
    with pytest.raises(PatchError):
        run(raw_bafu, tmp_path / "out", summary=tmp_path / "summary.json")
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["status"] == "failed"
    assert summary["error"] == "Patch 0000-broken left invalid data:"
    assert summary["output"] is None
    patches = {s["id"]: s for s in summary["steps"] if s["kind"] == "patch"}
    assert list(patches) == ["0000-broken"]  # the run stopped there
    assert patches["0000-broken"]["error"] == "Patch 0000-broken left invalid data:"
    assert all(s["error"] is None for s in summary["steps"] if s["kind"] == "import fix")


def test_summary_names_the_patch_whose_target_was_not_as_expected(raw_bafu, tmp_path, monkeypatch):
    _register(monkeypatch, "0000-stops", _unexpected_target)
    with pytest.raises(ValueError, match="expected 1.5 kg"):
        run(raw_bafu, tmp_path / "out", summary=tmp_path / "summary.json")
    summary = json.loads((tmp_path / "summary.json").read_text())
    (step,) = [s for s in summary["steps"] if s["id"] == "0000-stops"]
    assert step["error"] == "Dataset 100: expected 1.5 kg, found 2.5"  # the first line only
    assert step["datasets"] == 0
    assert summary["status"] == "failed"


def test_summary_recognises_a_known_release(raw_bafu, tmp_path, monkeypatch):
    url = "https://example.org/release-v1.zip"
    unknown = _run(raw_bafu, tmp_path / "a")["release"]
    monkeypatch.setitem(download.FINGERPRINTS, url, unknown["fingerprint"])
    monkeypatch.setitem(download.CHECKSUMS, url, "0" * 64)
    known = _run(raw_bafu, tmp_path / "b")["release"]
    assert unknown["url"] is None
    assert (known["url"], known["archive_sha256"]) == (url, "0" * 64)


def test_cli_writes_summary(raw_bafu, tmp_path, capsys):
    summary = tmp_path / "nested" / "summary.json"
    main(["run", str(raw_bafu), str(tmp_path / "out"), "--strict", "--summary", str(summary)])
    assert json.loads(summary.read_text())["status"] == "completed"
    assert f"Summary written to {summary}" in capsys.readouterr().out


def test_step_counts_exchanges_with_a_changed_value():
    step = StepLog("x", "patch", "", "", Provenance("Ann Author"))
    step.record(
        DatasetRef("a.xml", 1, "A", "CH"),
        [
            Change("flowData/exchange[1]/@CASNumber", None, "000050-00-0"),
            Change("flowData/exchange[1]/extensions/@brightwayMatch", None, "exactMatch"),
            Change("flowData/exchange[12]/@location", "CH", "RER"),
            Change("extensions/@maintenance", None, "not maintained"),
            Change("metaInformation/processInformation/dataSetInformation/@type", "1", "2"),
        ],
    )
    step.record(DatasetRef("b.xml", 2, "B", "CH"), [Change("flowData/exchange/@unit", "a", "b")])
    step.record(DatasetRef("c.xml", 3, "C", "CH"), [])
    assert (step.datasets, step.exchanges, step.changes) == (2, 3, 6)
