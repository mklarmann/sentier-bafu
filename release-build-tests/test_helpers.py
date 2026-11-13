"""The two helpers that prepare sentier-brightway's input. Synthetic tables only."""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "scripts"))

from release_build import data_root, inventory_metadata  # noqa: E402

TEXTS = {
    "title": "A database",
    "publisher": "An office",
    "license": "Terms of use",
    "citation": "Cite it",
    "provenance": "https://example.org/sources/x",
}
DISTINCT = {"sector": ["energy", "waste"], "source": ["x-2026"], "source_version": ["v1"]}
COUNTS = {"processes.parquet": 2, "exchanges.parquet": 5}


class Metadata(unittest.TestCase):
    def test_keys_sentier_brightway_reads(self):
        metadata = inventory_metadata.build_metadata(DISTINCT, COUNTS, TEXTS)
        self.assertEqual(metadata["source"], "x-2026")
        self.assertEqual(metadata["source_version"], "v1")
        self.assertEqual(metadata["sectors"], ["energy", "waste"])
        self.assertEqual(metadata["row_counts"], COUNTS)
        self.assertEqual(metadata["schema_version"], "0.3.0")
        self.assertNotIn("modified", metadata)

    def test_a_patched_release_is_marked_as_modified(self):
        changes = {"tool": "bafu-community-fixes", "datasets_changed_by_patch": {"0001": 3}}
        metadata = inventory_metadata.build_metadata(DISTINCT, COUNTS, TEXTS, changes)
        self.assertIs(metadata["modified"], True)
        self.assertEqual(metadata["modifications"], changes)

    def test_a_folder_with_two_sources_is_refused(self):
        mixed = {**DISTINCT, "source": ["x-2026", "y-2026"]}
        with self.assertRaisesRegex(ValueError, "one value"):
            inventory_metadata.build_metadata(mixed, COUNTS, TEXTS)

    @unittest.skipUnless(importlib.util.find_spec("pyarrow"), "pyarrow is not installed here")
    def test_columns_and_counts_are_read_from_the_tables(self):
        import pyarrow as pa
        import pyarrow.parquet as pq

        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            processes = {
                "process_id": ["a", "b", "c"],
                "sector": ["waste", "energy", "waste"],
                "source": ["x-2026"] * 3,
                "source_version": ["v1"] * 3,
            }
            pq.write_table(pa.table(processes), folder / "processes.parquet")
            pq.write_table(pa.table({"process_id": ["a"] * 4}), folder / "exchanges.parquet")
            distinct, counts = inventory_metadata.read_columns(folder)
        self.assertEqual(distinct, DISTINCT)
        self.assertEqual(counts, {"processes.parquet": 3, "exchanges.parquet": 4})
        json.dumps(inventory_metadata.build_metadata(distinct, counts, TEXTS))


class Source:
    """Stands in for sentier-brightway's pinned source."""

    def __init__(self, name, ref, files, repo="org/repo"):
        self.name, self.ref, self.files, self.repo = name, ref, files, repo


def make(source, commit, files):
    return Source(source.name, commit, files, source.repo)


class DataPins(unittest.TestCase):
    sources = (
        Source("sentier-vocab", "a" * 40, {"terms/x.parquet": "1" * 64}),
        Source("sentier-mappings", "b" * 40, {"m/one.json": "2" * 64, "m/two.json": "3" * 64}),
    )

    def test_without_overrides_the_pins_are_sentier_brightways(self):
        sources, record = data_root.apply_overrides(self.sources, {}, make)
        self.assertEqual([s.ref for s in sources], ["a" * 40, "b" * 40])
        self.assertEqual({entry["pinned_by"] for entry in record}, {"sentier-brightway"})

    def test_an_override_moves_one_source_and_is_recorded_with_its_reason(self):
        override = {"commit": "c" * 40, "reason": "a fix", "files": {"m/one.json": "4" * 64}}
        sources, record = data_root.apply_overrides(
            self.sources, {"sentier-mappings": override}, make
        )
        vocab, mappings = sources
        self.assertEqual(vocab.ref, "a" * 40)
        self.assertEqual(mappings.ref, "c" * 40)
        self.assertEqual(mappings.files, {"m/one.json": "4" * 64, "m/two.json": "3" * 64})
        entry = record[1]
        self.assertEqual(entry["pinned_by"], "this build")
        self.assertEqual(entry["reason"], "a fix")
        self.assertEqual(entry["sentier_brightway_commit"], "b" * 40)
        self.assertEqual(entry["files_that_differ"], ["m/one.json"])
        self.assertEqual(record[0]["pinned_by"], "sentier-brightway")

    def test_an_override_for_unknown_data_or_an_unknown_file_is_refused(self):
        with self.assertRaisesRegex(ValueError, "not pinned"):
            data_root.apply_overrides(self.sources, {"other": {"commit": "c" * 40}}, make)
        override = {"commit": "c" * 40, "reason": "x", "files": {"m/three.json": "4" * 64}}
        with self.assertRaisesRegex(ValueError, "other files"):
            data_root.apply_overrides(self.sources, {"sentier-mappings": override}, make)

    def test_the_committed_overrides_are_complete(self):
        import tomllib

        pins = tomllib.loads((REPOSITORY / "scripts/release_build/pins.toml").read_text())
        for name, override in pins.get("data", {}).items():
            self.assertRegex(override["commit"], r"^[0-9a-f]{40}$", name)
            self.assertTrue(override["reason"], name)
            for digest in override.get("files", {}).values():
                self.assertRegex(digest, r"^[0-9a-f]{64}$")


@unittest.skipUnless(
    importlib.util.find_spec("sentier_brightway"), "sentier-brightway is not installed here"
)
class PinnedData(unittest.TestCase):
    def test_everything_but_the_inventory_is_taken_from_the_pins(self):
        sources, record = data_root.pinned_sources()
        self.assertEqual(
            sorted(source.name for source in sources),
            ["sentier-mappings", "sentier-methods", "sentier-vocab"],
        )
        for source in sources:
            self.assertRegex(source.ref, r"^[0-9a-f]{40}$")
            for digest in source.files.values():
                self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertEqual({entry["pinned_by"] for entry in record}, {"sentier-brightway"})

    def test_the_committed_override_names_files_sentier_brightway_pins(self):
        import tomllib

        pins = tomllib.loads((REPOSITORY / "scripts/release_build/pins.toml").read_text())
        sources, record = data_root.pinned_sources(pins.get("data", {}))
        moved = [entry for entry in record if entry["pinned_by"] == "this build"]
        self.assertEqual([entry["name"] for entry in moved], sorted(pins.get("data", {})))


if __name__ == "__main__":
    unittest.main()
