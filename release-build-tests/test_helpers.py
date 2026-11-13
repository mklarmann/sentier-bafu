"""The two helpers that prepare sentier-brightway's input. Synthetic tables only."""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "scripts"))

from release_build import (  # noqa: E402
    data_root,
    inventory_metadata,
    label_release,
    mark_database,
    published_results,
)

HAS_ARROW = importlib.util.find_spec("pyarrow") is not None
HAS_PANDAS = importlib.util.find_spec("pandas") is not None

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
        self.assertEqual(metadata["label"], "Modified Data")
        self.assertEqual(metadata["title"], "A database, patched (Modified Data)")
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


OBSERVATION = {
    "dataset": "gas",
    "position": 1,
    "declared": {"name": "Gas, made up/m3", "category": "resources", "unit": "Nm3"},
    "patched": {"name": "Gas, made up", "category": "resources", "unit": "Nm3"},
}


class Labels(unittest.TestCase):
    names = ["Product", "Gas, made up/m3", "Other product", "Gas, made up/m3"]
    kinds = ["production", "biosphere", "production", "biosphere"]
    owners = ["gas", "gas", "other", "other"]

    def test_the_corrected_name_becomes_the_label_of_the_observed_exchange_only(self):
        names = label_release.relabel(self.names, self.kinds, self.owners, [OBSERVATION])
        self.assertEqual(names, ["Product", "Gas, made up", "Other product", "Gas, made up/m3"])
        self.assertEqual(self.names[1], "Gas, made up/m3")  # the input is not changed

    def test_a_row_that_is_not_the_declared_flow_is_refused(self):
        wrong_place = OBSERVATION | {"position": 0}
        with self.assertRaisesRegex(label_release.LabelError, "not the declared"):
            label_release.relabel(self.names, self.kinds, self.owners, [wrong_place])
        with self.assertRaisesRegex(label_release.LabelError, "No exchange"):
            label_release.relabel(
                self.names, self.kinds, self.owners, [OBSERVATION | {"position": 9}]
            )

    @unittest.skipUnless(HAS_ARROW, "pyarrow is not installed here")
    def test_tables_get_the_patched_source_and_the_observations_travel_beside(self):
        import pyarrow as pa
        import pyarrow.parquet as pq

        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            exchanges = {
                "process_id": self.owners,
                "flow": ["gas", "f1", "other", "f1"],
                "flow_name": self.names,
                "flow_type": self.kinds,
                "amount": [1.0, 2.0, 1.0, 3.0],
            }
            pq.write_table(pa.table(exchanges), folder / "exchanges.parquet")
            processes = {
                "process_id": ["gas", "other"],
                "sector": ["energy", "energy"],
                "source": ["bafu-2026"] * 2,
                "source_version": ["v1"] * 2,
            }
            pq.write_table(pa.table(processes), folder / "processes.parquet")
            receipt = {
                "source_observations": [OBSERVATION],
                "steps_by_dataset": {"gas": {"import_fixes": [], "patches": ["0007-names"]}},
            }
            result = label_release.label_folder(folder, receipt, "bafu-2026-v1-patched", "tree-1")
            written = pq.read_table(folder / "exchanges.parquet").to_pydict()
            labelled = pq.read_table(folder / "processes.parquet").to_pydict()
            beside = json.loads((folder / "source-observations.json").read_text())
        self.assertEqual(written["flow_name"][1], "Gas, made up")
        self.assertEqual(written["flow"], exchanges["flow"])  # identifiers stay the declared
        self.assertEqual(written["amount"], exchanges["amount"])
        self.assertEqual(set(labelled["source"]), {"bafu-2026-v1-patched"})
        self.assertEqual(set(labelled["source_version"]), {"tree-1"})
        self.assertEqual(beside, [OBSERVATION | {"steps": ["0007-names"]}])
        self.assertEqual(result["exchanges_linked_on_the_declared_flow"], 1)


@unittest.skipUnless(HAS_ARROW, "pyarrow is not installed here")
class FlowTerms(unittest.TestCase):
    def test_the_providers_flow_terms_are_written_again_under_the_patched_name(self):
        import pyarrow as pa
        import pyarrow.parquet as pq

        provider = data_root.SOURCE_IRI + "bafu-2026"
        rows = {
            "iri": ["flow-1", "flow-2", "process-1", "ef-1"],
            "type": ["elementary-flow", "elementary-flow", "process", "elementary-flow"],
            "pref_label": ["One", "Two", "A process", "An EF flow"],
            "source": [provider, provider, provider, data_root.SOURCE_IRI + "ef-3.1"],
            "attributes": ["{}"] * 4,
        }
        with tempfile.TemporaryDirectory() as temp:
            terms = Path(temp) / "terms"
            terms.mkdir()
            pq.write_table(pa.table(rows), terms / "all.parquet")
            target = Path(temp) / "out" / "patched.parquet"
            count = data_root.write_flow_terms(terms, target, "bafu-2026", "bafu-2026-v1-patched")
            written = pq.read_table(target).to_pydict()
            with self.assertRaisesRegex(ValueError, "No elementary flow terms"):
                data_root.write_flow_terms(terms, target, "other-source", "x")
        self.assertEqual(count, 2)
        self.assertEqual(written["iri"], ["flow-1", "flow-2"])
        self.assertEqual(set(written["source"]), {data_root.SOURCE_IRI + "bafu-2026-v1-patched"})
        self.assertEqual(written["pref_label"], ["One", "Two"])


BUILD = {
    "patched": True,
    "release_name": "X:2026 v1",
    "provider_tree_sha256": "a" * 64,
    "built_tree_sha256": "b" * 64,
    "patches": ["0001-example"],
    "import_fixes": ["renumber-exchanges"],
    "record_of_changes": ["release-report.html"],
    "build_steps": [{"id": "build-ef-3.1-links", "kind": "build step", "description": "x"}],
    "tools": {"this repository": "c" * 40},
    "data": [],
}


class Marker(unittest.TestCase):
    def test_a_patched_database_is_labelled_modified_data_with_its_patches(self):
        record = mark_database.release_record(BUILD, "Credit line")
        self.assertEqual(record["label"], "Modified Data")
        self.assertIs(record["modified_data"], True)
        self.assertEqual(record["patches"], ["0001-example"])
        self.assertEqual(record["credit"], "Credit line")
        self.assertEqual(record["provider_release"], "X:2026 v1")

    def test_the_provider_release_is_not(self):
        record = mark_database.release_record(BUILD | {"patched": False, "patches": []}, "c")
        self.assertEqual(record["label"], "Provider release")
        self.assertIs(record["modified_data"], False)

    def test_modified_data_may_not_carry_the_providers_name(self):
        modified = mark_database.release_record(BUILD, "c")
        provider = mark_database.release_record(BUILD | {"patched": False}, "c")
        for name in ("bafu-2026", "bafu-2026-residual"):
            with self.assertRaisesRegex(mark_database.MarkError, "BAFU's release"):
                mark_database.check_name(name, modified, "bafu-2026")
            mark_database.check_name(name, provider, "bafu-2026")
        mark_database.check_name("bafu-2026-v1-patched", modified, "bafu-2026")


@unittest.skipUnless(HAS_PANDAS, "pandas is not installed here")
class PublishedResults(unittest.TestCase):
    def test_shares_within_one_and_five_percent_per_category(self):
        import pandas as pd

        table = pd.DataFrame(
            {
                "code": ["a", "b", "c", "d"],
                "name": ["A", "B", "C", "D"],
                "climate": [0.0, 0.5, -3.0, None],
                "energy": [-20.0, -40.0, 0.2, 7.0],
                "water": [None, None, None, None],
            }
        )
        counts = {"processes": 5, "reference_rows": 5, "mapped": 4, "unmatched": 1}
        summary = published_results.summarise(table, counts)
        self.assertEqual((summary["joined"], summary["not_joined"]), (4, 1))
        climate, energy = summary["categories"]["climate"], summary["categories"]["energy"]
        self.assertEqual(climate["compared"], 3)
        self.assertAlmostEqual(climate["within_1_percent"], 66.67)
        self.assertEqual(climate["within_5_percent"], 100.0)
        self.assertEqual(climate["median_difference_percent"], 0.0)
        self.assertEqual(energy["within_1_percent"], 25.0)
        self.assertEqual(energy["median_difference_percent"], -9.9)
        self.assertEqual(summary["categories"]["water"], {"compared": 0})
        self.assertNotIn("name", summary["categories"])


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
