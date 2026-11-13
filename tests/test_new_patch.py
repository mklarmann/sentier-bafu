"""Starting a new patch (`scripts/new_patch.py`)."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from bafu_community_fixes import registry

REPO = Path(__file__).parents[1]
SCRIPT = REPO / "scripts" / "new_patch.py"
ISSUES = "https://github.com/example/repo/issues"
LEDGER = f"""# Findings

| ID | What | Datasets | Release | Status | Links |
|---|---|---|---|---|---|
| F3 | Locations | 573961 | 2026 v1 | open | [#8]({ISSUES}/8) |
| F14 | Wind | 584039 | 2026 v1 | open | [#29]({ISSUES}/29) · [#8]({ISSUES}/8) |
"""


@pytest.fixture(scope="module")
def new_patch():
    spec = importlib.util.spec_from_file_location("new_patch", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def root(tmp_path):
    """A checkout with two patches and a ledger."""
    patches = tmp_path / "src" / "bafu_community_fixes" / "patches"
    patches.mkdir(parents=True)
    for name in ("__init__.py", "p0001_first.py", "p0011_latest.py"):
        (patches / name).touch()
    for name in ("__init__.py", "pipeline.py", "registry.py", "xml.py"):
        (patches.parent / name).touch()  # so the linter sees the package as this project's
    (tmp_path / "tests").mkdir()
    (tmp_path / "community").mkdir()
    (tmp_path / "community" / "findings.md").write_text(LEDGER)
    return tmp_path


def test_scaffold_takes_the_next_number_and_the_findings_links(new_patch, root):
    patch_file, test_file = new_patch.scaffold(root, "storage-pump-wind", "F14", "Jane Doe")
    assert patch_file == (
        root / "src" / "bafu_community_fixes" / "patches" / "p0012_storage_pump_wind.py"
    )
    assert test_file == root / "tests" / "test_p0012_storage_pump_wind.py"
    source = patch_file.read_text()
    assert 'ID = "0012-storage-pump-wind"' in source
    assert 'findings=("F14",),' in source
    assert 'authored_by="Jane Doe",' in source
    assert "authorised_by=" not in source  # approval is someone else's to add
    assert (
        "    references=(\n"
        '        "https://github.com/example/repo/issues/29",\n'
        '        "https://github.com/example/repo/issues/8",\n'
        "    ),\n"
    ) in source
    assert "from bafu_community_fixes.patches.p0012_storage_pump_wind import ID" in (
        test_file.read_text()
    )
    assert new_patch.next_number(root) == 13


def test_scaffold_prefers_the_finding_record(new_patch, root):
    (root / "community" / "findings").mkdir()
    record = {"id": "F14", "links": ["https://github.com/example/repo/issues/99"]}
    (root / "community" / "findings" / "F14.json").write_text(json.dumps(record))
    patch_file, _ = new_patch.scaffold(root, "storage-pump-wind", "F14", "Jane Doe")
    assert '"https://github.com/example/repo/issues/99",' in patch_file.read_text()
    assert "issues/29" not in patch_file.read_text()


def test_scaffold_without_a_finding(new_patch, root):
    patch_file, _ = new_patch.scaffold(root, "pad-numbers", None, 'Jane "JD" Doe')
    source = patch_file.read_text()
    assert "    findings=(),\n" in source
    assert "    references=(),\n" in source
    assert 'authored_by="Jane \\"JD\\" Doe",' in source


@pytest.mark.parametrize(
    ("name", "finding", "message"),
    [
        ("storage-pump-wind", "F99", "no finding F99 in the ledger"),
        ("storage-pump-wind", "F1", "no finding F1 in the ledger"),  # F14 isn't F1
        ("storage-pump-wind", "14", "looks like 'F14'"),
        ("Storage_Pump", "F14", "must look like 'storage-pump-wind'"),
        ("0012-storage", "F14", None),  # allowed, if odd
    ],
)
def test_scaffold_checks_its_input(new_patch, root, name, finding, message):
    if message is None:
        new_patch.scaffold(root, name, finding, "Jane Doe")
        return
    with pytest.raises(new_patch.ScaffoldError, match=message):
        new_patch.scaffold(root, name, finding, "Jane Doe")
    assert new_patch.next_number(root) == 12  # nothing was written


def test_new_patch_is_valid_but_fails_until_it_is_written(new_patch, root, db, monkeypatch):
    patch_file, test_file = new_patch.scaffold(root, "storage-pump-wind", "F14", "Jane Doe")
    monkeypatch.setattr(registry, "_REGISTRY", {})
    exec(compile(patch_file.read_text(), str(patch_file), "exec"), {})
    (patch,) = registry._REGISTRY.values()
    assert patch.id == "0012-storage-pump-wind"
    assert patch.provenance.findings == ("F14",)
    assert patch.provenance.authorised_by is None
    assert patch.description.startswith("TODO")  # which `test_registry` doesn't let through
    with pytest.raises(NotImplementedError, match="0012-storage-pump-wind"):
        patch(db)
    compile(test_file.read_text(), str(test_file), "exec")


def test_new_patch_passes_the_linter(new_patch, root):
    files = new_patch.scaffold(root, "storage-pump-wind", "F14", "Jane Doe")
    config = ["--config", str(REPO / "pyproject.toml"), *map(str, files)]
    for command in (["check"], ["format", "--check"]):
        result = subprocess.run(
            [sys.executable, "-m", "ruff", *command, *config],
            cwd=root,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr


def test_command_line(new_patch, root, monkeypatch, capsys):
    monkeypatch.setattr(new_patch, "ROOT", root)
    assert new_patch.main(["storage-pump-wind", "--finding", "F14", "--author", "Jane Doe"]) == 0
    out = capsys.readouterr().out
    assert "Created src/bafu_community_fixes/patches/p0012_storage_pump_wind.py" in out
    assert "Created tests/test_p0012_storage_pump_wind.py" in out
    with pytest.raises(SystemExit, match="no finding F99"):
        new_patch.main(["other", "--finding", "F99", "--author", "Jane Doe"])
    with pytest.raises(SystemExit):  # a finding, or the statement that there is none
        new_patch.main(["other", "--author", "Jane Doe"])
