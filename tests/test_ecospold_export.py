"""The patched copy as ecoSpold v1 files again (`scripts/release_build/ecospold_export.py`).

The files come from a real patch run over the fixture, so these tests cover the path from
the patch tool's writer through the label to the read-back, and back into the patch tool's
own reader.
"""

import importlib.util
import json
import shutil
import zipfile
from pathlib import Path

import pytest

from bafu_community_fixes import xml
from bafu_community_fixes.compliance import schema
from bafu_community_fixes.pipeline import run
from bafu_community_fixes.summary import fingerprint

SCRIPT = Path(__file__).parents[1] / "scripts" / "release_build" / "ecospold_export.py"
MARK = "Modified Data"
CREDIT = "Life Cycle Inventory database of the Made-up Administration, MADE:2026"
MEMBERS = {"MODIFICATIONS.json": b'{"steps": []}\n', "NOTICE.txt": b"Modified Data.\n"}


@pytest.fixture(scope="module")
def step():
    spec = importlib.util.spec_from_file_location("ecospold_export", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def note(code):
    return f"{MARK}: part of a patched copy, not the original. Dataset {code}. Source: {CREDIT}."


@pytest.fixture
def patched(raw_bafu, tmp_path):
    """A patched copy of two datasets, as a patch run wrote it, with its summary."""
    source = tmp_path / "source"
    source.mkdir()
    for code in ("aaa", "bbb"):
        shutil.copy(raw_bafu, source / f"process_{code}.xml")
    run(source, tmp_path / "patched", summary=tmp_path / "summary.json")
    return tmp_path


def pack(step, patched, **changes):
    summary = json.loads((patched / "summary.json").read_text())["output"]
    options = {
        "notes": {code: note(code) for code in ("aaa", "bbb")},
        "mark": MARK,
        "credit": CREDIT,
        "members": MEMBERS,
    } | changes
    archive = patched / "copy-ecospold1.zip"
    stats = step.write(
        patched / "patched",
        archive,
        expected=(summary["files"], summary["fingerprint"]),
        **options,
    )
    return archive, stats, options


def rewrite(archive, change):
    """The archive again, with `change(name, data)` deciding what each member holds."""
    with zipfile.ZipFile(archive) as old:
        members = {name: old.read(name) for name in old.namelist()}
    with zipfile.ZipFile(archive, "w") as new:
        for name, data in members.items():
            data = change(name, data)
            if data is not None:
                new.writestr(name, data)


def test_the_archive_holds_every_patched_file_with_its_label_and_reads_back(step, patched):
    archive, stats, options = pack(step, patched)
    with zipfile.ZipFile(archive) as packed:
        assert sorted(packed.namelist()) == [
            "MODIFICATIONS.json",
            "NOTICE.txt",
            "process_aaa.xml",
            "process_bbb.xml",
        ]
        text = packed.read("process_aaa.xml").decode()
    assert f'generalComment="{note("aaa")}&#10;&#10;Some comment. Engine power: 5 kW."' in text
    assert f'<bcf:dataset label="{MARK}" credit="{CREDIT}">' in text
    assert "<bcf:importFix>location-codes</bcf:importFix>" in text  # what changed it stays
    assert stats["files"] == stats["datasets"] == 2
    assert step.check(archive, patched / "patched", **options) == []


def test_the_fingerprint_is_the_one_the_patch_tool_computes(step, patched):
    _, stats, _ = pack(step, patched)
    files = sorted((patched / "patched").glob("*.xml"))
    assert stats["fingerprint_before_the_label"] == fingerprint(patched / "patched", files)[0]
    assert stats["bytes_before_the_label"] == sum(file.stat().st_size for file in files)


def test_with_the_label_taken_off_a_file_is_byte_for_byte_what_the_patch_run_wrote(step, patched):
    archive, _, options = pack(step, patched)
    with zipfile.ZipFile(archive) as packed:
        root = step._parse(packed.read("process_bbb.xml"))
    assert step.unlabel(root, note("bbb"), MARK, CREDIT) == []
    assert step.serialise(root) == (patched / "patched" / "process_bbb.xml").read_bytes()


def test_the_patch_tool_reads_a_labelled_copy_and_writes_it_back_unchanged(step, patched, tmp_path):
    archive, _, _ = pack(step, patched)
    with zipfile.ZipFile(archive) as packed:
        packed.extractall(tmp_path / "unpacked")
    db = xml.load(tmp_path / "unpacked")
    assert {(dataset.ext.label, dataset.ext.credit) for dataset in db} == {(MARK, CREDIT)}
    assert all(dataset.ext.import_fixes for dataset in db)
    for doc in db.documents.values():
        assert schema().validate(xml.to_tree(doc))
    xml.write(db, tmp_path / "again")
    for name in ("process_aaa.xml", "process_bbb.xml"):
        assert (tmp_path / "again" / name).read_bytes() == (
            tmp_path / "unpacked" / name
        ).read_bytes()


def test_a_patch_run_writes_no_label(patched):
    text = (patched / "patched" / "process_aaa.xml").read_text()
    assert "label=" not in text and "credit=" not in text


def test_a_dataset_without_comment_or_extension_gets_both_and_loses_them_again(step):
    plain = (
        f'<ecoSpold xmlns="{step.ECOSPOLD_NS}"><dataset number="1"><metaInformation>'
        '<processInformation><referenceFunction name="made up"/></processInformation>'
        "</metaInformation><flowData/></dataset></ecoSpold>"
    ).encode()
    root = step._parse(plain)
    step.label(root, "The note.", MARK, CREDIT)
    text = step.serialise(root).decode()
    assert 'generalComment="The note."' in text
    assert f'<bcf:dataset label="{MARK}" credit="{CREDIT}"/>' in text
    assert step.unlabel(root, "The note.", MARK, CREDIT) == []
    assert step.canonical(root) == step.canonical(step._parse(plain))


def test_the_same_files_give_the_same_archive(step, patched):
    first = pack(step, patched)[0].read_bytes()
    assert pack(step, patched)[0].read_bytes() == first


@pytest.mark.parametrize(
    ("old", "new", "said"),
    [
        ('meanValue="3.2"', 'meanValue="3.3"', "differs from the file the patch run wrote"),
        (f' label="{MARK}"', ' label="Original"', "the extension lacks the label or the credit"),
        (f' credit="{CREDIT}"', "", "the extension lacks the label or the credit"),
        (f"{MARK}: part of", "Part of", "does not begin with the note of this dataset"),
        (' unit="kWh" category', " category", "not valid EcoSpold 1"),
        ("<bcf:importFix>location-codes</bcf:importFix>", "", "differs from the file"),
    ],
)
def test_the_read_back_finds_a_file_that_was_changed(step, patched, old, new, said):
    archive, _, options = pack(step, patched)

    def change(name, data):
        if name != "process_aaa.xml":
            return data
        assert old.encode() in data
        return data.replace(old.encode(), new.encode(), 1)

    rewrite(archive, change)
    problems = step.check(archive, patched / "patched", **options)
    assert problems and all(problem.startswith("process_aaa.xml: ") for problem in problems)
    assert any(said in problem for problem in problems)


def test_the_read_back_finds_a_missing_file_a_stray_one_and_a_changed_record(step, patched):
    archive, _, options = pack(step, patched)

    def change(name, data):
        if name == "process_bbb.xml":
            return None
        return b"other\n" if name == "NOTICE.txt" else data

    rewrite(archive, change)
    with zipfile.ZipFile(archive, "a") as packed:
        packed.writestr("left-over.txt", b"")
    problems = step.check(archive, patched / "patched", **options)
    assert "NOTICE.txt: not the one that was written beside the archive" in problems
    assert "1 file(s) that nothing accounts for, first left-over.txt" in problems
    assert "1 dataset(s) of the database have no file, first bbb" in problems
    assert "the archive holds 1 dataset files and the patch run wrote 2" in problems


def test_a_file_of_a_dataset_the_database_lacks_is_found(step, patched):
    archive, _, options = pack(step, patched)
    options["notes"] = {"aaa": note("aaa")}
    problems = step.check(archive, patched / "patched", **options)
    assert problems == ["1 file(s) hold no dataset of the database, first bbb"]


def test_files_that_are_not_the_ones_of_the_summary_are_not_packed(step, patched):
    path = patched / "patched" / "process_aaa.xml"
    path.write_text(path.read_text().replace('meanValue="3.2"', 'meanValue="3.3"'))
    with pytest.raises(step.EcospoldError, match="not the ones the summary of the patch run"):
        pack(step, patched)


def test_files_that_are_not_the_datasets_of_the_database_are_not_packed(step, patched):
    with pytest.raises(step.EcospoldError, match="1 dataset.s. without a file, 1 file.s."):
        pack(step, patched, notes={"aaa": note("aaa"), "ccc": note("ccc")})


def test_a_comment_that_would_be_too_long_stops_the_packing_and_names_the_file(step, patched):
    long = "x" * step.MAX_COMMENT
    with pytest.raises(step.EcospoldError, match="process_aaa.xml: with the note the general"):
        pack(step, patched, notes={"aaa": long, "bbb": note("bbb")})


def test_a_copy_that_is_labelled_already_is_not_labelled_twice(step, patched, tmp_path):
    archive, _, options = pack(step, patched)
    with zipfile.ZipFile(archive) as packed:
        packed.extractall(tmp_path / "unpacked")
    with pytest.raises(step.EcospoldError, match="labelled already"):
        step.write(tmp_path / "unpacked", tmp_path / "twice.zip", **options)
