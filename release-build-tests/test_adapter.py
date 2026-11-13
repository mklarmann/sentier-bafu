"""The adapter turns a release folder into the zip sentier-importers reads.

Synthetic EcoSpold only: no BAFU data. One test runs the patch tool on the package's own
fixture and is skipped where the package isn't installed.
"""

import importlib.util
import json
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "scripts"))

from release_build import adapter  # noqa: E402

NS = adapter.ECOSPOLD_NS
EXT = adapter.EXT_NS

PATCHED = f"""<?xml version='1.0' encoding='UTF-8'?>
<ecoSpold xmlns="{NS}" xmlns:bcf="{EXT}">
  <dataset number="100" generator="test">
    <metaInformation>
      <processInformation>
        <referenceFunction name="Product A" unit="kg" amount="1.0" category="chemicals"/>
        <geography location="CH"/>
      </processInformation>
    </metaInformation>
    <flowData>
      <exchange number="100" name="Product A" unit="kg" meanValue="1.0">
        <outputGroup>0</outputGroup>
      </exchange>
      <exchange number="200" name="Input B" location="CH" unit="kg" meanValue="0.5">
        <inputGroup>5</inputGroup>
      </exchange>
      <exchange number="1000200002" name="Input B" location="CH" unit="kg" meanValue="0.25">
        <inputGroup>5</inputGroup>
      </exchange>
      <exchange number="631" name="Methane" category="air" subCategory="low" unit="kg"
          meanValue="2.0">
        <outputGroup>4</outputGroup>
      </exchange>
      <exchange number="1000631002" name="Methane" category="air" subCategory="high" unit="kg"
          meanValue="3.0" generalComment="line one&#10;line two">
        <outputGroup>4</outputGroup>
      </exchange>
    </flowData>
    <bcf:extensions>
      <bcf:dataset>
        <bcf:importFix>renumber-exchanges</bcf:importFix>
        <bcf:patch>0001-example</bcf:patch>
        <bcf:patch>0010-links</bcf:patch>
      </bcf:dataset>
      <bcf:exchange number="1000200002" originalNumber="200"/>
      <bcf:exchange number="631" brightwayFlow="https://example.org/flows/1"
          brightwayMatch="exactMatch"/>
      <bcf:exchange number="1000631002" originalNumber="631"
          brightwayFlow="https://example.org/flows/1" brightwayMatch="closeMatch"/>
    </bcf:extensions>
  </dataset>
</ecoSpold>
""".encode()

PROVIDER = b"""<?xml version='1.0' encoding='UTF-8'?>
<ecoSpold>
  <dataset number="100" generator="test">
    <metaInformation>
      <processInformation>
        <referenceFunction name="Product A" unit="kg" amount="1.0" category="chemicals"/>
        <geography location="CH"/>
      </processInformation>
    </metaInformation>
    <flowData>
      <exchange number="100" name="Product A" unit="kg" meanValue="1.0">
        <outputGroup>0</outputGroup>
      </exchange>
      <exchange number="200" name="Input B" location="CH" unit="kg" meanValue="0.5">
        <inputGroup>5</inputGroup>
      </exchange>
      <exchange number="200" name="Input B" location="CH" unit="kg" meanValue="0.25">
        <inputGroup>5</inputGroup>
      </exchange>
    </flowData>
  </dataset>
</ecoSpold>
"""


def numbers(document: bytes) -> list[str]:
    return [e.get("number") for e in ET.fromstring(document).iter("exchange")]


class AdaptDocument(unittest.TestCase):
    def adapt(self, content: bytes, name: str = "process_abc.xml"):
        receipt = adapter.Receipt()
        return adapter.adapt_document(content, name, receipt), receipt

    def test_patched_file_loses_namespace_and_extensions(self):
        document, receipt = self.adapt(PATCHED)
        root = ET.fromstring(document)
        self.assertEqual(root.tag, "ecoSpold")
        self.assertIsNotNone(root.find("dataset/flowData/exchange"))
        self.assertFalse([e for e in root.iter() if e.tag.startswith("{")])
        self.assertNotIn(b"bcf", document)
        self.assertEqual(receipt.namespaced_files, 1)
        self.assertEqual(receipt.extension_blocks_removed, 1)

    def test_original_numbers_are_restored(self):
        document, receipt = self.adapt(PATCHED)
        self.assertEqual(numbers(document), ["100", "200", "200", "631", "631"])
        self.assertEqual(dict(receipt.numbers_restored), {"technosphere": 1, "biosphere": 1})

    def test_nothing_else_changes(self):
        document, _ = self.adapt(PATCHED)
        exchanges = list(ET.fromstring(document).iter("exchange"))
        self.assertEqual(
            [e.get("meanValue") for e in exchanges], ["1.0", "0.5", "0.25", "2.0", "3.0"]
        )
        self.assertEqual(exchanges[4].get("subCategory"), "high")
        self.assertEqual(exchanges[4].get("generalComment"), "line one\nline two")
        self.assertEqual(exchanges[4].findtext("outputGroup"), "4")

    def test_receipt_records_the_steps_of_each_dataset(self):
        _, receipt = self.adapt(PATCHED)
        self.assertEqual(
            receipt.steps_by_dataset,
            {
                "abc": {
                    "import_fixes": ["renumber-exchanges"],
                    "patches": ["0001-example", "0010-links"],
                }
            },
        )
        self.assertEqual(receipt.brightway_flow_links, 2)
        self.assertEqual((receipt.files, receipt.datasets, receipt.exchanges), (1, 1, 5))
        json.dumps(receipt.as_dict())  # counters must serialise as plain mappings
        self.assertEqual(receipt.as_dict()["patches"], {"0001-example": 1, "0010-links": 1})

    def test_provider_file_passes_through(self):
        document, receipt = self.adapt(PROVIDER)
        self.assertEqual(numbers(document), ["100", "200", "200"])
        self.assertEqual(receipt.namespaced_files, 0)
        self.assertEqual(receipt.extension_blocks_removed, 0)
        self.assertEqual(sum(receipt.numbers_restored.values()), 0)

    def test_dummy_number_without_original_is_refused(self):
        broken = PATCHED.replace(b'<bcf:exchange number="1000200002" originalNumber="200"/>', b"")
        with self.assertRaisesRegex(adapter.AdapterError, "dummy number"):
            self.adapt(broken)

    def test_extension_for_a_missing_exchange_is_refused(self):
        broken = PATCHED.replace(
            b'number="1000200002" originalNumber', b'number="1000999002" originalNumber'
        )
        with self.assertRaisesRegex(adapter.AdapterError, "not found"):
            self.adapt(broken)

    def test_foreign_namespace_is_refused(self):
        broken = PATCHED.replace(b"<flowData>", b'<flowData><x:y xmlns:x="urn:other"/>')
        with self.assertRaisesRegex(adapter.AdapterError, "unexpected namespace"):
            self.adapt(broken)

    def test_file_name_must_carry_the_dataset_id(self):
        with self.assertRaisesRegex(adapter.AdapterError, "file name"):
            self.adapt(PROVIDER, "dataset.xml")

    def test_kinds_follow_the_importer(self):
        kinds = [adapter._kind(e) for e in ET.fromstring(PROVIDER).iter("exchange")]
        self.assertEqual(kinds, ["production", "technosphere", "technosphere"])


DECLARED = b"""<?xml version='1.0' encoding='UTF-8'?>
<ecoSpold>
  <dataset number="100" generator="test">
    <flowData>
      <exchange number="100" name="Product A" unit="kg" meanValue="1.0">
        <outputGroup>0</outputGroup>
      </exchange>
      <exchange number="200" name="Input B" location="XX" unit="kg" meanValue="0.5">
        <inputGroup>5</inputGroup>
      </exchange>
      <exchange number="631" name="Gas, made up/m3" category="resources" subCategory="in ground"
          unit="Nm3" meanValue="2.0">
        <inputGroup>4</inputGroup>
      </exchange>
      <exchange number="632" name="Carbon, made up" category="resources" subCategory="biotic"
          unit="kg" meanValue="3.0">
        <inputGroup>4</inputGroup>
      </exchange>
      <exchange number="633" name="Methane" category="air" subCategory="low" unit="kg"
          meanValue="4.0">
        <outputGroup>4</outputGroup>
      </exchange>
    </flowData>
  </dataset>
</ecoSpold>
"""
# What a patch run makes of it: a name without its unit suffix, a moved compartment, a
# corrected supplier location and a corrected amount
CORRECTED = (
    DECLARED.replace(b"<ecoSpold>", f'<ecoSpold xmlns="{NS}">'.encode())
    .replace(b"Gas, made up/m3", b"Gas, made up")
    .replace(b'subCategory="biotic"', b'subCategory="in air"')
    .replace(b'location="XX"', b'location="YY"')
    .replace(b'meanValue="4.0"', b'meanValue="4.5"')
)


def flows(document: bytes) -> list[tuple]:
    return [
        tuple(e.get(key) for key in adapter.FLOW_IDENTITY)
        for e in ET.fromstring(document).iter("exchange")
    ]


class DeclaredFlows(unittest.TestCase):
    """Elementary exchanges keep the flow BAFU declared; everything else stays corrected."""

    def adapt(self, content=CORRECTED, declared=DECLARED):
        receipt = adapter.Receipt()
        return adapter.adapt_document(content, "process_abc.xml", receipt, declared), receipt

    def test_without_the_provider_release_the_corrected_flow_is_handed_on(self):
        document, receipt = self.adapt(declared=None)
        self.assertEqual(flows(document)[2][0], "Gas, made up")
        self.assertEqual(flows(document)[3][2], "in air")
        self.assertEqual(receipt.source_observations, [])

    def test_with_it_the_declared_flow_is_handed_on(self):
        document, receipt = self.adapt()
        self.assertEqual(flows(document), flows(DECLARED))
        self.assertEqual(
            receipt.source_observations,
            [
                {
                    "dataset": "abc",
                    "position": 2,
                    "declared": dict(zip(adapter.FLOW_IDENTITY, flows(DECLARED)[2], strict=True)),
                    "patched": dict(
                        zip(
                            adapter.FLOW_IDENTITY,
                            ("Gas, made up", "resources", "in ground", "Nm3"),
                            strict=True,
                        )
                    ),
                },
                {
                    "dataset": "abc",
                    "position": 3,
                    "declared": dict(zip(adapter.FLOW_IDENTITY, flows(DECLARED)[3], strict=True)),
                    "patched": dict(
                        zip(
                            adapter.FLOW_IDENTITY,
                            ("Carbon, made up", "resources", "in air", "kg"),
                            strict=True,
                        )
                    ),
                },
            ],
        )

    def test_corrections_that_are_not_a_flow_identity_stay(self):
        document, _ = self.adapt()
        exchanges = list(ET.fromstring(document).iter("exchange"))
        self.assertEqual(exchanges[1].get("location"), "YY")  # a technosphere input
        self.assertEqual(exchanges[4].get("meanValue"), "4.5")  # an elementary amount

    def test_an_unchanged_release_gives_no_observation(self):
        document, receipt = self.adapt(content=DECLARED)
        self.assertEqual(flows(document), flows(DECLARED))
        self.assertEqual(receipt.source_observations, [])

    def test_exchanges_that_do_not_pair_up_are_refused(self):
        fewer = DECLARED.replace(b'<exchange number="633"', b'<x number="633"').replace(
            b"</outputGroup>\n      </exchange>\n    </flowData>",
            b"</outputGroup>\n      </x>\n    </flowData>",
        )
        with self.assertRaisesRegex(adapter.AdapterError, "another number of exchanges"):
            self.adapt(declared=fewer)
        other = DECLARED.replace(b'number="632"', b'number="999"')
        with self.assertRaisesRegex(adapter.AdapterError, "not the same exchange"):
            self.adapt(declared=other)
        technosphere = DECLARED.replace(
            b'meanValue="3.0">\n        <inputGroup>4', b'meanValue="3.0">\n        <inputGroup>5'
        )
        with self.assertRaisesRegex(adapter.AdapterError, "not the same exchange"):
            self.adapt(declared=technosphere)

    def test_a_folder_is_read_beside_the_provider_release(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for folder, content in (("provider", DECLARED), ("patched", CORRECTED)):
                (root / folder).mkdir()
                (root / folder / "process_abc.xml").write_bytes(content)
            receipt = adapter.adapt_folder(
                root / "patched", root / "out.zip", declared=root / "provider"
            )
            self.assertEqual(len(receipt.source_observations), 2)
            self.assertEqual(receipt.declared_tree_sha256, adapter.tree_sha256(root / "provider"))
            with zipfile.ZipFile(root / "out.zip") as archive:
                written = archive.read("ecospold/process_abc.xml")
            self.assertEqual(flows(written), flows(DECLARED))
            json.dumps(receipt.as_dict())

            (root / "provider" / "process_abc.xml").unlink()
            (root / "provider" / "process_other.xml").write_bytes(DECLARED)
            with self.assertRaisesRegex(adapter.AdapterError, "not in the provider release"):
                adapter.adapt_folder(root / "patched", root / "x.zip", declared=root / "provider")


class AdaptFolder(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "release"
        self.source.mkdir()
        (self.source / "process_b.xml").write_bytes(PROVIDER)
        (self.source / "process_a.xml").write_bytes(PATCHED)

    def tearDown(self):
        self.temp.cleanup()

    def test_zip_is_sorted_and_reproducible(self):
        first = adapter.adapt_folder(self.source, self.root / "one.zip")
        second = adapter.adapt_folder(self.source, self.root / "two.zip")
        self.assertEqual(first.output_zip_sha256, second.output_zip_sha256)
        with zipfile.ZipFile(self.root / "one.zip") as archive:
            self.assertEqual(
                archive.namelist(), ["ecospold/process_a.xml", "ecospold/process_b.xml"]
            )
        self.assertEqual(first.files, 2)
        self.assertEqual(first.input_tree_sha256, adapter.tree_sha256(self.source))

    def test_tree_hash_follows_the_content(self):
        before = adapter.tree_sha256(self.source)
        (self.source / "process_b.xml").write_bytes(PROVIDER.replace(b"0.25", b"0.26"))
        self.assertNotEqual(before, adapter.tree_sha256(self.source))

    def test_empty_folder_is_refused(self):
        (self.root / "empty").mkdir()
        with self.assertRaisesRegex(adapter.AdapterError, "No XML files"):
            adapter.adapt_folder(self.root / "empty", self.root / "x.zip")

    def test_command_line_writes_zip_and_receipt(self):
        receipt = self.root / "receipt.json"
        code = adapter.main(
            [str(self.source), str(self.root / "cli.zip"), "--receipt", str(receipt)]
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(receipt.read_text())["exchanges"], 8)


@unittest.skipUnless(
    importlib.util.find_spec("bafu_community_fixes"), "the patch tool is not installed here"
)
class PatchToolContract(unittest.TestCase):
    """What the patch tool writes must stay readable by the adapter."""

    def test_output_of_the_patch_tool_adapts_back_to_the_original_numbers(self):
        from bafu_community_fixes.pipeline import run

        fixture = REPOSITORY / "tests" / "fixtures" / "raw_bafu.xml"
        original = numbers(fixture.read_bytes())
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "in" / "process_fixture.xml"
            source.parent.mkdir()
            source.write_bytes(fixture.read_bytes())
            run(source.parent, Path(temp) / "out")
            written = (Path(temp) / "out" / "process_fixture.xml").read_bytes()
            self.assertIn(NS.encode(), written)
            receipt = adapter.Receipt()
            adapted = adapter.adapt_document(written, "process_fixture.xml", receipt)
        renumbered = [e.get("number") for e in ET.fromstring(written).iter(f"{{{NS}}}exchange")]
        # The fixture must repeat a number, or this test could not fail
        self.assertLess(len(set(original)), len(original))
        self.assertEqual(len(set(renumbered)), len(renumbered))
        self.assertNotEqual(renumbered, original)
        self.assertEqual(numbers(adapted), original)
        self.assertEqual(receipt.namespaced_files, 1)
        self.assertGreater(sum(receipt.numbers_restored.values()), 0)


if __name__ == "__main__":
    unittest.main()
