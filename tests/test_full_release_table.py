"""The table CI writes from run summaries (`scripts/full_release_table.py`)."""

import contextlib
import copy
import importlib.util
import json
from pathlib import Path

import pytest

from bafu_community_fixes import download, registry
from bafu_community_fixes.changes import Provenance
from bafu_community_fixes.models import UncertaintyType
from bafu_community_fixes.pipeline import run
from bafu_community_fixes.registry import Patch

SCRIPT = Path(__file__).parents[1] / "scripts" / "full_release_table.py"
URL = "https://example.org/release-v1.zip"


@pytest.fixture(scope="module")
def table():
    spec = importlib.util.spec_from_file_location("full_release_table", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _lognormal(db):
    for dataset in db:
        dataset.exchanges[0].uncertainty_type = UncertaintyType.LOGNORMAL


def _mean_value(db):
    for dataset in db:
        dataset.exchanges[2].mean_value = 2.5


def _nothing(db):
    pass


def _stops(db):
    raise ValueError("Dataset 100: expected 1.5 kg, found 2.5")


@pytest.fixture
def summarise(raw_bafu, tmp_path, monkeypatch):
    """Run the fixture with only the given patches, as a known release; return the summary."""
    fingerprint = json.loads(_summary(raw_bafu, tmp_path / "probe", monkeypatch, {}).read_text())
    monkeypatch.setitem(download.FINGERPRINTS, URL, fingerprint["release"]["fingerprint"])
    monkeypatch.setitem(download.CHECKSUMS, URL, "c" * 64)

    def summarise(name, patches):
        return _summary(raw_bafu, tmp_path / name, monkeypatch, patches)

    return summarise


def _summary(raw_bafu, folder, monkeypatch, patches):
    registered = {
        id: Patch(id, "Change something", func, Provenance("Ann Author", authorised_by))
        for id, (func, authorised_by) in patches.items()
    }
    monkeypatch.setattr(registry, "_REGISTRY", registered)
    monkeypatch.setattr(registry, "available_patches", lambda: list(registered.values()))
    from bafu_community_fixes import pipeline

    monkeypatch.setattr(pipeline, "available_patches", lambda: list(registered.values()))
    with contextlib.suppress(ValueError):  # the summary is written even if a patch stops
        run(raw_bafu, folder / "out", xsd_check="every-step", summary=folder / "summary.json")
    return folder / "summary.json"


def test_table_of_a_good_run(table, summarise, capsys):
    head = summarise("head", {"0001-one": (_lognormal, "Olga Owner")})
    assert table.main([str(head), "--check", "--head-revision", "a" * 40]) == 0
    out = capsys.readouterr().out
    assert "**Completed** on `release-v1`: 1 datasets and 3 exchanges in 1 files." in out
    assert "archive SHA-256 `cccccccccccc…`" in out
    assert "revision `aaaaaaaaaaaa`" in out
    assert "after import and after every patch" in out
    assert (
        "| `0001-one` | patch | – | Ann Author | Olga Owner | 1 | 1 | 1 "
        "| `exchange/@uncertaintyType` (1) |"
    ) in out
    assert "| `location-codes` | import fix |" in out
    assert "[!CAUTION]" not in out and "[!WARNING]" not in out
    assert "What this pull request changes" not in out


def test_unauthorised_patch_is_a_warning_not_an_error(table, summarise, capsys):
    head = summarise("head", {"0001-one": (_lognormal, None)})
    assert table.main([str(head), "--check"]) == 0
    out = capsys.readouterr().out
    assert "> [!WARNING]\n> - `0001-one` is not yet authorised, and changed 1 dataset(s)." in out
    assert "| **not yet authorised** |" in out


def test_patch_that_changes_nothing_fails_the_check(table, summarise, capsys):
    head = summarise("head", {"0001-none": (_nothing, "Olga Owner")})
    assert table.main([str(head)]) == 0  # without --check, it only says so
    assert table.main([str(head), "--check"]) == 1
    captured = capsys.readouterr()
    assert "> - `0001-none` changed nothing on the full release: its target wasn't" in captured.out
    assert "error: 0001-none changed nothing on the full release" in captured.err


def test_patch_whose_target_is_not_as_expected_fails_the_check(table, summarise, capsys):
    head = summarise("head", {"0001-stops": (_stops, "Olga Owner"), "0002-x": (_lognormal, None)})
    assert table.main([str(head), "--check"]) == 1
    out = capsys.readouterr().out
    assert "**Failed** on `release-v1`" in out
    assert (
        "> - `0001-stops` stopped the run; its target was not as expected, or it left "
        "invalid data: Dataset 100: expected 1.5 kg, found 2.5"
    ) in out
    assert "| `0001-stops` | patch | – | Ann Author | Olga Owner | stopped |" in out
    assert "Patched release: nothing written" in out
    assert "0002-x" not in out  # the run never got there


def test_unknown_release_fails_the_check(table, summarise, monkeypatch, capsys):
    monkeypatch.delitem(download.FINGERPRINTS, URL)
    head = summarise("head", {"0001-one": (_lognormal, "Olga Owner")})
    assert table.main([str(head), "--check"]) == 1
    out = capsys.readouterr().out
    assert "**Completed** on an unknown input" in out
    assert "The input isn't a release this revision knows" in out


def test_pull_request_that_adds_a_patch(table, summarise, tmp_path, capsys):
    base = summarise("base", {"0001-one": (_lognormal, "Olga Owner")})
    head = summarise(
        "head", {"0001-one": (_lognormal, "Olga Owner"), "0002-two": (_mean_value, None)}
    )
    arguments = [str(head), "--base", str(base), "--base-revision", "b" * 40, "--check"]
    outputs = ["--head-output", str(head.parent / "out"), "--base-output", str(base.parent / "out")]
    assert table.main(arguments + outputs) == 0
    out = capsys.readouterr().out
    assert "Compared with a run of the base revision (`bbbbbbbbbbbb`)" in out
    assert "- The patched release **changes**: fingerprint `" in out
    assert "- Files of the patched release that differ: **1** of 1; new: 0;" in out
    assert "  - Differ: `raw_bafu.xml`" in out
    assert "| `0002-two` | new | +1 | +1 | +1 |" in out
    assert "0001-one` | changed" not in out


def test_pull_request_that_changes_and_removes_patches(table, summarise, capsys):
    base = summarise("base", {"0001-one": (_lognormal, "O"), "0002-two": (_mean_value, "O")})
    head_file = summarise("head", {"0001-one": (_lognormal, "O")})
    head = json.loads(head_file.read_text())
    next(s for s in head["steps"] if s["id"] == "0001-one")["exchanges"] = 1234
    head_file.write_text(json.dumps(head))
    assert table.main([str(head_file), "--base", str(base)]) == 0
    out = capsys.readouterr().out
    assert "| `0001-one` | changed | 1 | 1 → 1,234 (+1,233) | 1 |" in out
    assert "| `0002-two` | removed | −1 | −1 | −1 |" in out


def test_pull_request_that_changes_nothing_in_the_release(table, summarise, capsys):
    base = summarise("base", {"0001-one": (_lognormal, "Olga Owner")})
    head = summarise("head", {"0001-one": (_lognormal, "Olga Owner")})
    assert table.main([str(head), "--base", str(base)]) == 0
    out = capsys.readouterr().out
    assert "- The patched release is **byte for byte the same** as before" in out
    assert "No step is new or removed, and every step changes as much as before." in out


def test_base_without_a_summary(table, summarise, tmp_path, capsys):
    head = summarise("head", {"0001-one": (_lognormal, "Olga Owner")})
    assert table.main([str(head), "--base", str(tmp_path / "missing.json"), "--check"]) == 0
    assert "has no run summary, so there is nothing to compare" in capsys.readouterr().out


def test_base_that_read_another_release(table, summarise, capsys):
    head_file = summarise("head", {"0001-one": (_lognormal, "Olga Owner")})
    base = copy.deepcopy(json.loads(head_file.read_text()))
    base["release"].update(url=None, fingerprint="d" * 64)
    base_file = head_file.parent / "base.json"
    base_file.write_text(json.dumps(base))
    assert table.main([str(head_file), "--base", str(base_file)]) == 0
    out = capsys.readouterr().out
    assert "**The input differs.** The base revision read an unknown input" in out


def test_no_summary_at_all(table, tmp_path, capsys):
    assert table.main([str(tmp_path / "missing.json"), "--check"]) == 1
    assert "the run didn't get as far as writing one" in capsys.readouterr().out


def test_appends_to_a_file_and_annotates_on_github(table, summarise, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    head = summarise("head", {"0001-none": (_nothing, "Olga Owner")})
    out = tmp_path / "step-summary.md"
    out.write_text("earlier content\n")
    assert table.main([str(head), "--out", str(out), "--check"]) == 1
    assert out.read_text().startswith("earlier content\n## Full release run\n")
    assert capsys.readouterr().out.startswith(
        "::error title=Full release run::0001-none changed nothing on the full release"
    )
