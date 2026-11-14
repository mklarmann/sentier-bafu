"""What a patch needs to be registered, and what holds for the patches that are."""

import importlib.util
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


def _records() -> set[str]:
    """The ids of all findings: one record each, `community/findings/<n // 1000>/F<n>.json`."""
    return {p.stem for p in (REPO / "community" / "findings").rglob("F*.json")}


def test_findings_of_the_patches_have_a_record():
    known = _records()
    assert known
    for p in available_patches():
        assert set(p.provenance.findings) <= known, p.id


def _snapshot():
    """`scripts/patches_snapshot.py`, which writes the list of patches the site reads."""
    spec = importlib.util.spec_from_file_location(
        "patches_snapshot", REPO / "scripts" / "patches_snapshot.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_list_of_patches_the_site_reads_is_what_the_registry_gives(capsys):
    """`community/patches.json` is written from the registry and never kept by hand."""
    snapshot = _snapshot()
    wanted, how = snapshot.expected(REPO)
    assert how == snapshot.IMPORTED  # these tests run where the tool is installed
    committed = json.loads((REPO / "community" / "patches.json").read_text(encoding="utf-8"))
    assert snapshot.differences(committed, wanted) == []
    assert [p["id"] + "-" + p["slug"] for p in committed["patches"]] == [
        p.id for p in available_patches()
    ]
    capsys.readouterr()


def test_the_registry_reads_the_same_from_the_tool_its_listing_and_the_source(capsys):
    """The records are checked without the tool, from the source of the patch modules."""
    snapshot = _snapshot()
    main(["list", "--json"])
    printed = capsys.readouterr().out
    from_listing, _ = snapshot.expected(REPO, printed)
    from_tool, _ = snapshot.expected(REPO)
    config = json.loads((REPO / "site" / "config.json").read_text(encoding="utf-8"))
    from_source = snapshot.snapshot(
        snapshot.from_source(REPO), config["repository"], config.get("source_ref", "main")
    )
    assert from_listing == from_tool == from_source
    # who reported and who confirmed stay in the registry
    for step in json.loads(printed):
        for name in (step["reported_by"], step["confirmed_by"]):
            if name and name not in (step["authored_by"], step["authorised_by"]):
                assert name not in json.dumps(from_tool, ensure_ascii=False)


def test_list_shows_the_findings(capsys):
    main(["list"])
    lines = capsys.readouterr().out.splitlines()
    assert any(re.fullmatch(r"  0001-straw.*\t\[Chris Mutel\]\tF1", line) for line in lines)
    assert any(re.fullmatch(r"  0004-flow-.*\t\[Chris Mutel\]\tno finding", line) for line in lines)


def test_list_as_json_is_the_one_place_other_tools_read(capsys):
    main(["list", "--json"])
    listing = json.loads(capsys.readouterr().out)
    assert [step["kind"] for step in listing].count("patch") == len(available_patches())
    strawberry = next(step for step in listing if step["id"].startswith("0001-"))
    assert strawberry["findings"] == ["F1"]
    assert strawberry["authorised_by"] == "Chris Mutel"
    assert strawberry["references"][0].endswith("/sentier-bafu/issues/6")
    assert all((REPO / step["source"]).is_file() for step in listing)
    assert strawberry["source"].endswith("/patches/p0001_strawberry_polyethylene_disposal.py")
