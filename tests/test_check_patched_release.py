"""Checking the written files (`scripts/check_patched_release.py`)."""

import importlib.util
from pathlib import Path

import pytest

from bafu_community_fixes.pipeline import run

SCRIPT = Path(__file__).parents[1] / "scripts" / "check_patched_release.py"


@pytest.fixture(scope="module")
def checker():
    spec = importlib.util.spec_from_file_location("check_patched_release", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def release(raw_bafu, tmp_path):
    run(raw_bafu, tmp_path / "out", summary=tmp_path / "summary.json")
    return tmp_path


def test_written_release_is_valid(checker, release, capsys):
    arguments = [str(release / "out"), "--summary", str(release / "summary.json")]
    assert checker.main(arguments) == 0
    assert capsys.readouterr().out == (
        "1 files checked: all are valid EcoSpold 1 and are the ones the summary describes\n"
    )
    assert checker.main([str(release / "out")]) == 0


def test_file_that_breaks_the_schema(checker, release, capsys):
    path = release / "out" / "raw_bafu.xml"
    path.write_text(path.read_text().replace(' unit="kWh"', "", 1))
    assert checker.main([str(release / "out")]) == 1
    out = capsys.readouterr().out
    assert "raw_bafu.xml: line " in out and "unit" in out
    assert "1 files checked: not a valid patched copy" in out


def test_files_that_are_not_the_ones_in_the_summary(checker, release, capsys):
    path = release / "out" / "raw_bafu.xml"
    path.write_text(path.read_text() + "\n")  # still valid, but not what the run wrote
    assert checker.main([str(release / "out"), "--summary", str(release / "summary.json")]) == 1
    assert "are not the ones summary.json describes" in capsys.readouterr().out


def test_summary_of_a_run_that_wrote_nothing(checker, release):
    summary = release / "summary.json"
    summary.write_text(summary.read_text().replace('"output": {', '"output": null, "was": {'))
    assert checker.check(release / "out", summary)[1] == [
        "summary.json describes a run that wrote nothing"
    ]
