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


@pytest.fixture(autouse=True)
def _not_on_github(monkeypatch):
    """A test says itself when it runs "on GitHub".

    A runner sets `GITHUB_ACTIONS`, and the script then writes its errors as annotations
    (`::error …`); the tests that read `error: …` failed there and nowhere else.
    """
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)


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
        id: Patch(
            id, "Change something", func, Provenance("Ann Author", authorised_by, findings=("F7",))
        )
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
        "| `0001-one` | patch | F7 | Ann Author | Olga Owner | 1 | 1 | 1 "
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
    assert "| `0001-stops` | patch | F7 | Ann Author | Olga Owner | stopped |" in out
    assert "Patched copy: nothing written" in out
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
    assert "- The patched copy **changes**: fingerprint `" in out
    assert "- Files of the patched copy that differ: **1** of 1; new: 0;" in out
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


def test_pull_request_whose_new_patch_stops(table, summarise, capsys):
    base = summarise("base", {"0001-one": (_lognormal, "Olga Owner")})
    head = summarise("head", {"0001-one": (_lognormal, "Olga Owner"), "0002-stops": (_stops, None)})
    assert table.main([str(head), "--base", str(base), "--check"]) == 1
    out = capsys.readouterr().out
    assert "- This revision's run failed, so steps after the one that stopped are missing" in out
    assert "| `0002-stops` | new, stopped | – | – | – |" in out
    assert "\n\n\n" not in out


def test_pull_request_that_changes_nothing_in_the_release(table, summarise, capsys):
    base = summarise("base", {"0001-one": (_lognormal, "Olga Owner")})
    head = summarise("head", {"0001-one": (_lognormal, "Olga Owner")})
    assert table.main([str(head), "--base", str(base)]) == 0
    out = capsys.readouterr().out
    assert "- The patched copy is **byte for byte the same** as before" in out
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


# --- What each patch matched, against an earlier run -----------------------------------


def _with_counts(path, id, **counts):
    summary = json.loads(path.read_text())
    next(s for s in summary["steps"] if s["id"] == id).update(counts)
    path.write_text(json.dumps(summary))
    return path


def test_every_patch_is_listed_with_what_it_matched_before(table, summarise, capsys):
    base = summarise("base", {"0001-one": (_lognormal, "O"), "0002-two": (_mean_value, "O")})
    head = summarise("head", {"0001-one": (_lognormal, "O"), "0002-two": (_mean_value, "O")})
    assert table.main([str(head), "--base", str(base), "--check"]) == 0
    out = capsys.readouterr().out
    assert "### What each patch matched" in out
    assert "| `0001-one` | 1 | 1 | 1 | 1 | 1 | 1 | as before |" in out
    assert "| `0002-two` | 1 | 1 | 1 | 1 | 1 | 1 | as before |" in out
    assert "[!CAUTION]" not in out and "[!WARNING]" not in out


def test_patch_whose_matches_fell_to_zero_fails_and_says_what_it_matched_before(
    table, summarise, capsys
):
    base = summarise("base", {"0001-one": (_lognormal, "O"), "0002-two": (_mean_value, "O")})
    head = summarise("head", {"0001-one": (_lognormal, "O"), "0002-two": (_nothing, "O")})
    assert table.main([str(head), "--base", str(base), "--check"]) == 1
    captured = capsys.readouterr()
    assert "> [!CAUTION]\n> - `0002-two` changed nothing on the full release" in captured.out
    assert "it changed 1 dataset(s)." in captured.out
    assert "| `0002-two` | 0 | 0 | 0 | 1 | 1 | 1 | **matched nothing** |" in captured.out
    assert "error: 0002-two changed nothing on the full release" in captured.err


def test_patch_that_matched_fewer_than_before_is_a_warning(table, summarise, capsys):
    base = summarise("base", {"0001-one": (_lognormal, "O")})
    _with_counts(base, "0001-one", datasets=25, exchanges=25, changes=25)
    head = summarise("head", {"0001-one": (_lognormal, "O")})
    _with_counts(head, "0001-one", datasets=24, exchanges=24, changes=24)
    assert table.main([str(head), "--base", str(base), "--check"]) == 0  # said, not failed
    out = capsys.readouterr().out
    assert (
        "> [!WARNING]\n> - `0001-one` changed 24 dataset(s), 24 exchange(s) and 24 value(s);" in out
    )
    assert "it changed 25, 25 and 25." in out
    assert "| `0001-one` | 24 | 24 | 24 | 25 | 25 | 25 | **fewer than before** |" in out


def test_counts_are_compared_with_the_manifest_of_the_previous_release(
    table, summarise, tmp_path, capsys
):
    head = summarise("head", {"0001-one": (_lognormal, "O"), "0003-new": (_mean_value, "O")})
    fingerprint = json.loads(head.read_text())["release"]["fingerprint"]
    manifest = {
        "tag": "patched-2026-v1.1",
        "provider_release": {"fingerprint": fingerprint},
        "patches": [
            {"id": "0001-one", "datasets_changed": 1, "exchanges_changed": 1, "values_changed": 1},
            {"id": "0002-gone", "datasets_changed": 3, "exchanges_changed": 3, "values_changed": 3},
        ],
    }
    previous = tmp_path / "previous.json"
    previous.write_text(json.dumps(manifest))
    matches = tmp_path / "nested" / "matches.json"
    arguments = [str(head), "--previous", str(previous), "--matches-out", str(matches), "--check"]
    assert table.main(arguments) == 0
    out = capsys.readouterr().out
    assert "beside its counts in the build tagged patched-2026-v1.1 on the provider release" in out
    assert "| `0001-one` | 1 | 1 | 1 | 1 | 1 | 1 | as before |" in out
    assert "| `0003-new` | 1 | 1 | 1 | – | – | – | new |" in out
    assert "`0002-gone` ran in the build tagged patched-2026-v1.1" in out
    check = json.loads(matches.read_text())
    assert check["failures"] == []
    assert [row["result"] for row in check["patches"]] == ["as before", "new"]
    assert check["patches"][0] == {
        "id": "0001-one",
        "now": {"datasets": 1, "exchanges": 1, "changes": 1},
        "previous": {"datasets": 1, "exchanges": 1, "changes": 1},
        "result": "as before",
    }


def test_without_an_earlier_run_a_patch_is_only_checked_for_matching_nothing(
    table, summarise, tmp_path, capsys
):
    head = summarise("head", {"0001-one": (_lognormal, "O")})
    assert table.main([str(head), "--previous", str(tmp_path / "none.json"), "--check"]) == 0
    out = capsys.readouterr().out
    assert "There is no earlier run to compare with" in out
    assert "| `0001-one` | 1 | 1 | 1 | – | – | – | no earlier run |" in out
    assert "No earlier run at `none.json`" in out


def test_a_test_release_may_be_unknown_and_leave_patches_without_a_target(
    table, summarise, monkeypatch, capsys
):
    monkeypatch.delitem(download.FINGERPRINTS, URL)
    head = summarise("head", {"0001-one": (_lognormal, "O"), "0002-none": (_nothing, "O")})
    assert table.main([str(head), "--check"]) == 1
    capsys.readouterr()
    assert table.main([str(head), "--check", "--partial"]) == 0
    out = capsys.readouterr().out
    assert "[!CAUTION]" not in out
    assert "These patches found nothing to change in it: `0002-none`." in out
    assert "| `0002-none` | 0 | 0 | 0 | – | – | – | **matched nothing** |" in out
