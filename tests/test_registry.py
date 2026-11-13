"""What a patch needs to be registered, and what holds for the patches that are."""

import json
import re
from pathlib import Path

import pytest

from bafu_community_fixes import patches as patches_package
from bafu_community_fixes import registry
from bafu_community_fixes.cli import main
from bafu_community_fixes.registry import available_patches, patch

REPO = Path(__file__).parents[1]


@pytest.fixture
def empty_registry(monkeypatch):
    available_patches()  # import the real patches first, so they don't register again here
    monkeypatch.setattr(registry, "_REGISTRY", {})
    return registry._REGISTRY


def _func(db):
    """Do something."""


def test_patch_must_name_its_findings(empty_registry):
    with pytest.raises(TypeError, match="findings"):
        patch("0001-test", authored_by="Ann Author")(_func)
    assert empty_registry == {}


def test_findings_are_recorded(empty_registry):
    patch("0001-test", findings=("F1", "F14"), authored_by="Ann Author")(_func)
    assert empty_registry["0001-test"].provenance.findings == ("F1", "F14")


def test_patch_without_a_finding_says_so(empty_registry):
    patch("0001-test", findings=(), authored_by="Ann Author")(_func)
    assert empty_registry["0001-test"].provenance.findings == ()


@pytest.mark.parametrize("findings", [("14",), ("F0",), ("f14",), "F14", ("F14", "issue 29")])
def test_findings_must_be_ids(empty_registry, findings):
    with pytest.raises(ValueError, match="findings must be ids like"):
        patch("0001-test", findings=findings, authored_by="Ann Author")(_func)
    assert empty_registry == {}


@pytest.mark.parametrize("id", ["1-test", "0001_test", "0001-Test", "0001-", "test"])
def test_patch_id_must_be_a_number_and_a_name(empty_registry, id):
    with pytest.raises(ValueError, match="must look like '0012-short-name'"):
        patch(id, findings=(), authored_by="Ann Author")(_func)


def test_two_patches_cannot_have_the_same_number(empty_registry):
    patch("0012-one", findings=(), authored_by="Ann Author")(_func)
    with pytest.raises(ValueError, match="Patch 0012-two has the same number as 0012-one"):
        patch("0012-two", findings=(), authored_by="Ann Author")(_func)
    assert list(empty_registry) == ["0012-one"]


def test_every_patch_module_registers_the_patch_its_name_says():
    """A patch is registered by being in the folder; its file is named after its id."""
    folder = Path(patches_package.__file__).parent
    modules = sorted(p.stem for p in folder.glob("*.py") if p.stem != "__init__")
    registered = {p.func.__module__.rsplit(".", 1)[1]: p.id for p in available_patches()}
    assert sorted(registered) == modules
    assert registered == {"p" + id.replace("-", "_"): id for id in registered.values()}


def test_no_patch_is_left_as_a_template():
    for p in available_patches():
        assert "TODO" not in p.description + p.rationale, p.id


def _ledger() -> set[str]:
    """The ids of all findings: one record each, or a row in the ledger."""
    records = {p.stem for p in (REPO / "community" / "findings").glob("F*.json")}
    ledger = (REPO / "community" / "findings.md").read_text(encoding="utf-8")
    return records | set(re.findall(r"(?m)^\| (F\d+) \|", ledger))


def test_findings_of_the_patches_are_in_the_ledger():
    known = _ledger()
    assert known
    for p in available_patches():
        assert set(p.provenance.findings) <= known, p.id


def test_findings_of_the_patches_agree_with_the_reconciliation():
    """The receipt of 21 October lists patches and findings by hand; the patches now say it."""
    reconciliation = json.loads((REPO / "community" / "reconciliation.json").read_text())
    listed = {entry["id"]: tuple(entry["findings"]) for entry in reconciliation["patches"]}
    declared = {p.id: p.provenance.findings for p in available_patches()}
    assert len(listed) == 11
    assert {id: declared[id] for id in listed} == listed


def test_list_shows_the_findings(capsys):
    main(["list"])
    lines = capsys.readouterr().out.splitlines()
    assert any(re.fullmatch(r"  0001-straw.*\t\[Chris Mutel\]\tF1", line) for line in lines)
    assert any(re.fullmatch(r"  0004-flow-.*\t\[Chris Mutel\]\tno finding", line) for line in lines)
